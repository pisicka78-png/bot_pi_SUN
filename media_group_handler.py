import asyncio
from pathlib import Path
from typing import Optional

import aiosqlite
from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import SEND_CRON_HOUR, SEND_CRON_MINUTE, SEND_INTERVAL_MINUTES, SEND_MODE
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
        self.send_mode = SEND_MODE
        self.send_interval_minutes = SEND_INTERVAL_MINUTES
        self.send_cron_minute = SEND_CRON_MINUTE
        self.send_cron_hour = SEND_CRON_HOUR

        self.scheduler = AsyncIOScheduler()
        self._setup_scheduler()

    def _setup_scheduler(self) -> None:
        self.scheduler.remove_all_jobs()

        if self.send_mode == "manual":
            logger.info("Режим відправки: manual. Автоматична відправка вимкнена")
            return

        if self.send_mode == "immediate":
            logger.info("Режим відправки: immediate. Черга відправляється одразу після додавання")
            return

        if self.send_mode == "interval":
            self.scheduler.add_job(self.send_one_from_queue, IntervalTrigger(minutes=self.send_interval_minutes))
            if not self.scheduler.running:
                self.scheduler.start()
            logger.info("Режим відправки: interval, кожні %s хв", self.send_interval_minutes)
            return

        if self.send_mode == "cron":
            self.scheduler.add_job(
                self.send_one_from_queue,
                CronTrigger(hour=self.send_cron_hour, minute=self.send_cron_minute),
            )
            if not self.scheduler.running:
                self.scheduler.start()
            logger.info("Режим відправки: cron, hour=%s minute=%s", self.send_cron_hour, self.send_cron_minute)
            return

        logger.warning("Невідомий SEND_MODE=%s. Автоматична відправка вимкнена", self.send_mode)

    def set_send_mode(self, mode: str) -> None:
        if mode not in {"manual", "immediate", "interval", "cron"}:
            raise ValueError(f"Unsupported send mode: {mode}")

        self.send_mode = mode
        self._setup_scheduler()

    def get_send_mode_text(self) -> str:
        if self.send_mode == "manual":
            return "manual: тільки кнопка 🚀 Відправити або /send"
        if self.send_mode == "immediate":
            return "immediate: відправка одразу після додавання в чергу"
        if self.send_mode == "interval":
            return f"interval: автоматично кожні {self.send_interval_minutes} хв"
        if self.send_mode == "cron":
            return f"cron: hour={self.send_cron_hour}, minute={self.send_cron_minute}"
        return f"{self.send_mode}: невідомий режим"

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

        return await self._insert_queue_item(
            origin_msg_id=message.message_id,
            group_id=custom_group_id,
            file_id=file_id,
            file_type=file_type,
            caption=custom_caption,
            log_prefix="Додано в чергу",
        )

    async def add_local_media(
        self,
        origin_msg_id: int,
        group_id: str,
        file_path: str,
        file_type: str,
        caption: str,
    ) -> bool:
        if file_type not in {"local_video", "local_photo"}:
            logger.error("Непідтримуваний локальний тип медіа: %s", file_type)
            return False

        return await self._insert_queue_item(
            origin_msg_id=origin_msg_id,
            group_id=group_id,
            file_id=file_path,
            file_type=file_type,
            caption=caption,
            log_prefix="Додано локальне медіа в чергу",
        )

    async def _insert_queue_item(
        self,
        origin_msg_id: int,
        group_id: str,
        file_id: str,
        file_type: str,
        caption: str,
        log_prefix: str,
    ) -> bool:
        try:
            db = self._require_db()
            await db.execute(
                """
                INSERT INTO queue (media_group_id, origin_msg_id, file_id, file_type, caption)
                VALUES (?, ?, ?, ?, ?)
                """,
                (group_id, origin_msg_id, file_id, file_type, caption),
            )
            await db.commit()
            logger.info(
                "%s: message_id=%s group_id=%s type=%s file=%s",
                log_prefix,
                origin_msg_id,
                group_id,
                file_type,
                file_id,
            )
            await self.send_after_enqueue()
            return True
        except Exception as e:
            logger.error("Помилка БД при додаванні в чергу: %s", e)
            return False

    async def send_after_enqueue(self) -> None:
        if self.send_mode == "immediate":
            await self.send_one_from_queue()

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
            if not self._local_files_exist(rows):
                await self._delete_group(db, group_id)
                logger.error("Групу %s видалено з черги: локальний файл відсутній", group_id)
                return False

            if len(rows) == 1:
                await self._send_single(rows[0])
                log_label = "Повідомлення"
            else:
                await self._send_album(rows)
                log_label = "Альбом"

            await self._delete_group(db, group_id)
            await self._cleanup_local_files(rows)
            logger.info("%s %s успішно відправлено", log_label, group_id)
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

        if file_type == "local_video":
            await self.bot.send_video(
                chat_id=self.target_channel_id,
                video=FSInputFile(file_id),
                caption=caption,
                parse_mode="HTML",
            )
            return

        if file_type == "local_photo":
            await self.bot.send_photo(
                chat_id=self.target_channel_id,
                photo=FSInputFile(file_id),
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
            elif file_type == "local_video":
                media.append(InputMediaVideo(media=FSInputFile(file_id), caption=caption, parse_mode="HTML"))
            elif file_type == "local_photo":
                media.append(InputMediaPhoto(media=FSInputFile(file_id), caption=caption, parse_mode="HTML"))
            else:
                raise ValueError(f"Unsupported queued file type: {file_type}")

        await self.bot.send_media_group(chat_id=self.target_channel_id, media=media)

    @staticmethod
    def _local_files_exist(rows: list[QueueRow]) -> bool:
        for file_path, file_type, _ in rows:
            if file_type.startswith("local_") and not Path(file_path).exists():
                return False
        return True

    @staticmethod
    async def _cleanup_local_files(rows: list[QueueRow]) -> None:
        for file_path, file_type, _ in rows:
            if not file_type.startswith("local_"):
                continue
            for attempt in range(3):
                try:
                    Path(file_path).unlink(missing_ok=True)
                    break
                except PermissionError:
                    if attempt == 2:
                        logger.error("Не вдалося видалити локальний файл %s: файл зайнятий", file_path)
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error("Не вдалося видалити локальний файл %s: %s", file_path, e)
                    break

    async def cleanup(self) -> None:
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
            if self.db:
                await self.db.close()
            logger.info("Media group collector очищено")
        except Exception as e:
            logger.error("Помилка при очищенні collector: %s", e)
