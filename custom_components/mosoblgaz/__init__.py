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
import voluptuous as vol
from datetime import timedelta
from typing import Any, Awaitable, Mapping, MutableMapping, Sequence, TypeVar, final

from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers import entity_registry
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT, current_entry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

import homeassistant.helpers.config_validation as cv


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

_TConfigsList = TypeVar("_TConfigsList", bound=Sequence[Mapping[str, Any]])


def _unique_username_validator(configs: _TConfigsList) -> _TConfigsList:
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
                vol.All(
                    cv.removed("meter_name"),
                    cv.removed("invoice_name"),
                    cv.removed("meter_name"),
                    cv.removed("invoices"),
                    cv.removed("meters"),
                    cv.removed("contracts"),
                    cv.removed("privacy_logging"),
                    vol.Schema(
                        {
                            vol.Required(CONF_USERNAME): cv.string,
                            vol.Required(CONF_PASSWORD): cv.string,
                            vol.Optional(
                                CONF_SCAN_INTERVAL,
                                default=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
                            ): cv.positive_time_period,
                            vol.Optional(
                                CONF_INVERT_INVOICES, default=DEFAULT_INVERT_INVOICES
                            ): cv.boolean,
                            vol.Optional(
                                CONF_TIMEOUT, default=DEFAULT_TIMEOUT
                            ): cv.positive_time_period,
                        }
                    ),
                )
            ],
            _unique_username_validator,
        )
    },
    extra=vol.ALLOW_EXTRA,
)


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

    async def _async_update_data(self) -> dict[str, Contract]:
        if self.api.graphql_token:
            try:
                contracts = await async_run_with_exceptions(
                    self.api.fetch_contracts(with_data=True)
                )
            except ConfigEntryAuthFailed:
                self.logger.info("GraphQL token may be obsolete, ignoring")
                self.api.graphql_token = None

        if not self.api.graphql_token:
            temporary_token = await self.api.fetch_temporary_token()
            if isinstance(temporary_token, CaptchaResponse):
                raise ConfigEntryAuthFailed("CAPTCHA input required")
            await async_run_with_exceptions(self.api.authenticate(temporary_token))
            contracts = await async_run_with_exceptions(
                self.api.fetch_contracts(with_data=True)
            )

        if self.config_entry.data.get(CONF_GRAPHQL_TOKEN) != self.api.graphql_token:
            merge_data = dict(self.config_entry.data)
            merge_data[CONF_GRAPHQL_TOKEN] = self.api.graphql_token
            self.logger.debug(
                "GraphQL token has been updated: %s", self.api.graphql_token
            )
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=merge_data
            )

        return contracts


class MosoblgazCoordinatorEntity(CoordinatorEntity[MosoblgazUpdateCoordinator]):
    _attr_attribution: str = ATTRIBUTION

    _attr_has_entity_name: bool = True
    """Override type from Mapping to dict"""

    @property
    @final
    def logger(self):
        return self.coordinator.logger

    @property
    def api(self):
        return self.coordinator.api


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


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up the Mosoblgaz component."""
    hass.data[DOMAIN] = {}

    if not (domain_config := config.get(DOMAIN)):
        return True

    async_create_issue(
        hass,
        DOMAIN,
        "deprecated_yaml_configuration",
        is_fixable=False,
        issue_domain=DOMAIN,
        severity=IssueSeverity.WARNING,
        translation_key="deprecated_yaml_configuration",
    )

    _LOGGER.warning(
        (
            "YAML configuration of %s is deprecated and will be "
            "removed in the future versions. Your current "
            "configuration had been migrated to the database. "
            "Please, remove '%s: ...' from your configuration."
        ),
        DOMAIN,
        DOMAIN,
    )

    # Iterate over YAML configuration entries
    for user_cfg in domain_config:
        username = user_cfg[CONF_USERNAME]

        # Check if an entry with a valid unique ID already exists
        if hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, username):
            continue

        # Check against internal database for existing entries
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.source == SOURCE_IMPORT and entry.data[CONF_USERNAME] == username:
                break
        else:
            continue

        # Check whether the loaded entry contains password within data,
        # which is an indicator of the entry being updated.
        if CONF_PASSWORD in entry.data:
            continue

        # Update entry, import as version 3 initially
        hass.config_entries.async_update_entry(
            entry,
            data={
                CONF_USERNAME: username,
                CONF_PASSWORD: user_cfg[CONF_PASSWORD],
            },
            options={
                CONF_INVERT_INVOICES: user_cfg[CONF_INVERT_INVOICES],
                CONF_SCAN_INTERVAL: user_cfg[CONF_SCAN_INTERVAL],
                CONF_TIMEOUT: user_cfg[CONF_TIMEOUT],
            },
            unique_id=username,
            version=3,
        )

    return True


async def async_run_with_exceptions(coro: Awaitable):
    """Execute coroutine with Home Assistant exceptions."""
    try:
        return await coro
    except AuthenticationFailedException as exc:
        raise ConfigEntryAuthFailed(str(exc))
    except PartialOfflineException:
        raise ConfigEntryNotReady("Service is partially offline")
    except MosoblgazException as exc:
        raise ConfigEntryNotReady(f"Generic API error: {exc}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Configuration entry setup procedure"""
    if entry.source == SOURCE_IMPORT:
        return False

    logger = ConfigEntryLoggerAdapter(config_entry=entry)
    logger.debug("Setting up config entry")

    api_object = MosoblgazAPI(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=async_create_clientsession(hass),
        graphql_token=entry.data.get(CONF_GRAPHQL_TOKEN),
    )

    coordinator = MosoblgazUpdateCoordinator(hass, api_object, logger=logger)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Refresh configuration entry to set initial data
    await coordinator.async_config_entry_first_refresh()

    if not coordinator.data:
        # No reason to perform updates
        await coordinator.async_shutdown()

    # Forward entry setup to platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Create options update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    logger.debug("Successfully set up account")

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """React to options update"""
    ConfigEntryLoggerAdapter(config_entry=entry).debug("Reloading configuration entry")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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
