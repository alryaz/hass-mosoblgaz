# Мособлгаз для HomeAssistant
[![GitHub Page](https://img.shields.io/badge/GitHub-alryaz%2Fhass--mosoblgaz-blue)](https://github.com/alryaz/hass-mosoblgaz)
[![Donate Yandex](https://img.shields.io/badge/Donate-Yandex-red.svg)](https://money.yandex.ru/to/410012369233217)
[![Donate PayPal](https://img.shields.io/badge/Donate-Paypal-blueviolet.svg)](https://www.paypal.me/alryaz)
{% set mainline_num_ver = version_available.replace("v", "").replace(".", "") | int %}{%- set features = {
    'v0.0.1': 'Initial release, contracts / meters / invoices supported for reading',
    'v0.0.3': 'Invoice value inversion',
    'v0.0.6': 'Белые / чёрные / модифицируюшие списки'
}-%}{%- set breaking_changes = {
    'v0.0.3': ['Invoices show negative values on overpayment (as opposed positive to pre-0.0.3)']
} -%}{%- set bugfixes = {
    'v0.0.2': ['Fixed broken requests due to invalid offline statuses parsing'],
    'v0.0.3': ['Fixed double polling for entities and a typo within code'],
    'v0.0.5': ['Исправлена редкая ошибка с необычной отдачей данных',
               'Превентивно исправлено неправильное отображение атрибутов'],
    'v0.0.6': ['Исправлена ошибка, где селективная конфигурация не могла быть выполнена'],
} -%}
{% if installed %}{% if version_installed == "master" %}
#### ⚠ You are using development version
This branch may be unstable, as it contains commits not tested beforehand.  
Please, do not use this branch in production environments.
{% else %}{% if version_installed == version_available %}
#### ✔ Вы используете последнюю версию{% else %}{% set num_ver = version_installed.replace("v", "").replace(".","") | int %}
#### 🚨 Вы используете устаревшую версию!{% if num_ver < 20 %}
{% set print_header = True %}{% for ver, changes in breaking_changes.items() %}{% set ver = ver.replace("v", "").replace(".","") | int %}{% if num_ver < ver %}{% if print_header %}
##### Несовместимые изменения (`{{ version_installed }}` -> `{{ version_available }}`){% set print_header = False %}{% endif %}{% for change in changes %}
{{ '- '+change }}{% endfor %}{% endif %}{% endfor %}{% endif %}{% endif %}
{% set print_bugfix_header = True %}{% for ver, fixes in bugfixes.items() %}{% set ver = ver.replace("v", "").replace(".","") | int %}{% if num_ver < ver %}{% if print_bugfix_header %}
##### Исправления (`{{ version_installed }}` -> `{{ version_available }}`){% set print_bugfix_header = False %}{% endif %}{% for fix in fixes %}
{{ '- ' + fix }}{% endfor %}{% endif %}{% endfor %}

##### Features{% for ver, text in features.items() %}{% set feature_ver = ver.replace("v", "").replace(".", "") | int %}
- {% if num_ver < feature_ver %}**{% endif %}`{{ ver }}` {% if num_ver < feature_ver %}NEW** {% endif %}{{ text }}{% endfor %}

Please, report all issues to the [project's GitHub issues](https://github.com/alryaz/hass-mosoblgaz/issues).
{% endif %}{% else %}
## Features{% for ver, text in features.items() %}
- {{ text }} _(supported since `{{ ver }}`)_{% endfor %}
{% endif %}

## Screenshots
### Contract sensor
![Contract glance](https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/account_glance.png)

### Meter sensors
![Meter glance](https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/meter_glance.png)

### Invoice sensor
![Invoice sensor](https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/invoice_glance.png)



## Конфигурация
### Через интерфейс HomeAssistant
1. Откройте `Настройки` -> `Интеграции`
1. Нажмите внизу справа страницы кнопку с плюсом
1. Введите в поле поиска `Mosoblgaz` или `Мособлгаз`
   1. Если по какой-то причине интеграция не была найдена, убедитесь, что HomeAssistant был перезапущен после установки интеграции.
1. Выберите первый результат из списка
1. Введите данные вашей учётной записи для ЛК _"Мособлгаз"_
1. Нажмите кнопку `Продолжить`
1. Через несколько секунд начнётся обновление; проверяйте список ваших объектов на наличие
   объектов, чьи названия начинаются на `MOG`.
   
### Через `configuration.yaml`
#### Базовая конфигурация
Для настройки данной интеграции потребуются данные авторизации в ЛК Мособлгаз.  
`username` - Имя пользователя (телефон / адрес эл. почты)  
`password` - Пароль
```yaml
mosoblgaz:
  username: !secret mosoblgaz_username
  password: !secret mosoblgaz_password
```

#### Несколько пользователей
Возможно добавить несколько пользователей.
Для этого вводите данные, используя пример ниже:
```yaml
mosoblgaz:
    # Первый пользователь
  - username: !secret first_mosoblgaz_username
    password: !secret first_mosoblgaz_password

    # Второй пользователь
  - username: !secret second_mosoblgaz_username
    password: !secret second_mosoblgaz_password

    # Третий пользователь
  - username: !secret third_mosoblgaz_username
    password: !secret third_mosoblgaz_password 
```

#### Обновление конкретных контрактов
Селективное обновление контрактов используется для добавления определённых контрактов, и/или
отключения некоторых из их компонентов.

Обновление контрактов таким способом может выполняться по трём стратегиям:
- _Модификация_ - не используются значения типа _истина_ или _ложь_
- _Белый список_ - используются только значения истины (`true`, `on`, и т.д.); указание конкретных
  опций (_квитанции:_ `invoices`, _счётчики:_ `meters`) разрешает добавление
- _Чёрный список_ - используются только значения лжи (`false`, `off`, и т.д.); указание конкретных
  опций (_квитанции:_ `invoices`, _счётчики:_ `meters`) не запрещает добавление

При указании конкретных опций, сенсор контракта будет добавлен независимо от указанных опций. Для
отключения контракта полностью, воспользуйтесь стратегией _чёрного списка_.

**N.B.** При совместном использовании значений типа _ложь_ и _истина_ в одной конфигурации будет выбрана
стратегия _чёрного списка_. Данный способ конфигурации не имеет глубокого смысла, так как в чёрном
списке по умолчанию добавляются все контракты, кроме тех, что имеют значение _ложь_.

**Важно!** Во избежание проблем с загрузкой конфигураций, оборачивайте номера контрактов двойными
кавычками. Существуют случаи, когда ключ загружается не как строка, а число в недесятичной системе
счисления. Это не позволяет правильно сравнивать номера контрактов, из-за чего, например, некоторые
контракты из белого списка не будут добавлены. Смотрите примеры ниже для получения более подробного
представления о том, как следует выполнять конфигурацию.

##### Пример _Модификации_
В данном примере будут добавляться все контракты.
Контракт с номером `5612341421` будет добавлен только как контракт, без счётчиков и квитанций.  
Контракт с номером `512124124` будет добавлен без счётчиков.
```yaml
mosoblgaz:
  ...
  contracts:
    # Изменить способ добавления контракта
    # Отключить всё, кроме объекта контракта
    "5612341421":
      invoices: False
      meters: False

    # Изменить способ добавления контракта
    # Добавлять только квитанции, отключить счётчики
    "512124124":
      meters: False
```

##### Пример _Чёрного списка_
В данном примере будут добавляться все контракты, кроме `5612341421`, со счётчиками и квитанциями.  
Контракт с номером `512124124` будет добавлен без счётчиков.
```yaml
mosoblgaz:
  ...
  contracts:
    # Запретить добавление контракта
    "5612341421": false

    # Изменить способ добавления контракта
    # Добавлять только квитанции, отключить счётчики
    "512124124":
      meters: False
```

##### Пример _Белого списка_
В данном примере будут добавляться только контракты `5612341421` и `512124124`, при этом последний
будет добавлен без счётчиков.
```yaml
mosoblgaz:
  ...
  contracts:
    # Разрешить добавление контракта
    "5612341421": true

    # Разрешить добавление контракта
    # Добавлять только счётчики, отключить квитанции
    "512124124":
      invoices: False
```

#### Изменение интервалов обновления
Частота обновления данных (`scan_interval`) по умолчанию: 1 час  
```yaml
mosoblgaz:
  ...
  # Интервал обновления данных
  scan_interval:
    hours: 6
    seconds: 3
    minutes: 1
    ...

  # ... также возможно задать секундами
  scan_interval: 21600
```

#### Настройка имён объектов
На данный момент, именование объектов происходит используя метод `str.format(...)` языка Python. Изменение следующих
параметров влияет на ID создаваемых объектов и их имена.

Поддерживаемые замены: `group` (только для квитанций), `code`

Формат контракта (`contract_name`) по умолчанию: `MOG Contract {code}`  
Формат счётчика (`meter_name`) по умолчанию: `MOG Meter {code}`  
Формат квитанции (`invoice_name`) по умолчанию: `MOG {group} Invoice {code}`
```yaml
mosoblgaz:
  ...
  # Произвольный формат для контрактов
  contract_name: 'Мой супер {code} контракт' 

  # Произвольный формат для счётчиков
  meter_name: 'Счётчик {code} шипит'

  # Произвольный формат для квитанций
  meter_name: 'За {group} по {code} платим мало!'
```

#### Инвертирование значений квитанций
По умолчанию, квитанции отображают переплату в положительных числах. Если имеется желание обратить данное поведение,
(задолженность будеть показана положительной), укажите ключ `invert_invoices` со значением `true` в конфигурации:
```yaml
mosoblgaz:
  ...
  # Invert invoice values
  invert_invoices: true
```