"""오늘의 학습(M7) 전체 플로우를 실제 DB로 자동 시뮬레이션 (수동 클릭 없이 검증용, 1회성 스크립트).

관리자 telegram_id로 실제 handle_update를 반복 호출해 카드에 [아는단어], 문법 문제에 첫 번째 선택지로
자동 응답하며 끝까지 진행한다. send_message 등은 실제 텔레그램 대신 캡처만 한다(실제 발송 없음).
"""

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

captured: list[dict] = []


async def fake_send(chat_id, text, reply_markup=None):
    captured.append({"text": text, "reply_markup": reply_markup})
    print("SENT:", text[:100].replace("\n", " | "))


async def fake_answer_cb(callback_query_id, text=None):
    pass


async def fake_delete(chat_id, message_id):
    pass


router.send_message = fake_send
router.answer_callback_query = fake_answer_cb
router.delete_message = fake_delete


def _pick_callback_data(reply_markup: dict) -> str:
    buttons = [b for row in reply_markup["inline_keyboard"] for b in row]
    for b in buttons:
        if b["callback_data"].startswith("vocab:known:"):
            return b["callback_data"]
    return buttons[0]["callback_data"]


async def main() -> None:
    await init_db_pool()
    try:
        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": "/오늘학습"}})

        for step in range(300):
            if any("모두 마쳤습니다" in m["text"] or "이미 완료했습니다" in m["text"] for m in captured):
                print("=== DONE ===")
                return

            kb_msg = None
            for m in reversed(captured):
                if m["reply_markup"] and "inline_keyboard" in m["reply_markup"]:
                    kb_msg = m
                    break
            if kb_msg is None:
                print("=== 더 이상 진행할 버튼 메시지가 없음 (예상치 못한 정지) ===")
                return

            cb_data = _pick_callback_data(kb_msg["reply_markup"])
            captured.clear()
            await router.handle_update(
                {
                    "callback_query": {
                        "id": f"sim{step}",
                        "from": {"id": CHAT_ID},
                        "message": {"chat": {"id": CHAT_ID}, "message_id": 10000 + step},
                        "data": cb_data,
                    }
                }
            )

        print("=== 루프 상한 도달 (300회) ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
