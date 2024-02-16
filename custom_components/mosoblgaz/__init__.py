"""Mosoblgaz API"""
__all__ = [
    "privacy_formatter",
    "is_privacy_logging_enabled",
    "get_print_username",
    "async_setup",
    "async_setup_entry",
    "async_unload_entry",
    "async_update_options",
    "async_migrate_entry",
    "DOMAIN",
    "CONFIG_SCHEMA",
]

import logging
from datetime import timedelta
from typing import Any, List, Mapping, Optional, Union

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .const import *
from .api import (
    AuthenticationFailedException,
    MOSCOW_TIMEZONE,
    MosoblgazAPI,
    PartialOfflineException,
)

_LOGGER = logging.getLogger(__name__)


def privacy_formatter(value: Any) -> str:
    str_value = str(value)
    if len(str_value) <= 2:
        return str_value

    suffix = str_value[-max(2, int(round(0.2 * len(str_value)))) :]
    return "*" * (len(str_value) - len(suffix)) + suffix


def is_privacy_logging_enabled(
    hass: HomeAssistantType, config: Union[ConfigEntry, Mapping[str, Any]]
) -> bool:
    if isinstance(config, ConfigEntry):
        if config.source == SOURCE_IMPORT:
            config = hass.data.get(DATA_CONFIG, {}).get(
                config.data[CONF_USERNAME], {}
            )
        else:
            config = config.options

    return config.get(CONF_PRIVACY_LOGGING, DEFAULT_PRIVACY_LOGGING)


def get_print_username(
    hass: HomeAssistantType,
    config: Union[ConfigEntry, Mapping[str, Any]],
    privacy_logging: Optional[bool] = None,
) -> str:
    if isinstance(config, ConfigEntry):
        username = config.data[CONF_USERNAME]
    else:
        username = config[CONF_USERNAME]

    if privacy_logging is None:
        privacy_logging = is_privacy_logging_enabled(hass, config)

    return privacy_formatter(username) if privacy_logging else username


AUTHENTICATION_SUBCONFIG = {
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
}

NAME_FORMATS_SUBCONFIG = {
    vol.Optional(
        CONF_METER_NAME, default=DEFAULT_METER_NAME_FORMAT
    ): cv.string,
    vol.Optional(
        CONF_INVOICE_NAME, default=DEFAULT_INVOICE_NAME_FORMAT
    ): cv.string,
    vol.Optional(
        CONF_CONTRACT_NAME, default=DEFAULT_CONTRACT_NAME_FORMAT
    ): cv.string,
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
    ),
}

OPTIONS_SUBCONFIG = {
    vol.Optional(
        CONF_INVERT_INVOICES, default=DEFAULT_INVERT_INVOICES
    ): cv.boolean,
}

INTERVALS_SUBCONFIG = {
    vol.Optional(
        CONF_SCAN_INTERVAL, default=timedelta(seconds=DEFAULT_SCAN_INTERVAL)
    ): cv.positive_time_period,
    vol.Optional(
        CONF_TIMEOUT, default=timedelta(seconds=DEFAULT_TIMEOUT)
    ): cv.positive_time_period,
}


def _unique_username_validator(
    configs: List[Mapping[str, Any]]
) -> List[Mapping[str, Any]]:
    existing_usernames = set()
    exceptions = []
    for i, config in enumerate(configs):
        if config[CONF_USERNAME] in existing_usernames:
            exceptions.append(
                vol.Invalid("duplicate username entry detected", [i])
            )
        else:
            existing_usernames.add(config[CONF_USERNAME])

    if len(exceptions) > 1:
        raise vol.MultipleInvalid(exceptions)
    elif len(exceptions) == 1:
        raise exceptions[0]

    return configs


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Optional(
                            CONF_PRIVACY_LOGGING,
                            default=DEFAULT_PRIVACY_LOGGING,
                        ): cv.boolean,
                        **AUTHENTICATION_SUBCONFIG,
                        **NAME_FORMATS_SUBCONFIG,
                        **FILTER_SUBCONFIG,
                        **OPTIONS_SUBCONFIG,
                        **INTERVALS_SUBCONFIG,
                    }
                )
            ],
            _unique_username_validator,
        )
    },
    extra=vol.ALLOW_EXTRA,
)


