[<img src="https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/header.png" height="100">](https://mosoblgaz.ru/)
# _Мособлгаз_ для HomeAssistant
> Предоставление информации о текущем состоянии ваших контрактов с Мособлгаз.
>
>[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
>[![Лицензия](https://img.shields.io/badge/%D0%9B%D0%B8%D1%86%D0%B5%D0%BD%D0%B7%D0%B8%D1%8F-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
>[![Поддержка](https://img.shields.io/badge/%D0%9F%D0%BE%D0%B4%D0%B4%D0%B5%D1%80%D0%B6%D0%B8%D0%B2%D0%B0%D0%B5%D1%82%D1%81%D1%8F%3F-%D0%B4%D0%B0-green.svg)](https://github.com/alryaz/hass-mosoblgaz/graphs/commit-activity)
>
>[![Пожертвование Yandex](https://img.shields.io/badge/%D0%9F%D0%BE%D0%B6%D0%B5%D1%80%D1%82%D0%B2%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5-Yandex-red.svg)](https://money.yandex.ru/to/410012369233217)
>[![Пожертвование PayPal](https://img.shields.io/badge/%D0%9F%D0%BE%D0%B6%D0%B5%D1%80%D1%82%D0%B2%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5-Paypal-blueviolet.svg)](https://www.paypal.me/alryaz)

Данная интеграция предоставляет возможность системе HomeAssistant опрашивать API Мособлгаза.

## Скриншоты
[<img alt="Лицевой счёт" src="https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/contract_glance.png" height="240">](https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/contract_glance.png)
[<img alt="Счётчик МОГ" src="https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/meter_glance.png" height="240">](https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/meter_glance.png)
[<img alt="Квитанция" src="https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/invoice_glance.png" height="240">](https://raw.githubusercontent.com/alryaz/hass-mosoblgaz/master/images/invoice_glance.png)

## Установка
### Посредством HACS
1. Откройте HACS (через `Extensions` в боковой панели)
1. Добавьте новый произвольный репозиторий:
   1. Выберите `Integration` (`Интеграция`) в качестве типа репозитория
   1. Введите ссылку на репозиторий: `https://github.com/alryaz/hass-mosoblgaz`
   1. Нажмите кнопку `Add` (`Добавить`)
   1. Дождитесь добавления репозитория (занимает до 10 секунд)
   1. Теперь вы должны видеть доступную интеграцию `Mosoblgaz (Мособлгаз)` в списке новых интеграций.
1. Нажмите кнопку `Install` чтобы увидеть доступные версии
1. Установите последнюю версию нажатием кнопки `Install`
1. Перезапустите HomeAssistant

_Примечание:_ Не рекомендуется устанавливать ветку `master`. Она используется исключительно для разработки. 

### Вручную
Клонируйте репозиторий во временный каталог, затем создайте каталог `custom_components` внутри папки конфигурации
вашего HomeAssistant (если она еще не существует). Затем переместите папку `mosoblgaz` из папки `custom_components` 
репозитория в папку `custom_components` внутри папки конфигурации HomeAssistant.
Пример (при условии, что конфигурация HomeAssistant доступна по адресу `/mnt/homeassistant/config`) для Unix-систем:
```
git clone https://github.com/alryaz/hass-mosoblgaz.git hass-mosoblgaz
mkdir -p /mnt/homeassistant/config/custom_components
mv hass-mosoblgaz/custom_components/mosoblgaz /mnt/homeassistant/config/custom_components
```

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
  # Invert invoice values
  invert_invoices: true
```