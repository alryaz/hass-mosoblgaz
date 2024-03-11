"""
Sensor for Mosoblgaz cabinet.
Retrieves values regarding current state of contracts.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from functools import partial
from typing import (
    Any,
    Callable,
    Iterable,
    Mapping,
    Optional,
    Type,
    Union,
)

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import (
    SensorDeviceClass,
    ATTR_STATE_CLASS,
    SensorStateClass,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    UnitOfVolume,
)
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import get_print_username, is_privacy_logging_enabled, privacy_formatter
from .api import (
    Contract,
    INVOICE_GROUP_GAS,
    INVOICE_GROUP_TECH,
    INVOICE_GROUP_VDGO,
    Invoice,
    Meter,
    MosoblgazAPI,
    MosoblgazException,
    PartialOfflineException,
)
from .const import *

_LOGGER: logging.Logger = logging.getLogger(__name__)

INDICATIONS_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Required(vol.Match(r"t\d+")): cv.positive_float,
    }
)

INDICATIONS_SEQUENCE_SCHEMA = vol.All(
    vol.Any(vol.All(cv.positive_float, cv.ensure_list), [cv.positive_float]),
    lambda x: dict(map(lambda y: ("t" + str(y[0]), y[1]), enumerate(x, start=1))),
)

SERVICE_PUSH_INDICATIONS: Final = "push_indications"
SERVICE_PUSH_INDICATIONS_SCHEMA: Final = vol.Schema(
    vol.All(
        cv.make_entity_service_schema(
            {
                vol.Required(ATTR_INDICATIONS): vol.Any(
                    vol.All(
                        cv.string,
                        lambda x: list(map(str.strip, x.split(","))),
                        INDICATIONS_SEQUENCE_SCHEMA,
                    ),
                    INDICATIONS_MAPPING_SCHEMA,
                    INDICATIONS_SEQUENCE_SCHEMA,
                ),
                # vol.Optional(ATTR_IGNORE_PERIOD, default=False): cv.boolean,
                vol.Optional(ATTR_IGNORE_INDICATIONS, default=False): cv.boolean,
                vol.Optional(ATTR_INCREMENTAL, default=False): cv.boolean,
                vol.Optional("notification"): lambda x: x,
            }
        ),
        cv.deprecated("notification"),
    )
)


def get_should_add_entities(
    contract_id: str,
    default_add_contracts: Union[bool, Mapping[str, Any]] = DEFAULT_ADD_CONTRACTS,
    default_add_meters: bool = DEFAULT_ADD_METERS,
    default_add_invoices: bool = DEFAULT_ADD_INVOICES,
) -> tuple[bool, bool, bool]:
    """
    Whether entities should be added to a given contract ID according to config.
    :param contract_id:
    :param default_add_contracts:
    :param default_add_meters:
    :param default_add_invoices:
    :return:
    """
    if isinstance(default_add_contracts, Mapping):
        contract_conf = default_add_contracts.get(contract_id)
        if contract_conf is not None:
            if contract_conf is True:
                # Contract is specified to be "true", enable everything
                return True, True, True
            elif contract_conf is False:
                # Contract is specified to be "false", disable everything
                return False, False, False
            else:
                # Contract has specific settings
                return (
                    contract_conf.get(CONF_CONTRACTS, default_add_contracts),
                    contract_conf.get(CONF_METERS, default_add_meters),
                    contract_conf(CONF_INVOICES, default_add_invoices),
                )

    return default_add_contracts, default_add_meters, default_add_invoices


async def async_account_updater(
    hass: HomeAssistantType,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: Callable[[Iterable[Entity]], Any],
    now: Optional[datetime] = None,
) -> Union[bool, int]:
    """Perform update on account"""
    entry_id = config_entry.entry_id
    user_cfg = config_entry.data
    username = user_cfg[CONF_USERNAME]

    if config_entry.source == SOURCE_IMPORT:
        user_cfg = hass.data[DATA_CONFIG][username]
        options_cfg = user_cfg
    else:
        options_cfg = config_entry.options

    # Privacy logging configuration
    privacy_logging_enabled = is_privacy_logging_enabled(hass, config_entry)
    print_username = get_print_username(
        hass,
        config_entry,
        privacy_logging=privacy_logging_enabled,
    )
    log_prefix = f"(user|{print_username})"

    _LOGGER.debug(f"{log_prefix} Running updater at {now or datetime.now()}")
    api: "MosoblgazAPI" = hass.data.get(DATA_API_OBJECTS, {}).get(entry_id)

    if not api:
        _LOGGER.debug(f"{log_prefix} Updater found no API object")
        return False

    try:
        # Contract fetching phase
        contracts = await api.fetch_contracts(with_data=True)

    except PartialOfflineException:
        _LOGGER.error(f"{log_prefix} Partial offline, will delay entity update")
        return False

    except MosoblgazException as exc:
        _LOGGER.error(f"{log_prefix} Error fetching contracts: {exc}")
        return False

    # Do not process contracts if none received
    # Return zero new entities
    if not contracts:
        _LOGGER.info(f"{log_prefix} Did not receive any contract data")
        return 0

    # Entity adding defaults
    if config_entry.source == SOURCE_IMPORT:
        default_add_meters = user_cfg.get(CONF_METERS, DEFAULT_ADD_METERS)
        default_add_invoices = user_cfg.get(CONF_INVOICES, DEFAULT_ADD_INVOICES)
        default_add_contracts = user_cfg.get(CONF_CONTRACTS, DEFAULT_ADD_CONTRACTS)

        name_format_meters = user_cfg.get(CONF_METER_NAME, DEFAULT_METER_NAME_FORMAT)
        name_format_invoices = user_cfg.get(
            CONF_INVOICE_NAME, DEFAULT_INVOICE_NAME_FORMAT
        )
        name_format_contracts = user_cfg.get(
            CONF_CONTRACT_NAME, DEFAULT_CONTRACT_NAME_FORMAT
        )
    else:
        default_add_meters, default_add_invoices, default_add_contracts = (
            DEFAULT_ADD_METERS,
            DEFAULT_ADD_INVOICES,
            DEFAULT_ADD_CONTRACTS,
        )
        name_format_meters, name_format_invoices, name_format_contracts = (
            DEFAULT_METER_NAME_FORMAT,
            DEFAULT_INVOICE_NAME_FORMAT,
            DEFAULT_CONTRACT_NAME_FORMAT,
        )

    # Common options collection
    invert_invoices = options_cfg.get(CONF_INVERT_INVOICES)

    # Prepare created entities holder
    entry_entities = hass.data.setdefault(DATA_ENTITIES, {}).setdefault(entry_id, {})

    # Prepare temporary data holders
    tasks = []
    new_entities = []

    # Remove obsolete entities
    obsolete_contract_ids = entry_entities.keys() - contracts.keys()
    for contract_id in obsolete_contract_ids:
        contract_entities = entry_entities[contract_id]

        if MOGContractSensor in contract_entities:
            tasks.append(contract_entities[MOGContractSensor].async_remove())
            del contract_entities[MOGContractSensor]

        if MOGMeterSensor in contract_entities:
            tasks.extend(
                map(
                    lambda x: x.async_remove(),
                    contract_entities[MOGMeterSensor],
                )
            )
            del contract_entities[MOGMeterSensor]

        if MOGInvoiceSensor in contract_entities:
            tasks.extend(
                map(
                    lambda x: x.async_remove(),
                    contract_entities[MOGInvoiceSensor],
                )
            )
            del contract_entities[MOGInvoiceSensor]

        del entry_entities[contract_id]

    # Iterate over fetched contracts
    for contract_id, contract in contracts.items():
        # Setup logging prefix for contract during processing
        print_contract_id = contract_id
        if privacy_logging_enabled:
            print_contract_id = privacy_formatter(print_contract_id)

        contract_log_prefix = f"{log_prefix} (contract|{print_contract_id})"

        # Prepare entities holder
        if contract_id in entry_entities:
            _LOGGER.debug(f"{contract_log_prefix} Refreshing entity data")
            contract_entities = entry_entities[contract_id]
        else:
            contract_entities = {}
            entry_entities[contract_id] = contract_entities
            _LOGGER.debug(f"{contract_log_prefix} Setting up new entities")

        contract_entities: dict[
            Type[MOGEntity],
            Union[
                MOGContractSensor,
                dict[str, Union[MOGMeterSensor, MOGInvoiceSensor]],
            ],
        ]

        # Get adding parameters
        add_contracts, add_meters, add_invoices = get_should_add_entities(
            contract_id=contract_id,
            default_add_meters=default_add_meters,
            default_add_invoices=default_add_invoices,
            default_add_contracts=default_add_contracts,
        )

        # Process contract entity
        contract_entity: Optional[MOGContractSensor] = contract_entities.get(
            MOGContractSensor
        )
        if contract_entity:
            contract_entity.contract = contract

            if contract_entity.enabled:
                _LOGGER.debug(f"{contract_log_prefix} Updating contract entity")
                contract_entity.async_schedule_update_ha_state(force_refresh=True)
            else:
                _LOGGER.debug(
                    f"{contract_log_prefix} Not updating disabled contract entity"
                )

        else:
            contract_entity = MOGContractSensor(
                contract=contract,
                name_format=name_format_contracts,
                default_add=default_add_contracts,
            )
            new_entities.append(contract_entity)
            contract_entities[MOGContractSensor] = contract_entity
            tasks.append(contract_entity.async_update())
            _LOGGER.debug(f"{contract_log_prefix} Creating new contract entity")

        # Process meter entities
        meters = contract.meters
        meter_entities = contract_entities.setdefault(MOGMeterSensor, {})
        obsolete_meter_ids = meter_entities.keys() - meters.keys()
        for meter_id in obsolete_meter_ids:
            tasks.append(meter_entities[meter_id].async_remove())
            del meter_entities[meter_id]

        for meter_id, meter in meters.items():
            meter_entity = meter_entities.get(meter_id)

            # Logging prefix for meters
            print_meter_id = meter_id
            if privacy_logging_enabled:
                print_meter_id = privacy_formatter(print_meter_id)

            meter_log_prefix = f"{contract_log_prefix} (meter|{print_meter_id})"

            if meter_entity:
                meter_entity.contract = contract
                meter_entity.meter = meter

                if meter_entity.enabled:
                    _LOGGER.debug(f"{meter_log_prefix} Updating meter entity")
                    meter_entity.async_schedule_update_ha_state(force_refresh=True)
                else:
                    _LOGGER.debug(
                        f"{meter_log_prefix} Not updating disabled meter entity"
                    )
            else:
                meter_entity = MOGMeterSensor(
                    contract=contract,
                    meter=meter,
                    name_format=name_format_meters,
                    default_add=add_meters,
                )
                new_entities.append(meter_entity)
                meter_entities[meter_id] = meter_entity
                tasks.append(meter_entity.async_update())
                _LOGGER.debug(f"{meter_log_prefix} Adding new meter entity")

        # Process invoice entities
        invoice_entities = contract_entities.setdefault(MOGInvoiceSensor, {})
        obsolete_group_codes = (
            invoice_entities.keys() - contract.all_invoices_by_groups.keys()
        )

        for group_code, invoices in contract.all_invoices_by_groups.items():
            invoice_entity: Optional[MOGInvoiceSensor] = invoice_entities.get(
                group_code
            )

            invoice_log_prefix = f"{contract_log_prefix} (invoice|{group_code})"

            if invoice_entity:
                if not invoices:
                    obsolete_group_codes.add(group_code)
                    continue

                invoice_entity.contract = contract
                invoice_entity.invoices = invoices

                if invoice_entity.enabled:
                    _LOGGER.debug(f"{invoice_log_prefix} Updating meter entity")
                    invoice_entity.async_schedule_update_ha_state(force_refresh=True)
                else:
                    _LOGGER.debug(
                        f"{invoice_log_prefix} Not updating disabled meter entity"
                    )

            elif invoices:
                invoice_entity = MOGInvoiceSensor(
                    contract=contract,
                    group_code=group_code,
                    invoices=invoices,
                    name_format=name_format_invoices,
                    default_add=add_invoices,
                    invert_state=invert_invoices,
                )
                new_entities.append(invoice_entity)
                invoice_entities[group_code] = invoice_entity
                tasks.append(invoice_entity.async_update())
                if invert_invoices:
                    _LOGGER.debug(
                        f"{invoice_log_prefix} Adding new inverted invoice entity"
                    )
                else:
                    _LOGGER.debug(f"{invoice_log_prefix} Adding new invoice entity")

        if obsolete_group_codes:
            _LOGGER.debug(
                f"{contract_log_prefix} Removing invoices for "
                f"obsolete groups: {obsolete_group_codes}",
            )
            for group_code in obsolete_group_codes:
                tasks.append(invoice_entities[group_code].async_remove())
                del invoice_entities[group_code]

    # Perform scheduled tasks before other procedures
    if tasks:
        _LOGGER.debug(f"{log_prefix} Performing {len(tasks)} tasks")
        await asyncio.wait(list(map(hass.loop.create_task, tasks)))

    if new_entities:
        _LOGGER.debug(f"{log_prefix} Adding {len(new_entities)} new entities")
        async_add_entities(new_entities)
    else:
        _LOGGER.debug(f"{log_prefix} Not adding new entities")

    return len(new_entities)


async def async_setup_entry(
    hass: HomeAssistantType,
    config_entry: config_entries.ConfigEntry,
    async_add_devices: Callable[[Iterable[Entity]], Any],
):
    """
    Setup configuration entry.
    :param hass:
    :param config_entry:
    :param async_add_devices:
    :return:
    """
    user_cfg = {**config_entry.data}
    username = user_cfg[CONF_USERNAME]

    if config_entry.source == config_entries.SOURCE_IMPORT:
        user_cfg = hass.data[DATA_CONFIG][username]
        options_cfg = user_cfg
    else:
        options_cfg = config_entry.options

    log_prefix = f"(user|{get_print_username(hass, config_entry)})"

    _LOGGER.debug(f'{log_prefix} Setting up entry "{config_entry.entry_id}"')

    update_call = partial(async_account_updater, hass, config_entry, async_add_devices)

    try:
        result = await update_call()

        if result is False:
            _LOGGER.error(f"{log_prefix} Error running updater (see messages above)")
            return False

        if result == 0:
            _LOGGER.warning(
                f"{log_prefix} No contracts or meters discovered, "
                f"check your configuration"
            )
            return True

        config_scan_interval = options_cfg.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        if not isinstance(config_scan_interval, timedelta):
            config_scan_interval = timedelta(seconds=config_scan_interval)

        updater_cancel: Optional[Callable] = None

        async def force_update(
            scan_interval: Optional[timedelta] = None,
        ) -> Union[bool, int]:
            nonlocal updater_cancel
            if updater_cancel:
                updater_cancel()

            try:
                return await update_call(scan_interval or config_scan_interval)
            finally:
                updater_cancel = async_track_time_interval(
                    hass, update_call, config_scan_interval
                )
                hass.data.setdefault(DATA_UPDATERS, {})[config_entry.entry_id] = (
                    updater_cancel,
                    force_update,
                )

        await force_update()

        _LOGGER.info(
            f"{log_prefix} Will update account every "
            f"{config_scan_interval.total_seconds()} seconds",
        )
        return True

    except MosoblgazException as exc:
        raise PlatformNotReady(f"Critical error occurred: {exc}") from None


# noinspection PyUnusedLocal
async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: Callable[[Iterable[Entity]], Any],
    discovery_info=None,
):
    """Set up the sensor platform"""
    return False


class MOGEntity(Entity):
    _attr_should_poll: bool = False
    _attr_attribution: str = ATTRIBUTION

    SENSOR_TYPE = NotImplemented
    UNIQUE_ID_FORMAT = "{sensor_type}_{contract_code}"

    def __init__(
        self,
        contract: "Contract",
        name_format: str | None = None,
        default_add: bool = True,
    ):
        self.contract = contract

        self._name_format: str | None = name_format
        self._attr_entity_registry_enabled_default: bool = default_add

        self._attr_state: Optional[Union[float, int, str]] = None

    @property
    def contract_id(self):
        return self.contract.contract_id

    @property
    def extra_state_attributes(self):
        """Return the attribute(s) of the sensor"""
        return {
            **self.base_attributes,
            **(self._attr_extra_state_attributes or {}),
        }

    @property
    def base_attributes(self):
        return {
            ATTR_CONTRACT_CODE: self.contract.contract_id,
        }

    @property
    def name_placeholders(self) -> Mapping[str, str]:
        return {
            "sensor_type": self.SENSOR_TYPE,
            "contract_code": self.contract_id,
        }

    @property
    def name(self):
        """Return the name of the sensor"""
        try:
            return self._name_format.format(**self.name_placeholders)
        except KeyError:
            return self._name_format

    @property
    def unique_id(self) -> str | None:
        try:
            return self.UNIQUE_ID_FORMAT.format(**self.name_placeholders)
        except KeyError:
            return self._name_format

    async def async_update_bound_account(self) -> None:
        registry_entry = self.registry_entry
        if not registry_entry:
            raise Exception("registry entry not found")

        config_entry_id = registry_entry.config_entry_id
        if not config_entry_id:
            raise Exception("config entry not found")

        try:
            update_cancel, restart_call = self.hass.data[DATA_UPDATERS][config_entry_id]
        except KeyError:
            raise Exception("updater not found")

        return await restart_call()


class MOGContractSensor(MOGEntity):
    """The class for this sensor"""

    _attr_icon: str = "mdi:file-document-edit"
    _attr_device_class: SensorDeviceClass = SensorDeviceClass.MONETARY
    _attr_unit_of_measurement: str = RUB_CURRENCY

    def __init__(
        self,
        contract: Contract,
        name_format: str,
        default_add: bool = DEFAULT_ADD_CONTRACTS,
    ):
        super().__init__(
            contract=contract,
            name_format=name_format,
            default_add=default_add,
        )

    async def async_update(self):
        """The update method"""
        contract = self.contract

        self._attr_state = self.contract.balance
        self._attr_extra_state_attributes = {
            ATTR_CONTRACT_CODE: contract.contract_id,
            ATTR_ADDRESS: contract.address,
            ATTR_PERSON: contract.person,
            ATTR_DEPARTMENT: contract.department_title,
        }

    @property
    def unique_id(self):
        """Return the unique ID of the sensor"""
        return "ls_" + str(self.contract.contract_id)

    @property
    def name_placeholders(self) -> Mapping[str, str]:
        return {
            **super().name_placeholders,
            "department": self.contract.department_title,
        }


class MOGMeterSensor(MOGEntity):
    """The class for this sensor"""

    _attr_ico: str = "mdi:counter"
    _attr_unit_of_measurement: str = UnitOfVolume.CUBIC_METERS
    _attr_device_class: SensorDeviceClass = SensorDeviceClass.GAS
    _attr_supported_features: int = FEATURE_PUSH_INDICATIONS

    SENSOR_TYPE = "meter"
    UNIQUE_ID_FORMAT = "{sensor_type}_{meter_code}"

    def __init__(
        self,
        contract: Contract,
        name_format: str,
        meter: "Meter",
        default_add: bool = DEFAULT_ADD_METERS,
    ):
        super().__init__(
            contract=contract,
            name_format=name_format,
            default_add=default_add,
        )

        self.meter = meter

    async def async_added_to_hass(self) -> None:
        self.platform.async_register_entity_service(
            SERVICE_PUSH_INDICATIONS,
            SERVICE_PUSH_INDICATIONS_SCHEMA,
            "async_service_" + SERVICE_PUSH_INDICATIONS,
            (FEATURE_PUSH_INDICATIONS,),
        )

    async def async_update(self):
        """The update method"""
        history_entry = self.meter.last_history_entry

        self._attr_state = history_entry.value if history_entry else 0
        extra_state_attributes = (
            {
                ATTR_COLLECTED_AT: history_entry.collected_at.isoformat(),
                ATTR_LAST_VALUE: history_entry.value,
                ATTR_LAST_COST: history_entry.cost,
                ATTR_LAST_CHARGED: history_entry.charged,
                ATTR_PREVIOUS_VALUE: history_entry.previous_value,
            }
            if history_entry
            else dict.fromkeys(
                (
                    ATTR_COLLECTED_AT,
                    ATTR_LAST_VALUE,
                    ATTR_LAST_COST,
                    ATTR_LAST_CHARGED,
                    ATTR_PREVIOUS_VALUE,
                ),
                None,
            )
        )
        extra_state_attributes[ATTR_STATE_CLASS] = SensorStateClass.TOTAL_INCREASING

        self._attr_extra_state_attributes = extra_state_attributes

    @property
    def base_attributes(self):
        return {
            **super().base_attributes,
            ATTR_METER_CODE: self.meter.device_id,
            ATTR_SERIAL: self.meter.serial,
        }

    @property
    def name_placeholders(self) -> Mapping[str, str]:
        return {
            **super().name_placeholders,
            "meter_code": self.meter.device_id,
            "device_code": self.meter.device_id,
            "device_id": self.meter.device_id,
            "meter_id": self.meter.device_id,
        }

    def _fire_callback_event(
        self,
        call_data: Mapping[str, Any],
        event_data: Mapping[str, Any],
        event_id: str,
    ) -> None:
        hass = self.hass
        comment = event_data.get(ATTR_COMMENT)

        if comment is not None:
            message = str(comment)
            comment = "Response comment: " + str(comment)
        else:
            comment = "Response comment not provided"
            message = comment

        _LOGGER.log(
            logging.INFO if event_data.get(ATTR_SUCCESS) else logging.ERROR,
            comment,
        )

        meter_code = self.meter.device_id

        event_data = {
            ATTR_ENTITY_ID: self.entity_id,
            ATTR_METER_CODE: meter_code,
            ATTR_CALL_PARAMS: dict(call_data),
            ATTR_SUCCESS: False,
            ATTR_INDICATIONS: None,
            ATTR_COMMENT: message,
            **event_data,
        }

        _LOGGER.debug(f"Firing {event_id} with fields: {event_data}")

        hass.bus.async_fire(event_type=event_id, event_data=event_data)

    @staticmethod
    def _get_real_indications(
        meter: Meter, call_data: Mapping
    ) -> Mapping[str, Union[int, float]]:
        indications: dict[str, Union[int, float]] = dict(call_data[ATTR_INDICATIONS])
        is_incremental = call_data[ATTR_INCREMENTAL]

        try:
            new_indication = int(indications["t1"])
        except KeyError:
            if indications:
                raise ValueError("single (first, 't1') zone is supported")
            else:
                # @TODO: redundant?
                raise ValueError("no zones provided")

        if "t1" not in indications and len(indications) > 1:
            raise ValueError("single zone is supported")

        if is_incremental:
            history_entry = meter.last_history_entry
            new_indication += history_entry.value if history_entry else 0

        indications["t1"] = new_indication

        return indications

    async def async_service_push_indications(self, **call_data):
        """
        Push indications entity service.
        :param call_data: Parameters for service call
        :return:
        """
        _LOGGER.info(f"{self} Begin handling indications submission")

        meter = self.meter

        if meter is None:
            raise Exception("Meter is unavailable")

        event_data = {}

        try:
            indications = self._get_real_indications(meter, call_data)

            event_data[ATTR_INDICATIONS] = dict(
                indications
            )  # compatibility with common

            new_indication = indications["t1"]
            event_data[ATTR_INDICATION] = new_indication  # integration-specific

            await meter.push_indication(
                new_indication,
                ignore_values=call_data[ATTR_IGNORE_INDICATIONS],
            )

        except MosoblgazException as exc:
            event_data[ATTR_COMMENT] = f"API error: {exc}"
            raise

        except BaseException as exc:
            event_data[ATTR_COMMENT] = f"Unknown error: {exc}"
            _LOGGER.error(event_data[ATTR_COMMENT], exc_info=exc)
            raise

        else:
            event_data[ATTR_COMMENT] = "Indications submitted successfully"
            event_data[ATTR_SUCCESS] = True

            # @TODO: this looks weird, but this is how the component was made
            await self.async_update_bound_account()
            self.async_schedule_update_ha_state(force_refresh=True)

        finally:
            self._fire_callback_event(
                call_data,
                event_data,
                DOMAIN + "_" + SERVICE_PUSH_INDICATIONS,
            )

            _LOGGER.info("End handling indications submission")

    async def async_service_remove_last_indication(self, **call_data):
        pass


class MOGInvoiceSensor(MOGEntity):
    _attr_icon: str = "mdi:receipt"
    _attr_unit_of_measurement: str = RUB_CURRENCY
    _attr_device_class: SensorDeviceClass = SensorDeviceClass.MONETARY

    SENSOR_TYPE = "invoice"
    UNIQUE_ID_FORMAT = "{sensor_type}_{contract_code}_{group_code}"

    FRIENDLY_GROUP_NAMES = {
        INVOICE_GROUP_VDGO: "VDGO",
    }
    GROUP_ICONS = {
        INVOICE_GROUP_VDGO: "mdi:progress-wrench",
        INVOICE_GROUP_TECH: "mdi:pipe-wrench",
        INVOICE_GROUP_GAS: "mdi:stove",
    }

    def __init__(
        self,
        contract: Contract,
        name_format: str,
        group_code: str,
        invoices: dict[tuple[int, int], "Invoice"],
        invert_state: bool = False,
        default_add: bool = DEFAULT_ADD_INVOICES,
    ):
        super().__init__(
            contract=contract,
            name_format=name_format,
            default_add=default_add,
        )

        self.group_code = group_code
        self._invert_state = invert_state
        self.invoices = invoices
        self._attr_extra_state_attributes = dict.fromkeys(
            (
                ATTR_PERIOD,
                ATTR_TOTAL,
                ATTR_PAID,
                ATTR_BALANCE,
                ATTR_PAYMENTS_COUNT,
                ATTR_PREVIOUS_PERIOD,
                ATTR_PREVIOUS_TOTAL,
                ATTR_PREVIOUS_PAID,
                ATTR_PREVIOUS_BALANCE,
                ATTR_PREVIOUS_PAYMENTS_COUNT,
            )
        )

    @property
    def invoices(self) -> list["Invoice"]:
        return self._invoices

    @invoices.setter
    def invoices(self, value: dict[tuple[int, int], "Invoice"]):
        self._invoices = list(
            sorted(value.values(), key=lambda x: x.period, reverse=True)
        )

    @property
    def last_invoice(self) -> Optional["Invoice"]:
        if len(self._invoices) > 0:
            return self._invoices[0]

    @property
    def previous_invoice(self) -> Optional["Invoice"]:
        if len(self._invoices) > 1:
            return self._invoices[1]

    @property
    def base_attributes(self):
        return {
            **super().base_attributes,
            ATTR_INVOICE_GROUP: self.group_code,
        }

    async def async_update(self):
        """The update method"""
        attributes = self._attr_extra_state_attributes

        if len(self._invoices) > 0:
            last_invoice = self._invoices[0]

            attributes[ATTR_PERIOD] = last_invoice.period.isoformat()
            attributes[ATTR_TOTAL] = last_invoice.total
            attributes[ATTR_PAID] = last_invoice.paid
            attributes[ATTR_BALANCE] = last_invoice.balance
            attributes[ATTR_PAYMENTS_COUNT] = last_invoice.payments_count

            # Update state
            state_value = last_invoice.paid + last_invoice.balance - last_invoice.total
            if self._invert_state:
                state_value *= -1

            state_value = round(state_value, 2)

            if state_value == 0:
                # while this looks weird, it gets rid of a useless negative sign
                state_value = 0.0

            self._attr_state = state_value

            # Update previous invoice, if available
            previous_invoice = self.previous_invoice

            if previous_invoice:
                attributes[ATTR_PREVIOUS_PERIOD] = previous_invoice.period.isoformat()
                attributes[ATTR_PREVIOUS_TOTAL] = previous_invoice.total
                attributes[ATTR_PREVIOUS_PAID] = previous_invoice.paid
                attributes[ATTR_PREVIOUS_BALANCE] = previous_invoice.balance
                attributes[ATTR_PREVIOUS_PAYMENTS_COUNT] = (
                    previous_invoice.payments_count
                )

    @property
    def icon(self) -> str | None:
        return self.GROUP_ICONS.get(self.group_code, super().icon)

    @property
    def name_placeholders(self) -> Mapping[str, str]:
        group_code = self.group_code
        group_name = self.FRIENDLY_GROUP_NAMES.get(group_code)
        if group_name is None:
            group_name = group_code.replace("_", " ").capitalize()

        return {
            **super().name_placeholders,
            "group": group_name,
            "group_name": group_name,
            "group_code": group_code,
            "group_id": group_code,
        }
