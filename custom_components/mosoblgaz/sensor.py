"""
Sensor for Mosoblgaz cabinet.
Retrieves values regarding current state of contracts.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Dict, Optional, Tuple, Union, List, Any, Mapping, Type, Callable, Iterable

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_USERNAME, CONF_SCAN_INTERVAL, ATTR_ATTRIBUTION
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import HomeAssistantType, ConfigType

from . import privacy_formatter, get_print_username, is_privacy_logging_enabled
from .const import *
from .mosoblgaz import MosoblgazAPI, MosoblgazException, Meter, Invoice, Contract, PartialOfflineException, \
    INVOICE_GROUP_VDGO, INVOICE_GROUP_TECH, INVOICE_GROUP_GAS

_LOGGER = logging.getLogger(__name__)


INDICATIONS_SCHEMA = vol.Any(
    {vol.All(int, vol.Range(1, DEFAULT_MAX_INDICATIONS)): cv.positive_int},
    vol.All([cv.positive_int], vol.Length(1, DEFAULT_MAX_INDICATIONS))
)


def get_should_add_entities(
    contract_id: str,
    default_add_contracts: Union[bool, Mapping[str, Any]] = DEFAULT_ADD_CONTRACTS,
    default_add_meters: bool = DEFAULT_ADD_METERS,
    default_add_invoices: bool = DEFAULT_ADD_INVOICES
) -> Tuple[bool, bool, bool]:
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
                    contract_conf(CONF_INVOICES, default_add_invoices)
                )

    return default_add_contracts, default_add_meters, default_add_invoices


async def async_account_updater(
    hass: HomeAssistantType,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: Callable[[Iterable[Entity]], Any],
    now: Optional[datetime] = None
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
    log_prefix = f'(user|{get_print_username(hass, config_entry, privacy_logging=privacy_logging_enabled)})'

    _LOGGER.debug('%s Running updater at %s', log_prefix, now or datetime.now())
    api: 'MosoblgazAPI' = hass.data.get(DATA_API_OBJECTS, {}).get(entry_id)

    if not api:
        _LOGGER.debug('%s Updater found no API object', log_prefix)
        return False

    try:
        # Contract fetching phase
        contracts = await api.fetch_contracts(with_data=True)

    except PartialOfflineException:
        _LOGGER.error('%s Partial offline, will delay entity update', log_prefix)
        return False

    except MosoblgazException as e:
        _LOGGER.error('%s Error fetching contracts: %s', log_prefix, e)
        return False

    # Do not process contracts if none received
    # Return zero new entities
    if not contracts:
        _LOGGER.info('%s Did not receive any contract data', log_prefix)
        return 0

    # Entity adding defaults
    if config_entry.source == SOURCE_IMPORT:
        default_add_meters = user_cfg.get(CONF_METERS, DEFAULT_ADD_METERS)
        default_add_invoices = user_cfg.get(CONF_INVOICES, DEFAULT_ADD_INVOICES)
        default_add_contracts = user_cfg.get(CONF_CONTRACTS, DEFAULT_ADD_CONTRACTS)

        name_format_meters = user_cfg.get(CONF_METER_NAME, DEFAULT_METER_NAME_FORMAT)
        name_format_invoices = user_cfg.get(CONF_INVOICE_NAME, DEFAULT_INVOICE_NAME_FORMAT)
        name_format_contracts = user_cfg.get(CONF_CONTRACT_NAME, DEFAULT_CONTRACT_NAME_FORMAT)
    else:
        default_add_meters, default_add_invoices, default_add_contracts =\
            DEFAULT_ADD_METERS, DEFAULT_ADD_INVOICES, DEFAULT_ADD_CONTRACTS
        name_format_meters, name_format_invoices, name_format_contracts =\
            DEFAULT_METER_NAME_FORMAT, DEFAULT_INVOICE_NAME_FORMAT, DEFAULT_CONTRACT_NAME_FORMAT

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
            tasks.extend(map(lambda x: x.async_remove(), contract_entities[MOGMeterSensor]))
            del contract_entities[MOGMeterSensor]

        if MOGInvoiceSensor in contract_entities:
            tasks.extend(map(lambda x: x.async_remove(), contract_entities[MOGInvoiceSensor]))
            del contract_entities[MOGInvoiceSensor]

        del entry_entities[contract_id]

    # Iterate over fetched contracts
    for contract_id, contract in contracts.items():
        # Setup logging prefix for contract during processing
        print_contract_id = contract_id
        if privacy_logging_enabled:
            print_contract_id = privacy_formatter(print_contract_id)

        contract_log_prefix = log_prefix + f' (contract|{print_contract_id})'

        # Prepare entities holder
        if contract_id in entry_entities:
            _LOGGER.debug('%s Refreshing entity data', contract_log_prefix)
            contract_entities = entry_entities[contract_id]
        else:
            contract_entities = {}
            entry_entities[contract_id] = contract_entities
            _LOGGER.debug('%s Setting up new entities', contract_log_prefix)

        contract_entities: Dict[
            Type[MOGEntity],
            Union[
                MOGContractSensor,
                Dict[str, Union[MOGMeterSensor, MOGInvoiceSensor]]
            ]
        ]

        # Get adding parameters
        add_contracts, add_meters, add_invoices = get_should_add_entities(
            contract_id=contract_id,
            default_add_meters=default_add_meters,
            default_add_invoices=default_add_invoices,
            default_add_contracts=default_add_contracts,
        )

        # Process contract entity
        contract_entity: Optional[MOGContractSensor] = contract_entities.get(MOGContractSensor)
        if contract_entity:
            contract_entity.contract = contract

            if contract_entity.enabled:
                _LOGGER.debug('%s Updating contract entity', contract_log_prefix)
                contract_entity.async_schedule_update_ha_state(force_refresh=True)
            else:
                _LOGGER.debug('%s Not updating disabled contract entity', contract_log_prefix)

        else:
            contract_entity = MOGContractSensor(
                contract=contract,
                name_format=name_format_contracts,
                default_add=default_add_contracts,
            )
            new_entities.append(contract_entity)
            contract_entities[MOGContractSensor] = contract_entity
            tasks.append(contract_entity.async_update())
            _LOGGER.debug('%s Creating new contract entity', contract_log_prefix)

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

            meter_log_prefix = contract_log_prefix + f' (meter|{print_meter_id})'

            if meter_entity:
                meter_entity.contract = contract
                meter_entity.meter = meter

                if meter_entity.enabled:
                    _LOGGER.debug('%s Updating meter entity', meter_log_prefix)
                    meter_entity.async_schedule_update_ha_state(force_refresh=True)
                else:
                    _LOGGER.debug('%s Not updating disabled meter entity', meter_log_prefix)
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
                _LOGGER.debug('%s Adding new meter entity', meter_log_prefix)

        # Process invoice entities
        invoice_entities = contract_entities.setdefault(MOGInvoiceSensor, {})
        obsolete_group_codes = invoice_entities.keys() - contract.all_invoices_by_groups.keys()

        for group_code, invoices in contract.all_invoices_by_groups.items():
            invoice_entity: Optional[MOGInvoiceSensor] = invoice_entities.get(group_code)

            invoice_log_prefix = contract_log_prefix + f' (invoice|{group_code})'

            if invoice_entity:
                if not invoices:
                    obsolete_group_codes.add(group_code)
                    continue

                invoice_entity.contract = contract
                invoice_entity.invoices = invoices

                if invoice_entity.enabled:
                    _LOGGER.debug('%s Updating meter entity', invoice_log_prefix)
                    invoice_entity.async_schedule_update_ha_state(force_refresh=True)
                else:
                    _LOGGER.debug('%s Not updating disabled meter entity', invoice_log_prefix)

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
                    _LOGGER.debug('%s Adding new inverted invoice entity', invoice_log_prefix)
                else:
                    _LOGGER.debug('%s Adding new invoice entity', invoice_log_prefix)

        if obsolete_group_codes:
            _LOGGER.debug('%s Removing invoices for obsolete groups: %s', contract_log_prefix, obsolete_group_codes)
            for group_code in obsolete_group_codes:
                tasks.append(invoice_entities[group_code].async_remove())
                del invoice_entities[group_code]

    # Perform scheduled tasks before other procedures
    if tasks:
        _LOGGER.debug('%s Performing %d tasks', log_prefix, len(tasks))
        await asyncio.wait(tasks)

    if new_entities:
        _LOGGER.debug('%s Adding %d new entities', log_prefix, len(new_entities))
        async_add_entities(new_entities)
    else:
        _LOGGER.debug('%s Not adding new entities', log_prefix)

    return len(new_entities)


async def async_setup_entry(
    hass: HomeAssistantType,
    config_entry: config_entries.ConfigEntry,
    async_add_devices: Callable[[Iterable[Entity]], Any]
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

    log_prefix = f'(user|{get_print_username(hass, config_entry)})'

    _LOGGER.debug('%s Setting up entry "%s"', log_prefix, config_entry.entry_id)

    update_call = partial(async_account_updater, hass, config_entry, async_add_devices)

    try:
        result = await update_call()

        if result is False:
            _LOGGER.error('%s Error running updater (see messages above)', log_prefix)
            return False

        if result == 0:
            _LOGGER.warning('%s No contracts or meters discovered, check your configuration', log_prefix)
            return True

        scan_interval = options_cfg.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        if not isinstance(scan_interval, timedelta):
            scan_interval = timedelta(seconds=scan_interval)

        hass.data.setdefault(DATA_UPDATERS, {})[config_entry.entry_id] = \
            async_track_time_interval(hass, update_call, scan_interval)

        _LOGGER.info('%s Will update account every %d seconds', log_prefix, scan_interval.total_seconds())
        return True

    except MosoblgazException as e:
        raise PlatformNotReady('%s Critical error occurred: %s', log_prefix, e) from None


# noinspection PyUnusedLocal
async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: Callable[[Iterable[Entity]], Any],
    discovery_info=None
):
    """Set up the sensor platform"""
    return False


class MOGEntity(Entity):
    SENSOR_TYPE = NotImplemented
    UNIQUE_ID_FORMAT = "{sensor_type}_{contract_code}"

    def __init__(self, contract: 'Contract', icon: Optional[str] = None, name_format: Optional[str] = None,
                 unit: Optional[str] = None, default_add: bool = True):
        self.contract = contract

        self._icon: Optional[str] = icon
        self._unit: Optional[str] = unit
        self._name_format: Optional[str] = name_format
        self._default_add: bool = default_add

        self._attributes: Optional[Dict[str, Union[float, int, str]]] = None
        self._state: Optional[Union[float, int, str]] = None

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._default_add

    @property
    def contract_id(self):
        return self.contract.contract_id

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.

        False if entity pushes its state to HA.
        """
        return False

    @property
    def state(self):
        """Return the state of the sensor"""
        return self._state

    @property
    def device_state_attributes(self):
        """Return the attribute(s) of the sensor"""
        return {
            **self.base_attributes,
            **(self._attributes or {}),
        }

    @property
    def base_attributes(self):
        return {
            ATTR_CONTRACT_CODE: self.contract.contract_id,
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def icon(self):
        return self._icon

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
            return self._name_format.format(
                **self.name_placeholders
            )
        except KeyError:
            return self._name_format

    @property
    def unique_id(self) -> Optional[str]:
        try:
            return self.UNIQUE_ID_FORMAT.format(
                **self.name_placeholders
            )
        except KeyError:
            return self._name_format


class MOGContractSensor(MOGEntity):
    """The class for this sensor"""
    def __init__(self, contract: Contract, name_format: str, default_add: bool = DEFAULT_ADD_CONTRACTS):
        super().__init__(
            contract=contract,
            icon='mdi:file-document-edit',
            name_format=name_format,
            default_add=default_add,
            unit=RUB_CURRENCY,
        )

    async def async_update(self):
        """The update method"""
        contract = self.contract

        self._state = self.contract.balance
        self._attributes = {
            ATTR_CONTRACT_CODE: contract.contract_id,
            ATTR_ADDRESS: contract.address,
            ATTR_PERSON: contract.person,
            ATTR_DEPARTMENT: contract.department_title,
        }

    @property
    def unique_id(self):
        """Return the unique ID of the sensor"""
        return 'ls_' + str(self.contract.contract_id)

    @property
    def name_placeholders(self) -> Mapping[str, str]:
        return {
            **super().name_placeholders,
            "department": self.contract.department_title
        }


class MOGMeterSensor(MOGEntity):
    """The class for this sensor"""
    SENSOR_TYPE = "meter"

    def __init__(self, contract: Contract, name_format: str, meter: 'Meter',
                 default_add: bool = DEFAULT_ADD_METERS):
        super().__init__(
            contract=contract,
            name_format=name_format,
            unit='м\u00B3',
            icon='mdi:counter',
            default_add=default_add,
        )

        self.meter = meter

    async def async_update(self):
        """The update method"""
        history_entry = self.meter.last_history_entry

        self._state = history_entry.new_value if history_entry else 0
        self._attributes = {
            ATTR_COLLECTED_AT: history_entry.collected_at.isoformat() if history_entry else None,
            ATTR_LAST_VALUE: history_entry.new_value if history_entry else None,
            ATTR_LAST_COST: history_entry.cost if history_entry else None,
            ATTR_LAST_CHARGED: history_entry.charged if history_entry else None,
            ATTR_PREVIOUS_VALUE: history_entry.previous_value if history_entry else None,
        }

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


class MOGInvoiceSensor(MOGEntity):
    SENSOR_TYPE = "invoice"

    FRIENDLY_GROUP_NAMES = {
        INVOICE_GROUP_VDGO: 'VDGO',
    }
    GROUP_ICONS = {
        INVOICE_GROUP_VDGO: 'mdi:progress-wrench',
        INVOICE_GROUP_TECH: 'mdi:pipe-wrench',
        INVOICE_GROUP_GAS: 'mdi:stove',
    }

    def __init__(self, contract: Contract, name_format: str, group_code: str,
                 invoices: Dict[Tuple[int, int], 'Invoice'], invert_state: bool = False,
                 default_add: bool = DEFAULT_ADD_INVOICES):
        super().__init__(
            contract=contract,
            name_format=name_format,
            icon='mdi:receipt',
            unit=RUB_CURRENCY,
            default_add=default_add,
        )

        self.group_code = group_code
        self._invert_state = invert_state
        self.invoices = invoices
        self._attributes = dict.fromkeys((
            ATTR_PERIOD, ATTR_TOTAL, ATTR_PAID, ATTR_BALANCE, ATTR_PAYMENTS_COUNT,
            ATTR_PREVIOUS_PERIOD, ATTR_PREVIOUS_TOTAL, ATTR_PREVIOUS_PAID,
            ATTR_PREVIOUS_BALANCE, ATTR_PREVIOUS_PAYMENTS_COUNT,
        ))

    @property
    def invoices(self) -> List['Invoice']:
        return self._invoices

    @invoices.setter
    def invoices(self, value: Dict[Tuple[int, int], 'Invoice']):
        self._invoices = list(sorted(value.values(), key=lambda x: x.period, reverse=True))

    @property
    def last_invoice(self) -> Optional['Invoice']:
        if len(self._invoices) > 0:
            return self._invoices[0]

    @property
    def previous_invoice(self) -> Optional['Invoice']:
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
        attributes = self._attributes
        
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

            self._state = state_value

            # Update previous invoice, if available
            previous_invoice = self.previous_invoice

            if previous_invoice:
                attributes[ATTR_PREVIOUS_PERIOD] = previous_invoice.period.isoformat()
                attributes[ATTR_PREVIOUS_TOTAL] = previous_invoice.total
                attributes[ATTR_PREVIOUS_PAID] = previous_invoice.paid
                attributes[ATTR_PREVIOUS_BALANCE] = previous_invoice.balance
                attributes[ATTR_PREVIOUS_PAYMENTS_COUNT] = previous_invoice.payments_count

    @property
    def icon(self) -> Optional[str]:
        return self.GROUP_ICONS.get(self.group_code, super().icon)

    @property
    def name_placeholders(self) -> Mapping[str, str]:
        group_code = self.group_code
        group_name = self.FRIENDLY_GROUP_NAMES.get(group_code)
        if group_name is None:
            group_name = group_code.replace('_', ' ').capitalize()

        return {
            **super().name_placeholders,
            "group": group_name,
            "group_name": group_name,
            "group_code": group_code,
            "group_id": group_code,
        }
