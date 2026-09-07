import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


async def _post(method: str, payload: dict) -> None:
    if not settings.bot_token:
        logger.warning("BOT_TOKEN not set — skipping Telegram call %s: %s", method, payload)
        return

    url = f"{TELEGRAM_API_BASE}/bot{settings.bot_token}/{method}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            logger.error("Telegram %s failed (%s): %s", method, response.status_code, response.text)


async def send_message(chat_id: int | str, text: str, reply_markup: Optional[dict] = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await _post("sendMessage", payload)


def build_inline_keyboard(buttons: list[tuple[str, str]], columns: int = 1) -> dict:
    """buttons: [(표시텍스트, callback_data), ...] -> Telegram inline_keyboard 구조 (섹션15-6)."""
    keyboard: list[list[dict]] = []
    row: list[dict] = []
    for label, callback_data in buttons:
        row.append({"text": label, "callback_data": callback_data})
        if len(row) == columns:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return {"inline_keyboard": keyboard}


def build_reply_keyboard(rows: list[list[str]]) -> dict:
    """rows: [[버튼라벨, ...], ...] -> Telegram reply_keyboard 구조 (메인 메뉴, 섹션15-6)."""
    return {
        "keyboard": [[{"text": label} for label in row] for row in rows],
        "resize_keyboard": True,
    }


async def answer_callback_query(callback_query_id: str, text: Optional[str] = None) -> None:
    payload: dict = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    await _post("answerCallbackQuery", payload)


async def delete_message(chat_id: int | str, message_id: int) -> None:
    await _post("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


async def set_my_commands(commands: list[tuple[str, str]], chat_id: Optional[int | str] = None) -> None:
    """텔레그램 '/' 자동완성 메뉴에 명령어를 등록한다.

    명령어 이름은 텔레그램 규칙상 영문 소문자/숫자/밑줄만 가능해서 한글 명령어는 등록할 수 없다
    (한글 명령어 자체는 계속 타이핑으로 동작함, 자동완성 목록에만 안 뜰 뿐).
    chat_id를 주면 해당 채팅에만(예: 관리자) 추가 명령어를 노출한다.
    """
    payload: dict = {"commands": [{"command": cmd, "description": desc} for cmd, desc in commands]}
    if chat_id is not None:
        payload["scope"] = {"type": "chat", "chat_id": chat_id}
    await _post("setMyCommands", payload)
