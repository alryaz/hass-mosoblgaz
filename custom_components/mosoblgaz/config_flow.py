import logging

from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL

from . import DOMAIN, CONF_METERS, CONF_INVOICES, AuthenticationFailedException, PartialOfflineException, \
    CONF_CONTRACTS, DEFAULT_SCAN_INTERVAL
from .mosoblgaz import MosoblgazException

_LOGGER = logging.getLogger(__name__)

CONF_ENABLE_CONTRACT = "enable_contract"
CONF_ADD_ALL_CONTRACTS = "add_all_contracts"


@config_entries.HANDLERS.register(DOMAIN)
class MosoblgazFlowHandler(config_entries.ConfigFlow):
    """Handle a config flow for Mosoblgaz config entries."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Instantiate config flow."""
        self._contracts = None
        self._last_contract_id = None
        self._current_config = None

        import voluptuous as vol
        from collections import OrderedDict

        schema_user = OrderedDict()
        schema_user[vol.Required(CONF_USERNAME)] = str
        schema_user[vol.Required(CONF_PASSWORD)] = str
        schema_user[vol.Optional(CONF_ADD_ALL_CONTRACTS)] = bool
        schema_user[vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL.seconds)] = int
        self.schema_user = vol.Schema(schema_user)

        schema_contract = OrderedDict()
        schema_contract[vol.Optional(CONF_ENABLE_CONTRACT, default=True)] = bool
        schema_contract[vol.Optional(CONF_METERS, default=True)] = bool
        schema_contract[vol.Optional(CONF_INVOICES, default=True)] = bool
        self.schema_contract = vol.Schema(schema_contract)

    async def _check_entry_exists(self, username: str):
        current_entries = self._async_current_entries()

        for config_entry in current_entries:
            if config_entry.data.get(CONF_USERNAME) == username:
                return True

        return False

    # Initial step for user interaction
    async def async_step_user(self, user_input=None):
        """Handle a flow start."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self.schema_user)

        username = user_input[CONF_USERNAME]

        if await self._check_entry_exists(username):
            return self.async_abort("already_exists")

        from .mosoblgaz import MosoblgazAPI

        try:
            api = MosoblgazAPI(username=username, password=user_input[CONF_PASSWORD])
            await api.authenticate()
            contracts = await api.fetch_contracts(with_data=False)

            if not contracts:
                return self.async_abort("contracts_missing")

        except AuthenticationFailedException:
            # @TODO: display captcha
            return self.async_show_form(step_id="user", data_schema=self.schema_user,
                                        errors={"base": "invalid_credentials"})

        except PartialOfflineException:
            return self.async_abort("partial_offline")

        except MosoblgazException:
            return self.async_abort("api_error")

        if not user_input.get(CONF_ADD_ALL_CONTRACTS):
            self._current_config = {**user_input, CONF_CONTRACTS: {}}
            self._contracts = contracts
            return await self.async_step_contract()

        return self.async_create_entry(title="User: " + username, data=user_input)

    async def async_step_contract(self, user_input=None):
        if self._last_contract_id is None:
            contract_id = list(self._contracts.keys())[0]
            del self._contracts[contract_id]
            self._last_contract_id = contract_id

        else:
            contract_id = self._last_contract_id

        if user_input is None:
            return self.async_show_form(step_id="contract",
                                        data_schema=self.schema_contract,
                                        description_placeholders={"code": contract_id})

        if user_input.get(CONF_ENABLE_CONTRACT):
            contract_config = {
                CONF_METERS: user_input.get(CONF_METERS),
                CONF_INVOICES: user_input.get(CONF_INVOICES),
            }

        else:
            contract_config = False

        self._current_config[CONF_CONTRACTS][contract_id] = contract_config

        if self._contracts:
            return await self.async_step_contract()

        if all(filter(lambda x: not x, self._current_config[CONF_CONTRACTS].values())):
            return self.async_abort('nothing_enabled')

        return self.async_create_entry(title='User: ' + u)

    async def async_step_import(self, user_input=None):
        if user_input is None:
            return self.async_abort("unknown_error")

        username = user_input[CONF_USERNAME]

        if await self._check_entry_exists(username):
            return self.async_abort("already_exists")

        return self.async_create_entry(title="User: " + username, data={CONF_USERNAME: username})