@callback
def _find_existing_entry(
    hass: HomeAssistantType, username: str
) -> Optional[config_entries.ConfigEntry]:
    existing_entries = hass.config_entries.async_entries(DOMAIN)
    for config_entry in existing_entries:
        if config_entry.data[CONF_USERNAME] == username:
            return config_entry


async def async_setup(hass: HomeAssistantType, config: ConfigType):
    """Set up the Mosoblgaz component."""
    domain_config = config.get(DOMAIN)

    # Skip YAML import if domain configuration is empty
    if not domain_config:
        return True

    # Setup YAML configuration placeholders
    yaml_config = {}
    hass.data[DATA_CONFIG] = yaml_config

    # Iterate over YAML configuration entries
    for user_cfg in domain_config:
        username = user_cfg[CONF_USERNAME]

        # Create logging prefix
        log_prefix = f"(user|{get_print_username(hass, user_cfg)}) "

        _LOGGER.debug(log_prefix + "Loading configuration from YAML")

        # Check against internal database for existing entries
        existing_entry = _find_existing_entry(hass, username)
        if existing_entry:
            if existing_entry.source == config_entries.SOURCE_IMPORT:
                # Do not add duplicate import entry
                _LOGGER.debug(log_prefix + "Skipping existing import binding")
                yaml_config[username] = user_cfg
            else:
                # Do not add YAML entry override
                _LOGGER.warning(
                    log_prefix + "YAML config is overridden via UI!"
                )
            continue

        yaml_config[username] = user_cfg

        _LOGGER.debug(log_prefix + "Creating import entry")

        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data={CONF_USERNAME: username},
            )
        )

    return True


async def async_setup_entry(
    hass: HomeAssistantType, config_entry: config_entries.ConfigEntry
):
    """Configuration entry setup procedure"""
    user_cfg = config_entry.data
    username = user_cfg[CONF_USERNAME]

    if config_entry.source == config_entries.SOURCE_IMPORT:
        yaml_config = hass.data.get(DATA_CONFIG)

        if not yaml_config or username not in yaml_config:
            _LOGGER.info(
                "Removing entry %s after removal from YAML configuration."
                % config_entry.entry_id
            )
            hass.async_create_task(
                hass.config_entries.async_remove(config_entry.entry_id)
            )
            return False

        user_cfg = yaml_config[username]
        options_cfg = user_cfg
    else:
        options_cfg = config_entry.options

    log_prefix = f"(user|{get_print_username(hass, user_cfg)})"
    _LOGGER.debug("%s Setting up config entry", log_prefix)

    from .api import MosoblgazAPI, MosoblgazException, today_blackout

    timeout = options_cfg.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
    if isinstance(timeout, timedelta):
        timeout = aiohttp.ClientTimeout(total=timeout.total_seconds())
    elif isinstance(timeout, (int, float)):
        timeout = aiohttp.ClientTimeout(total=timeout)
    else:
        raise TypeError("Invalid timeout type, report to the developer")

    session = aiohttp.ClientSession(timeout=timeout)

    try:
        try:
            api_object = MosoblgazAPI(
                username=username,
                password=user_cfg[CONF_PASSWORD],
                session=session,
            )

            await api_object.authenticate()

            contracts = await api_object.fetch_contracts(with_data=False)

        except AuthenticationFailedException as e:
            _LOGGER.error(log_prefix + "Error authenticating: %s", e)
            raise ConfigEntryNotReady

        except PartialOfflineException:
            _LOGGER.error(
                "%s Service appears to be partially offline, which prevents "
                "the component from fetching data. Delaying config entry setup.",
                log_prefix,
            )
            raise ConfigEntryNotReady

        except MosoblgazException as e:
            _LOGGER.error('%s API error with user: "%s"', log_prefix, e)
            raise ConfigEntryNotReady

    except BaseException:
        await session.close()
        raise

    if not contracts:
        _LOGGER.warning("%s No contracts found under username", log_prefix)
        await session.close()
        return False

    hass.data.setdefault(DATA_API_OBJECTS, {})[
        config_entry.entry_id
    ] = api_object

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(
            config_entry, SENSOR_DOMAIN
        )
    )

    _LOGGER.debug("%s Attaching options update listener", log_prefix)
    options_listener = config_entry.add_update_listener(async_update_options)
    hass.data.setdefault(DATA_OPTIONS_LISTENERS, {})[
        config_entry.entry_id
    ] = options_listener

    _LOGGER.debug("%s Successfully set up account", log_prefix)

    return True


