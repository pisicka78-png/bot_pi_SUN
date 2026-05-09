import os

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
SOURCE_CHANNEL_ID = os.getenv("SOURCE_CHANNEL_ID")
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL_ID")
TARGET_LINK = os.getenv("TARGET_LINK", "https://t.me/vash_kanal")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

ACCOUNT_BOOTSTRAP_ENABLED = os.getenv("ACCOUNT_BOOTSTRAP_ENABLED", "false").lower() == "true"
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_USER_PHONE = os.getenv("TELEGRAM_USER_PHONE")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "telegram_account")
BOT_USERNAME = os.getenv("BOT_USERNAME")
SOURCE_CHANNEL_REF = os.getenv("SOURCE_CHANNEL_REF") or SOURCE_CHANNEL_ID
TARGET_CHANNEL_REF = os.getenv("TARGET_CHANNEL_REF") or TARGET_CHANNEL_ID
ACCOUNT_SOURCE_ENABLED = os.getenv("ACCOUNT_SOURCE_ENABLED", "false").lower() == "true"
ACCOUNT_SOURCE_DOWNLOAD_DIR = os.getenv("ACCOUNT_SOURCE_DOWNLOAD_DIR", "downloads")
SEND_MODE = os.getenv("SEND_MODE", "interval").lower()
SEND_INTERVAL_MINUTES = int(os.getenv("SEND_INTERVAL_MINUTES", "30"))
SEND_CRON_MINUTE = os.getenv("SEND_CRON_MINUTE", "*/30")
SEND_CRON_HOUR = os.getenv("SEND_CRON_HOUR", "*")


missing = [
    name
    for name, value in {
        "BOT_TOKEN": BOT_TOKEN,
        "SOURCE_CHANNEL_ID": SOURCE_CHANNEL_ID,
        "TARGET_CHANNEL_ID": TARGET_CHANNEL_ID,
    }.items()
    if not value
]

if missing:
    raise RuntimeError(f"Missing required environment values: {', '.join(missing)}")
