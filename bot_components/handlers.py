from random import choice

from aiogram import Bot, F, Router
from aiogram.filters import ChatMemberUpdatedFilter, Command, MEMBER, LEFT
from aiogram.types import BotCommand, ChatMemberUpdated, KeyboardButton, Message, ReplyKeyboardMarkup

from bot_components.album_middleware import AlbumMiddleware
from bot_components.state import BotState
from bot_components.text_processing import replace_links
from config import SOURCE_CHANNEL_ID, TARGET_CHANNEL_ID, TARGET_LINK
from logger_config import logger


EASTER_EGGS = [
    "P.S. Черга під контролем, паніки немає.",
    "Міні-пасхалка: якщо БД порожня, це не дзен, це просто /status.",
    "Операція пройшла без драматичних монологів.",
    "Секретний відділ черги каже: все по плану.",
    "Бот не спить. Бот просто економить відповіді.",
]

SECRET_MESSAGES = [
    "Секрет знайдено: найскладніше в боті було додати правильного бота в канал.",
    "Архіваріус file_id доповідає: відео не загублені, вони просто живуть у Telegram.",
    "Рівень доступу: людина, яка знає, де лежить queue.db.",
]

BTN_STATUS = "📦 Статус"
BTN_SEND = "🚀 Відправити"
BTN_CHECK = "🔍 Перевірити доступ"
BTN_TEST_TARGET = "🎯 Тест target"
BTN_SECRET = "🗝 Пасхалка"
BTN_HELP = "ℹ️ Допомога"

MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_STATUS), KeyboardButton(text=BTN_SEND)],
        [KeyboardButton(text=BTN_CHECK), KeyboardButton(text=BTN_TEST_TARGET)],
        [KeyboardButton(text=BTN_SECRET), KeyboardButton(text=BTN_HELP)],
    ],
    resize_keyboard=True,
    input_field_placeholder="Обери дію",
)


def build_caption(message: Message) -> str:
    source_html = message.html_text if (message.text or message.caption) else ""
    return replace_links(source_html, TARGET_LINK)


def with_easter_egg(text: str) -> str:
    return f"{text}\n\n_{choice(EASTER_EGGS)}_"


def help_text() -> str:
    return (
        "✅ Бот запущен.\n\n"
        "Он слушает посты в source-канале "
        f"`{SOURCE_CHANNEL_ID}` и отправляет очередь в target-канал `{TARGET_CHANNEL_ID}`.\n\n"
        "Кнопки меню:\n"
        f"{BTN_STATUS} - показать очередь\n"
        f"{BTN_SEND} - вручную отправить первый объект\n"
        f"{BTN_CHECK} - проверить доступ к каналам\n"
        f"{BTN_TEST_TARGET} - отправить тест в target\n"
        f"{BTN_SECRET} - секретная пасхалка\n\n"
        "Команды тоже работают: /status, /send, /check, /testtarget, /secret."
    )


async def set_bot_menu(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Відкрити меню"),
            BotCommand(command="status", description="Показати чергу"),
            BotCommand(command="send", description="Відправити перший об'єкт"),
            BotCommand(command="check", description="Перевірити доступи"),
            BotCommand(command="testtarget", description="Тест target-каналу"),
            BotCommand(command="secret", description="Пасхалка"),
        ]
    )


