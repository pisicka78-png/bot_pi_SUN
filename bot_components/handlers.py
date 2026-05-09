from random import choice
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import ChatMemberUpdatedFilter, Command, MEMBER, LEFT
from aiogram.types import BotCommand, ChatMemberUpdated, KeyboardButton, Message, ReplyKeyboardMarkup

from bot_components.album_middleware import AlbumMiddleware
from bot_components.state import BotState
from bot_components.text_processing import replace_links
from config import (
    ACCOUNT_SOURCE_ENABLED,
    SEND_CRON_HOUR,
    SEND_CRON_MINUTE,
    SEND_INTERVAL_MINUTES,
    SEND_MODE,
    SOURCE_CHANNEL_ID,
    TARGET_CHANNEL_ID,
    TARGET_LINK,
)
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
BTN_MODE = "⚙️ Режим відправки"
BTN_SECRET = "🗝 Пасхалка"
BTN_HELP = "ℹ️ Допомога"
BTN_MODE_MANUAL = "✋ Ручний"
BTN_MODE_IMMEDIATE = "⚡ Одразу"
BTN_MODE_INTERVAL = "⏱ По інтервалу"
BTN_MODE_CRON = "🕒 По часу"
BTN_BACK = "⬅️ Назад"

MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_STATUS), KeyboardButton(text=BTN_SEND)],
        [KeyboardButton(text=BTN_CHECK), KeyboardButton(text=BTN_TEST_TARGET)],
        [KeyboardButton(text=BTN_MODE), KeyboardButton(text=BTN_SECRET)],
        [KeyboardButton(text=BTN_HELP)],
    ],
    resize_keyboard=True,
    input_field_placeholder="Обери дію",
)

MODE_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_MODE_MANUAL), KeyboardButton(text=BTN_MODE_IMMEDIATE)],
        [KeyboardButton(text=BTN_MODE_INTERVAL), KeyboardButton(text=BTN_MODE_CRON)],
        [KeyboardButton(text=BTN_BACK)],
    ],
    resize_keyboard=True,
    input_field_placeholder="Обери режим",
)

MODE_BY_BUTTON = {
    BTN_MODE_MANUAL: "manual",
    BTN_MODE_IMMEDIATE: "immediate",
    BTN_MODE_INTERVAL: "interval",
    BTN_MODE_CRON: "cron",
}


def build_caption(message: Message) -> str:
    source_html = message.html_text if (message.text or message.caption) else ""
    return replace_links(source_html, TARGET_LINK)


def with_easter_egg(text: str) -> str:
    return f"{text}\n\n_{choice(EASTER_EGGS)}_"


def send_mode_text(state: BotState | None = None) -> str:
    if state and state.collector:
        return state.collector.get_send_mode_text()

    if SEND_MODE == "manual":
        return "manual: тільки кнопка 🚀 Відправити або /send"
    if SEND_MODE == "immediate":
        return "immediate: відправка одразу після додавання в чергу"
    if SEND_MODE == "interval":
        return f"interval: автоматично кожні {SEND_INTERVAL_MINUTES} хв"
    if SEND_MODE == "cron":
        return f"cron: hour={SEND_CRON_HOUR}, minute={SEND_CRON_MINUTE}"
    return f"{SEND_MODE}: невідомий режим"


def update_env_value(key: str, value: str, env_path: str = ".env") -> None:
    path = Path(env_path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated = False

    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = f"{key}={value}"
            updated = True
            break

    if not updated:
        lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def help_text(state: BotState | None = None) -> str:
    return (
        "✅ Бот запущен.\n\n"
        "Он слушает посты в source-канале "
        f"`{SOURCE_CHANNEL_ID}` и отправляет очередь в target-канал `{TARGET_CHANNEL_ID}`.\n\n"
        "Кнопки меню:\n"
        f"{BTN_STATUS} - показать очередь\n"
        f"{BTN_SEND} - вручную отправить первый объект\n"
        f"{BTN_CHECK} - проверить доступ к каналам\n"
        f"{BTN_TEST_TARGET} - отправить тест в target\n"
        f"{BTN_MODE} - змінити режим відправки\n"
        f"{BTN_SECRET} - секретная пасхалка\n\n"
        f"Режим відправки: {send_mode_text(state)}\n\n"
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
            BotCommand(command="mode", description="Змінити режим відправки"),
            BotCommand(command="secret", description="Пасхалка"),
        ]
    )


