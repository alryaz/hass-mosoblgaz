import logging
from typing import Any, Dict, Optional

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from . import privacy_formatter
from .api import (
    AuthenticationFailedException,
    MosoblgazException,
    PartialOfflineException,
)
from .const import (
    CONF_INVERT_INVOICES,
    CONF_PRIVACY_LOGGING,
    DEFAULT_INVERT_INVOICES,
    DEFAULT_PRIVACY_LOGGING,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CONF_ENABLE_CONTRACT = "enable_contract"
CONF_ADD_ALL_CONTRACTS = "add_all_contracts"


class MosoblgazFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mosoblgaz config entries."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Instantiate config flow."""
        self._contracts = None
        self._last_contract_id = None
        self._current_config = None

        from collections import OrderedDict

        self.schema_user = vol.Schema(OrderedDict())

    async def _check_entry_exists(self, username: str):
        current_entries = self._async_current_entries()

        for config_entry in current_entries:
            if config_entry.data.get(CONF_USERNAME) == username:
                return True

        return False

    # Initial step for user interaction
    async def async_step_user(self, user_input: Optional[dict[str, Any]] = None):
        """Handle a flow start."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): cv.string,
                        vol.Required(CONF_PASSWORD): cv.string,
                    }
                ),
            )

        username = user_input[CONF_USERNAME]

        if await self._check_entry_exists(username):
            return self.async_abort("already_exists")

        from .api import MosoblgazAPI

        try:
            async with aiohttp.ClientSession() as session:
                api = MosoblgazAPI(
                    username=username,
                    password=user_input[CONF_PASSWORD],
                    session=session,
                )

                await api.authenticate()

                contracts = await api.fetch_contracts(with_data=False)

                if not contracts:
                    return self.async_abort("contracts_missing")

        except AuthenticationFailedException as exc:
            _LOGGER.error(f"Error during authentication flow: {exc}", exc_info=exc)
            # @TODO: display captcha
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_USERNAME, default=user_input[CONF_USERNAME]
                        ): cv.string,
                        vol.Required(
                            CONF_PASSWORD, default=user_input[CONF_PASSWORD]
                        ): cv.string,
                    }
                ),
                errors={"base": "invalid_credentials"},
            )

        except PartialOfflineException:
            return self.async_abort("partial_offline")

        except MosoblgazException:
            return self.async_abort("api_error")

        return self.async_create_entry(title="User: " + username, data=user_input)

    async def async_step_import(self, user_input=None):
        """
        Handler for imported configurations (from YAML).
        :param user_input: YAML configuration (at least username required)
        :return: Entry creation command
        """
        if user_input is None:
            return self.async_abort("unknown_error")

        username = user_input[CONF_USERNAME]

        if await self._check_entry_exists(username):
            return self.async_abort("already_exists")

        return self.async_create_entry(
            title="User: " + username, data={CONF_USERNAME: username}
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Mosoblgaz options callback."""
        return MosoblgazOptionsFlowHandler(config_entry)


class MosoblgazOptionsFlowHandler(config_entries.OptionsFlow):
    """Mosoblgaz options flow handler"""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize Mosoblgaz options flow handler"""
        self.config_entry = config_entry
        username = config_entry.data[CONF_USERNAME]
        options_source = (
            config_entry.data
            if config_entry.source == SOURCE_IMPORT
            else config_entry.options
        )
        if options_source.get(CONF_PRIVACY_LOGGING, DEFAULT_PRIVACY_LOGGING):
            print_username = privacy_formatter(username)
        else:
            print_username = username
        self.log_prefix = f"(user|{print_username})"

    async def async_step_init(self, user_input=None):
        """
        Options flow entry point.
        :param user_input: User input mapping
        :return: Flow response
        """
        if self.config_entry.source == SOURCE_IMPORT:
            return await self.async_step_import(user_input=user_input)
        return await self.async_step_user(user_input=user_input)

    async def async_step_import(self, user_input=None):
        """
        Callback for entries imported from YAML.
        :param user_input: User input mapping
        :return: Flow response
        """
        _LOGGER.debug(
            f"{self.log_prefix} Showing options form for imported configuration"
        )
        return self.async_show_form(step_id="import")

    async def async_step_user(self, user_input=None):
        """
        Callback for entries created via "Integrations" UI.
        :param user_input: User input mapping
        :return: Flow response
        """
        if user_input is not None:
            _LOGGER.debug(f"{self.log_prefix} Saving options: {user_input}")
            return self.async_create_entry(title="", data=user_input)

        _LOGGER.debug(f"{self.log_prefix} Showing options form for GUI configuration")

        options = self.config_entry.options or {}

        default_invert_invoices = options.get(
            CONF_INVERT_INVOICES, DEFAULT_INVERT_INVOICES
        )
        default_timeout = options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        default_scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        default_privacy_logging = options.get(
            CONF_PRIVACY_LOGGING, DEFAULT_PRIVACY_LOGGING
        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INVERT_INVOICES, default=default_invert_invoices
                    ): cv.boolean,
                    vol.Optional(
                        CONF_TIMEOUT, default=default_timeout
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=default_scan_interval
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_PRIVACY_LOGGING, default=default_privacy_logging
                    ): cv.boolean,
                }
            ),
        )
