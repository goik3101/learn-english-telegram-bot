"""M16 TTS 실제 검증 — 실제 Google Cloud TTS + 실제 텔레그램 음성메시지 전송까지 확인 (1회성).

send_message/send_voice를 모킹하지 않고 실제로 호출해 관리자 텔레그램 채팅에 진짜 카드/음성메시지가 오는지 확인한다.
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
from app.repo import tts_cache as tts_cache_repo  # noqa: E402
from app.vocab import service as vocab_service  # noqa: E402


async def main() -> None:
    if not settings.admin_telegram_id:
        raise SystemExit("ADMIN_TELEGRAM_ID가 .env에 설정되어 있지 않습니다.")

    telegram_id = settings.admin_telegram_id
    chat_id = int(telegram_id)

    await init_db_pool()
    try:
        print("1) /단어학습 시작 (실제 텔레그램으로 카드가 전송됩니다)...")
        await router.handle_update({"message": {"chat": {"id": chat_id}, "text": "/단어학습"}})

        item = vocab_service.current_item(telegram_id)
        if item is None:
            print("오늘 학습할 새 단어가 없어 카드가 없습니다. 관리자 계정으로 실제 텔레그램에서 확인해 주세요.")
            return

        print(f"2) 현재 카드 단어: '{item.word}' (word_id={item.word_id}) — 🔊 발음 듣기 첫 클릭(캐시 미스, 실제 합성)...")
        key = tts_cache_repo.cache_key(item.word, "en-US", "en-US-Standard-C")
        before = await tts_cache_repo.get_cached_audio(key)
        print("   caching 이전 상태:", "있음" if before is not None else "없음")

        await router.handle_update(
            {
                "callback_query": {
                    "id": "verify1",
                    "from": {"id": chat_id},
                    "message": {"chat": {"id": chat_id}, "message_id": 1},
                    "data": f"ttsword:{item.word_id}",
                }
            }
        )

        after = await tts_cache_repo.get_cached_audio(key)
        assert after is not None, "1차 호출 후 캐시에 오디오가 저장되어 있어야 함"
        print(f"   캐시 저장 확인 OK (오디오 {len(after)} bytes)")

        print("3) 🔊 발음 듣기 두 번째 클릭(캐시 히트, API 재호출 없이 바로 재생되어야 함)...")
        await router.handle_update(
            {
                "callback_query": {
                    "id": "verify2",
                    "from": {"id": chat_id},
                    "message": {"chat": {"id": chat_id}, "message_id": 1},
                    "data": f"ttsword:{item.word_id}",
                }
            }
        )
        print("   두 번째 음성메시지도 전송됨 (실제 텔레그램에서 총 2개의 음성메시지를 확인해 주세요)")

        print("4) 카드가 여전히 살아있는지 확인 — [아는단어]로 정상 마무리...")
        await router.handle_update(
            {
                "callback_query": {
                    "id": "verify3",
                    "from": {"id": chat_id},
                    "message": {"chat": {"id": chat_id}, "message_id": 1},
                    "data": f"vocab:known:{item.word_id}",
                }
            }
        )
        print("   완료 — 카드가 정상적으로 진행되어 다음 단계로 넘어갔거나 세션이 종료되었습니다.")

        print("\n=== 실제 텔레그램 앱에서 확인해 주세요: 단어 카드 1개 + 음성메시지(음성 노트) 2개가 와 있어야 합니다 ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