async def async_update_options(
    hass: HomeAssistantType, config_entry: config_entries.ConfigEntry
):
    """React to options update"""
    log_prefix = f"(user|{get_print_username(hass, config_entry)})"
    _LOGGER.debug(
        "%s Reloading configuration entry due to options update", log_prefix
    )
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistantType, config_entry: config_entries.ConfigEntry
) -> bool:
    entry_id = config_entry.entry_id
    user_cfg = config_entry.data
    print_username = user_cfg[CONF_USERNAME]

    if config_entry.source == SOURCE_IMPORT:
        user_cfg = hass.data[DATA_CONFIG][print_username]

    if user_cfg.get(CONF_PRIVACY_LOGGING, DEFAULT_PRIVACY_LOGGING):
        print_username = privacy_formatter(print_username)

    log_prefix = f"(user|{print_username})"

    _LOGGER.debug("%s Beginning unload procedure", log_prefix)

    if DATA_UPDATERS in hass.data and entry_id in hass.data[DATA_UPDATERS]:
        # Remove API objects
        _LOGGER.debug("%s Unloading updater", log_prefix)
        updater_cancel, force_update = hass.data[DATA_UPDATERS].pop(entry_id)
        if updater_cancel:
            updater_cancel()
        if not hass.data[DATA_UPDATERS]:
            del hass.data[DATA_UPDATERS]

    if (
        DATA_API_OBJECTS in hass.data
        and entry_id in hass.data[DATA_API_OBJECTS]
    ):
        # Remove API objects
        _LOGGER.debug("%s Unloading API object", log_prefix)
        del hass.data[DATA_API_OBJECTS][entry_id]
        if not hass.data[DATA_API_OBJECTS]:
            del hass.data[DATA_API_OBJECTS]

    if DATA_ENTITIES in hass.data and entry_id in hass.data[DATA_ENTITIES]:
        # Remove references to created entities
        _LOGGER.debug("%s Unloading entities", log_prefix)
        del hass.data[DATA_ENTITIES][entry_id]
        await hass.async_create_task(
            hass.config_entries.async_forward_entry_unload(
                config_entry, SENSOR_DOMAIN
            )
        )
        if not hass.data[DATA_ENTITIES]:
            del hass.data[DATA_ENTITIES]

    if (
        DATA_OPTIONS_LISTENERS in hass.data
        and entry_id in hass.data[DATA_OPTIONS_LISTENERS]
    ):
        _LOGGER.debug("%s Unsubscribing options updates", log_prefix)
        hass.data[DATA_OPTIONS_LISTENERS][entry_id]()
        del hass.data[DATA_OPTIONS_LISTENERS][entry_id]
        if not hass.data[DATA_OPTIONS_LISTENERS]:
            del hass.data[DATA_OPTIONS_LISTENERS]

    _LOGGER.debug("%s Main unload procedure complete", log_prefix)

    return True


async def async_migrate_entry(
    hass: HomeAssistantType, config_entry: config_entries.ConfigEntry
) -> bool:
    current_version = config_entry.version
    update_args = {}
    old_data = config_entry.data

    _LOGGER.debug(
        'Migrating entry "%s" (type="%s") from version %s',
        config_entry.entry_id,
        config_entry.source,
        current_version,
    )

    if current_version == 1:
        if config_entry.source != SOURCE_IMPORT:
            new_data = update_args.setdefault("data", {})
            new_data[CONF_USERNAME] = old_data[CONF_USERNAME]
            new_data[CONF_PASSWORD] = old_data[CONF_PASSWORD]

            if CONF_INVERT_INVOICES in old_data:
                new_options = update_args.setdefault("options", {})
                new_options[CONF_INVERT_INVOICES] = old_data[
                    CONF_INVERT_INVOICES
                ]

        current_version = 2

    config_entry.version = current_version

    if update_args:
        _LOGGER.debug('Updating configuration entry "%s" with new data')
        hass.config_entries.async_update_entry(config_entry, **update_args)

    _LOGGER.debug(
        'Migration of entry "%s" to version %s successful',
        config_entry.entry_id,
        current_version,
    )
    return True
