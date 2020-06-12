# HomeAssistant Mosoblgaz sensors
> Provide information about current state of your Mosoblgaz contracts.
>
>[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
>[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
>[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/alryaz/hass-hekr-component/graphs/commit-activity)
>[![Donate Yandex](https://img.shields.io/badge/Donate-Yandex-red.svg)](https://money.yandex.ru/to/410012369233217)
>[![Donate PayPal](https://img.shields.io/badge/Donate-Paypal-blueviolet.svg)](https://www.paypal.me/alryaz)

This custom component provides Mosoblgaz API polling capabilities to HomeAssistant.

## Installation
### Via HACS
1. Open HACS (via `Extensions` in the sidebar)
1. Add a new custom repository:
   1. Select `Integration` as custom repository type
   1. Enter custom repository URL: `https://github.com/alryaz/hass-mosoblgaz`
   1. Press `Add` button
   1. Wait until repository gets added 
   1. You should now see `Mosoblgaz (Мособлгаз)` integration available in the list of newly added integrations
1. Click `Install` button to view available versions
1. Install latest version by pressing `Install`

_NOTE:_ It is not recommended to install `master` branch. It is intended for development only. 

### Manually
Clone the repository to a temporary directory, then create a `custom_components` directory inside your HomeAssistant
config folder (if it doesn't exist yet). Then, move `Mosoblgaz` folder from `custom_components` folder of
the repository to the `custom_components` folder inside your HomeAssistant configuration.  
An example (assuming HomeAssistant configuration is available at `/mnt/homeassistant/config`) for Unix-based
systems is available below:
```
git clone https://github.com/alryaz/hass-mosoblgaz.git hass-mosoblgaz
mkdir -p /mnt/homeassistant/config/custom_components
mv hass-mosoblgaz/custom_components/mosoblgaz /mnt/homeassistant/config/custom_components
```

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