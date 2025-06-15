from base64 import b64encode
import logging
from typing import Any, Final, Mapping

from homeassistant.helpers.aiohttp_client import (
    async_get_clientsession,
)
import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    CONN_CLASS_CLOUD_POLL,
)
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from custom_components.mosoblgaz.api import (
    AuthenticationFailedException,
    CaptchaResponse,
    MosoblgazAPI,
    MosoblgazException,
    PartialOfflineException,
)
from custom_components.mosoblgaz.const import (
    CONF_GRAPHQL_TOKEN,
    CONF_INVERT_INVOICES,
    DEFAULT_INVERT_INVOICES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CONF_CAPTCHA: Final = "captcha"
CONF_ENABLE_CONTRACT: Final = "enable_contract"
CONF_ADD_ALL_CONTRACTS: Final = "add_all_contracts"

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

REAUTH_WITH_CAPTCHA_SCHEMA = REAUTH_SCHEMA.extend(
    {
        vol.Optional(CONF_CAPTCHA): cv.string,
    }
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

USER_WITH_CAPTCHA_SCHEMA = USER_SCHEMA.extend(
    {
        vol.Optional(CONF_CAPTCHA): cv.string,
    }
)


class _FormException(Exception):
    """Class for exceptions pertaining to forms"""


class MosoblgazFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mosoblgaz config entries."""

    VERSION = 3
    MINOR_VERSION = 2
    CONNECTION_CLASS = CONN_CLASS_CLOUD_POLL

    _api: MosoblgazAPI

    def __init__(self) -> None:
        self._temporary_token: str | CaptchaResponse | None = None

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_user(self._get_reauth_entry())

    async def async_step_user(
        self, user_input: Mapping[str, Any] | ConfigEntry | None = None
    ) -> ConfigFlowResult:
        """Route based on the required of the temporary token presence."""

        # Handle input coming from reauth entry
        self._api = MosoblgazAPI("", "", async_get_clientsession(self.hass))

        _LOGGER.info("Showing user step")

        # Prefetch temporary token
        self._temporary_token = await self._api.fetch_temporary_token()
        if isinstance(self._temporary_token, CaptchaResponse):
            method = self.async_step_with_captcha
        else:
            method = self.async_step_without_captcha

        # Run one of the captcha methods
        return await method({CONF_USERNAME: self._api.username}, True)

    async def _async_process_authentication(
        self, user_input: dict[str, Any]
    ) -> ConfigFlowResult:
        if self.source == SOURCE_REAUTH:
            self._api.username = self._get_reauth_entry().data[CONF_USERNAME]
        else:
            self._api.username = user_input[CONF_USERNAME]

        self._api.password = user_input.pop(CONF_PASSWORD)
        captcha = ""

        if self._temporary_token is None:
            # Processing came from oone of the methods, however
            # something managed to lose temporary token. While this
            # should never occur, fix it 'just in case it happens'.
            _LOGGER.debug("Fixing flow on non-existing temporary token")
            self._temporary_token = await self._api.fetch_temporary_token()

        if isinstance(self._temporary_token, CaptchaResponse):
            try:
                captcha = user_input.pop(CONF_CAPTCHA)
            except KeyError:
                # Processing came from 'without_captcha', but evidently
                # expected to come from 'with_captcha'; fix flow, although
                # this should never occur.
                _LOGGER.debug("Fixing flow on non-existent CAPTCHA")
            else:
                if captcha:
                    # Attempt solving CAPTCHA
                    try:
                        self._temporary_token = await self._api.solve_captcha(
                            captcha, self._temporary_token
                        )
                    except PartialOfflineException:
                        return self.async_abort(reason="partial_offline")
                    except AuthenticationFailedException:
                        raise _FormException({"captcha": "invalid_captcha"})
                    except MosoblgazException:
                        raise _FormException({"base": "unknown_error"})
                    if not self._temporary_token:
                        # @TODO: handle this issue
                        raise _FormException({"base": "empty_temporary_token"})
                else:
                    # Attempt to fetch a new CAPTCHA
                    self._temporary_token = await self._api.fetch_temporary_token()

        if isinstance(self._temporary_token, CaptchaResponse):
            return await self.async_step_with_captcha(user_input, True)

        try:
            await self._api.authenticate(self._temporary_token, captcha)
        except PartialOfflineException:
            return self.async_abort(reason="partial_offline")
        except AuthenticationFailedException:
            # @TODO: handle this issue
            raise _FormException({"base": "invalid_credentials"})
        except MosoblgazException:
            raise _FormException({"base": "unknown_error"})

        data = {
            CONF_PASSWORD: self._api.password,
            CONF_GRAPHQL_TOKEN: self._api.graphql_token,
        }

        await self.async_set_unique_id(self._api.username)

        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=data
            )

        self._abort_if_unique_id_configured()
        data[CONF_USERNAME] = self._api.username
        return self.async_create_entry(title=self._api.username, data=data)

    async def async_step_without_captcha(
        self,
        user_input: dict[str, Any] | None = None,
        after_process: bool = False,
    ) -> ConfigFlowResult:
        _LOGGER.info("Showing without captcha step")
        errors = None
        if not (after_process or user_input is None):
            try:
                return await self._async_process_authentication(user_input)
            except _FormException as exc:
                errors = exc.args[0]
        return self.async_show_form(
            step_id="without_captcha",
            data_schema=self.add_suggested_values_to_schema(
                REAUTH_SCHEMA if self.source == SOURCE_REAUTH else USER_SCHEMA,
                {CONF_USERNAME: self._api.username},
            ),
            errors=errors,
        )

    async def async_step_with_captcha(
        self,
        user_input: dict[str, Any] | None = None,
        after_process: bool = False,
    ) -> ConfigFlowResult:
        _LOGGER.info("Showing with captcha step")
        errors = None
        if not (after_process or user_input is None):
            try:
                return await self._async_process_authentication(user_input)
            except _FormException as exc:
                errors = exc.args[0]
        temporay_token = self._temporary_token
        if not isinstance(temporay_token, CaptchaResponse):
            return self.async_abort(reason="unknown_error")
        description_placeholders = {
            "captcha_token": temporay_token.token,
            "captcha_valid": temporay_token.valid_until,
        }
        async with self._api._session.get(temporay_token.file_url) as response:
            description_placeholders["captcha_url"] = (
                "data:image/"
                + temporay_token.file_url.rsplit(".", 1)[1]
                + ";base64,"
                + b64encode(await response.read()).decode("ascii")
            )
        return self.async_show_form(
            step_id="with_captcha",
            data_schema=self.add_suggested_values_to_schema(
                (
                    REAUTH_WITH_CAPTCHA_SCHEMA
                    if self.source == SOURCE_REAUTH
                    else USER_WITH_CAPTCHA_SCHEMA
                ),
                {CONF_USERNAME: self._api.username},
            ),
            description_placeholders=description_placeholders,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> "MosoblgazOptionsFlowHandler":
        """Mosoblgaz options callback."""
        return MosoblgazOptionsFlowHandler(config_entry)


OPTIONS_SCHEMA: Final[vol.Schema] = vol.Schema(
    {
        vol.Optional(CONF_INVERT_INVOICES, default=DEFAULT_INVERT_INVOICES): cv.boolean,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
        vol.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): cv.positive_int,
    }
)


class MosoblgazOptionsFlowHandler(OptionsFlow):
    """Mosoblgaz options flow handler"""

    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__()
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """
        Options flow entry point.
        :param user_input: User input mapping
        :return: Flow response
        """

        # Execute unawaited coroutine
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """
        Callback for entries created via "Integrations" UI.
        :param user_input: User input mapping
        :return: Flow response
        """
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        else:
            # Use default options
            user_input = self.config_entry.options

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, user_input),
        )
