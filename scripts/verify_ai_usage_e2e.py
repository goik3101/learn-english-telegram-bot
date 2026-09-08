"""M17 AI 사용량 모니터링을 실제 DB/실제 Gemini/실제 TTS로 검증 (1회성 스크립트).

실제 API를 한 번씩 호출한 뒤 ai_usage_log에 정확히 기록되고, /AI사용량 명령이 그 값을 반영하는지 확인한다.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.ai import gemini_client, tts_client  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.handlers import router  # noqa: E402
from app.repo import ai_usage as ai_usage_repo  # noqa: E402

captured: list[dict] = []


async def fake_send(chat_id, text, reply_markup=None):
    captured.append({"text": text})
    print("SENT:", text.replace("\n", " | "))


router.send_message = fake_send


async def main() -> None:
    if not settings.admin_telegram_id:
        raise SystemExit("ADMIN_TELEGRAM_ID가 .env에 설정되어 있지 않습니다.")

    await init_db_pool()
    try:
        before_today = await ai_usage_repo.get_today_counts()
        print("1) 이전 오늘 카운트:", before_today)

        print("2) 실제 Gemini 호출 1회...")
        text = await gemini_client.generate_text("Say 'hello' in one word.")
        print("   Gemini 응답:", text.strip()[:50])

        tts_available = tts_client.is_available()
        if tts_available:
            print("3) 실제 TTS 합성 1회 (캐시 미스를 위해 고유 문구 사용)...")
            import time

            unique_text = f"usage check {int(time.time())}"
            audio = await tts_client.synthesize_speech(unique_text)
            print(f"   합성된 오디오: {len(audio)} bytes")
        else:
            print("3) GOOGLE_TTS_API_KEY 없음 — TTS 호출은 건너뜀")

        after_today = await ai_usage_repo.get_today_counts()
        print("4) 이후 오늘 카운트:", after_today)

        assert after_today.get("gemini", 0) == before_today.get("gemini", 0) + 1, "gemini 호출 카운트가 1 증가해야 함"
        print("   gemini 카운트 +1 확인 OK")

        if tts_available:
            assert after_today.get("google_tts", 0) == before_today.get("google_tts", 0) + 1, "tts 호출 카운트가 1 증가해야 함"
            print("   google_tts 카운트 +1 확인 OK")

        print("5) /AI사용량 관리자 명령으로 실제 조회...")
        await router.handle_update(
            {"message": {"chat": {"id": int(settings.admin_telegram_id)}, "text": "/AI사용량"}}
        )
        assert any("Gemini" in m["text"] for m in captured)
        assert any("Google Cloud TTS" in m["text"] for m in captured)
        print("=== /AI사용량 명령 정상 응답 확인 OK ===")

        print("\n=== 모두 통과 ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
