from dataclasses import dataclass
from typing import Optional

from bot_components.account_source_listener import AccountSourceListener
from media_group_handler import MediaGroupCollector


@dataclass
class BotState:
    collector: Optional[MediaGroupCollector] = None
    account_source_listener: Optional[AccountSourceListener] = None
