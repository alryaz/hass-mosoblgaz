"""Constants for Mosoblgaz module"""

from typing import Final

PLATFORMS = ["sensor"]

CONF_GRAPHQL_TOKEN: Final = "graphql_token"
CONF_INVERT_INVOICES: Final = "invert_invoices"

DOMAIN: Final = "mosoblgaz"

DEFAULT_SCAN_INTERVAL: Final = 60 * 60  # 1 hour
DEFAULT_TIMEOUT: Final = 30  # 30 seconds
DEFAULT_INVERT_INVOICES: Final = False

FEATURE_PUSH_INDICATIONS: Final = 1

ATTRIBUTION: Final = "Data provided by Mosoblgaz"
RUB_CURRENCY: Final = "RUB"

# Common attributes
ATTR_CONTRACT_CODE: Final = "contract_code"

# Device attributes
ATTR_DEVICE_CODE: Final = "device_code"
ATTR_CLASS_NAME: Final = "class_name"

# Meter attributes
ATTR_SERIAL: Final = "serial"
ATTR_METER_CODE: Final = "meter_code"

# -- Indications service attributes
ATTR_INDICATIONS: Final = "indications"
ATTR_IGNORE_PERIOD: Final = "ignore_period"
ATTR_COMMENT: Final = "comment"
ATTR_SUCCESS: Final = "success"
ATTR_CALL_PARAMS: Final = "call_params"
ATTR_INDICATION: Final = "indication"
ATTR_IGNORE_INDICATIONS: Final = "ignore_indications"
ATTR_INCREMENTAL: Final = "incremental"
ATTR_RETURN_ON_ERROR: Final = "return_on_error"

# Contract attributes
ATTR_ADDRESS: Final = "address"
ATTR_PERSON: Final = "person"
ATTR_DEPARTMENT: Final = "department"

ATTR_COLLECTED_AT: Final = "collected_at"
ATTR_LAST_VALUE: Final = "last_value"
ATTR_LAST_COST: Final = "last_cost"
ATTR_LAST_CHARGED: Final = "last_charged"
ATTR_PREVIOUS_VALUE: Final = "previous_value"

# Invoice attributes
ATTR_INVOICE_GROUP: Final = "invoice_group"
ATTR_INVOICE_NAME: Final = "invoice_name"
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
