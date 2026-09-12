import html
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def spoiler_html(text: str) -> str:
    """탭하면 보이고 다시 탭하면 가려지는 텔레그램 스포일러(모자이크) — HTML parse_mode 전용.

    정답을 곧바로 노출하지 않고 사용자가 원할 때만 확인하게 할 때 쓴다(예: 단어학습 주관식
    직전 오답 공개). 이 헬퍼로 감싼 부분 외의 문구도 HTML 특수문자가 섞이면 파싱 오류가
    나므로, 같은 메시지 안의 나머지 동적 문자열도 html.escape()로 함께 이스케이프할 것.
    """
    return f'<span class="tg-spoiler">{html.escape(text)}</span>'


async def _post(method: str, payload: dict) -> None:
    if not settings.bot_token:
        logger.warning("BOT_TOKEN not set — skipping Telegram call %s: %s", method, payload)
        return

    url = f"{TELEGRAM_API_BASE}/bot{settings.bot_token}/{method}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            logger.error("Telegram %s failed (%s): %s", method, response.status_code, response.text)


def _split_long_text(text: str, limit: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """텔레그램 메시지 4096자 제한을 넘는 텍스트(AI 생성 지문/설명 등)를 여러 메시지로 나눈다.

    안 나누면 sendMessage가 400을 반환해 메시지 전체가 사용자에게 조용히 전달되지 않는다
    (_post는 실패를 로그만 남기고 호출부에 알리지 않음).
    """
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


async def send_message(
    chat_id: int | str, text: str, reply_markup: Optional[dict] = None, parse_mode: Optional[str] = None
) -> None:
    chunks = _split_long_text(text)
    for index, chunk in enumerate(chunks):
        payload: dict = {"chat_id": chat_id, "text": chunk}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup and index == len(chunks) - 1:
            payload["reply_markup"] = reply_markup
        await _post("sendMessage", payload)


async def send_voice(chat_id: int | str, audio_bytes: bytes, caption: Optional[str] = None) -> None:
    """OGG_OPUS 등 텔레그램이 지원하는 인코딩의 음성을 음성메시지로 전송 (M16 발음듣기)."""
    if not settings.bot_token:
        logger.warning("BOT_TOKEN not set — skipping Telegram call sendVoice")
        return

    url = f"{TELEGRAM_API_BASE}/bot{settings.bot_token}/sendVoice"
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption
    files = {"voice": ("speech.ogg", audio_bytes, "audio/ogg")}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, data=data, files=files)
        if response.status_code != 200:
            logger.error("Telegram sendVoice failed (%s): %s", response.status_code, response.text)


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
