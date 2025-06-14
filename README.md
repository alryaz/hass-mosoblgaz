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

> ⚠️ **Внимание!** Конфигурация посредством YAML не поддерживается с 2025.6.0

Поддерживается весь основной функционал конфигурации через веб-интерфейс _Home
Assistant_. Конфигурация данным способов
возможна без перезагрузки _Home Assistant_.

[![Установить интеграцию mosoblgaz](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=mosoblgaz)

<details>
  <summary>Вручную (если кнопка выше не работает)</summary>
  Для перехода к настройке, выполните следующие действия:
  <ol>
    <li>Перейдите в раздел <i>Настройки</i>&nbsp;&#10230;&nbsp;<i>Интеграции</i> (`/config/integrations`)</li>
    <li>Нажмите на круглую кнопку с плюсом внутри в нижнем правом углу экрана</li>
    <li>Во всплывшем окне, введите в верхнем поле поиска: <b>Mosoblgaz</b>; одним из результатов должен оказаться <b>Mosoblgaz&nbsp;(Мособлгаз)</b> (с соответствующим логотипом <i>Мособлгаза</i>)</li>
    <li>Нажмите на предложенный результат</li>
    <li>Введите имя пользователя и пароль в соответствующие поля</li>
    <li>Нажмите внизу справа на кнопку <i>Подтвердить</i>. В случае обнаружения системой каких-либо ошибок, они будут отображены в окошке</li>
    <li>Обновление займёт не более 5-10 секунд (проверено на Raspberry Pi 4), элементы в конфигурации по-умолчанию должны появиться на главном экране (при использовании конфигурациии Lovelace по-умолчанию)</li>
  </ol>
</details>

<!-- ## Смена пароля настроенной учётной записи

1. Перейдите в раздел <i>Настройки</i>&nbsp;&#10230;&nbsp;<i>Интеграции</i> (`/config/integrations`)
2.  -->