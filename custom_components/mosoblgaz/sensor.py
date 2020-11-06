"""
Sensor for Mosoblgaz cabinet.
Retrieves values regarding current state of contracts.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Dict, Optional, Tuple, Union, List, Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_SCAN_INTERVAL, ATTR_ATTRIBUTION
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import HomeAssistantType, ConfigType

from . import DATA_CONFIG, CONF_CONTRACTS, DEFAULT_SCAN_INTERVAL, DATA_API_OBJECTS, DATA_ENTITIES, DATA_UPDATERS, \
    DEFAULT_METER_NAME_FORMAT, CONF_METER_NAME, CONF_CONTRACT_NAME, \
    DEFAULT_CONTRACT_NAME_FORMAT, CONF_INVOICES, DEFAULT_INVOICE_NAME_FORMAT, CONF_INVOICE_NAME, CONF_METERS, \
    CONF_INVERT_INVOICES, DEFAULT_ADD_INVOICES, DEFAULT_ADD_METERS, DEFAULT_ADD_CONTRACTS, DEFAULT_PRIVACY_LOGGING, \
    CONF_PRIVACY_LOGGING
from .mosoblgaz import MosoblgazAPI, MosoblgazException, Meter, Invoice, Contract, PartialOfflineException

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Data provided by Mosoblgaz"
RUB_CURRENCY = "руб."

ENTITIES_CONTRACT = 'contract'
ENTITIES_METER_TARIFF = 'meter_tariff'

ATTR_INDICATIONS = "indications"
ATTR_IGNORE_PERIOD = "ignore_period"

ATTR_CONTRACT_CODE = "contract_code"
ATTR_METER_CODE = "meter_code"

ATTR_SERIAL = "serial"

ATTR_ADDRESS = "address"
ATTR_PERSON = "person"
ATTR_DEPARTMENT = "department"

ATTR_COLLECTED_AT = "collected_at"
ATTR_LAST_VALUE = "last_value"
ATTR_LAST_COST = "last_cost"
ATTR_LAST_CHARGED = "last_charged"
ATTR_PREVIOUS_VALUE = "previous_value"

ATTR_INVOICE_GROUP = "invoice_group"
ATTR_PERIOD = "period"
ATTR_TOTAL = "total"
ATTR_PAID = "paid"
ATTR_BALANCE = "balance"
ATTR_PAYMENTS_COUNT = "payments_count"

DEFAULT_MAX_INDICATIONS = 3
INDICATIONS_SCHEMA = vol.Any(
    {vol.All(int, vol.Range(1, DEFAULT_MAX_INDICATIONS)): cv.positive_int},
    vol.All([cv.positive_int], vol.Length(1, DEFAULT_MAX_INDICATIONS))
)


def privacy_formatter(value: Any) -> str:
    str_value = str(value)
    if len(str_value) <= 2:
        return str_value

    suffix = str_value[:-max(2, int(round(0.2, len(str_value))))]
    return '*' * (len(str_value)-len(suffix)) + suffix


async def _entity_updater(hass: HomeAssistantType, entry_id: str, user_cfg: ConfigType, async_add_entities,
                          now: Optional[datetime] = None) -> Union[bool, Tuple[int, int, int]]:
    username = user_cfg[CONF_USERNAME]

    _LOGGER.debug('Running updater for entry %s at %s' % (entry_id, now or datetime.now()))
    api: 'MosoblgazAPI' = hass.data.get(DATA_API_OBJECTS, {}).get(entry_id)

    if not api:
        _LOGGER.debug('Updater for entry %s found no API object' % entry_id)
        return False

    try:
        # Contract fetching phase
        contracts = await api.fetch_contracts(with_data=True)

    except PartialOfflineException:
        _LOGGER.error('Partial offline on username %s, will delay entity update' % username)
        return False

    except MosoblgazException as e:
        _LOGGER.error('Error fetching contracts: %s' % e)
        return False

    use_contracts_filter = user_cfg.get(CONF_CONTRACTS)

    # Fetch custom name formats (or select defaults)
    contract_name_format = user_cfg.get(CONF_CONTRACT_NAME, DEFAULT_CONTRACT_NAME_FORMAT)
    meter_name_format = user_cfg.get(CONF_METER_NAME, DEFAULT_METER_NAME_FORMAT)
    invoice_name_format = user_cfg.get(CONF_INVOICE_NAME, DEFAULT_INVOICE_NAME_FORMAT)

    # Fetch default filter configuration
    default_add_meters = user_cfg.get(CONF_METERS, DEFAULT_ADD_METERS)
    default_add_invoices = user_cfg.get(CONF_INVOICES, DEFAULT_ADD_INVOICES)

    # Privacy logging configuration
    privacy_logging_enabled = user_cfg.get(CONF_PRIVACY_LOGGING, DEFAULT_PRIVACY_LOGGING)

    created_entities = hass.data.setdefault(DATA_ENTITIES, {}).get(entry_id)
    if created_entities is None:
        created_entities = {}
        hass.data[DATA_ENTITIES][entry_id] = created_entities

    new_contracts = {}
    new_meters = {}
    new_invoices = {}

    tasks = []
    for contract_id, contract in contracts.items():
        log_ext = (contract_id, username)
        if privacy_logging_enabled:
            log_ext = tuple(map(privacy_formatter, log_ext))

        add_meters, add_invoices = default_add_meters, default_add_invoices

        if use_contracts_filter:
            contract_conf = user_cfg[CONF_CONTRACTS].get(contract_id, DEFAULT_ADD_CONTRACTS)

            if contract_conf is False:
                _LOGGER.info('Not setting up contract %s on username %s' % log_ext)
                continue
            elif contract_conf is not False:
                add_meters = contract_conf.get(CONF_METERS, add_meters)
                add_invoices = contract_conf.get(CONF_INVOICES, add_invoices)

        _LOGGER.debug('Setting up contract %s on username %s' % log_ext)

        contract_entity = created_entities.get(contract_id)
        if contract_entity is None:
            contract_entity = MOGContractSensor(contract, contract_name_format)
            new_contracts[contract_id] = contract_entity
            tasks.append(contract_entity.async_update())
        else:
            contract_entity.contract = contract
            contract_entity.async_schedule_update_ha_state(force_refresh=True)

        # Process meters
        if add_meters:
            _LOGGER.debug('Will be updating meters for %s on username %s' % (contract_id, username))
            meters = contract.meters

            if contract_entity.meter_entities is None:
                meter_entities = {}
                contract_entity.meter_entities = meter_entities

            else:
                meter_entities = contract_entity.meter_entities

                for meter_id in meter_entities.keys() - meters.keys():
                    tasks.append(hass.async_create_task(meter_entities[meter_id].async_remove()))
                    del meter_entities[meter_id]

            for meter_id, meter in meters.items():
                meter_entity = meter_entities.get(meter_id)

                if meter_entity is None:
                    meter_entity = MOGMeterSensor(meter, meter_name_format)
                    meter_entities[meter_id] = meter_entity
                    new_meters[meter_id] = meter_entity
                    tasks.append(meter_entity.async_update())

                else:
                    meter_entity.meter = meter
                    meter_entity.async_schedule_update_ha_state(force_refresh=True)
        else:
            _LOGGER.debug('Not setting up meters for %s on username %s' % log_ext)

        # Process last and previous invoices
        if add_invoices:
            _LOGGER.debug('Will be updating invoices for %s on username %s' % log_ext)
            invert_invoices = user_cfg[CONF_INVERT_INVOICES]
            for group, invoices in contract.all_invoices_by_groups.items():
                if invoices:
                    if contract_entity.invoice_entities is None:
                        contract_entity.invoice_entities = {}
                        invoice_entity = None
                    else:
                        invoice_entity = contract_entity.invoice_entities.get(group)

                    if invoice_entity:
                        contract_entity.invoice_entities[group].invoices = invoices
                        contract_entity.async_schedule_update_ha_state(force_refresh=True)

                    else:
                        invoice_entity = MOGInvoiceSensor(invoices, invoice_name_format, invert_invoices)
                        new_invoices[(contract.contract_id, group)] = invoice_entity
                        contract_entity.invoice_entities[group] = invoice_entity
                        tasks.append(invoice_entity.async_update())
        else:
            _LOGGER.debug('Not setting up invoices for %s on username %s' % log_ext)

    if tasks:
        await asyncio.wait(tasks)

    if new_contracts:
        async_add_entities(new_contracts.values())

    if new_meters:
        async_add_entities(new_meters.values())

    if new_invoices:
        async_add_entities(new_invoices.values())

    created_entities.update(new_contracts)

    _LOGGER.debug('Successful update on entry %s' % entry_id)
    _LOGGER.debug('New meters: %s' % new_meters)
    _LOGGER.debug('New contracts: %s' % new_contracts)
    _LOGGER.debug('New invoices: %s' % new_invoices)

    return len(new_contracts), len(new_meters), len(new_invoices)


async def async_setup_entry(hass: HomeAssistantType, config_entry: config_entries.ConfigEntry, async_add_devices):
    user_cfg = {**config_entry.data}
    username = user_cfg[CONF_USERNAME]

    _LOGGER.debug('Setting up entry for username "%s" from sensors' % username)

    if config_entry.source == config_entries.SOURCE_IMPORT:
        user_cfg = hass.data[DATA_CONFIG].get(username)
        scan_interval = user_cfg[CONF_SCAN_INTERVAL]

    elif CONF_SCAN_INTERVAL in user_cfg:
        scan_interval = timedelta(seconds=user_cfg[CONF_SCAN_INTERVAL])

    else:
        scan_interval = DEFAULT_SCAN_INTERVAL

    update_call = partial(_entity_updater, hass, config_entry.entry_id, user_cfg, async_add_devices)

    try:
        result = await update_call()

        if result is False:
            return False

        if not sum(result):
            _LOGGER.warning('No contracts or meters discovered, check your configuration')
            return True

        hass.data.setdefault(DATA_UPDATERS, {})[config_entry.entry_id] = \
            async_track_time_interval(hass, update_call, scan_interval)

        new_contracts, new_meters, new_invoices = result

        _LOGGER.info('Set up %d contracts, %d meters and %d invoices, will refresh every %s seconds'
                     % (new_contracts, new_meters, new_invoices, scan_interval.seconds + scan_interval.days*86400))
        return True

    except MosoblgazException as e:
        raise PlatformNotReady('Error while setting up entry "%s": %s' % (config_entry.entry_id, str(e))) from None


async def async_setup_platform(hass: HomeAssistantType, config: ConfigType, async_add_entities,
                               discovery_info=None):
    """Set up the sensor platform"""
    return False


class MOGEntity(Entity):
    def __init__(self):
        self._icon: Optional[str] = None
        self._state: Optional[Union[float, int, str]] = None
        self._unit: Optional[str] = None
        self._attributes: Optional[Dict[str, Union[float, int, str]]] = None

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
        if self._attributes is None:
            return None
        return {**self._attributes, ATTR_ATTRIBUTION: ATTRIBUTION}

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def icon(self):
        return self._icon


class MOGContractSensor(MOGEntity):
    """The class for this sensor"""
    def __init__(self, contract: 'Contract', name_format: str):
        super().__init__()

        self._name_format = name_format
        self._icon = 'mdi:stove'
        self.contract: 'Contract' = contract

        self.meter_entities: Optional[Dict[str, 'MOGMeterSensor']] = None
        self.invoice_entities: Optional[Dict[str, 'MOGInvoiceSensor']] = None

    async def async_update(self):
        """The update method"""
        attributes = {
            ATTR_CONTRACT_CODE: self.contract.contract_id,
            ATTR_ADDRESS: self.contract.address,
            ATTR_PERSON: self.contract.person,
            ATTR_DEPARTMENT: self.contract.department_title,
        }

        self._state = self.contract.balance
        self._unit = RUB_CURRENCY

        self._attributes = attributes
        _LOGGER.debug('Update for contract %s finished' % self)

    @property
    def name(self):
        """Return the name of the sensor"""
        return self._name_format.format(
            code=self.contract.contract_id,
            department=self.contract.department_title
        )

    @property
    def unique_id(self):
        """Return the unique ID of the sensor"""
        return 'ls_' + str(self.contract.contract_id)


class MOGMeterSensor(MOGEntity):
    """The class for this sensor"""
    def __init__(self, meter: 'Meter', name_format: str):
        super().__init__()

        self._icon = 'mdi:counter'
        self._name_format = name_format
        self._unit = 'м\u00B3'
        self.meter = meter

    async def async_update(self):
        """The update method"""
        attributes = {
            ATTR_CONTRACT_CODE: self.meter.contract.contract_id,
            ATTR_METER_CODE: self.meter.device_id,
        }

        if self.meter.serial:
            attributes[ATTR_SERIAL] = self.meter.serial

        meter_status = 0

        history_entry = self.meter.last_history_entry
        if history_entry:
            attributes.update({
                ATTR_COLLECTED_AT: history_entry.collected_at.isoformat(),
                ATTR_LAST_VALUE: history_entry.new_value,
                ATTR_LAST_COST: history_entry.cost,
                ATTR_LAST_CHARGED: history_entry.charged,
                ATTR_PREVIOUS_VALUE: history_entry.previous_value,
            })
            meter_status = history_entry.new_value

        self._state = meter_status
        self._attributes = attributes

        _LOGGER.debug('Update for meter %s finished' % self)

    @property
    def name(self):
        """Return the name of the sensor"""
        return self._name_format.format(code=self.meter.device_id)

    @property
    def unique_id(self):
        """Return the unique ID of the sensor"""
        return 'meter_' + str(self.meter.device_id)


class MOGInvoiceSensor(MOGEntity):
    FRIENDLY_GROUP_NAMES = {
        'vkgo': 'VKGO',
    }

    def __init__(self, invoices: Dict[Tuple[int, int], 'Invoice'],
                 name_format: str, invert_state: bool = False):
        super().__init__()

        self._invert_state = invert_state
        self._icon = 'mdi:receipt'
        self._unit = RUB_CURRENCY
        self._name_format = name_format
        self.invoices = invoices

    @property
    def invoices(self) -> List['Invoice']:
        return self._invoices

    @invoices.setter
    def invoices(self, value: Dict[Tuple[int, int], 'Invoice']):
        self._invoices = list(sorted(value.values(), key=lambda x: x.period, reverse=True))

    @property
    def last_invoice(self) -> 'Invoice':
        return self._invoices[0]

    @property
    def previous_invoice(self):
        if len(self._invoices) > 1:
            return self._invoices[1]

    async def async_update(self):
        """The update method"""
        last_invoice = self.last_invoice
        attributes = {
            ATTR_CONTRACT_CODE: last_invoice.contract.contract_id,
            ATTR_INVOICE_GROUP: last_invoice.group,
        }

        for prefix, invoice in {'': last_invoice, 'previous_': self.previous_invoice}.items():
            if invoice:
                attributes.update({
                    prefix + ATTR_PERIOD: invoice.period.isoformat(),
                    prefix + ATTR_TOTAL: invoice.total,
                    prefix + ATTR_PAID: invoice.paid,
                    prefix + ATTR_BALANCE: invoice.balance,
                    prefix + ATTR_PAYMENTS_COUNT: invoice.payments_count,
                })

        state_value = last_invoice.paid + last_invoice.balance - last_invoice.total
        if self._invert_state:
            state_value *= -1

        state_value = round(state_value, 2)

        if state_value == 0:
            # while this looks weird, it gets rid of a useless negative sign
            state_value = 0.0

        self._state = state_value
        self._attributes = attributes

        _LOGGER.debug('Update for invoice %s finished' % self)

    @property
    def name(self):
        """Return the name of the sensor"""
        last_invoice = self.last_invoice
        group_code = last_invoice.group
        group_name = self.FRIENDLY_GROUP_NAMES.get(group_code)
        if group_name is None:
            group_name = group_code.replace('_', ' ').capitalize()

        return self._name_format.format(
            code=last_invoice.contract.contract_id,
            group=group_name,
            group_code=group_code
        )

    @property
    def unique_id(self):
        """Return the unique ID of the sensor"""
        last_invoice = self.last_invoice
        return 'invoice_' + str(last_invoice.contract.contract_id) + '_' + str(last_invoice.group)
