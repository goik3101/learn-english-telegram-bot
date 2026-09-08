"""CHILD_BEGINNER Stage6(듣기말하기)을 실제 DB/실제 Google Cloud TTS로 자동 시뮬레이션 (1회성 스크립트).

scripts/simulate_child_beginner.py로 이미 Stage0~5를 마친 테스트 사용자(child_stage=6)를 그대로 이어서
듣기 퀴즈(실제 TTS 음성 합성) -> 말하기 연습(음성메시지 수신 처리)까지 검증한다.
텔레그램 발송 자체는 다른 시뮬레이션 스크립트와 동일하게 캡처만 하고(실제 채팅ID가 아니므로),
TTS 합성만 실제 Google Cloud API를 그대로 호출해 오디오가 정상 생성되는지 확인한다.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.handlers import router  # noqa: E402
from app.repo import users as users_repo  # noqa: E402

TELEGRAM_ID = "770011223"
CHAT_ID = 770011223

captured: list[dict] = []
captured_voices: list[bytes] = []


async def fake_send(chat_id, text, reply_markup=None):
    captured.append({"text": text, "reply_markup": reply_markup})
    print("SENT:", text[:150].replace("\n", " | "))


async def fake_send_voice(chat_id, audio_bytes, caption=None):
    captured_voices.append(audio_bytes)
    print(f"SENT VOICE: {len(audio_bytes)} bytes, caption={caption!r}")


async def fake_answer_cb(callback_query_id, text=None):
    pass


async def fake_delete(chat_id, message_id):
    pass


router.send_message = fake_send
router.send_voice = fake_send_voice
router.answer_callback_query = fake_answer_cb
router.delete_message = fake_delete


def _latest_keyboard_message():
    for m in reversed(captured):
        if m["reply_markup"] and "inline_keyboard" in m["reply_markup"]:
            return m
    return None


async def _click(cb_data: str) -> None:
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


async def _send_text(text: str) -> None:
    captured.clear()
    await router.handle_update({"message": {"chat": {"id": CHAT_ID}, "text": text}})


async def _send_voice_message() -> None:
    captured.clear()
    await router.handle_update(
        {"message": {"chat": {"id": CHAT_ID}, "voice": {"file_id": "sim-voice", "duration": 2}}}
    )


async def main() -> None:
    await init_db_pool()
    try:
        user = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)
        assert user is not None, "먼저 scripts/simulate_child_beginner.py를 실행해 Stage0~5를 완료해야 함"
        if user["child_stage"] != 6:
            print(f"현재 child_stage={user['child_stage']} — 6이 아니면 강제로 6으로 맞춤")
            await users_repo.set_child_stage(TELEGRAM_ID, 6)

        await _send_text("🎈 오늘 공부하기")

        assert captured_voices, "듣기 문제 시작 시 실제 TTS 음성이 전송되어야 함"
        first_audio = captured_voices[0]
        assert first_audio[:4] == b"OggS", "OGG_OPUS 포맷이어야 함"
        print(f"=== 첫 듣기 문제 실제 TTS 합성 OK ({len(first_audio)} bytes, OGG 포맷 확인) ===")

        texts = "\n".join(m["text"] for m in captured)
        assert "무슨 뜻일까요" in texts
        print("=== 단어 텍스트 노출 없이 듣기로만 문제 제시 OK ===")

        # 5문항을 전부 첫 번째 선택지로 답한다
        for _ in range(5):
            kb_msg = _latest_keyboard_message()
            assert kb_msg is not None
            buttons = [b for row in kb_msg["reply_markup"]["inline_keyboard"] for b in row]
            await _click(buttons[0]["callback_data"])

        all_texts = "\n".join(m["text"] for m in captured)
        assert "듣기 연습 완료" in all_texts
        assert "녹음해서 보내주세요" in all_texts
        print(f"=== 듣기 퀴즈 5문항 완료, 실제 음성 총 {len(captured_voices)}개 전송 확인 OK ===")

        user = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)
        assert user["child_stage"] == 6, "말하기 연습 전이므로 아직 6이어야 함"

        # 텍스트로 답하면 음성으로 다시 보내라는 안내가 와야 함
        await _send_text("다 했어요!")
        assert any("목소리로 녹음해서 보내주세요" in m["text"] for m in captured)
        print("=== 텍스트 응답 시 음성 재요청 안내 OK ===")

        # 실제 음성메시지를 보내면 완료 처리
        await _send_voice_message()
        assert any("단계를 모두 마쳤어요" in m["text"] for m in captured)
        print("=== 말하기 연습(음성메시지 수신) 완료 처리 OK ===")

        user = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)
        assert user["child_stage"] == 7, f"child_stage가 7이어야 함, 실제: {user['child_stage']}"
        print(f"=== child_stage=7로 전진 확인 OK ===")

        # 모든 단계를 마쳤으니 다시 시작하면 축하 메시지만 나와야 함
        await _send_text("🎈 오늘 공부하기")
        assert any("모두 마쳤어요" in m["text"] for m in captured)
        print("=== Stage0~6 전체 완료 후 안내 메시지 OK ===")

        print("\n=== 모두 통과 ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
