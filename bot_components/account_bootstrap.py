from dataclasses import dataclass
from typing import Optional

from config import (
    ACCOUNT_BOOTSTRAP_ENABLED,
    BOT_USERNAME,
    TARGET_CHANNEL_REF,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_SESSION,
    TELEGRAM_USER_PHONE,
)
from logger_config import logger


@dataclass(frozen=True)
class AccountBootstrapConfig:
    api_id: int
    api_hash: str
    phone: str
    session: str
    bot_username: str
    target_ref: str


def _build_config(bot_username_from_api: Optional[str]) -> Optional[AccountBootstrapConfig]:
    if not ACCOUNT_BOOTSTRAP_ENABLED:
        return None

    bot_username = (BOT_USERNAME or bot_username_from_api or "").lstrip("@")
    missing = [
        name
        for name, value in {
            "TELEGRAM_API_ID": TELEGRAM_API_ID,
            "TELEGRAM_API_HASH": TELEGRAM_API_HASH,
            "TELEGRAM_USER_PHONE": TELEGRAM_USER_PHONE,
            "BOT_USERNAME": bot_username,
            "TARGET_CHANNEL_REF": TARGET_CHANNEL_REF,
        }.items()
        if not value
    ]
    if missing:
        logger.warning("Account bootstrap skipped. Missing values: %s", ", ".join(missing))
        return None

    return AccountBootstrapConfig(
        api_id=int(TELEGRAM_API_ID),
        api_hash=str(TELEGRAM_API_HASH),
        phone=str(TELEGRAM_USER_PHONE),
        session=TELEGRAM_SESSION,
        bot_username=bot_username,
        target_ref=str(TARGET_CHANNEL_REF),
    )


async def ensure_bot_in_channels(bot_username_from_api: Optional[str]) -> None:
    config = _build_config(bot_username_from_api)
    if not config:
        return

    try:
        from telethon import TelegramClient
        from telethon.errors import ChatAdminRequiredError, UserAlreadyParticipantError
        from telethon.tl.functions.channels import EditAdminRequest, InviteToChannelRequest
        from telethon.tl.types import ChatAdminRights
    except ImportError:
        logger.error("Account bootstrap enabled, but Telethon is not installed. Run: python -m pip install -r requirements.txt")
        return

    rights = ChatAdminRights(
        change_info=False,
        post_messages=True,
        edit_messages=True,
        delete_messages=True,
        ban_users=False,
        invite_users=True,
        pin_messages=False,
        add_admins=False,
        anonymous=False,
        manage_call=False,
    )

    client = TelegramClient(config.session, config.api_id, config.api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.info("Потрібен вхід у Telegram акаунт. Введи код у консолі першого запуску.")
            await client.start(phone=config.phone)

        bot_entity = await client.get_entity(config.bot_username)

        for label, channel_ref in (("target", config.target_ref),):
            try:
                channel = await client.get_entity(channel_ref)
            except Exception as e:
                logger.error("Failed to resolve %s channel %s: %s", label, channel_ref, e)
                continue

            try:
                await client(InviteToChannelRequest(channel=channel, users=[bot_entity]))
                logger.info("Bot @%s added to %s channel", config.bot_username, label)
            except UserAlreadyParticipantError:
                logger.info("Bot @%s already exists in %s channel", config.bot_username, label)
            except Exception as e:
                logger.error(
                    "Failed to add bot @%s to %s channel. "
                    "Account must be channel owner/admin with invite rights. Error: %s",
                    config.bot_username,
                    label,
                    e,
                )

            try:
                await client(
                    EditAdminRequest(
                        channel=channel,
                        user_id=bot_entity,
                        admin_rights=rights,
                        rank="Queue bot",
                    )
                )
                logger.info("Bot @%s promoted in %s channel", config.bot_username, label)
            except ChatAdminRequiredError:
                logger.error("Account is not allowed to manage admins in %s channel", label)
            except Exception as e:
                logger.error("Failed to promote bot in %s channel: %s", label, e)
    finally:
        await client.disconnect()