def create_router(bot: Bot, state: BotState) -> Router:
    router = Router()
    router.channel_post.middleware(AlbumMiddleware())

    @router.channel_post(F.chat.id == int(SOURCE_CHANNEL_ID))
    async def handle_channel_message(message: Message, album: list[Message] | None = None) -> None:
        if ACCOUNT_SOURCE_ENABLED:
            logger.info(
                "Bot API source post skipped because ACCOUNT_SOURCE_ENABLED=true: message_id=%s",
                message.message_id,
            )
            return

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
            with_easter_egg(help_text(state)),
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
                f"Target: `{TARGET_CHANNEL_ID}`\n"
                f"Режим: `{send_mode_text(state)}`"
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
            with_easter_egg(help_text(state)),
            reply_markup=MENU_KEYBOARD,
            parse_mode="Markdown",
        )

    @router.message(Command("mode"))
    @router.message(F.text == BTN_MODE)
    async def mode_menu(message: Message) -> None:
        await message.answer(
            "⚙️ Обери режим відправки:\n\n"
            "✋ Ручний - тільки кнопка 🚀 Відправити.\n"
            "⚡ Одразу - новий пост одразу летить у target.\n"
            f"⏱ По інтервалу - кожні {SEND_INTERVAL_MINUTES} хв.\n"
            f"🕒 По часу - cron hour={SEND_CRON_HOUR}, minute={SEND_CRON_MINUTE}.\n\n"
            f"Поточний режим: {send_mode_text(state)}",
            reply_markup=MODE_KEYBOARD,
        )

    @router.message(F.text.in_(tuple(MODE_BY_BUTTON.keys())))
    async def set_mode(message: Message) -> None:
        if not state.collector:
            await message.answer("❌ Collector не ініціалізований.", reply_markup=MENU_KEYBOARD)
            return

        mode = MODE_BY_BUTTON[message.text]
        try:
            state.collector.set_send_mode(mode)
            update_env_value("SEND_MODE", mode)
            logger.info("Режим відправки змінено користувачем %s: %s", message.from_user.id, mode)
            await message.answer(
                with_easter_egg(f"✅ Режим змінено: `{send_mode_text(state)}`"),
                parse_mode="Markdown",
                reply_markup=MENU_KEYBOARD,
            )
        except Exception as e:
            logger.error("Не вдалося змінити режим відправки: %s", e)
            await message.answer(f"❌ Не вдалося змінити режим: `{e}`", parse_mode="Markdown", reply_markup=MENU_KEYBOARD)

    @router.message(F.text == BTN_BACK)
    async def back_to_menu(message: Message) -> None:
        await message.answer("Меню відкрите.", reply_markup=MENU_KEYBOARD)

    @router.message(Command("check"))
    @router.message(F.text == BTN_CHECK)
    async def check_access_command(message: Message) -> None:
        bot_info = await bot.get_me()
        lines = [f"Current bot: @{bot_info.username} / id {bot_info.id}", ""]
        if ACCOUNT_SOURCE_ENABLED:
            lines.append("Source читається акаунтом через Telethon, Bot API доступ до source не потрібен.")
            lines.append("")

        targets = (("Target", TARGET_CHANNEL_ID),) if ACCOUNT_SOURCE_ENABLED else (
            ("Source", SOURCE_CHANNEL_ID),
            ("Target", TARGET_CHANNEL_ID),
        )
        for label, chat_id in targets:
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