def create_router(bot: Bot, state: BotState) -> Router:
    router = Router()
    router.channel_post.middleware(AlbumMiddleware())

    @router.channel_post(F.chat.id == int(SOURCE_CHANNEL_ID))
    async def handle_channel_message(message: Message, album: list[Message] | None = None) -> None:
        messages_to_process = album if album else [message]
        group_id = message.media_group_id or f"single_{message.message_id}"

        logger.info(
            "Отримано пост із source: chat_id=%s message_id=%s group_id=%s items=%s has_photo=%s has_video=%s",
            message.chat.id,
            message.message_id,
            group_id,
            len(messages_to_process),
            bool(message.photo),
            bool(message.video),
        )

        if not state.collector:
            logger.error("Collector не ініціалізований")
            return

        for msg in messages_to_process:
            await state.collector.add_message(
                msg,
                custom_caption=build_caption(msg),
                custom_group_id=group_id,
            )

    @router.edited_channel_post(F.chat.id == int(SOURCE_CHANNEL_ID))
    async def handle_edited_channel_post(message: Message) -> None:
        if state.collector:
            await state.collector.update_message_in_db(
                message,
                custom_caption=build_caption(message),
            )
            logger.info("Текст повідомлення %s оновлено в черзі.", message.message_id)

    @router.channel_post()
    async def handle_unmatched_channel_post(message: Message) -> None:
        logger.info(
            "Пропущено channel_post з іншого каналу: chat_id=%s title=%s message_id=%s",
            message.chat.id,
            message.chat.title,
            message.message_id,
        )

    @router.edited_channel_post()
    async def handle_unmatched_edited_channel_post(message: Message) -> None:
        logger.info(
            "Пропущено edited_channel_post з іншого каналу: chat_id=%s title=%s message_id=%s",
            message.chat.id,
            message.chat.title,
            message.message_id,
        )

    @router.message(Command("start"))
    async def start_command(message: Message) -> None:
        await message.answer(
            with_easter_egg(help_text()),
            reply_markup=MENU_KEYBOARD,
            parse_mode="Markdown",
        )

    @router.message(Command("status"))
    @router.message(F.text == BTN_STATUS)
    async def status_command(message: Message) -> None:
        if not state.collector:
            await message.answer("❌ Collector не инициализирован.")
            return

        files_count, groups_count = await state.collector.get_queue_stats()
        await message.answer(
            with_easter_egg(
                "📦 Очередь:\n"
                f"Медиафайлов: {files_count}\n"
                f"Груп/постов: {groups_count}\n\n"
                f"Source: `{SOURCE_CHANNEL_ID}`\n"
                f"Target: `{TARGET_CHANNEL_ID}`"
            ),
            parse_mode="Markdown",
            reply_markup=MENU_KEYBOARD,
        )

    @router.message(Command("secret"))
    @router.message(F.text == BTN_SECRET)
    async def secret_command(message: Message) -> None:
        await message.answer(f"🗝 {choice(SECRET_MESSAGES)}", reply_markup=MENU_KEYBOARD)

    @router.message(F.text == BTN_HELP)
    async def help_button(message: Message) -> None:
        await message.answer(
            with_easter_egg(help_text()),
            reply_markup=MENU_KEYBOARD,
            parse_mode="Markdown",
        )

    @router.message(Command("check"))
    @router.message(F.text == BTN_CHECK)
    async def check_access_command(message: Message) -> None:
        bot_info = await bot.get_me()
        lines = [f"Current bot: @{bot_info.username} / id {bot_info.id}", ""]

        for label, chat_id in (("Source", SOURCE_CHANNEL_ID), ("Target", TARGET_CHANNEL_ID)):
            try:
                chat = await bot.get_chat(chat_id)
                try:
                    member = await bot.get_chat_member(chat.id, bot_info.id)
                    status = getattr(member, "status", "unknown")
                    lines.append(f"OK {label}: {chat.id} / @{chat.username} / {status}")
                except Exception as member_error:
                    lines.append(
                        f"WARN {label}: {chat.id} / @{chat.username}, но статус бота не читается: {member_error}"
                    )
            except Exception as chat_error:
                lines.append(f"ERROR {label}: {chat_id} не доступен: {chat_error}")

        await message.answer("\n".join(lines), reply_markup=MENU_KEYBOARD)

    @router.message(Command("testtarget"))
    @router.message(F.text == BTN_TEST_TARGET)
    async def test_target_command(message: Message) -> None:
        try:
            sent = await bot.send_message(
                chat_id=TARGET_CHANNEL_ID,
                text="Тестовое сообщение от бота. Target доступен.",
            )
            await message.answer(
                with_easter_egg(f"✅ Target доступен. Отправлено сообщение id `{sent.message_id}`."),
                parse_mode="Markdown",
                reply_markup=MENU_KEYBOARD,
            )
        except Exception as e:
            await message.answer(
                f"❌ Target недоступен для отправки: `{e}`",
                parse_mode="Markdown",
                reply_markup=MENU_KEYBOARD,
            )

    @router.message(Command("send"))
    @router.message(F.text == BTN_SEND)
    async def manual_send_command(message: Message) -> None:
        if not state.collector:
            await message.answer("❌ Помилка: Collector не ініціалізований.", reply_markup=MENU_KEYBOARD)
            return

        logger.info("Ручний запуск відправки користувачем %s", message.from_user.id)
        sent = await state.collector.send_one_from_queue()
        if sent:
            await message.answer(
                with_easter_egg("✅ Перший об'єкт із черги відправлено."),
                parse_mode="Markdown",
                reply_markup=MENU_KEYBOARD,
            )
        else:
            await message.answer(
                with_easter_egg("ℹ️ Черга порожня або відправка не вдалася. Дивись bot.log."),
                parse_mode="Markdown",
                reply_markup=MENU_KEYBOARD,
            )

    @router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
    async def on_bot_added_to_channel(event: ChatMemberUpdated) -> None:
        logger.info("Bot added to chat %s (%s)", event.chat.id, event.chat.title)

    @router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=LEFT))
    async def on_bot_removed_from_channel(event: ChatMemberUpdated) -> None:
        logger.info("Bot removed from chat %s (%s)", event.chat.id, event.chat.title)

    return router
