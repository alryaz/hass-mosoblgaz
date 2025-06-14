"""Constants for Mosoblgaz module"""

from typing import Final

CONF_GRAPHQL_TOKEN: Final = "graphql_token"
CONF_CONTRACTS: Final = "contracts"
CONF_METER_NAME: Final = "meter_name"
CONF_CONTRACT_NAME: Final = "contract_name"
CONF_METERS: Final = "meters"
CONF_INVOICES: Final = "invoices"
CONF_INVOICE_NAME: Final = "invoice_name"
CONF_INVERT_INVOICES: Final = "invert_invoices"
CONF_PRIVACY_LOGGING: Final = "privacy_logging"

DOMAIN: Final = "mosoblgaz"
DATA_CONFIG: Final = DOMAIN + "_config"
DATA_API_OBJECTS: Final = DOMAIN + "_api_objects"
DATA_ENTITIES: Final = DOMAIN + "_entities"
DATA_UPDATERS: Final = DOMAIN + "_updaters"
DATA_OPTIONS_LISTENERS: Final = DOMAIN + "_options_listeners"

DEFAULT_SCAN_INTERVAL: Final = 60 * 60  # 1 hour
DEFAULT_TIMEOUT: Final = 30  # 30 seconds
DEFAULT_CONTRACT_NAME_FORMAT: Final = "MOG Contract {contract_code}"
DEFAULT_METER_NAME_FORMAT: Final = "MOG Meter {meter_code}"
DEFAULT_INVOICE_NAME_FORMAT: Final = "MOG {group} Invoice {contract_code}"
DEFAULT_INVERT_INVOICES: Final = False
DEFAULT_ADD_INVOICES: Final = True
DEFAULT_ADD_METERS: Final = True
DEFAULT_ADD_CONTRACTS: Final = True
DEFAULT_PRIVACY_LOGGING: Final = True

ATTRIBUTION: Final = "Data provided by Mosoblgaz"
RUB_CURRENCY: Final = "руб."

ENTITIES_CONTRACT: Final = "contract"
ENTITIES_METER_TARIFF: Final = "meter_tariff"

ATTR_INDICATIONS: Final = "indications"
ATTR_IGNORE_PERIOD: Final = "ignore_period"

# Common attributes
ATTR_CONTRACT_CODE: Final = "contract_code"
ATTR_METER_CODE: Final = "meter_code"

# Meter attributes
ATTR_SERIAL: Final = "serial"

# Contract attributes
ATTR_ADDRESS: Final = "address"
ATTR_PERSON: Final = "person"
ATTR_DEPARTMENT: Final = "department"

ATTR_COLLECTED_AT: Final = "collected_at"
ATTR_LAST_VALUE: Final = "last_value"
ATTR_LAST_COST: Final = "last_cost"
ATTR_LAST_CHARGED: Final = "last_charged"
ATTR_PREVIOUS_VALUE: Final = "previous_value"

ATTR_INVOICE_GROUP: Final = "invoice_group"
ATTR_PERIOD: Final = "period"
ATTR_TOTAL: Final = "total"
ATTR_PAID: Final = "paid"
ATTR_BALANCE: Final = "balance"
ATTR_PAYMENTS_COUNT: Final = "payments_count"

ATTR_PREVIOUS_PERIOD: Final = "previous_period"
ATTR_PREVIOUS_TOTAL: Final = "previous_total"
ATTR_PREVIOUS_PAID: Final = "previous_paid"
ATTR_PREVIOUS_BALANCE: Final = "previous_balance"
ATTR_PREVIOUS_PAYMENTS_COUNT: Final = "previous_payments_count"

DEFAULT_MAX_INDICATIONS: Final = 3
ATTR_COMMENT: Final = "comment"
ATTR_SUCCESS: Final = "success"
ATTR_CALL_PARAMS: Final = "call_params"
ATTR_INDICATION: Final = "indication"
FEATURE_PUSH_INDICATIONS: Final = 1
ATTR_IGNORE_INDICATIONS: Final = "ignore_indications"
ATTR_INCREMENTAL: Final = "incremental"
