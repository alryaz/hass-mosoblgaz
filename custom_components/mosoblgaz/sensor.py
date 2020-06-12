"""
Sensor for Mosoblgaz cabinet.
Retrieves values regarding current state of contracts.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Dict, Optional, Tuple, Union, List

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
    DEFAULT_CONTRACT_NAME_FORMAT, CONF_INVOICES, DEFAULT_INVOICE_NAME_FORMAT, CONF_INVOICE_NAME, CONF_METERS
from .mosoblgaz import MosoblgazAPI, MosoblgazException, Meter, Invoice, Contract, PartialOfflineException

_LOGGER = logging.getLogger(__name__)

ENTITIES_CONTRACT = 'contract'
ENTITIES_METER_TARIFF = 'meter_tariff'

ATTR_INDICATIONS = "indications"
ATTR_IGNORE_PERIOD = "ignore_period"

DEFAULT_MAX_INDICATIONS = 3
INDICATIONS_SCHEMA = vol.Any(
    {vol.All(int, vol.Range(1, DEFAULT_MAX_INDICATIONS)): cv.positive_int},
    vol.All([cv.positive_int], vol.Length(1, DEFAULT_MAX_INDICATIONS))
)


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

    use_filter = CONF_CONTRACTS in user_cfg

    # Fetch custom name formats (or select defaults)
    contract_name_format = user_cfg.get(CONF_CONTRACT_NAME, DEFAULT_CONTRACT_NAME_FORMAT)
    meter_name_format = user_cfg.get(CONF_METER_NAME, DEFAULT_METER_NAME_FORMAT)
    invoice_name_format = user_cfg.get(CONF_INVOICE_NAME, DEFAULT_INVOICE_NAME_FORMAT)

    created_entities = hass.data.setdefault(DATA_ENTITIES, {}).get(entry_id)
    if created_entities is None:
        created_entities = {}
        hass.data[DATA_ENTITIES][entry_id] = created_entities

    new_contracts = {}
    new_meters = {}
    new_invoices = {}

    tasks = []
    for contract_id, contract in contracts.items():
        if use_filter and contract_id not in user_cfg[CONF_CONTRACTS].keys():
            _LOGGER.debug('Not setting up contract %s due to configuration exclusion for username %s'
                          % (contract_id, username))
            continue

        _LOGGER.debug('Setting up contract %s for username %s' % (contract_id, username))

        contract_entity = created_entities.get(contract_id)
        if contract_entity is None:
            contract_entity = MOGContractSensor(contract, contract_name_format)
            new_contracts[contract_id] = contract_entity
            tasks.append(contract_entity.async_update())
        else:
            contract_entity.contract = contract
            contract_entity.async_schedule_update_ha_state(force_refresh=True)

        # Process meters
        if not use_filter or user_cfg[CONF_CONTRACTS][contract_id].get(CONF_METERS, True):
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

        # Process last and previous invoices
        if not use_filter or user_cfg[CONF_CONTRACTS][contract_id].get(CONF_INVOICES, True):
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
                        invoice_entity = MOGInvoiceSensor(invoices, invoice_name_format)
                        new_invoices[(contract.contract_id, group)] = invoice_entity
                        contract_entity.invoice_entities[group] = invoice_entity
                        tasks.append(invoice_entity.async_update())

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

ATTRIBUTION = "Data provided by Mosoblgaz"


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
            'contract_code': self.contract.contract_id,
            'address': self.contract.address,
            'person': self.contract.person,
            'department': self.contract.department_title,
        }

        self._state = self.contract.balance
        self._unit = 'руб.'

        self._attributes = attributes
        _LOGGER.debug('Update for contract %s finished' % self)

    @property
    def name(self):
        """Return the name of the sensor"""
        return self._name_format.format(code=self.contract.contract_id, department=self.contract.department_title)

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
            'contract_code': self.meter.contract.contract_id,
            'meter_code': self.meter.device_id,
        }

        if self.meter.serial:
            attributes['serial'] = self.meter.serial

        meter_status = 0

        history_entry = self.meter.last_history_entry
        if history_entry:
            attributes.update({
                'collected_at': history_entry.collected_at.isoformat(),
                'last_value': history_entry.new_value,
                'last_cost': history_entry.cost,
                'last_charged': history_entry.charged,
                'previous_value': history_entry.previous_value,
            })
            meter_status = history_entry.new_value

        self._state = meter_status
        self._attributes = attributes

    @property
    def name(self):
        """Return the name of the sensor"""
        return self._name_format.format(code=self.meter.device_id)

    @property
    def unique_id(self):
        """Return the unique ID of the sensor"""
        return 'meter_' + str(self.meter.device_id)


class MOGInvoiceSensor(MOGEntity):
    def __init__(self, invoices: Dict[Tuple[int, int], 'Invoice'], invoice_group: str, name_format: str):
        super().__init__()

        self._icon = 'mdi:receipt'
        self._unit = 'руб.'
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
            'contract_code': last_invoice.contract.contract_id,
            'invoice_group': last_invoice.group,
        }

        for prefix, invoice in {'': last_invoice, 'previous_': self.previous_invoice}.items():
            if invoice:
                attributes.update({
                    prefix + 'period': invoice.period.isoformat(),
                    prefix + 'total': invoice.total,
                    prefix + 'paid': invoice.paid,
                    prefix + 'balance': invoice.balance,
                    prefix + 'payments_count': invoice.payments_count,
                })

        self._state = round(last_invoice.total - last_invoice.paid, 2)
        self._attributes = attributes

    @property
    def friendly_group_name(self):
        group = self.last_invoice.group
        if group == 'vkgo':
            return 'VKGO'
        return group.capitalize()

    @property
    def contract_id(self):
        return self.last_invoice.contract.contract_id

    @property
    def name(self):
        """Return the name of the sensor"""
        return self._name_format.format(code=self.contract_id, group=self.friendly_group_name)

    @property
    def unique_id(self):
        """Return the unique ID of the sensor"""
        return 'invoice_' + str(self.contract_id)
