# Telegram Media Queue Bot

Бот переносить фото/відео з одного Telegram-каналу в інший через чергу SQLite.

Є два режими читання source-каналу:

- **Bot API** - бот має бути адміном у source-каналі.
- **Account source** - Telegram-акаунт підписаний на source-канал, читає нові пости через Telethon і завантажує медіа локально. У цьому режимі бота не треба додавати в source-канал.

## Поточна схема

Для сценарію, де бот не доданий у source:

1. акаунт Alesya підключається через Telethon;
2. акаунт слухає `SOURCE_CHANNEL_REF`, наприклад `@bedia_studio`;
3. нові фото/відео завантажуються в `downloads/`;
4. шлях до файлу записується в `queue.db`;
5. Bot API відправляє медіа в `TARGET_CHANNEL_ID`, наприклад канал `@bigpenisist`;
6. після успішної відправки запис із БД і локальний файл видаляються.

## Структура

- `main.py` - запуск бота, polling, lifecycle.
- `config.py` - читає `.env`.
- `media_group_handler.py` - SQLite-черга і відправка медіа.
- `bot_components/handlers.py` - команди, меню, Bot API handlers.
- `bot_components/account_source_listener.py` - слухає source через Telegram-акаунт.
- `bot_components/account_bootstrap.py` - опціонально додає/піднімає бота в target через акаунт.
- `bot_components/album_middleware.py` - збір Bot API альбомів.
- `bot_components/text_processing.py` - заміна посилань.

## `.env`

Приклад:

```env
BOT_TOKEN=your-bot-token
SOURCE_CHANNEL_ID=-1001234567890
TARGET_CHANNEL_ID=-1003963815868
TARGET_LINK=https://t.me/your_channel
LOG_LEVEL=INFO

ACCOUNT_BOOTSTRAP_ENABLED=true
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your-api-hash
TELEGRAM_USER_PHONE=+380000000000
TELEGRAM_SESSION=telegram_account
BOT_USERNAME=big_penisist_bot
SOURCE_CHANNEL_REF=@bedia_studio
TARGET_CHANNEL_REF=@bigpenisist
ACCOUNT_SOURCE_ENABLED=true
ACCOUNT_SOURCE_DOWNLOAD_DIR=downloads
SEND_MODE=manual
SEND_INTERVAL_MINUTES=30
SEND_CRON_HOUR=*
SEND_CRON_MINUTE=*/30
```

### Основні ключі

- `BOT_TOKEN` - токен бота з `@BotFather`.
- `SOURCE_CHANNEL_ID` - id source-каналу для Bot API режиму.
- `TARGET_CHANNEL_ID` - id target-каналу, куди бот публікує.
- `TARGET_LINK` - посилання, на яке замінюються знайдені URL у підписах.
- `LOG_LEVEL` - рівень логів.

### Ключі акаунта

- `ACCOUNT_SOURCE_ENABLED=true` - читати source-канал через акаунт.
- `TELEGRAM_API_ID` і `TELEGRAM_API_HASH` - з `https://my.telegram.org`.
- `TELEGRAM_USER_PHONE` - номер Telegram-акаунта.
- `TELEGRAM_SESSION` - назва локального session-файлу.
- `SOURCE_CHANNEL_REF` - username source-каналу, наприклад `@bedia_studio`.
- `TARGET_CHANNEL_REF` - username target-каналу, наприклад `@bigpenisist`.
- `BOT_USERNAME` - username бота без або з `@`.

`ACCOUNT_BOOTSTRAP_ENABLED=true` пробує через акаунт додати/підняти бота в target-каналі. Для цього акаунт має бути власником або адміном target-каналу з правами додавати адміністраторів.

## Режим відправки

Режим задається в `.env` через `SEND_MODE`.

```env
SEND_MODE=manual
```

Доступні значення:

- `manual` - бот тільки складає медіа в чергу. Відправка тільки вручну через `🚀 Відправити` або `/send`.
- `immediate` - бот відправляє медіа одразу після додавання в чергу.
- `interval` - бот відправляє один об'єкт із черги кожні `SEND_INTERVAL_MINUTES`.
- `cron` - бот відправляє за cron-розкладом `SEND_CRON_HOUR` + `SEND_CRON_MINUTE`.

Приклади:

```env
SEND_MODE=immediate
```

```env
SEND_MODE=interval
SEND_INTERVAL_MINUTES=10
```

```env
SEND_MODE=cron
SEND_CRON_HOUR=9,13,18
SEND_CRON_MINUTE=0
```

## Перший запуск акаунта

Встановити залежності:

```bash
python -m pip install -r requirements.txt
```

Запустити в консолі:

```bash
python main.py
```

Першого разу Telethon попросить код входу з Telegram. Після входу створиться:

```text
telegram_account.session
```

Цей файл не можна комітити. Він уже доданий у `.gitignore`.

## Меню бота

У особистому чаті з ботом:

```text
/start
```

Кнопки:

- `📦 Статус` - показати чергу.
- `🚀 Відправити` - відправити перший об'єкт із черги.
- `🔍 Перевірити доступ` - перевірити source/target.
- `🎯 Тест target` - надіслати тест у target.
- `🗝 Пасхалка` - секретна відповідь.
- `ℹ️ Допомога` - підказка.

## Черга

Bot API режим зберігає Telegram `file_id`.

Account source режим зберігає локальний шлях до файлу в `downloads/`.

Таблиця `queue`:

- `media_group_id`;
- `origin_msg_id`;
- `file_id` - Telegram `file_id` або локальний шлях;
- `file_type` - `photo`, `video`, `local_photo`, `local_video`;
- `caption`;
- `added_at`.

Після перезапуску бот продовжує працювати з `queue.db`. Якщо видалити `queue.db`, черга зникне.

## Відправка

Автоматично кожні 30 хвилин:

```python
CronTrigger(minute="*/30")
```

Вручну через меню або:

```text
/send
```

## Обмеження

- старі пости не підтягнуться, бот/акаунт бачить тільки нові після запуску;
- текст без фото/відео не додається в чергу;
- документи, audio, voice, sticker не обробляються;
- великий альбом може не відправитися через ліміти Telegram;
- `/send` поки не обмежений конкретним адміном;
- якщо account source читає канал, медіа тимчасово лежить у `downloads/`.
