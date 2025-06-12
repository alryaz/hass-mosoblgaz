import asyncio
import json
import logging
import re
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Mapping, Optional, Union

import aiohttp
from dateutil.tz import gettz

_LOGGER = logging.getLogger(__name__)

HistoryEntryDataType = dict[str, Union[str, dict[str, int]]]
DeviceDataType = dict[str, Any]
InvoiceDataType = Mapping[str, Any]

INVOICE_GROUP_GAS = "gas"
INVOICE_GROUP_VDGO = "vdgo"
INVOICE_GROUP_TECH = "tech"
INVOICE_GROUPS = (INVOICE_GROUP_GAS, INVOICE_GROUP_VDGO, INVOICE_GROUP_TECH)


def convert_date_dict(date_dict: dict[str, Union[str, int]]) -> datetime:
    return datetime.fromisoformat(date_dict["date"]).replace(
        tzinfo=gettz(date_dict["timezone"])
    )


MOSCOW_TIMEZONE = gettz("Europe/Moscow")


def today_blackout(
    check: Optional[datetime] = None,
) -> Union[tuple[datetime, datetime], bool]:
    today = datetime.now(tz=MOSCOW_TIMEZONE)
    blackout_start = today.replace(hour=5, minute=30, second=0)
    blackout_end = today.replace(hour=6, minute=0, second=0)
    if check is None:
        return blackout_start, blackout_end
    return blackout_start <= check <= blackout_end


class ClassCodes:
    UNKNOWN = -1
    METERS = [10100, 10101, 10102]
    STOVE = 102
    HEATER = 103
    BOILER = 104
    HEATING_APPLIANCE = 105
    OTHER = 106
    OUTDOOR_PIPELINE = 201
    INDOOR_PIPELINE = 203
    SECURITY_DEVICE = 204
    CONNECTION_VALVE = 206


