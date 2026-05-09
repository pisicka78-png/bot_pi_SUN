from typing import Optional

import aiosqlite
from aiogram import Bot
from aiogram.types import InputMediaPhoto, InputMediaVideo, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from logger_config import logger


CREATE_QUEUE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_group_id TEXT NOT NULL,
    origin_msg_id INTEGER,
    file_id TEXT NOT NULL,
    file_type TEXT NOT NULL,
    caption TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


QueueRow = tuple[str, str, Optional[str]]


class MediaGroupCollector:
    def __init__(self, bot: Bot, target_channel_id: int, db_path: str = "queue.db"):
        self.bot = bot
        self.target_channel_id = target_channel_id
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(self.send_one_from_queue, CronTrigger(minute="*/30"))
        self.scheduler.start()
        logger.info("Планувальник запущено: відправка за розкладом (кожні 30 хвилин)")

    async def initialize(self) -> None:
        try:
            self.db = await aiosqlite.connect(self.db_path)
            await self.db.execute(CREATE_QUEUE_TABLE_SQL)
            await self.db.commit()
            logger.info("Підключення до БД встановлено: %s", self.db_path)
        except Exception as e:
            logger.error("Помилка при ініціалізації БД: %s", e)
            raise

    def _require_db(self) -> aiosqlite.Connection:
        if not self.db:
            raise RuntimeError("Database connection not initialized")
        return self.db

    @staticmethod
    def _extract_media(message: Message) -> tuple[Optional[str], Optional[str]]:
        if message.video:
            return message.video.file_id, "video"
        if message.photo:
            return message.photo[-1].file_id, "photo"
        return None, None

    async def add_message(self, message: Message, custom_caption: str, custom_group_id: str) -> bool:
        file_id, file_type = self._extract_media(message)
        if not file_id or not file_type:
            logger.info("Повідомлення %s пропущено: підтримуються тільки photo/video", message.message_id)
            return False

        try:
            db = self._require_db()
            await db.execute(
                """
                INSERT INTO queue (media_group_id, origin_msg_id, file_id, file_type, caption)
                VALUES (?, ?, ?, ?, ?)
                """,
                (custom_group_id, message.message_id, file_id, file_type, custom_caption),
            )
            await db.commit()
            logger.info(
                "Додано в чергу: message_id=%s group_id=%s type=%s",
                message.message_id,
                custom_group_id,
                file_type,
            )
            return True
        except Exception as e:
            logger.error("Помилка БД: %s", e)
            return False

    async def update_message_in_db(self, message: Message, custom_caption: str = "") -> None:
        try:
            db = self._require_db()
            await db.execute(
                "UPDATE queue SET caption = ? WHERE origin_msg_id = ?",
                (custom_caption, message.message_id),
            )
            await db.commit()
        except Exception as e:
            logger.error("Помилка при оновленні бази: %s", e)

    async def get_queue_stats(self) -> tuple[int, int]:
        try:
            db = self._require_db()
            cursor = await db.execute("SELECT COUNT(*), COUNT(DISTINCT media_group_id) FROM queue")
            row = await cursor.fetchone()
            return (int(row[0] or 0), int(row[1] or 0)) if row else (0, 0)
        except Exception as e:
            logger.error("Помилка при читанні статистики черги: %s", e)
            return 0, 0

    async def send_one_from_queue(self) -> bool:
        try:
            db = self._require_db()
            group_id = await self._get_next_group_id(db)
            if not group_id:
                return False

            rows = await self._get_group_rows(db, group_id)
            if not rows:
                return False

            if len(rows) == 1:
                await self._send_single(rows[0])
                log_label = "Повідомлення"
            else:
                await self._send_album(rows)
                log_label = "Альбом"

            await self._delete_group(db, group_id)
            logger.info("✅ %s %s успішно відправлено", log_label, group_id)
            return True
        except Exception as e:
            logger.error("Помилка у send_one_from_queue: %s", e)
            return False

    async def _get_next_group_id(self, db: aiosqlite.Connection) -> Optional[str]:
        cursor = await db.execute("SELECT media_group_id FROM queue ORDER BY added_at ASC, id ASC LIMIT 1")
        row = await cursor.fetchone()
        return str(row[0]) if row else None

    async def _get_group_rows(self, db: aiosqlite.Connection, group_id: str) -> list[QueueRow]:
        cursor = await db.execute(
            "SELECT file_id, file_type, caption FROM queue WHERE media_group_id = ? ORDER BY id ASC",
            (group_id,),
        )
        return await cursor.fetchall()

    async def _delete_group(self, db: aiosqlite.Connection, group_id: str) -> None:
        await db.execute("DELETE FROM queue WHERE media_group_id = ?", (group_id,))
        await db.commit()

    async def _send_single(self, row: QueueRow) -> None:
        file_id, file_type, caption = row
        if file_type == "video":
            await self.bot.send_video(
                chat_id=self.target_channel_id,
                video=file_id,
                caption=caption,
                parse_mode="HTML",
            )
            return

        if file_type == "photo":
            await self.bot.send_photo(
                chat_id=self.target_channel_id,
                photo=file_id,
                caption=caption,
                parse_mode="HTML",
            )
            return

        raise ValueError(f"Unsupported queued file type: {file_type}")

    async def _send_album(self, rows: list[QueueRow]) -> None:
        media = []
        main_caption = rows[0][2]

        for index, (file_id, file_type, _) in enumerate(rows):
            caption = main_caption if index == 0 else None
            if file_type == "video":
                media.append(InputMediaVideo(media=file_id, caption=caption, parse_mode="HTML"))
            elif file_type == "photo":
                media.append(InputMediaPhoto(media=file_id, caption=caption, parse_mode="HTML"))
            else:
                raise ValueError(f"Unsupported queued file type: {file_type}")

        await self.bot.send_media_group(chat_id=self.target_channel_id, media=media)

    async def cleanup(self) -> None:
        try:
            self.scheduler.shutdown()
            if self.db:
                await self.db.close()
            logger.info("Media group collector очищено")
        except Exception as e:
            logger.error("Помилка при очищенні collector: %s", e)
