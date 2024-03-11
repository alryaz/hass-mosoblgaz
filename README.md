[<img src="https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/header.png" height="100">](https://mosoblgaz.ru/)
# _Мособлгаз_ для Home Assistant
> Предоставление информации о текущем состоянии ваших контрактов с Мособлгаз.
>
> [![hacs_badge](https://img.shields.io/badge/HACS-Default-green.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
> [![Лицензия](https://img.shields.io/badge/%D0%9B%D0%B8%D1%86%D0%B5%D0%BD%D0%B7%D0%B8%D1%8F-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
> [![Поддержка](https://img.shields.io/badge/%D0%9F%D0%BE%D0%B4%D0%B4%D0%B5%D1%80%D0%B6%D0%B8%D0%B2%D0%B0%D0%B5%D1%82%D1%81%D1%8F%3F-%D0%B4%D0%B0-green.svg?style=for-the-badge)](https://github.com/alryaz/hass-mosoblgaz/graphs/commit-activity)

> 💵 **Пожертвование на развитие проекта**  
> [![Пожертвование YooMoney](https://img.shields.io/badge/YooMoney-8B3FFD.svg?style=for-the-badge)](https://yoomoney.ru/to/410012369233217)
> [![Пожертвование Тинькофф](https://img.shields.io/badge/Tinkoff-F8D81C.svg?style=for-the-badge)](https://www.tinkoff.ru/cf/3g8f1RTkf5G)
> [![Пожертвование Cбербанк](https://img.shields.io/badge/Сбербанк-green.svg?style=for-the-badge)](https://www.sberbank.com/ru/person/dl/jc?linkname=3pDgknI7FY3z7tJnN)
> [![Пожертвование DonationAlerts](https://img.shields.io/badge/DonationAlerts-fbaf2b.svg?style=for-the-badge)](https://www.donationalerts.com/r/alryaz)
>
> 💬 **Техническая поддержка**  
> [![Группа в Telegram](https://img.shields.io/endpoint?url=https%3A%2F%2Ftg.sumanjay.workers.dev%2Falryaz_ha_addons&style=for-the-badge)](https://telegram.dog/alryaz_ha_addons)

[![My Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=hass-mosoblgaz&owner=alryaz&category=Integration)

Данная интеграция предоставляет возможность системе HomeAssistant опрашивать API Мособлгаза.

## Скриншоты

<details>
    <summary>Лицевой счёт Мособлгаз</summary>
    <img src="https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/contract_glance.png" alt="Скриншот: лицевой счёт Мособлгаз">
</details>
<details>
    <summary>Счётчик Мособлгаз</summary>
    <img src="https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/meter_glance.png" alt="Скриншот: счётчик Мособлгаз">
</details>
<details>
    <summary>Квитанция Мособлгаз</summary>
    <img src="https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/invoice_glance.png" alt="Скриншот: квитанция Мособлгаз">
</details>

## Установка

### Home Assistant Community Store

> 🎉  **Рекомендованный метод установки.**

[![Открыть Ваш Home Assistant и открыть репозиторий внутри Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alryaz&repository=hass-mosoblgaz&category=integration)

1. Установите HACS ([инструкция по установке на оф. сайте](https://hacs.xyz/docs/installation/installation/)).
2. Добавьте репозиторий в список дополнительных:
    1. Откройте главную страницу _HACS_.
    2. Откройте раздел _Интеграции (Integrations)_.
    3. Нажмите три точки сверху справа (дополнительное меню).
    4. Выберите _Пользовательские репозитории_.
    5. Скопируйте `https://github.com/alryaz/hass-mosoblgaz` в поле ввода
    6. Выберите _Интеграция (Integration)_ в выпадающем списке.
    7. Нажмите _Добавить (Add)_.
3. Найдите `Mosoblgaz` в поиске по интеграциям.
4. Установите последнюю версию компонента, нажав на кнопку `Установить` (`Install`).
5. Перезапустите сервер _Home Assistant_.

### Вручную

> ⚠️ **Внимание!** Данный вариант **<ins>не рекомендуется</ins>** в силу
> сложности поддержки установленной интеграции в актуальном состоянии.

1. Скачайте [архив с актуальной стабильной версией интеграции](https://github.com/alryaz/hass-mosoblgaz/releases/latest/download/mosoblgaz.zip)
2. Создайте папку (если не существует) `custom_components` внутри папки с конфигурацией Home Assistant
3. Создайте папку `mosoblgaz` внутри папки `custom_components`
4. Извлеките содержимое скачанного архива в папку `mosoblgaz`
5. Перезапустите сервер _Home Assistant_

## Конфигурация

### Через интерфейс _"Интеграции"_

Поддерживается базовый функционал конфигурации через веб-интерфейс _Home
Assistant_. Конфигурация данным способов
возможна без перезагрузки _Home Assistant_.

[![Установить интеграцию mosoblgaz](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=mosoblgaz)
   
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

#### Добавление конкретных опций
Для всех контрактов одновременно возможно отключить как квитанции, так и счётчики по умолчанию<sup>1</sup>.
```yaml
mosoblgaz:
  ...
  # Отключить все квитанции
  invoices: false
  # Отключить все счётчики
  meters: false
```

<sup>1</sup> Данная опция позволяет задать значения по умолчанию. Их поконтрактное переопределение
описано в следующем разделе конфигурации.

#### Обновление конкретных контрактов
Селективное обновление контрактов используется для скрытия определённых контрактов от HomeAssistant
(на уровне их форсированного недобавления в интерфейс).

По умолчанию включается весь функционал для всех обрабатываемых данных.

**Важно!** Во избежание проблем с загрузкой конфигураций, оборачивайте номера контрактов двойными
кавычками. Существуют случаи, когда ключ загружается не как строка, а число в недесятичной системе
счисления. Это не позволяет правильно сравнивать номера контрактов, из-за чего, например, некоторые
контракты из белого списка не будут добавлены. Смотрите примеры ниже для получения более подробного
представления о том, как следует выполнять конфигурацию.

```yaml
mosoblgaz:
  ...
  # По умолчанию отключить квитанции для всех контрактов
  invoices: false

  contracts:
    # Контракт не будет добавлен
    # Счётчики не будут добавлены
    # Квитанции не будут добавлены
    "5612341421": false

    # Контракт будет добавлен
    # Счётчики будут добавлены
    # Квитанции будут добавлены
    "5612341422": true

    # Контракт будет добавлен
    # Счётчики не будут добавлены
    # Квитанции не будут добавлены
    "5612341423":
      meters: false

    # Контракт будет добавлен
    # Счётчики будут добавлены
    # Квитанции будут добавлены
    "5612341424":
      invoices: true

    # Для всех остальных контрактов, не указанных в настройке:
    # Счётчики будут добавлены
    # Квитанции не будут добавлены
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
  invoice_name: 'За {group} по {code} платим мало!'
```

#### Инвертирование значений квитанций
По умолчанию, квитанции отображают переплату в положительных числах. Если имеется желание обратить данное поведение,
(задолженность будеть показана положительной), укажите ключ `invert_invoices` со значением `true` в конфигурации:
```yaml
mosoblgaz:
  ...
  # Поменять знак (+ на -) на счетах
  invert_invoices: true
```

#### Увеличение времени ожидания ответа сервера
При использовании компонента в сети с низкой пропускной способностью и высокими задержками, запросы могут переставать
быть отвеченными сервером. Возможно увеличить время ожидания ответа от сервера путём указания параметра ниже.

> **Важно!** Значение параметра не должно превышать интервал обновления.

```yaml
mosoblgaz:
  ...
  # Время ожидания ответа от сервера
  timeout:
    minutes: 1
    ...

  # ... также возможно задать секундами
  timeout: 60
```

> *N.B.* Данная опция также доступна в меню "Настройки" интеграции (при настройке через UI)

#### Логирование без личных данных
При написании багрепорта требуется добавить вывод лог-файлов. Если Вы желаете скрыть Ваши личные данные из этих
логов, не прибегая к их замене, укажите данный параметр в конфигурации:
```yaml
logger:
  # Настройка логирования производится через компонент `logging`
  logs:
    # Задать уровень логгирования по умолчанию `debug` (отладка)
    custom_components.mosoblgaz: debug
...
mosoblgaz:
  ...
  # Invert invoice values
  privacy_logging: true
```

> *N.B.* Данная опция также доступна в меню "Настройки" интеграции (при настройке через UI)
