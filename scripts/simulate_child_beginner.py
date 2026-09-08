"""CHILD_BEGINNER 모드(M15, 10세 이하)를 실제 DB로 자동 시뮬레이션 (1회성 스크립트).

가상의 8세 사용자로 Stage0(알파벳) -> Stage1(파닉스) -> Stage2(기초단어) -> Stage3(기초문장)
-> Stage4(QA) -> Stage5(짧은지문)까지 전부 진행해 메뉴 분리/진도 전진/콘텐츠뱅크 조회가
실제로 동작하는지 확인한다. Stage6(듣기말하기)는 TTS(M16) 이후로 보류되어 대상에서 제외.
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


async def _run_current_stage_to_completion(expected_stage: int) -> None:
    """현재 표시된 세션(카드 또는 퀴즈)을 끝까지 진행해 stage 완료 메시지가 뜰 때까지 클릭한다."""
    for _ in range(40):
        if any("단계를 모두 마쳤어요" in m["text"] for m in captured):
            break
        kb_msg = _latest_keyboard_message()
        if kb_msg is None:
            break
        buttons = [b for row in kb_msg["reply_markup"]["inline_keyboard"] for b in row]
        await _click(buttons[0]["callback_data"])

    assert any("단계를 모두 마쳤어요" in m["text"] for m in captured), f"stage {expected_stage} 완료 메시지가 와야 함"
    user = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)
    assert user["child_stage"] == expected_stage + 1, f"child_stage가 {expected_stage + 1}이어야 함, 실제: {user['child_stage']}"
    print(f"=== Stage{expected_stage} 완료 -> child_stage={user['child_stage']} OK ===")


async def main() -> None:
    await init_db_pool()
    try:
        existing = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)
        if existing is not None:
            print(f"(참고) 기존 테스트 사용자 재사용 예정이었으나 매번 새 진행을 보려면 DB에서 지워야 함: id={existing['id']}")

        await _send_text("/start")
        if existing is None:
            await users_repo.approve_user(TELEGRAM_ID)
            await _send_text("/start")

        user = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)
        if user["learning_mode"] is None:
            await _send_text("8")
            user = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)

        assert user["learning_mode"] == "CHILD_BEGINNER", f"실제: {user['learning_mode']}"
        print(f"=== 나이 8 -> CHILD_BEGINNER 배정 OK (child_stage={user['child_stage']}) ===")

        # 메뉴 분리 확인: GENERAL 메뉴 문구가 아니라 어린이 전용 메뉴/문구여야 함
        await _send_text("이상한말")
        assert any("골라주세요" in m["text"] for m in captured)
        assert not any("이해하지 못했어요" in m["text"] for m in captured)
        print("=== 전용 메뉴 분리 확인 OK ===")

        for stage in range(6):
            await _send_text("🎈 오늘 공부하기")
            await _run_current_stage_to_completion(stage)

        # 진도 확인
        await _send_text("⭐ 내 진도")
        progress_text = "\n".join(m["text"] for m in captured)
        print("=== 진도 화면 ===")
        print(progress_text)
        assert progress_text.count("✅") == 6

        print("\n=== 모두 통과 ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
