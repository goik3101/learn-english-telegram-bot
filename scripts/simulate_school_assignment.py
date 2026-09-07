"""학교 수행평가 텍스트 학습(M12) 플로우를 실제 DB/실제 Gemini로 자동 시뮬레이션 (1회성 스크립트)."""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.config import settings  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.handlers import router  # noqa: E402

if not settings.admin_telegram_id:
    raise SystemExit("ADMIN_TELEGRAM_ID가 .env에 설정되어 있지 않습니다.")
TELEGRAM_ID = settings.admin_telegram_id
CHAT_ID = int(TELEGRAM_ID)

SAMPLE_TEXT = (
    "Coral reefs, often called the rainforests of the sea, have been severely damaged by rising ocean "
    "temperatures over the past two decades. Scientists have found that even a two-degree increase can "
    "trigger widespread bleaching, which threatens the thousands of marine species that depend on reefs "
    "for shelter and food."
)

captured: list[dict] = []


async def fake_send(chat_id, text, reply_markup=None):
    captured.append({"text": text, "reply_markup": reply_markup})
    print("SENT:", text[:200].replace("\n", " | "))


async def fake_answer_cb(callback_query_id, text=None):
    pass


async def fake_delete(chat_id, message_id):
    pass


router.send_message = fake_send
router.answer_callback_query = fake_answer_cb
router.delete_message = fake_delete


def _pick_callback_data(reply_markup: dict, prefer_prefix: str | None = None) -> str:
    buttons = [b for row in reply_markup["inline_keyboard"] for b in row]
    if prefer_prefix:
        for b in buttons:
            if b["callback_data"].startswith(prefer_prefix):
                return b["callback_data"]
    return buttons[0]["callback_data"]


def _latest_keyboard_message():
    for m in reversed(captured):
        if m["reply_markup"] and "inline_keyboard" in m["reply_markup"]:
            return m
    return None


async def main() -> None:
    await init_db_pool()
    try:
        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": "/수행평가"}})

        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": SAMPLE_TEXT}})

        # 단어 카드가 있으면 전부 [아는단어]로 빠르게 넘어간다 (예상문제 첫 문항이 뜰 때까지)
        for _ in range(20):
            if any("예상문제 1" in m["text"] for m in captured):
                break
            kb_msg = _latest_keyboard_message()
            if kb_msg is None:
                break
            cb_data = _pick_callback_data(kb_msg["reply_markup"], prefer_prefix="vocab:known:")
            captured.clear()
            await router.handle_update(
                {
                    "callback_query": {
                        "id": "sim",
                        "from": {"id": CHAT_ID},
                        "message": {"chat": {"id": CHAT_ID}, "message_id": 1},
                        "data": cb_data,
                    }
                }
            )

        all_texts = "\n".join(m["text"] for m in captured)
        assert "예상문제 1" in all_texts, "예상 시험문제 1번에 도달해야 함"
        print("=== 문법해설 + 예상문제 1번 도달 OK ===")

        # 예상문제를 끝까지 정답으로 진행
        for _ in range(10):
            kb_msg = _latest_keyboard_message()
            if kb_msg is None:
                break
            buttons = [b for row in kb_msg["reply_markup"]["inline_keyboard"] for b in row]
            cb_data = buttons[0]["callback_data"]
            captured.clear()
            await router.handle_update(
                {
                    "callback_query": {
                        "id": "sim",
                        "from": {"id": CHAT_ID},
                        "message": {"chat": {"id": CHAT_ID}, "message_id": 1},
                        "data": cb_data,
                    }
                }
            )
            if any("학교 수행평가 학습 완료" in m["text"] for m in captured):
                break

        assert any("학교 수행평가 학습 완료" in m["text"] for m in captured), "완료 메시지가 와야 함"
        print("=== 완료 메시지 확인 OK ===")
        print("\n=== 모두 통과 ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
