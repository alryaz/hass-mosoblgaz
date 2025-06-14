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
from typing import Any, Awaitable, Mapping, MutableMapping, Optional

from homeassistant.helpers.aiohttp_client import async_create_clientsession
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT, current_entry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USERNAME,
)
from homeassistant.core import callback, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .api import (
    AuthenticationFailedException,
    CaptchaResponse,
    Contract,
    MosoblgazException,
    PartialOfflineException,
)
from .const import *

_LOGGER = logging.getLogger(__name__)


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
    ),
}

OPTIONS_SUBCONFIG = {
    vol.Optional(CONF_INVERT_INVOICES, default=DEFAULT_INVERT_INVOICES): cv.boolean,
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
    configs: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    existing_usernames = set()
    exceptions = []
    for i, config in enumerate(configs):
        if config[CONF_USERNAME] in existing_usernames:
            exceptions.append(vol.Invalid("duplicate username entry detected", [i]))
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
                        cv.deprecated(
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
    hass: HomeAssistant, username: str
) -> Optional[config_entries.ConfigEntry]:
    existing_entries = hass.config_entries.async_entries(DOMAIN)
    for config_entry in existing_entries:
        if config_entry.data[CONF_USERNAME] == username:
            return config_entry


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up the Mosoblgaz component."""
    hass.data[DATA_API_OBJECTS] = {}

    return True


async def run_with_cnr(coro: Awaitable):
    try:
        return await coro
    except AuthenticationFailedException as exc:
        raise ConfigEntryAuthFailed(str(exc))
    except PartialOfflineException:
        raise ConfigEntryNotReady("Service is partially offline")
    except MosoblgazException as exc:
        raise ConfigEntryNotReady(f"Generic API error: {exc}")


async def async_setup_entry(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
):
    """Configuration entry setup procedure"""
    user_cfg = config_entry.data
    username = user_cfg[CONF_USERNAME]

    if config_entry.source == config_entries.SOURCE_IMPORT:
        return False

    logger = ConfigEntryLoggerAdapter(config_entry=config_entry)
    _LOGGER.debug("Setting up config entry")

    from .api import MosoblgazAPI, MosoblgazException, today_blackout

    api_object = MosoblgazAPI(
        username=username,
        password=user_cfg[CONF_PASSWORD],
        session=async_create_clientsession(hass),
        graphql_token=user_cfg.get(CONF_GRAPHQL_TOKEN),
    )

    contracts: dict[str, Contract] | None = None
    if api_object.graphql_token:
        try:
            contracts = await run_with_cnr(api_object.fetch_contracts())
        except ConfigEntryAuthFailed:
            logger.info("GraphQL token may be obsolete, ignoring")
            api_object.graphql_token = None

    if not api_object.graphql_token:
        temporary_token = await api_object.fetch_temporary_token()
        if isinstance(temporary_token, CaptchaResponse):
            raise ConfigEntryAuthFailed("CAPTCHA input required")
        await run_with_cnr(api_object.authenticate(temporary_token))
        contracts = await run_with_cnr(api_object.fetch_contracts())

    if user_cfg.get(CONF_GRAPHQL_TOKEN) != api_object.graphql_token:
        merge_data = dict(config_entry.data)
        merge_data[CONF_GRAPHQL_TOKEN] = api_object.graphql_token
        logger.debug("GraphQL token has been updated: %s", api_object.graphql_token)
        hass.config_entries.async_update_entry(config_entry, data=merge_data)

    if not contracts:
        logger.warning("No contracts found under username")
        return False

    hass.data[DATA_API_OBJECTS][config_entry.entry_id] = api_object

    # Forward entry setup to platform
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # Create options update listener
    config_entry.async_on_unload(config_entry.add_update_listener(async_update_options))

    _LOGGER.debug("Successfully set up account")

    return True


class ConfigEntryLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that prefixes config entry ID."""

    def __init__(
        self,
        logger: logging.Logger = _LOGGER,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        if (config_entry or (config_entry := current_entry.get())) is None:
            raise RuntimeError("no context of config entry")
        super().__init__(logger, {"config_entry": config_entry})
        self.config_entry = config_entry

    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        return "[%s] %s" % (self.config_entry.entry_id[-6:], msg), kwargs


async def async_update_options(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
):
    """React to options update"""
    ConfigEntryLoggerAdapter(config_entry=config_entry).debug(
        "Reloading configuration entry"
    )
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
) -> bool:
    entry_id = config_entry.entry_id

    logger = ConfigEntryLoggerAdapter(config_entry=config_entry)
    logger.debug("Beginning unload procedure")

    if not await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS):
        return False

    hass.data[DATA_ENTITIES].pop(entry_id, None)

    if DATA_UPDATERS in hass.data and entry_id in hass.data[DATA_UPDATERS]:
        # Remove API objects
        logger.debug("Unloading updater")
        updater_cancel, force_update = hass.data[DATA_UPDATERS].pop(entry_id)
        if updater_cancel:
            updater_cancel()
        if not hass.data[DATA_UPDATERS]:
            del hass.data[DATA_UPDATERS]

    if DATA_API_OBJECTS in hass.data and entry_id in hass.data[DATA_API_OBJECTS]:
        # Remove API objects
        logger.debug("Unloading API object")
        del hass.data[DATA_API_OBJECTS][entry_id]
        if not hass.data[DATA_API_OBJECTS]:
            del hass.data[DATA_API_OBJECTS]

    logger.debug("Main unload procedure complete")

    return True


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
) -> bool:
    _LOGGER.debug(
        f'Migrating entry "{config_entry.entry_id}" '
        f"(type={config_entry.source}) "
        f"from version {config_entry.version}",
    )

    if config_entry.source == SOURCE_IMPORT:
        hass.config_entries.async_update_entry(
            config_entry,
        )

    if config_entry.version == 1:
        hass.config_entries.async_update_entry(
            config_entry,
            data={
                CONF_USERNAME: config_entry.data[CONF_USERNAME],
                CONF_PASSWORD: config_entry.data[CONF_PASSWORD],
            },
            options={
                CONF_INVERT_INVOICES: config_entry.data.get(
                    CONF_INVERT_INVOICES, DEFAULT_INVERT_INVOICES
                )
            },
            version=2,
        )

    if config_entry.version == 2:
        hass.config_entries.async_update_entry(
            config_entry, unique_id=config_entry.data[CONF_USERNAME], version=3
        )

    _LOGGER.debug(
        f"Migration of entry {config_entry.entry_id} "
        f"to version {config_entry.version} successful",
    )
    return True
