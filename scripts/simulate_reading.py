"""해석(M8) 플로우를 실제 DB/실제 Gemini로 자동 시뮬레이션 (수동 타이핑 없이 검증용, 1회성 스크립트).

1) 일부러 부실한 해석을 2번 보내 힌트->정답공개 흐름을 확인
2) 모범 번역을 그대로 보내 "한 번에 정답" 흐름을 확인
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.config import settings  # noqa: E402
from app.db import close_db_pool, get_pool, init_db_pool  # noqa: E402
from app.handlers import router  # noqa: E402

if not settings.admin_telegram_id:
    raise SystemExit("ADMIN_TELEGRAM_ID가 .env에 설정되어 있지 않습니다.")
TELEGRAM_ID = settings.admin_telegram_id
CHAT_ID = int(TELEGRAM_ID)

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


async def lookup_model_translation(passage_text: str) -> str:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select model_translation_ko from reading_passages where passage_text = %s", (passage_text,)
            )
            row = await cur.fetchone()
            return row["model_translation_ko"]


async def main() -> None:
    await init_db_pool()
    try:
        print("=== 라운드 1: 부실한 해석 2번 -> 힌트 후 정답공개 ===")
        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": "/해석"}})
        passage_text = captured[-1]["text"].split("\n\n", 1)[-1]

        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": "잘 모르겠어요 대충 이런 내용?"}})
        assert "모범 번역" not in captured[-1]["text"], "1차 시도에서 정답이 공개되면 안 됨"
        print("1차 피드백 OK (정답 미공개):", captured[-1]["text"][:120])

        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": "여전히 잘 모르겠어요"}})
        assert "모범 번역" in captured[-1]["text"], "2차(최대) 시도에서는 정답이 공개되어야 함"
        print("2차 피드백 OK (정답 공개):", captured[-1]["text"][:200])

        print("\n=== 라운드 2: 모범 번역 그대로 제출 -> 한 번에 정답 처리 ===")
        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": "/해석"}})
        passage_text2 = captured[-1]["text"].split("\n\n", 1)[-1]
        model_translation = await lookup_model_translation(passage_text2)

        captured.clear()
        await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": model_translation}})
        print("정답 제출 결과:", captured[-1]["text"][:200])
        assert "모범 번역" in captured[-1]["text"]

        print("\n=== 모두 통과 ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
