"""
Logging configuration
"""
import sys
import logging
from config import LOG_LEVEL

# Налаштування виводу в UTF-8 для Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

# Обмежте рівень логування для сторонніх бібліотек
logging.getLogger("aiosqlite").setLevel(logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.INFO)

logger = logging.getLogger(__name__)
