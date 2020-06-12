# HomeAssistant Hekr Devices Integration
[![GitHub Page](https://img.shields.io/badge/GitHub-alryaz%2Fhass--mosoblgaz-blue)](https://github.com/alryaz/hass-mosoblgaz)
[![Donate Yandex](https://img.shields.io/badge/Donate-Yandex-red.svg)](https://money.yandex.ru/to/410012369233217)
[![Donate PayPal](https://img.shields.io/badge/Donate-Paypal-blueviolet.svg)](https://www.paypal.me/alryaz)
{% set mainline_num_ver = version_available.replace("v", "").replace(".", "") | int %}{%- set features = {
    'v0.0.1': 'Initial release, contracts / meters / invoices supported for reading',
}-%}{%- set breaking_changes = {} -%}{%- set bugfixes = {} -%}
{% if installed %}{% if version_installed == "master" %}
#### ⚠ You are using development version
This branch may be unstable, as it contains commits not tested beforehand.  
Please, do not use this branch in production environments.
{% else %}{% if version_installed == version_available %}
#### ✔ You are using mainline version{% else %}{% set num_ver = version_installed.replace("v", "").replace(".","") | int %}
#### 🚨 You are using an outdated release of Hekr component{% if num_ver < 20 %}
{% set print_header = True %}{% for ver, changes in breaking_changes.items() %}{% set ver = ver.replace("v", "").replace(".","") | int %}{% if num_ver < ver %}{% if print_header %}
##### Breaking changes (`{{ version_installed }}` -> `{{ version_available }}`){% set print_header = False %}{% endif %}{% for change in changes %}
{{ '- '+change.pop(0) }}{% for changeline in change %}
{{ '  '+changeline }}{% endfor %}{% endfor %}{% endif %}{% endfor %}
{% endif %}{% endif %}

{% set print_header = True %}{% for ver, fixes in bugfixes.items() %}{% set ver = ver.replace("v", "").replace(".","") | int %}{% if num_ver < ver %}{% if print_header %}
##### Bug fixes (`{{ version_installed }}` -> `{{ version_available }}`){% set print_header = False %}{% endif %}{% for fix in fixes %}
{{ '- ' + fix }}{% endfor %}{% endif %}{% endfor %}

##### Features{% for ver, text in features.items() %}{% set feature_ver = ver.replace("v", "").replace(".", "") | int %}
- {% if num_ver < feature_ver %}**{% endif %}`{{ ver }}` {% if num_ver < feature_ver %}NEW** {% endif %}{{ text }}{% endfor %}

Please, report all issues to the [project's GitHub issues](https://github.com/alryaz/hass-mosoblgaz/issues).
{% endif %}{% else %}
## Features{% for ver, text in features.items() %}
- {{ text }} _(supported since `{{ ver }}`)_{% endfor %}
{% endif %}

## !!! WARNING !!!
Although indication submission is partially available in this version of the component, it is in no way
secure or error-proof. Since more testing is required, and there are date restrictions in place,
this feature will be complete by one of the next minor releases.

## Configuration
### Basic configuration example
```yaml
mosoblgaz:
  username: !secret mosoblgaz_username
  password: !secret mosoblgaz_password
```

### Multiple users
```yaml
mosoblgaz:
    # First user
  - username: !secret first_mosoblgaz_username
    password: !secret first_mosoblgaz_password

    # Second user
  - username: !secret second_mosoblgaz_username
    password: !secret second_mosoblgaz_password

    # Third user
  - username: !secret third_mosoblgaz_username
    password: !secret third_mosoblgaz_password 
```

### Update only specific contracts

```yaml
mosoblgaz:
  ...
  contracts:
    # Update every part of the contract (including meters, invoices, and what's to come)
    135112512: True
    
    # Disable contract completely
    5612341421: False

    # Add only account and invoice sensors, but not meters.
    512124124:
      invoices: True
      meters: False
```

### Change update schedule
Default `scan_interval`: 1 hour  
```yaml
mosoblgaz:
  ...
  # Interval for entity updates
  scan_interval:
    hours: 6

  # ... also possible to set via seconds
  scan_interval: 21600
```

### Configure invoices
Invoice entities are updated during the main update schedule. They display the total amount
requested by the operating company. **They don't reflect whether your payment has already
been processed!** They are designed to serve as attribute holders for pricing decomposition.
```yaml
mosoblgaz:
  ...
  # Enable invoices for every contract (default behaviour)
  invoices: true

  # Enable invoices for certain contracts
  invoices: ['1131241222']

  # Disable invoices for every contract
  invoices: false
```

### Custom names for entities
Currently, naming entities supports basic formatting based on python `str.format(...)` method. Changing
these parameters (assuming setup without explicit overrides via *Customize* interface or alike) will have effect both on entity IDs and friendly names.
  
Supported replacements are: `code`, `group` (only for invoices)

Default `contract_name`: `MOG Contract {code}` (ex.: `MOG Contract 214651241`)  
Default `meter_name`: `MOG Meter {code}` (ex. `MOG Meter 214651241`)  
Default `invoice_name`: `MES {group} Invoice {code}` (ex. `MOG Gas Invoice 214651241`)
```yaml
mosoblgaz:
  ...
  # Custom contract name format
  contract_name: 'My super {code} contract'

  # Custom meter name format
  meter_name: 'Ultimate {code} gasification'

  # Custom invoice name format
  invoice_name: 'What {group} costs on {code}'
```