"""
Sensor for Mosoblgaz cabinet.
Retrieves values regarding current state of contracts.
"""

from abc import ABC
import asyncio
from datetime import date
import logging
from typing import Any, Generic, Mapping, TypeVar, Union, final

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import VolSchemaType
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_MODEL, EntityCategory, UnitOfVolume
from homeassistant.core import HomeAssistant, SupportsResponse

from custom_components.mosoblgaz import (
    MosoblgazCoordinatorEntity,
    MosoblgazUpdateCoordinator,
    ConfigEntryLoggerAdapter,
)
from custom_components.mosoblgaz.api import (
    Contract,
    INVOICE_GROUP_GAS,
    INVOICE_GROUP_TECH,
    INVOICE_GROUP_VDGO,
    Device,
    Meter,
    MosoblgazException,
)
from custom_components.mosoblgaz.const import *

_LOGGER: logging.Logger = logging.getLogger(__name__)

INDICATIONS_MAPPING_SCHEMA: Final[VolSchemaType] = vol.Schema(
    {
        vol.Required(vol.Match(r"t\d+")): cv.positive_float,
    }
)

INDICATIONS_SEQUENCE_SCHEMA: Final[VolSchemaType] = vol.All(
    vol.Any(vol.All(cv.positive_float, cv.ensure_list), [cv.positive_float]),
    lambda x: dict(map(lambda y: ("t" + str(y[0]), y[1]), enumerate(x, start=1))),
)

