"""회화(M9) 플로우를 실제 DB/실제 Gemini로 자동 시뮬레이션 (수동 타이핑 없이 검증용, 1회성 스크립트)."""

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

REPLIES = [
    "I studied English and read a book about economics.",
    "Yes, it was interesting but a bit difficult for me.",
    "I usually study in the morning before work.",
    "I like learning new vocabulary the most.",
    "Maybe conversation practice, because it feels the hardest.",
]

captured: list[dict] = []


async def fake_send(chat_id, text, reply_markup=None):
    captured.append({"text": text, "reply_markup": reply_markup})
    print("SENT:", text[:150].replace("\n", " | "))


async def fake_answer_cb(callback_query_id, text=None):
    pass


async def fake_delete(chat_id, message_id):
    pass


router.send_message = fake_send
router.answer_callback_query = fake_answer_cb
router.delete_message = fake_delete


async def main() -> None:
    await init_db_pool()
    try:
        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": "/회화"}})

        for i, reply in enumerate(REPLIES, start=1):
            print(f"--- turn {i} ---")
            captured.clear()
            await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": reply}})

        assert "회화 연습 완료" in captured[-1]["text"], "5턴 후 완료 메시지가 와야 함"
        print("\n=== 모두 통과 (5턴 완료) ===")

        # 하루 1회 제한 확인: 다시 시작하면 차단되어야 함
        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": "/회화"}})
        assert "이미 완료" in captured[-1]["text"], "같은 날 재시작은 차단되어야 함"
        print("=== 하루 1회 제한 확인 OK ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
