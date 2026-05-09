"""
Telegram Media Queue Bot entrypoint.
"""
import asyncio
import sys

from aiogram import Bot, Dispatcher

from bot_components.handlers import create_router, set_bot_menu
from bot_components.state import BotState
from config import BOT_TOKEN, SOURCE_CHANNEL_ID, TARGET_CHANNEL_ID
from logger_config import logger
from media_group_handler import MediaGroupCollector


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher()
state = BotState()


async def setup_bot() -> None:
    try:
        bot_info = await bot.get_me()
        logger.info("Bot started: @%s (ID: %s)", bot_info.username, bot_info.id)

        state.collector = MediaGroupCollector(
            bot=bot,
            target_channel_id=TARGET_CHANNEL_ID,
            db_path="queue.db",
        )
        await state.collector.initialize()
        await set_bot_menu(bot)

        dispatcher.include_router(create_router(bot, state))
        logger.info("Forwarding messages from %s to %s", SOURCE_CHANNEL_ID, TARGET_CHANNEL_ID)
    except Exception as e:
        logger.error("Failed to setup bot: %s", e)
        raise


async def cleanup_bot() -> None:
    if state.collector:
        await state.collector.cleanup()
        logger.info("Media group collector cleaned up")

    await bot.session.close()
    logger.info("Bot session closed")


async def main() -> None:
    await setup_bot()

    try:
        logger.info("Starting bot polling...")
        await dispatcher.start_polling(
            bot,
            allowed_updates=["message", "channel_post", "edited_channel_post", "my_chat_member"],
            skip_updates=True,
        )
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error("Bot error: %s", e)
    finally:
        await cleanup_bot()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as e:
        logger.error("Fatal error: %s", e)
