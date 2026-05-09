from dataclasses import dataclass
from typing import Optional

from media_group_handler import MediaGroupCollector


@dataclass
class BotState:
    collector: Optional[MediaGroupCollector] = None
