import os

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
SOURCE_CHANNEL_ID = os.getenv("SOURCE_CHANNEL_ID")
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL_ID")
TARGET_LINK = os.getenv("TARGET_LINK", "https://t.me/vash_kanal")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


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
