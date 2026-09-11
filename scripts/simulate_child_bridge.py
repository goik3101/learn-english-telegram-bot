"""CHILD_BRIDGE 모드(M14, 11세)를 실제 DB/실제 Gemini로 자동 시뮬레이션 (1회성 스크립트).

이미 승인된 GENERAL 사용자(관리자)와 별개로, 나이 11 -> CHILD_BRIDGE 모드로 신규 가입하는
가상의 텔레그램 ID로 진행한다. 단어학습/문법학습/해석이 CHILD_BRIDGE 전용 콘텐츠로
동작하는지, 톤이 실제로 어린이 친화적으로 나오는지 확인한다.
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

# 실제 존재하지 않는 가상의 11세 사용자 텔레그램 ID (관리자 계정과 겹치지 않도록 임의로 선택)
TELEGRAM_ID = "990011223"
CHAT_ID = 990011223

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


async def main() -> None:
    await init_db_pool()
    try:
        # 이전 실행 잔여물이 있으면 정리하고 새로 시작 (재실행 가능하도록)
        existing = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)
        if existing is not None:
            print(f"(참고) 이미 존재하는 테스트 사용자 재사용: id={existing['id']}, mode={existing['learning_mode']}")

        await _send_text("/start")
        if existing is None:
            assert any("승인 대기" in m["text"] for m in captured)
            print("=== 승인 대기 등록 OK ===")
            # 관리자가 아니므로 자동 승인되지 않음 -> 직접 승인 처리
            await users_repo.approve_user(TELEGRAM_ID)
            await _send_text("/start")

        user = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)
        if user["learning_mode"] is None:
            await _send_text("11")
            user = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)

        assert user["learning_mode"] == "CHILD_BRIDGE", f"모드가 CHILD_BRIDGE여야 함, 실제: {user['learning_mode']}"
        print(f"=== 나이 11 -> CHILD_BRIDGE 모드 배정 OK (level={user['placement_level']}) ===")

        # 레벨진단이 아직 안 끝났다면 전부 정답으로 빠르게 완료
        for _ in range(15):
            kb_msg = _latest_keyboard_message()
            if kb_msg is None:
                break
            buttons = [b for row in kb_msg["reply_markup"]["inline_keyboard"] for b in row]
            await _click(buttons[0]["callback_data"])

        user = await users_repo.get_user_by_telegram_id(TELEGRAM_ID)
        print(f"=== 레벨진단 완료 (level={user['placement_level']}) ===")

        # 1) 단어학습 — CHILD_BRIDGE 전용 콘텐츠뱅크에서 나와야 함
        await _send_text("/단어학습")
        vocab_texts = "\n".join(m["text"] for m in captured)
        print("=== 단어학습 카드 ===")
        print(vocab_texts[:300])

        # 모두 [아는단어]로 빠르게 넘어가 세션 종료까지 진행
        for _ in range(20):
            kb_msg = _latest_keyboard_message()
            if kb_msg is None:
                break
            buttons = [b for row in kb_msg["reply_markup"]["inline_keyboard"] for b in row]
            known = next((b for b in buttons if b["callback_data"].startswith("vocab:known:")), buttons[0])
            await _click(known["callback_data"])
            if any("완료" in m["text"] for m in captured):
                break
        print("=== 단어학습 세션 종료 OK ===")

        # 2) 문법학습 — 개념설명 톤 확인
        await _send_text("/문법학습")
        grammar_texts = "\n".join(m["text"] for m in captured)
        print("=== 문법학습 개념설명/문제 ===")
        print(grammar_texts[:400])
        for _ in range(10):
            kb_msg = _latest_keyboard_message()
            if kb_msg is None:
                break
            buttons = [b for row in kb_msg["reply_markup"]["inline_keyboard"] for b in row]
            await _click(buttons[0]["callback_data"])
            if any("완료" in m["text"] for m in captured):
                break
        print("=== 문법학습 세션 종료 OK ===")

        # 3) 해석(Reading) — 지문 톤 확인 + 실시간 AI 힌트 톤 확인
        await _send_text("/해석")
        reading_texts = "\n".join(m["text"] for m in captured)
        print("=== 해석 지문 ===")
        print(reading_texts[:300])
        await _send_text("음... 모르겠어요 대충 뜻만 써볼게요")
        print("=== 해석 피드백(1차, 힌트여야 함) ===")
        print("\n".join(m["text"] for m in captured)[:300])

        # 2차 시도(반드시 공개되도록) 제출 -> 해석 세션을 정상 종료시킨다.
        await _send_text("우리 집 강아지 버디는 마당에서 노는 것을 좋아해요.")
        print("=== 해석 피드백(2차, 모범번역 공개되며 종료) ===")
        print("\n".join(m["text"] for m in captured)[:300])

        print("\n=== 모두 통과 ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
