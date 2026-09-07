"""텍스트 붙여넣기 학습(M11) 플로우를 실제 DB/실제 Gemini로 자동 시뮬레이션 (1회성 스크립트)."""

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
    "Renewable energy sources such as solar and wind power are becoming increasingly cost-competitive "
    "with fossil fuels. Many governments are now offering substantial subsidies to accelerate this "
    "transition, hoping to mitigate the long-term consequences of climate change."
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
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": "/텍스트학습"}})

        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": SAMPLE_TEXT}})

        # 단어 카드가 있으면 전부 [아는단어]로 빠르게 넘어간다
        for _ in range(20):
            if any("한국어로 해석" in m["text"] for m in captured):
                break
            kb_msg = None
            for m in reversed(captured):
                if m["reply_markup"] and "inline_keyboard" in m["reply_markup"]:
                    kb_msg = m
                    break
            if kb_msg is None:
                break
            cb_data = _pick_callback_data(kb_msg["reply_markup"])
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

        assert any("한국어로 해석" in m["text"] for m in captured), "해석 요청 단계에 도달해야 함"
        print("=== 해석 요청 단계 도달 OK ===")

        captured.clear()
        await router.handle_update(
            {
                "message": {
                    "chat": {"id": CHAT_ID},
                    "text": "재생에너지가 화석연료와 가격 경쟁력을 갖춰가고 있고, 정부들이 보조금을 주고 있다.",
                }
            }
        )
        assert any("완료" in m["text"] for m in captured), "완료 메시지가 와야 함"
        print("=== 완료 메시지 확인 OK ===")
        print("\n=== 모두 통과 ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
