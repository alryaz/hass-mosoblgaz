"""Mosoblgaz API"""

__all__ = [
    "async_setup",
    "async_setup_entry",
    "async_unload_entry",
    "async_update_options",
    "async_migrate_entry",
    "DOMAIN",
    "CONFIG_SCHEMA",
    "MosoblgazUpdateCoordinator",
    "MosoblgazCoordinatorEntity",
    "ConfigEntryLoggerAdapter",
]

import asyncio
import logging
from datetime import timedelta
from typing import Any, Awaitable, Mapping, MutableMapping, final
import voluptuous as vol

from homeassistant.helpers import entity_registry
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
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


from custom_components.mosoblgaz.api import (
    AuthenticationFailedException,
    CaptchaResponse,
    Contract,
    MosoblgazAPI,
    MosoblgazException,
    PartialOfflineException,
)
from custom_components.mosoblgaz.const import *

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
                        cv.deprecated("privacy_logging"): cv.boolean,
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


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up the Mosoblgaz component."""
    hass.data[DOMAIN] = {}

    return True


class MosoblgazUpdateCoordinator(DataUpdateCoordinator[dict[str, Contract]]):
    def __init__(
        self,
        hass: HomeAssistant,
        api: MosoblgazAPI,
        update_interval: timedelta | None = None,
        logger: logging.Logger | logging.LoggerAdapter = _LOGGER,
    ) -> None:
        self.api = api
        super().__init__(hass, logger, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self):
        return await self.api.fetch_contracts(with_data=True)


class MosoblgazCoordinatorEntity(CoordinatorEntity[MosoblgazUpdateCoordinator]):
    _attr_attribution: str = ATTRIBUTION

    _attr_translation_placeholders: dict[str, str]
    """Override type from Mapping to dict"""

    @property
    @final
    def logger(self):
        return self.coordinator.logger

    @property
    def api(self):
        return self.coordinator.api


async def run_with_cnr(coro: Awaitable):
    try:
        return await coro
    except AuthenticationFailedException as exc:
        raise ConfigEntryAuthFailed(str(exc))
    except PartialOfflineException:
        raise ConfigEntryNotReady("Service is partially offline")
    except MosoblgazException as exc:
        raise ConfigEntryNotReady(f"Generic API error: {exc}")


async def async_setup_entry(hass: HomeAssistant, entry: config_entries.ConfigEntry):
    """Configuration entry setup procedure"""
    user_cfg = entry.data

    if entry.source == config_entries.SOURCE_IMPORT:
        return False

    logger = ConfigEntryLoggerAdapter(config_entry=entry)
    logger.debug("Setting up config entry")

    api_object = MosoblgazAPI(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=async_create_clientsession(hass),
        graphql_token=entry.data.get(CONF_GRAPHQL_TOKEN),
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

    if entry.data.get(CONF_GRAPHQL_TOKEN) != api_object.graphql_token:
        merge_data = dict(entry.data)
        merge_data[CONF_GRAPHQL_TOKEN] = api_object.graphql_token
        logger.debug("GraphQL token has been updated: %s", api_object.graphql_token)
        hass.config_entries.async_update_entry(entry, data=merge_data)

    if not contracts:
        logger.warning("No contracts found under username")
        return False

    coordinator = MosoblgazUpdateCoordinator(hass, api_object, logger=logger)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Refresh configuration entry to set initial data
    await coordinator.async_config_entry_first_refresh()

    # Forward entry setup to platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Create options update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    logger.debug("Successfully set up account")

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
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload Raise3D entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if not unload_ok:
        return False

    hass.data[DOMAIN].pop(entry.entry_id)
    return True


async def async_migrate_entry(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    _LOGGER.debug(
        f'Migrating entry "{entry.entry_id}" '
        f"(type={entry.source}) "
        f"from version {entry.version}",
    )

    if entry.source == SOURCE_IMPORT:
        hass.config_entries.async_update_entry(
            entry,
        )

    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry,
            data={
                CONF_USERNAME: entry.data[CONF_USERNAME],
                CONF_PASSWORD: entry.data[CONF_PASSWORD],
            },
            options={
                CONF_INVERT_INVOICES: entry.data.get(
                    CONF_INVERT_INVOICES, DEFAULT_INVERT_INVOICES
                )
            },
            version=2,
        )

    if entry.version == 2:
        hass.config_entries.async_update_entry(
            entry, unique_id=entry.data[CONF_USERNAME], version=3
        )

    if entry.version == 3:
        if entry.minor_version == 1:
            await entity_registry.async_migrate_entries(
                hass,
                entry.entry_id,
                lambda x: (
                    {"new_unique_id": "contract_" + x.unique_id[3:]}
                    if x.unique_id.startswith("ls_")
                    else None
                ),
            )
            hass.config_entries.async_update_entry(entry, minor_version=2)

    _LOGGER.debug(
        f"Migration of entry {entry.entry_id} "
        f"to version {entry.version} successful",
    )
    return True
