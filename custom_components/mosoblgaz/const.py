"""Constants for Mosoblgaz module"""
CONF_CONTRACTS = "contracts"
CONF_METER_NAME = "meter_name"
CONF_CONTRACT_NAME = "contract_name"
CONF_METERS = "meters"
CONF_INVOICES = "invoices"
CONF_INVOICE_NAME = "invoice_name"
CONF_INVERT_INVOICES = "invert_invoices"
CONF_PRIVACY_LOGGING = "privacy_logging"

DOMAIN = "mosoblgaz"
DATA_CONFIG = DOMAIN + "_config"
DATA_API_OBJECTS = DOMAIN + "_api_objects"
DATA_ENTITIES = DOMAIN + "_entities"
DATA_UPDATERS = DOMAIN + "_updaters"
DATA_OPTIONS_LISTENERS = DOMAIN + "_options_listeners"

DEFAULT_SCAN_INTERVAL = 60 * 60  # 1 hour
DEFAULT_TIMEOUT = 30  # 30 seconds
DEFAULT_CONTRACT_NAME_FORMAT = "MOG Contract {contract_code}"
DEFAULT_METER_NAME_FORMAT = "MOG Meter {meter_code}"
DEFAULT_INVOICE_NAME_FORMAT = "MOG {group} Invoice {contract_code}"
DEFAULT_INVERT_INVOICES = False
DEFAULT_ADD_INVOICES = True
DEFAULT_ADD_METERS = True
DEFAULT_ADD_CONTRACTS = True
DEFAULT_PRIVACY_LOGGING = False

ATTRIBUTION = "Data provided by Mosoblgaz"
RUB_CURRENCY = "руб."

ENTITIES_CONTRACT = "contract"
ENTITIES_METER_TARIFF = "meter_tariff"

ATTR_INDICATIONS = "indications"
ATTR_IGNORE_PERIOD = "ignore_period"

# Common attributes
ATTR_CONTRACT_CODE = "contract_code"
ATTR_METER_CODE = "meter_code"

# Meter attributes
ATTR_SERIAL = "serial"

# Contract attributes
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

ATTR_PREVIOUS_PERIOD = "previous_period"
ATTR_PREVIOUS_TOTAL = "previous_total"
ATTR_PREVIOUS_PAID = "previous_paid"
ATTR_PREVIOUS_BALANCE = "previous_balance"
ATTR_PREVIOUS_PAYMENTS_COUNT = "previous_payments_count"

DEFAULT_MAX_INDICATIONS = 3
