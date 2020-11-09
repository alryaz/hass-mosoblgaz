"""Mosoblgaz API"""
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Optional, Dict, Union, Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT
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
CONF_PRIVACY_LOGGING = "privacy_logging"

DOMAIN = 'mosoblgaz'
DATA_CONFIG = DOMAIN + '_config'
DATA_API_OBJECTS = DOMAIN + '_api_objects'
DATA_ENTITIES = DOMAIN + '_entities'
DATA_UPDATERS = DOMAIN + '_updaters'

DEFAULT_SCAN_INTERVAL = timedelta(hours=1)
DEFAULT_TIMEOUT = timedelta(seconds=5)
DEFAULT_CONTRACT_NAME_FORMAT = 'MOG Contract {contract_code}'
DEFAULT_METER_NAME_FORMAT = 'MOG Meter {meter_code}'
DEFAULT_INVOICE_NAME_FORMAT = 'MOG {group} Invoice {contract_code}'
DEFAULT_INVERT_INVOICES = False
DEFAULT_ADD_INVOICES = True
DEFAULT_ADD_METERS = True
DEFAULT_ADD_CONTRACTS = True
DEFAULT_PRIVACY_LOGGING = False

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


def privacy_formatter(value: Any) -> str:
    str_value = str(value)
    if len(str_value) <= 2:
        return str_value

    suffix = str_value[-max(2, int(round(0.2*len(str_value)))):]
    return '*' * (len(str_value)-len(suffix)) + suffix


AUTHENTICATION_SUBCONFIG = {
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
}

NAME_FORMATS_SUBCONFIG = {
    vol.Optional(CONF_METER_NAME, default=DEFAULT_METER_NAME_FORMAT): cv.string,
    vol.Optional(CONF_INVOICE_NAME, default=DEFAULT_INVOICE_NAME_FORMAT): cv.string,
    vol.Optional(CONF_CONTRACT_NAME, default=DEFAULT_CONTRACT_NAME_FORMAT): cv.string,
}

DEFAULT_FILTER_SUBCONFIG = {
    vol.Optional(CONF_INVOICES, default=DEFAULT_ADD_INVOICES): cv.boolean,
    vol.Optional(CONF_METERS, default=DEFAULT_ADD_METERS): cv.boolean,
    vol.Optional(CONF_CONTRACTS, default=DEFAULT_ADD_CONTRACTS): cv.boolean,
}

FILTER_SUBCONFIG = {
    **DEFAULT_FILTER_SUBCONFIG,
    vol.Optional(CONF_CONTRACTS): vol.Any(
        cv.boolean,
        {
            cv.string: vol.Any(
                vol.Optional(cv.boolean, default=DEFAULT_ADD_CONTRACTS),
                vol.Schema(DEFAULT_FILTER_SUBCONFIG),
            ),
        },
    )
}

OPTIONS_SUBCONFIG = {
    vol.Optional(CONF_INVERT_INVOICES, default=DEFAULT_INVERT_INVOICES): cv.boolean,
}

INTERVALS_SUBCONFIG = {
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): POSITIVE_PERIOD_SCHEMA,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): POSITIVE_PERIOD_SCHEMA,
}

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(cv.ensure_list, [vol.Schema(
            {
                vol.Optional(CONF_PRIVACY_LOGGING, default=DEFAULT_PRIVACY_LOGGING): cv.boolean,
                **AUTHENTICATION_SUBCONFIG,
                **NAME_FORMATS_SUBCONFIG,
                **FILTER_SUBCONFIG,
                **OPTIONS_SUBCONFIG,
                **INTERVALS_SUBCONFIG,
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

        print_username = username
        if user_cfg.get(CONF_PRIVACY_LOGGING, DEFAULT_PRIVACY_LOGGING):
            print_username = privacy_formatter(username)

        log_prefix = f'(user|{print_username}) '

        _LOGGER.debug(log_prefix + 'Loading configuration from YAML')

        existing_entry = _find_existing_entry(hass, username)
        if existing_entry:
            if existing_entry.source == config_entries.SOURCE_IMPORT:
                _LOGGER.debug(log_prefix + 'Skipping existing import binding')
                yaml_config[username] = user_cfg
            else:
                _LOGGER.warning(log_prefix + 'YAML config is overridden via UI!')
            continue

        if username in yaml_config:
            _LOGGER.warning(log_prefix + 'User is set up multiple times. Check your configuration.')
            continue

        yaml_config[username] = user_cfg

        _LOGGER.debug(log_prefix + 'Creating import entry')

        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data={CONF_USERNAME: username},
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistantType, config_entry: config_entries.ConfigEntry):
    """Configuration entry setup procedure"""
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

    print_username = username
    if user_cfg.get(CONF_PRIVACY_LOGGING, DEFAULT_PRIVACY_LOGGING):
        print_username = privacy_formatter(username)

    log_prefix = f'(user|{print_username})'

    _LOGGER.debug('%s Setting up config entry', log_prefix)

    from .mosoblgaz import MosoblgazAPI, MosoblgazException, today_blackout

    try:
        api_object = MosoblgazAPI(username, user_cfg[CONF_PASSWORD])

        await api_object.authenticate()

        contracts = await api_object.fetch_contracts(with_data=True)

    except AuthenticationFailedException as e:
        _LOGGER.error(log_prefix + 'Error authenticating: %s', e)
        return False

    except PartialOfflineException:
        _LOGGER.error('%s Service appears to be partially offline, which prevents '
                      'the component from fetching data. Delaying config entry setup.', log_prefix)
        raise ConfigEntryNotReady()

    except MosoblgazException as e:
        _LOGGER.error('%s API error with user: "%s"', log_prefix, e)
        return False

    if not contracts:
        _LOGGER.warning('%s No contracts found under username', log_prefix)
        return False

    hass.data.setdefault(DATA_API_OBJECTS, {})[config_entry.entry_id] = api_object

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(
            config_entry,
            SENSOR_DOMAIN
        )
    )

    _LOGGER.debug('%s Successfully set up account', log_prefix)

    return True


async def async_unload_entry(hass: HomeAssistantType, config_entry: config_entries.ConfigEntry) -> bool:
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

    return True


async def async_migrate_entry(hass: HomeAssistantType, config_entry: config_entries.ConfigEntry) -> bool:
    current_version = config_entry.version
    update_args = {}
    old_data = config_entry.data

    _LOGGER.debug('Migrating entry "%s" (type="%s") from version %s',
                  config_entry.entry_id,
                  config_entry.source,
                  current_version)

    if current_version == 1:
        if config_entry.source != SOURCE_IMPORT:
            new_data = update_args.setdefault('data', {})
            new_data[CONF_USERNAME] = old_data[CONF_USERNAME]
            new_data[CONF_PASSWORD] = old_data[CONF_PASSWORD]

            if CONF_INVERT_INVOICES in old_data:
                new_options = update_args.setdefault('options', {})
                new_options[CONF_INVERT_INVOICES] = old_data[CONF_INVERT_INVOICES]

        current_version = 2

    config_entry.version = current_version

    if update_args:
        _LOGGER.debug('Updating configuration entry "%s" with new data')
        hass.config_entries.async_update_entry(config_entry, **update_args)

    _LOGGER.debug('Migration of entry "%s" to version %s successful',
                  config_entry.entry_id,
                  current_version)
    return True