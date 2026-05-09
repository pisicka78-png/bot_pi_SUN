from html import escape
from pathlib import Path
from typing import Optional

from bot_components.text_processing import replace_links
from config import (
    ACCOUNT_SOURCE_DOWNLOAD_DIR,
    ACCOUNT_SOURCE_ENABLED,
    SOURCE_CHANNEL_REF,
    TARGET_LINK,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_SESSION,
)
from logger_config import logger
from media_group_handler import MediaGroupCollector


class AccountSourceListener:
    def __init__(self, collector: MediaGroupCollector):
        self.collector = collector
        self.client = None
        self.download_dir = Path(ACCOUNT_SOURCE_DOWNLOAD_DIR)

    async def start(self) -> bool:
        if not ACCOUNT_SOURCE_ENABLED:
            return False

        if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
            logger.warning("Account source listener skipped: TELEGRAM_API_ID/TELEGRAM_API_HASH are missing")
            return False

        try:
            from telethon import TelegramClient, events
        except ImportError:
            logger.error("Account source listener enabled, but Telethon is not installed")
            return False

        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.client = TelegramClient(TELEGRAM_SESSION, int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
        await self.client.connect()

        if not await self.client.is_user_authorized():
            logger.error("Account source listener needs an authorized Telethon session. Run account login first.")
            await self.stop()
            return False

        source = await self.client.get_entity(SOURCE_CHANNEL_REF)

        @self.client.on(events.NewMessage(chats=source))
        async def handle_source_message(event):
            await self._handle_source_message(event.message)

        logger.info("Account source listener started for %s", SOURCE_CHANNEL_REF)
        return True

    async def stop(self) -> None:
        if self.client:
            await self.client.disconnect()
            logger.info("Account source listener stopped")

    async def _handle_source_message(self, message) -> None:
        file_type = self._detect_media_type(message)
        if not file_type:
            logger.info("Account source message %s skipped: only photo/video are supported", message.id)
            return

        file_path = await message.download_media(file=str(self.download_dir))
        if not file_path:
            logger.info("Account source message %s skipped: media download returned empty path", message.id)
            return

        group_id = f"account_group_{message.grouped_id}" if message.grouped_id else f"account_single_{message.id}"
        caption = replace_links(escape(message.message or ""), TARGET_LINK)

        await self.collector.add_local_media(
            origin_msg_id=message.id,
            group_id=group_id,
            file_path=str(file_path),
            file_type=file_type,
            caption=caption,
        )

    @staticmethod
    def _detect_media_type(message) -> Optional[str]:
        if getattr(message, "video", None):
            return "local_video"
        if getattr(message, "photo", None):
            return "local_photo"
        return None