SERVICE_PUSH_INDICATIONS: Final[str] = "push_indications"
SERVICE_PUSH_INDICATIONS_SCHEMA: Final[VolSchemaType] = cv.make_entity_service_schema(
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
        vol.Optional(ATTR_RETURN_ON_ERROR, default=False): cv.boolean,
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """
    Setup configuration entry.
    :param hass:
    :param config_entry:
    :param async_add_devices:
    :return:
    """
    logger = ConfigEntryLoggerAdapter(config_entry=config_entry)
    logger.debug("Setting up sensor platform entry")

    coordinator: MosoblgazUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    new_entities = []
    new_group_codes = set()
    known_group_codes = set(MosoblgazInvoiceSensor.GROUP_ICONS)

    # Iterate over fetched contracts
    for contract in coordinator.data.values():
        # Add contract sensor
        new_entities.append(MosoblgazContractSensor(coordinator, contract))

        for meter in contract.meters.values():
            new_entities.append(MosoblgazMeterSensor(coordinator, meter))

        for  device in contract.devices.values():
            if device.is_archived:
                continue
            if not device.is_active:
                continue
            new_entities.append(MosoblgazDeviceEOLSensor(coordinator, device))

        fetched_group_codes = contract.all_invoices_by_groups.keys()
        new_group_codes.update(fetched_group_codes - known_group_codes)

        for group_code in known_group_codes.union(fetched_group_codes):
            new_entities.append(
                MosoblgazInvoiceSensor(coordinator, contract, group_code)
            )

    if new_entities:
        logger.info("Adding %d entities for sensor platform", len(new_entities))
        async_add_entities(new_entities)
    else:
        logger.info("No new entities for sensor platform")

    return True


class MosoblgazBaseSensor(MosoblgazCoordinatorEntity, SensorEntity, ABC):
    def __init__(
        self,
        coordinator: MosoblgazUpdateCoordinator,
        contract: Contract,
    ) -> None:
        self.contract: Contract = contract
        super().__init__(coordinator)

        # Set initial attributes
        attrs = {ATTR_CONTRACT_CODE: contract.contract_id}
        self._attr_extra_state_attributes = attrs
        self._attr_device_info = DeviceInfo(
            manufacturer="Mosoblgaz",
            serial_number=contract.contract_id,
            model=contract.address,
            translation_key="contract",
            translation_placeholders={"contract_code": contract.contract_id},
            identifiers={(DOMAIN, "contract_{}".format(contract.contract_id))},
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        # Since our platform refreshes first,
        # apply data to entities on launch
        # @TODO: check for FOUCs
        self._handle_coordinator_update()

    def _handle_contract_update(self) -> None:
        """Handle when contract data is updated"""

    def _handle_contract_missing(self) -> None:
        """Handle when contract data is missing"""

    @final
    def _handle_coordinator_update(self):
        """Handle contract data retrieval"""
        try:
            self.contract = self.coordinator.data[self.contract.contract_id]
        except KeyError:
            self.logger.debug(
                "Entity %s has no contract to update with", self.entity_id
            )
            self._attr_available = False
            self._handle_contract_missing()
        else:
            self.logger.debug(
                "Entity %s updates with matching contract", self.entity_id
            )
            self._attr_available = True
            self._handle_contract_update()
        # Run coordinator update from the Home Assistantclass
        return super()._handle_coordinator_update()


class MosoblgazContractSensor(MosoblgazBaseSensor):
    """The class for this sensor"""

    _attr_icon: str = "mdi:file-document-edit"
    _attr_device_class: SensorDeviceClass = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement: str = RUB_CURRENCY
    _attr_translation_key: str = "contract"
    _attr_suggested_display_precision: int = 2

    def __init__(self, coordinator: MosoblgazUpdateCoordinator, contract: Contract):
        super().__init__(coordinator, contract)

        # Set initial attributes
        self._attr_unique_id = "contract_{}".format(contract.contract_id)
        self._attr_native_value = 0.0

    def _handle_contract_update(self):
        self._attr_native_value = self.contract.balance
        self._attr_extra_state_attributes.update(
            {
                ATTR_ADDRESS: self.contract.address,
                ATTR_PERSON: self.contract.person,
                ATTR_DEPARTMENT: self.contract.department_title,
            }
        )


_TDevice = TypeVar("_TDevice", bound=Device)


class MosoblgazBaseDeviceSensor(MosoblgazBaseSensor, Generic[_TDevice]):
    def __init__(self, coordinator, device: _TDevice):
        self.device: _TDevice = device
        super().__init__(coordinator, device.contract)

        # Set initial attributes
        self._attr_device_info = DeviceInfo(
            translation_key="device",
            translation_placeholders={ATTR_MODEL: device.model},
            model=device.model,
            manufacturer=device.manufacturer,
            model_id=device.device_class_code,
            serial_number=device.serial,
            identifiers={(DOMAIN, "device_{}".format(device.device_id))},
            via_device=(DOMAIN, "contract_{}".format(device.contract.contract_id)),
        )

    def _handle_device_update(self):
        """Handle when device data is updated"""

    def _handle_device_missing(self):
        """Handle when device data is missing"""

    @final
    def _handle_contract_update(self):
        """Handle contract data retrieval"""
        try:
            self.device = self.contract.devices[self.device.device_id]
        except KeyError:
            self.logger.debug("Entity %s has no device to update with", self.entity_id)
            self._attr_available = False
            self._handle_device_missing()
        else:
            self.logger.debug("Entity %s updates with matching device", self.entity_id)
            self._attr_available = True
            self._handle_device_update()


class MosoblgazMeterSensor(MosoblgazBaseDeviceSensor[Meter]):
    """The class for this sensor"""

    _attr_icon: str = "mdi:counter"
    _attr_native_unit_of_measurement: str = UnitOfVolume.CUBIC_METERS
    _attr_device_class: SensorDeviceClass = SensorDeviceClass.GAS
    _attr_supported_features: int = FEATURE_PUSH_INDICATIONS
    _attr_state_class: str = SensorStateClass.TOTAL_INCREASING
    _attr_native_value: int | float = 0
    _attr_translation_key: str = "meter"
    _attr_suggested_display_precision: int = 0

    def __init__(self, coordinator, device: Meter):
        super().__init__(coordinator, device)

        # Set initial attributes
        self._attr_unique_id = "meter_{}".format(device.device_id)
        self._attr_extra_state_attributes.update(
            {
                ATTR_METER_CODE: self.device.device_id,
                ATTR_SERIAL: self.device.serial,
            }
        )
        # Reset extra attributes
        self._set_initial_state()

    def _set_initial_state(self):
        self._attr_native_value = 0
        for key in (
            ATTR_COLLECTED_AT,
            ATTR_LAST_VALUE,
            ATTR_LAST_COST,
            ATTR_LAST_CHARGED,
            ATTR_PREVIOUS_VALUE,
        ):
            self._attr_extra_state_attributes[key] = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.platform.async_register_entity_service(
            SERVICE_PUSH_INDICATIONS,
            SERVICE_PUSH_INDICATIONS_SCHEMA,
            "async_service_" + SERVICE_PUSH_INDICATIONS,
            (FEATURE_PUSH_INDICATIONS,),
            supports_response=SupportsResponse.OPTIONAL,
        )

    def _handle_device_update(self):
        """Extrapolate data for meter"""
        if history_entry := self.device.last_history_entry:
            self._attr_native_value = history_entry.value
            self._attr_extra_state_attributes.update(
                {
                    ATTR_COLLECTED_AT: history_entry.collected_at.isoformat(),
                    ATTR_LAST_VALUE: history_entry.value,
                    ATTR_LAST_COST: history_entry.cost,
                    ATTR_LAST_CHARGED: history_entry.charged,
                    ATTR_PREVIOUS_VALUE: history_entry.previous_value,
                }
            )
        else:
            self._set_initial_state()

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

        meter = self.device

        if meter is None:
            raise Exception("Meter is unavailable")

        event_data = {
            ATTR_SUCCESS: False,
            ATTR_ENTITY_ID: self.entity_id,
            ATTR_METER_CODE: self.device.device_id,
            ATTR_SERIAL: self.device.serial,
            ATTR_CALL_PARAMS: dict(call_data),
            ATTR_SUCCESS: False,
            ATTR_INDICATIONS: None,
            ATTR_COMMENT: "Response comment not provided",
        }

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
            if not call_data.get(ATTR_RETURN_ON_ERROR):
                raise

        except BaseException as exc:
            event_data[ATTR_COMMENT] = f"Unknown error: {exc}"
            _LOGGER.error(event_data[ATTR_COMMENT], exc_info=exc)
            if not call_data.get(ATTR_RETURN_ON_ERROR):
                raise

        else:
            event_data[ATTR_COMMENT] = "Indications submitted successfully"
            event_data[ATTR_SUCCESS] = True

        finally:
            # Deprecated, will be removed in 2025.7.0
            self.hass.bus.async_fire(
                event_type=DOMAIN + "_" + SERVICE_PUSH_INDICATIONS,
                event_data=event_data,
            )

            _LOGGER.info("End handling indications submission")

        try:
            await self.coordinator.async_request_refresh()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self.logger.warning(
                "Error occurred after attempting to schedule update: %s", exc
            )

        return event_data

    async def async_service_remove_last_indication(self, **call_data):
        pass


class MosoblgazDeviceEOLSensor(MosoblgazBaseDeviceSensor[Device]):
    _attr_icon: str = "mdi:calendar-blank"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "device_eol"

    def __init__(self, coordinator, device: Device):
        super().__init__(coordinator, device)

        # Set initial attributes
        self._attr_unique_id = "device_eol_{}".format(device.device_id)
        self._attr_extra_state_attributes.update(
            {
                ATTR_DEVICE_CODE: device.device_id,
                ATTR_CLASS_NAME: device.device_class,
            }
        )

    def _handle_device_update(self):
        eol_date = self.device.end_of_life_date
        self._attr_native_value = eol_date
        self._attr_icon = (
            "mdi:calendar-blank"
            if eol_date is None
            else (
                "mdi:calendar-alert"
                if eol_date <= date.today()
                else "mdi:calendar-check"
            )
        )


class MosoblgazInvoiceSensor(MosoblgazBaseSensor):
    _attr_icon: str = "mdi:receipt"
    _attr_native_unit_of_measurement = RUB_CURRENCY
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_translation_key = "invoice"
    _attr_suggested_display_precision = 2

    GROUP_ICONS = {
        INVOICE_GROUP_VDGO: "mdi:progress-wrench",
        INVOICE_GROUP_TECH: "mdi:pipe-wrench",
        INVOICE_GROUP_GAS: "mdi:stove",
    }

    def __init__(
        self,
        coordinator: MosoblgazCoordinatorEntity,
        contract: Contract,
        group_code: str,
    ):
        super().__init__(coordinator, contract)
        self._group_code = group_code

        # Set initial attributes
        self._attr_unique_id = "invoice_{}_{}".format(contract.contract_id, group_code)
        self._attr_extra_state_attributes[ATTR_INVOICE_GROUP] = group_code
        self._attr_icon = self.GROUP_ICONS.get(group_code, self._attr_icon)
        if group_code in self.GROUP_ICONS:
            self._attr_translation_key = "invoice_{}".format(group_code)
        else:
            self._attr_translation_placeholders = {"group_code": group_code}

        # Reset extra attributes
        self._set_initial_state()

    @property
    def group_code(self) -> str:
        return self._group_code

    def _set_initial_state(self):
        """Set initial state for the entity's extra_state_attributes"""
        self._attr_native_value = 0.0
        for key in (
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
        ):
            self._attr_extra_state_attributes[key] = None

    def _handle_contract_update(self):
        """The update method"""
        attributes = self._attr_extra_state_attributes

        try:
            invoices_map = self.contract.all_invoices_by_groups[self.group_code]
        except KeyError:
            self._attr_available = False
            return

        if not invoices_map:
            self._set_initial_state()
            return

        sorted_invoices = sorted(
            invoices_map.values(), key=lambda x: x.period, reverse=True
        )

        # @TODO: convert this to programmatic evaluation
        last_invoice = sorted_invoices[0]
        attributes[ATTR_PERIOD] = last_invoice.period.isoformat()
        attributes[ATTR_TOTAL] = last_invoice.total
        attributes[ATTR_PAID] = last_invoice.paid
        attributes[ATTR_BALANCE] = last_invoice.balance
        attributes[ATTR_PAYMENTS_COUNT] = last_invoice.payments_count

        # Update state
        state_value = last_invoice.paid + last_invoice.balance - last_invoice.total
        if self.coordinator.should_invert_invoices:
            state_value *= -1

        if state_value == 0:
            # while this looks weird, it gets rid of a useless negative sign
            state_value = 0.0

        self._attr_native_value = state_value

        # Update previous invoice, if available
        if len(sorted_invoices) == 1:
            return

        previous_invoice = sorted_invoices[1]
        attributes[ATTR_PREVIOUS_PERIOD] = previous_invoice.period.isoformat()
        attributes[ATTR_PREVIOUS_TOTAL] = previous_invoice.total
        attributes[ATTR_PREVIOUS_PAID] = previous_invoice.paid
        attributes[ATTR_PREVIOUS_BALANCE] = previous_invoice.balance
        attributes[ATTR_PREVIOUS_PAYMENTS_COUNT] = previous_invoice.payments_count