class Queries:
    _compiled_queries = {}

    @classmethod
    def compile_sub_query(
        cls,
        queries: list,
        section: str | None = None,
        indent_level: int = 0,
        indent_str: str = " ",
    ) -> str:
        buffer = "{" if section is None else indent_str * indent_level + section + " {"

        indent_level += 1
        for sub_query in queries:
            if isinstance(sub_query, tuple):
                if isinstance(sub_query[0], tuple):
                    section_name = (
                        sub_query[0][0]
                        + "("
                        + ", ".join(["%s: $%s" % v for v in sub_query[0][1].items()])
                        + ")"
                    )
                else:
                    section_name = sub_query[0]

                buffer += "\n" + cls.compile_sub_query(
                    sub_query[1], section_name, indent_level, indent_str
                )

            elif isinstance(sub_query, str):
                buffer += "\n" + indent_str * indent_level + sub_query

        if indent_level > 1:
            buffer += "\n" + indent_str * indent_level + "__typename"

        buffer += "\n" + indent_str * (indent_level - 1) + "}"
        return buffer

    @classmethod
    def query(cls, template: str, use_name: Union[bool, str] = True) -> str:
        if not hasattr(cls, template):
            raise ValueError('%s does not have "%s" query' % cls.__name__)

        prefix = (
            ""
            if use_name is False
            else "query %s " % (template if use_name is True else use_name)
        )

        if template in cls._compiled_queries:
            compiled_query = cls._compiled_queries[template]

        else:
            template_format = getattr(cls, template)
            if isinstance(template_format, tuple):
                compiled_query = (
                    "("
                    + ", ".join(["$%s: %s" % v for v in template_format[0].items()])
                    + ")"
                    + cls.compile_sub_query(template_format[1])
                )
            else:
                compiled_query = cls.compile_sub_query(template_format)

            cls._compiled_queries[template] = compiled_query

        return prefix + compiled_query

    getInternalSystemStatuses = [("me", ["id"]), "internalSystemStatuses"]
    messagesCount = [
        (
            "messages",
            [
                "id",
                "level",
                "sticky",
                "tag",
                "text",
                "type",
                "textAsJsonArray",
            ],
        ),
    ]
    initialData = [
        ("me", ["id", "name", "featureFlags", ("contracts", ["number"])]),
        (
            "metadata",
            [
                "lkk3Enabled",
                "supportPhone",
                "supportPhoneActive",
                "supportPhoneNormalized",
                "newcomer",
            ],
        ),
        "internalSystemStatuses",
        *messagesCount,
    ]
    accountsList = [
        (
            "me",
            [
                "id",
                (
                    "contracts",
                    [
                        "number",
                        "alias",
                        "address",
                        "existsRealMeter",
                        "houseCategory",
                        ("liveBalance", ["number", "liveBalance"]),
                        ("filial", ["id", "title"]),
                        ("contractData", ["number", ("Devices", ["ID"])]),
                    ],
                ),
            ],
        )
    ]
    contractDevices = (
        {"number": "String!"},
        [
            (
                "me",
                [
                    "id",
                    (
                        ("contract", {"number": "number"}),
                        [
                            ("filial", ["id", "title"]),
                            "alias",
                            "address",
                            "calculationsAndPayments",
                            "name",
                            "number",
                            "vdgo",
                            "existsRealMeter",
                            (
                                "contractData",
                                [
                                    # ("TO", ["number", ("Dogovors", ["Num", "Code"])]),
                                    "number",
                                    (
                                        "Nach",
                                        [
                                            "number",
                                            (
                                                "sch",
                                                [
                                                    "number",
                                                    (
                                                        "data",
                                                        ["Id", "Cost", "Dim"],
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                    (
                                        "Devices",
                                        [
                                            "ID",
                                            "ClassCode",
                                            "Model",
                                            "DateNextCheck",
                                            "ClassName",
                                            "ManfNo",
                                            "Status",
                                        ],
                                    ),
                                ],
                            ),
                            (
                                "contractTODocuments",
                                [("contract", ["number"]), ("file", ["id"])],
                            ),
                            ("liveBalance", ["number", "liveBalance"]),
                            ("metersHistory", ["number", "data"]),
                        ],
                    ),
                ],
            )
        ],
    )


class MosoblgazAPI:
    BASE_URL = "https://lkk.mosoblgaz.ru"
    AUTH_URL = BASE_URL + "/auth/login"
    BATCH_URL = BASE_URL + "/graphql/batch"
    CAPTCHA_URL = "https://captcha.mosoblgaz.ru"

    def __init__(
        self,
        username: str,
        password: str,
        session: Optional[aiohttp.ClientSession] = None,
        x_system_auth_token: str | None = None,
        site_key: str | None = None,
    ):
        self.__username = username
        self.__password = password
        self.__graphql_token = None

        self._site_key = site_key

        self._session = session or aiohttp.ClientSession()
        self._x_system_auth_token: str | None = x_system_auth_token

        self._contracts: dict[str, Contract] = {}

    @property
    def is_logged_in(self):
        return self.__graphql_token is not None

    async def fetch_csrf_token(self):
        fetch_url = self.AUTH_URL

        try:
            async with self._session.get(fetch_url) as request:
                html = await request.text()

                if m := re.search(
                    re.escape(self.CAPTCHA_URL + r"/api.js?site-key=") + "([a-f0-9]+)",
                    html,
                ):
                    # Update site key
                    self._site_key = m.group(1)

                results = re.search(r'csrf_token"\s+value="([^"]+)', html)

                if results is None:
                    raise AuthenticationFailedException("No CSRF token found")

        except aiohttp.ClientError as exc:
            error_msg = f"Error fetching CSRF token: {exc}"
            _LOGGER.error(error_msg)
            raise AuthenticationFailedException(error_msg)

        except asyncio.TimeoutError:
            error_msg = "Timeout fetching CSRF token"
            _LOGGER.error(error_msg)
            raise AuthenticationFailedException(error_msg)

        csrf_token = results[1]

        _LOGGER.debug(f"Fetched CSRF token: {csrf_token}")

        return csrf_token

    async def fetch_x_system_auth_token(self):
        try:
            async with self._session.get(
                self.BASE_URL + "/lkk3/asset-manifest.json",
                allow_redirects=False,
            ) as request:
                if request.status != 200:
                    raise AuthenticationFailedException(
                        "Asset manifest could not be fetched"
                    )

                manifest_contents = await request.json()

                try:
                    main_js_location = manifest_contents["files"]["main.js"]
                except KeyError:
                    raise AuthenticationFailedException(
                        "Asset manifest does not contain main.js"
                    )

            async with self._session.get(
                self.BASE_URL + main_js_location, allow_redirects=False
            ) as request:
                if request.status != 200:
                    raise AuthenticationFailedException(
                        "Main JS code could not be fetched"
                    )
                js_code = await request.text()
                results = re.search(
                    r'[\'"]X-SYSTEM-AUTH-TOKEN[\'"]\s*:\s*[\'"]([^\'"]+)[\'"]',
                    js_code,
                )

                if results is None:
                    raise AuthenticationFailedException("No X-SYSTEM-AUTH token found")

        except aiohttp.ClientError as exc:
            error_msg = f"Error fetching X-SYSTEM-AUTH token: {exc}"
            _LOGGER.error(error_msg)
            raise AuthenticationFailedException(error_msg)

        except asyncio.TimeoutError:
            error_msg = "Timeout fetching X-SYSTEM-AUTH token"
            _LOGGER.error(error_msg)
            raise AuthenticationFailedException(error_msg)

        x_system_auth_token = results[1]

        _LOGGER.debug(f"Fetched X-SYSTEM-AUTH token: {x_system_auth_token}")

        return x_system_auth_token

    async def fetch_temporary_token(self, action: str) -> str | None:
        if not self._site_key:
            _LOGGER.info(f"Attempting to make request without site key")

        _LOGGER.debug(f"Fetching temporary token for action: {action}")

        # Perform POST request for captchas
        async with self._session.post(
            self.CAPTCHA_URL + "/api/captchas",
            json={"action": action},
            headers={"Site-Key": self._site_key} if self._site_key else {},
        ) as response:
            data = await response.json()
        if data.get("showCaptcha"):
            # @TODO: support captcha retrieval
            raise AuthenticationFailedException("captcha required (not supported)")
        if temporary_token := data.get("temporaryToken"):
            _LOGGER.debug(f"Fetched temporary token: {temporary_token}")
        else:
            _LOGGER.debug(f"Temporary token not provided in: {data}")
        return temporary_token

    async def authenticate(self, captcha_result: str | None = None):
        csrf_token, x_system_auth_token = await asyncio.gather(
            self.fetch_csrf_token(),
            self.fetch_x_system_auth_token(),
        )

        self._x_system_auth_token = x_system_auth_token

        try:
            auth_request_data = {
                "mog_login[username]": self.__username,
                "mog_login[password]": self.__password,
                "mog_login[captcha]": captcha_result or "",
                "_csrf_token": csrf_token,
                "_remember_me": "on",
            }

            if temporary_token := await self.fetch_temporary_token("login"):
                auth_request_data["mog-captcha-response"] = temporary_token

            async with self._session.post(
                self.AUTH_URL, data=auth_request_data
            ) as response:
                if response.status not in [200, 301, 302]:
                    if _LOGGER.level == logging.DEBUG:
                        _LOGGER.debug(f"Response: {await response.text()}")

                    raise AuthenticationFailedException(
                        f"Error status ({response.status})"
                    )

                _LOGGER.debug(f"Authentication on account {self.__username} successful")

            async with self._session.head(self.BASE_URL + "/lkk3/") as response:
                graphql_token = response.headers.get("Token")

                if not graphql_token:
                    _LOGGER.debug(
                        f"No graphql token found in: headers={response.headers}, body={await response.text()}"
                    )
                    raise AuthenticationFailedException("Failed to grab GraphQL token")

                _LOGGER.debug(f"GraphQL token: {graphql_token}")

                self.__graphql_token = graphql_token

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout executing authentication request")
            raise AuthenticationFailedException(
                "Timeout executing authentication request"
            )

    async def perform_single_query(
        self, query: str, variables: Optional[dict[str, Any]] = None
    ):
        return (await self.perform_queries([(query, variables)]))[0]

    async def perform_queries(
        self, queries: list[Union[str, tuple[str, Optional[dict[str, Any]]]]]
    ) -> list[dict[str, Any]]:
        """Perform multiple queries at once."""
        if not self.is_logged_in:
            raise AuthenticationFailedException(
                "Authentication required prior to making batch requests"
            )

        payload = []
        for query_variables in queries:
            if isinstance(query_variables, str):
                query = query_variables
                variables = {}
            else:
                query, variables = query_variables

            operation_name = None
            if query.startswith("query "):
                try:
                    name_start = query.index(" ") + 1
                    name_end = query.index(" ", name_start)
                    operation_name = query[name_start:name_end] or None
                except ValueError:
                    pass

            payload.append(
                {
                    "operationName": operation_name,
                    "query": query,
                    "variables": {} if variables is None else variables,
                }
            )

        if _LOGGER.level == logging.DEBUG:
            _LOGGER.debug(f"Sending payload: {payload}")

        try:
            async with self._session.post(
                self.BATCH_URL,
                json=payload,
                headers={"token": self.__graphql_token},
            ) as response:
                try:
                    listed_data = list(map(lambda x: x["data"], await response.json()))
                except (
                    json.decoder.JSONDecodeError,
                    aiohttp.ContentTypeError,
                    ValueError,
                    AttributeError,
                    LookupError,
                ) as exc:
                    _LOGGER.debug(f"Response text: {await response.text()}")
                    raise QueryFailedException("decoding error") from exc
                else:
                    _LOGGER.debug(f"Received data: {listed_data}")
                    return listed_data

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout executing query")
            raise QueryFailedException("Timeout executing query")

    @property
    def contracts(self) -> dict[str, "Contract"]:
        return self._contracts

    @staticmethod
    def check_statuses_response(
        statuses_response: dict[str, Union[bool, str]],
        raise_for_statuses: bool = True,
        check_keys: Optional[dict[str, Union[bool, str]]] = None,
        with_default: bool = True,
    ):
        if "internalSystemStatuses" in statuses_response:
            statuses_response = statuses_response["internalSystemStatuses"]

        statuses_keys = (
            {
                # "apple_pay_enabled": True,
                "coffee_break": False,
                # "google_pay_enabled": True,
                # "pps_tech_coffee_break": True,
                # "pps_tech_request_coffee_break": True,
                # "recurring_payments_enabled": True,
                # "saupg_status": "online",
                # "saupg_values_coffee_break": True,
                # "soo_coffee_break": True,
                # "support_coffee_break": True,
                # "tech_request_coffee_break": True,
                # "visit_coffee_break": True,
            }
            if with_default
            else {}
        )
        if check_keys is not None:
            statuses_keys.update(check_keys)

        bad_statuses = [
            "%s =/= %s" % (status_key, good_value)
            for status_key, good_value in statuses_keys.items()
            if statuses_response.get(status_key) != good_value
        ]
        if bad_statuses and raise_for_statuses:
            raise PartialOfflineException(", ".join(bad_statuses))
        return bad_statuses or None

    async def fetch_contracts(
        self, with_data: bool = False, raise_for_statuses: bool = True
    ) -> dict[str, "Contract"]:
        _LOGGER.debug("Fetching contracts list")

        statuses_query = Queries.query("getInternalSystemStatuses")
        contracts_query = Queries.query("accountsList")

        response_list = await self.perform_queries([statuses_query, contracts_query])
        status_response, contracts_response = response_list

        self.check_statuses_response(
            status_response, raise_for_statuses=raise_for_statuses
        )

        contract_ids = set()
        for contract in contracts_response["me"]["contracts"]:
            device_ids = {
                device["ID"] for device in contract["contractData"]["Devices"]
            }
            contract_id = contract["number"]
            contract_ids.add(contract_id)

            if contract_id in self._contracts:
                self._contracts[contract_id].update_device_ids(device_ids)
            else:
                self._contracts[contract_id] = Contract(self, contract_id, device_ids)

        for contract_id in self._contracts.keys() - contract_ids:
            del self._contracts[contract_id]

        if with_data:
            contract_data_query = Queries.query("contractDevices")
            for contract, data in zip(
                self._contracts.values(),
                await self.perform_queries(
                    [
                        (contract_data_query, {"number": contract_id})
                        for contract_id in self._contracts.keys()
                    ]
                ),
            ):
                contract.data = data["me"]["contract"]

        _LOGGER.debug(f"Fetched contracts data: {self._contracts}")

        return self._contracts

    async def push_indication(
        self,
        contract_id: str,
        meter_id: str,
        value: Union[int, float],
        date_: Optional[Union[datetime, date]] = None,
    ):
        x_system_auth_token = self._x_system_auth_token
        if x_system_auth_token is None:
            raise AuthenticationFailedException("X-SYSTEM-AUTH token required")

        if date_ is None:
            date_ = date.today()
        elif isinstance(date_, datetime):
            date_ = date_.date()

        push_url = (
            self.BASE_URL + f"/api/contracts/{contract_id}/meters/{meter_id}/values"
        )
        async with self._session.post(
            push_url,
            json={
                "date": date_.isoformat(),
                "value": str(int(value)),
            },
            headers={
                "X-SYSTEM-AUTH": x_system_auth_token,
                "token": self.__graphql_token,
            },
            allow_redirects=False,
        ) as response:
            json_data = await response.json()

        _LOGGER.debug(f"Received JSON push data from {push_url}: {json_data}")

        if not json_data["success"]:
            error_data = json_data.get("error", {})
            raise MosoblgazException(
                f"({error_data.get('code', 999)}) {error_data.get('text', 'Unknown error')}"
            )


class Contract:
    def __init__(
        self,
        api: MosoblgazAPI,
        contract_id: str,
        device_ids: Optional[set[str]] = None,
    ):
        self.api = api

        self._contract_id = contract_id
        self._devices: dict[str, Optional[Device]] = (
            {} if device_ids is None else dict.fromkeys(device_ids, None)
        )
        self._invoices: Optional[dict[str, dict[tuple[int, int], Invoice]]] = None

        self._data = None

    def __str__(self):
        return self.__class__.__name__ + ("[%s]" % self._contract_id)

    def __repr__(self):
        return "<" + self.__str__() + ">"

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value: dict[str, Any]):
        self._data = value

        device_ids = set()
        for device_data in self.devices_data:
            device_id: str = device_data["ID"]
            device_ids.add(device_id)

            is_meter = device_data["ClassCode"] in ClassCodes.METERS

            if self._devices.get(device_id) is None:
                factory = Meter if is_meter else Device
                device = factory(self, device_data)
            else:
                device = self._devices[device_id]
                device.data = device_data

            if is_meter:
                for history_pair in self.history_data:
                    if history_pair["info"]["ID"] == device.device_id:
                        device.history = history_pair["values"]
                        break

            self._devices[device_id] = device

        for device_id in self._devices.keys() - device_ids:
            del self._devices[device_id]

        # Process invoices
        if self._invoices is None:
            self._invoices = {}

        for invoice_group in INVOICE_GROUPS:
            invoice_data = self._data["calculationsAndPayments"].get(invoice_group)
            invoices = self._invoices.setdefault(invoice_group, {})

            if invoice_data:
                invoice_periods = set()

                for period, invoice in invoice_data.items():
                    month, year = map(int, period.split("."))
                    period = (year, month)
                    invoice_periods.add(period)

                    if period in invoices:
                        invoices[period].data = invoice
                    else:
                        invoices[period] = Invoice(self, invoice_group, invoice, period)

                for invoice_key in invoices.keys() - invoice_periods:
                    del invoices[invoice_key]

    @property
    def _property_data(self) -> dict[str, Any]:
        if self._data is None:
            raise ContractUpdateRequiredException(self)
        return self._data

    def update_device_ids(self, device_ids: set):
        for device_id in self._devices.keys() - device_ids:
            del self._devices[device_id]

        for device_id in device_ids - self._devices.keys():
            self._devices[device_id] = None

    @property
    def contract_id(self):
        return self._contract_id

    @property
    def person(self):
        return self._property_data["name"]

    @property
    def department_title(self):
        return self._property_data["filial"]["title"]

    @property
    def has_devices(self):
        return bool(self._devices)

    @property
    def devices(self):
        if None in self._devices.values():
            raise ContractUpdateRequiredException(self)

        return self._devices

    @property
    def meters(self) -> dict[str, "Meter"]:
        return {i: d for i, d in self.devices.items() if isinstance(d, Meter)}

    async def update_data(self):
        contract_data_query = Queries.query("contractDevices")
        response = await self.api.perform_single_query(
            contract_data_query, {"number": self._contract_id}
        )
        self.data = response["me"]["contract"]

    # Data properties
    @property
    def address(self):
        return self._property_data["address"]

    @property
    def alias(self) -> str | None:
        return self._property_data["alias"] or None

    @property
    def all_invoices_by_groups(
        self,
    ) -> dict[str, dict[tuple[int, int], "Invoice"]]:
        if self._invoices is None:
            raise ContractUpdateRequiredException(self)

        return self._invoices

    @property
    def last_invoices_by_groups(self) -> dict[str, "Invoice"]:
        all_invoices = self.all_invoices_by_groups
        group_count = sum(
            [bool(group_invoices) for group_invoices in all_invoices.values()]
        )
        last_invoices = dict()

        while len(last_invoices) != group_count:
            today = date.today()
            period = (today.year, today.month)
            for group in all_invoices.keys() - last_invoices.keys():
                if period in all_invoices[group]:
                    last_invoices[group] = all_invoices[group][period]

        return last_invoices

    @property
    def invoices_gas(self) -> dict[tuple[int, int], "Invoice"]:
        return self.all_invoices_by_groups[INVOICE_GROUP_GAS]

    @property
    def invoices_tech(self) -> dict[tuple[int, int], "Invoice"]:
        return self.all_invoices_by_groups[INVOICE_GROUP_TECH]

    @property
    def invoices_vdgo(self) -> dict[tuple[int, int], "Invoice"]:
        return self.all_invoices_by_groups[INVOICE_GROUP_VDGO]

    @property
    def balance(self):
        return round(
            float(self._property_data.get("liveBalance", {}).get("liveBalance", 0.0)),
            2,
        )

    @property
    def devices_data(self) -> list[dict[str, Any]]:
        return self._property_data["contractData"]["Devices"]

    @property
    def meters_data(self):
        return list(
            filter(
                lambda x: x["ClassCode"] in ClassCodes.METERS,
                self.devices_data,
            )
        )

    @property
    def history_data(self):
        return self._property_data["metersHistory"]["data"]

    async def push_indication(
        self,
        meter_id: str,
        value: Union[int, float],
        date_: Optional[Union[datetime, date]] = None,
    ):
        return await self.api.push_indication(self.contract_id, meter_id, value, date_)


class Device:
    def __init__(self, contract: Contract, data: DeviceDataType):
        self._contract = contract
        self._data = data

    def __str__(self):
        return f"Device[{self.device_id}]"

    def __repr__(self):
        return "<" + self.__str__() + ">"

    @property
    def contract(self) -> "Contract":
        return self._contract

    @property
    def device_id(self) -> str:
        return self._data["ID"]

    @property
    def data(self) -> DeviceDataType:
        return self._data

    @data.setter
    def data(self, value: DeviceDataType):
        self._data = value

    @property
    def device_class_code(self) -> int:
        return int(self.data.get("ClassCode", -1))

    @property
    def device_class(self) -> str | None:
        try:
            return list(ClassCodes.__dict__.keys())[
                list(ClassCodes.__dict__.values()).index(self.device_class_code)
            ].lower()
        except IndexError:
            return None

    @property
    def device_class_name(self) -> str:
        return self.data["ClassName"]

    @property
    def model(self) -> str:
        return self.data["Model"]


class Meter(Device):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._history = None
        self._last_history_period = None

    @property
    def serial(self) -> str | None:
        return self.data.get("ManfNo")

    @property
    def date_next_check(self) -> date:
        return date.fromisoformat(self.data["DateNextCheck"])

    @property
    def history(self) -> Optional[dict[tuple[int, int, int], "HistoryEntry"]]:
        return self._history

    @history.setter
    def history(self, value: list[dict[str, Union[str, dict[str, int]]]]) -> None:
        if self._history is None:
            self._history = {}

        last_history_period = (0, 0, 0)
        for history_data in value:
            history_date = convert_date_dict(history_data["Date"])
            period = (history_date.year, history_date.month, history_date.day)

            if period > last_history_period:
                last_history_period = period

            if period in self._history:
                self._history[period].data = history_data
            else:
                self._history[period] = HistoryEntry(self, history_data)

        self._last_history_period = last_history_period

    @property
    def last_history_entry(self) -> Optional["HistoryEntry"]:
        if self._history is not None:
            return self.history[self._last_history_period]

    async def push_indication(
        self,
        value: Union[int, float],
        date_: Optional[Union[datetime, date]] = None,
        ignore_values: bool = False,
    ):
        if not ignore_values:
            history_entry = self.last_history_entry
            if history_entry and int(value) < int(history_entry.value):
                raise ValueError("new value is less than previous value")
        return await self.contract.push_indication(self.device_id, value, date_)


class HistoryEntry:
    def __init__(self, meter: "Meter", data: HistoryEntryDataType):
        self._meter = meter
        self.data = data

    @property
    def collected_at(self) -> datetime:
        return convert_date_dict(self._data["Date"])

    @property
    def meter(self):
        return self._meter

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value: HistoryEntryDataType):
        self._data = value

    @property
    def cost(self) -> float:
        return float(self._data.get("Cost") or 0.0)

    @property
    def delta(self) -> int:
        if "M3" in self._data:
            return int(self._data.get("M3", 0))
        return self.value - self.previous_value

    @property
    def previous_value(self) -> int:
        return int(self._data.get("prevV", 0))

    @property
    def value(self) -> int:
        return int(self._data.get("V", 0))

    @property
    def charged(self) -> float:
        return round(self.cost * self.delta, 2)


class Invoice:
    def __init__(
        self,
        contract: Contract,
        group: str,
        data: InvoiceDataType,
        period: tuple[int, int],
    ):
        self._contract = contract
        self._group = group
        self._period = date(*period, 1)
        self._payments: Optional[list[Payment]] = []
        self.data = data

    @property
    def contract(self) -> Contract:
        return self._contract

    @property
    def group(self) -> str:
        return self._group

    @property
    def data(self) -> InvoiceDataType:
        """Invoice data getter"""
        return MappingProxyType(self._data)

    @data.setter
    def data(self, value: InvoiceDataType) -> None:
        """Invoice data setter"""
        if value is None:
            raise ValueError("data value cannot be empty")

        self._payments.clear()

        payments = value.get("payments")
        if payments:
            for payment_data in payments:
                self._payments.append(Payment(payment_data))

        self._data = value

    @property
    def balance(self) -> float:
        """Balance at the moment of invoice issue"""
        return round(float(self._data.get("balance") or 0.0), 2)

    @property
    def paid(self) -> Optional[float]:
        """Paid amount (if available)"""
        return round(float(self._data.get("paid") or 0.0), 2)

    @property
    def payments(self) -> list["Payment"]:
        """List of payments"""
        return self._payments

    @property
    def payments_count(self) -> int:
        """Payments amount"""
        return len(self._payments)

    @property
    def period(self) -> date:
        """Invoice period"""
        return self._period

    @property
    def total(self) -> Optional[float]:
        """Invoice total"""
        return round(float(self._data.get("invoice") or 0.0), 2)


class Payment:
    """Payment class"""

    # @TODO: add more properties
    def __init__(self, data: dict[str, Any]):
        self._data = data

    @property
    def datetime(self) -> datetime:
        return convert_date_dict(self._data["date"])


class MosoblgazException(Exception):
    prefix = "Mosoblgaz API error"

    def __init__(self, reason):
        super(MosoblgazException, self).__init__(f"{self.prefix}: {reason}")


class RequestFailedException(MosoblgazException):
    prefix = "Request failed"


class AuthenticationFailedException(MosoblgazException):
    prefix = "Failed to authenticate"


class QueryFailedException(RequestFailedException):
    prefix = "Query request failed"


class QueryNotFoundException(MosoblgazException):
    prefix = "Query not found"


class ContractUpdateRequiredException(MosoblgazException):
    prefix = "Contract requires data update"


class PartialOfflineException(MosoblgazException):
    prefix = "Service reported partial offline status"
