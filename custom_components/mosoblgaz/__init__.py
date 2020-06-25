"""Mosoblgaz API"""
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Optional, Dict, Union

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import (CONF_USERNAME, CONF_PASSWORD,
                                 CONF_SCAN_INTERVAL, CONF_TIMEOUT)
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import HomeAssistantType, ConfigType

from .mosoblgaz import MosoblgazAPI, AuthenticationFailedException, MOSCOW_TIMEZONE, PartialOfflineException

if TYPE_CHECKING:
    from .sensor import MOGContractSensor

_LOGGER = logging.getLogger(__name__)

CONF_CONTRACTS = "contracts"
CONF_METER_NAME = "meter_name"
CONF_CONTRACT_NAME = "contract_name"
CONF_METERS = "meters"
CONF_INVOICES = "invoices"
CONF_INVOICE_NAME = "invoice_name"
CONF_INVERT_INVOICES = "invert_invoices"

DOMAIN = 'mosoblgaz'
DATA_CONFIG = DOMAIN + '_config'
DATA_API_OBJECTS = DOMAIN + '_api_objects'
DATA_ENTITIES = DOMAIN + '_entities'
DATA_UPDATERS = DOMAIN + '_updaters'

DEFAULT_SCAN_INTERVAL = timedelta(hours=1)
DEFAULT_TIMEOUT = timedelta(seconds=5)
DEFAULT_CONTRACT_NAME_FORMAT = 'MOG Contract {code}'
DEFAULT_METER_NAME_FORMAT = 'MOG Meter {code}'
DEFAULT_INVOICE_NAME_FORMAT = 'MOG {group} Invoice {code}'
DEFAULT_INVERT_INVOICES = False
DEFAULT_ADD_INVOICES = True
DEFAULT_ADD_METERS = True

POSITIVE_PERIOD_SCHEMA = vol.All(cv.time_period, cv.positive_timedelta)


def filter_strategies(value: Dict[str, Union[bool, Dict[str, bool]]]) -> Dict[str, Union[bool, Dict[str, bool]]]:
    if False in value.values():
        # Blacklist strategy / Стратегия чёрного списка
        return {
            contract_id: setting
            for contract_id, setting in value.items()
            if setting is not True
        }
    return value


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(cv.ensure_list, [vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_CONTRACTS): vol.All({cv.string: vol.Any(cv.boolean, vol.Schema({
                    vol.Optional(CONF_INVOICES, default=DEFAULT_ADD_INVOICES): cv.boolean,
                    vol.Optional(CONF_METERS, default=DEFAULT_ADD_METERS): cv.boolean,
                }))}, filter_strategies),
                vol.Optional(CONF_INVERT_INVOICES, default=DEFAULT_INVERT_INVOICES): cv.boolean,
                vol.Optional(CONF_METER_NAME, default=DEFAULT_METER_NAME_FORMAT): cv.string,
                vol.Optional(CONF_CONTRACT_NAME, default=DEFAULT_CONTRACT_NAME_FORMAT): cv.string,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): POSITIVE_PERIOD_SCHEMA,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): POSITIVE_PERIOD_SCHEMA,
            }
        )])
    },
    extra=vol.ALLOW_EXTRA,
)


@callback
def _find_existing_entry(hass: HomeAssistantType, username: str) -> Optional[config_entries.ConfigEntry]:
    existing_entries = hass.config_entries.async_entries(DOMAIN)
    for config_entry in existing_entries:
        if config_entry.data[CONF_USERNAME] == username:
            return config_entry


async def async_setup(hass: HomeAssistantType, config: ConfigType):
    """Set up the Mosoblgaz component."""
    domain_config = config.get(DOMAIN)
    if not domain_config:
        return True

    domain_data = {}
    hass.data[DOMAIN] = domain_data

    yaml_config = {}
    hass.data[DATA_CONFIG] = yaml_config

    for user_cfg in domain_config:

        username = user_cfg[CONF_USERNAME]

        _LOGGER.debug('User "%s" entry from YAML' % username)

        existing_entry = _find_existing_entry(hass, username)
        if existing_entry:
            if existing_entry.source == config_entries.SOURCE_IMPORT:
                yaml_config[username] = user_cfg
                _LOGGER.debug('Skipping existing import binding')
            else:
                _LOGGER.warning('YAML config for user %s is overridden by another config entry!' % username)
            continue

        if username in yaml_config:
            _LOGGER.warning('User "%s" set up multiple times. Check your configuration.' % username)
            continue

        yaml_config[username] = user_cfg
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data={CONF_USERNAME: username},
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistantType, config_entry: config_entries.ConfigEntry):
    user_cfg = config_entry.data
    username = user_cfg[CONF_USERNAME]

    if config_entry.source == config_entries.SOURCE_IMPORT:
        yaml_config = hass.data.get(DATA_CONFIG)
        if not yaml_config or username not in yaml_config:
            _LOGGER.info('Removing entry %s after removal from YAML configuration.' % config_entry.entry_id)
            hass.async_create_task(
                hass.config_entries.async_remove(config_entry.entry_id)
            )
            return False

        user_cfg = yaml_config.get(username)

    _LOGGER.debug('Setting up config entry for user "%s"' % username)

    from .mosoblgaz import MosoblgazAPI, MosoblgazException, today_blackout

    try:
        api_object = MosoblgazAPI(username, user_cfg[CONF_PASSWORD])

        await api_object.authenticate()

        contracts = await api_object.fetch_contracts(with_data=True)

        if CONF_CONTRACTS in user_cfg and user_cfg[CONF_CONTRACTS]:
            contracts = {k: v for k, v in contracts.items() if k in user_cfg[CONF_CONTRACTS]}

    except AuthenticationFailedException as e:
        _LOGGER.error('Error authenticating with user "%s": %s' % (username, e))
        return False

    except PartialOfflineException as e:
        _LOGGER.error('Service appears to be partially offline, which prevents the component from fetching data. '
                      'Delaying config entry setup.')
        raise ConfigEntryNotReady()

    except MosoblgazException as e:
        _LOGGER.error('API error with user "%s": "%s"' % (username, e))
        return False

    if not contracts:
        _LOGGER.warning('No contracts found under username "%s"' % username)
        return False

    hass.data.setdefault(DATA_API_OBJECTS, {})[config_entry.entry_id] = api_object

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(
            config_entry,
            SENSOR_DOMAIN
        )
    )

    _LOGGER.debug('Successfully set up user "%s"' % username)
    return True


async def async_unload_entry(hass: HomeAssistantType, config_entry: config_entries.ConfigEntry):
    entry_id = config_entry.entry_id

    if DATA_UPDATERS in hass.data and entry_id in hass.data[DATA_UPDATERS]:
        # Remove API objects
        hass.data[DATA_UPDATERS].pop(entry_id)
        if not hass.data[DATA_UPDATERS]:
            del hass.data[DATA_UPDATERS]

    if DATA_API_OBJECTS in hass.data and entry_id in hass.data[DATA_API_OBJECTS]:
        # Remove API objects
        del hass.data[DATA_API_OBJECTS][entry_id]
        if not hass.data[DATA_API_OBJECTS]:
            del hass.data[DATA_API_OBJECTS]

    if DATA_ENTITIES in hass.data and entry_id in hass.data[DATA_ENTITIES]:
        # Remove references to created entities
        del hass.data[DATA_ENTITIES][entry_id]
        hass.async_create_task(
            hass.config_entries.async_forward_entry_unload(
                config_entry,
                SENSOR_DOMAIN
            )
        )
        if not hass.data[DATA_ENTITIES]:
            del hass.data[DATA_ENTITIES]
