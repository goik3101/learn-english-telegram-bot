import logging

from app import menu
from app.config import settings
from app.telegram_client import set_my_commands

logger = logging.getLogger(__name__)


async def register_bot_commands() -> None:
    """텔레그램 '/' 자동완성 메뉴에 영문 명령어를 등록 (관리자 채팅에는 관리자 전용 명령어도 추가)."""
    if not settings.bot_token:
        return

    await set_my_commands(menu.GENERAL_COMMANDS)
    logger.info("registered %d general bot commands", len(menu.GENERAL_COMMANDS))

    if settings.admin_telegram_id:
        await set_my_commands(menu.GENERAL_COMMANDS + menu.ADMIN_ONLY_COMMANDS, chat_id=settings.admin_telegram_id)
        logger.info("registered admin bot commands for chat %s", settings.admin_telegram_id)
