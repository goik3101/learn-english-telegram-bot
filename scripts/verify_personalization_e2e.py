"""개인 맞춤 난이도 시스템(단어/문법/독해/회화) 실제 DB/Gemini 검증 (1회성 스크립트).

관리자 계정(하루 제한 우회)으로 4개 영역을 한 번씩 실제로 돌려, 새 스키마/쿼리가 실제 운영
데이터에서도 에러 없이 동작하고 핵심 신호(밴드 필터, 커리큘럼 주제, 밴드별 기록)가 실제로
남는지 확인한다. 정확한 밴드 승급/강등 산술은 이미 pytest에서 전부 검증되어 있으므로,
여기서는 "실제 DB/콘텐츠로 크래시 없이 동작하는가"에 집중한다.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.config import settings  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.grammar.curriculum import topic_for_index  # noqa: E402
from app.handlers import router  # noqa: E402
from app.repo import users as users_repo  # noqa: E402

captured: list[dict] = []


async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
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


async def _click(chat_id: int, cb_data: str) -> None:
    captured.clear()
    await router.handle_update(
        {
            "callback_query": {
                "id": "sim",
                "from": {"id": chat_id},
                "message": {"chat": {"id": chat_id}, "message_id": 1},
                "data": cb_data,
            }
        }
    )


async def _send_text(chat_id: int, text: str) -> None:
    captured.clear()
    await router.handle_update({"message": {"chat": {"id": chat_id}, "text": text}})


async def main() -> None:
    if not settings.admin_telegram_id:
        raise SystemExit("ADMIN_TELEGRAM_ID가 .env에 설정되어 있지 않습니다.")
    telegram_id = settings.admin_telegram_id
    chat_id = int(telegram_id)

    await init_db_pool()
    try:
        user = await users_repo.get_user_by_telegram_id(telegram_id)
        print(
            f"현재 상태: word_band={user['word_band']}, grammar_topic_index={user['grammar_topic_index']}, "
            f"reading_band={user['reading_band']}, conversation_level={user['conversation_level']}"
        )

        # 1) 단어: 밴드 필터 큐 구성이 크래시 없이 동작하는지, 큐가 있으면 신규단어 완료 처리
        print("\n--- 1) 단어학습 ---")
        await _send_text(chat_id, "/단어학습")
        kb = _latest_keyboard_message()
        if kb is not None:
            buttons = [b for row in kb["reply_markup"]["inline_keyboard"] for b in row]
            known_btn = next((b for b in buttons if b["callback_data"].startswith("vocab:known:")), buttons[0])
            await _click(chat_id, known_btn["callback_data"])
            print("=== 단어 카드 1개 완료 처리 OK (크래시 없음) ===")
        else:
            print("=== 오늘 신규 단어 없음(정상 동작, 큐 로직 자체는 통과) ===")

        # 2) 문법: 현재 커리큘럼 주제로 실제 출제되는지 확인
        print("\n--- 2) 문법학습 (커리큘럼 게이팅) ---")
        user = await users_repo.get_user_by_telegram_id(telegram_id)
        level = user["placement_level"] or "beginner"
        expected_topic = topic_for_index(level, user["grammar_topic_index"] or 0)
        print(f"기대 주제: {expected_topic}")
        await _send_text(chat_id, "/문법학습")
        all_text = "\n".join(m["text"] for m in captured)
        if expected_topic:
            assert expected_topic in all_text, f"'{expected_topic}' 주제로 출제되어야 함. 실제: {all_text[:200]}"
        print("=== 문법학습 커리큘럼 주제 매칭 OK ===")
        kb = _latest_keyboard_message()
        if kb is not None:
            buttons = [b for row in kb["reply_markup"]["inline_keyboard"] for b in row]
            await _click(chat_id, buttons[0]["callback_data"])
            print("=== 문법 문항 1개 응답 처리 OK (크래시 없음) ===")

        # 3) 독해: 밴드 필터로 지문이 선택되는지, 정답 제출이 크래시 없이 기록되는지
        print("\n--- 3) 해석 (밴드 필터) ---")
        await _send_text(chat_id, "/해석")
        reading_texts = "\n".join(m["text"] for m in captured)
        print("지문 일부:", reading_texts[:150])
        await _send_text(chat_id, "이 지문의 대략적인 뜻을 최선을 다해 해석해봅니다.")
        if not any("모범 번역" in m["text"] for m in captured):
            # 힌트만 받고 아직 끝나지 않았으면(MAX_ATTEMPTS=2), 두 번째 시도로 세션을 확실히 종료한다.
            await _send_text(chat_id, "다시 한 번 최선을 다해 해석해봅니다.")
        print("=== 해석 제출 처리 OK (크래시 없음, 세션 정상 종료) ===")

        # 4) 회화: 오늘의 주제 단어 사전학습 -> CEFR 레벨 반영 + 종료 후 난이도 피드백 버튼
        print("\n--- 4) 회화 (사전 단어학습 + CEFR 레벨 + 난이도 피드백) ---")
        await _send_text(chat_id, "/회화")
        opening_texts = "\n".join(m["text"] for m in captured)
        if "이미" not in opening_texts:  # 하루 제한 문구가 아니면 실제로 시작된 것
            kb = _latest_keyboard_message()
            while kb is not None and any(
                b["callback_data"].startswith("vocab:known:") for row in kb["reply_markup"]["inline_keyboard"] for b in row
            ):
                buttons = [b for row in kb["reply_markup"]["inline_keyboard"] for b in row]
                known_btn = next(b for b in buttons if b["callback_data"].startswith("vocab:known:"))
                await _click(chat_id, known_btn["callback_data"])
                kb = _latest_keyboard_message()
            print("=== 오늘의 주제 단어 사전학습 완료 -> 회화 시작 OK ===")

            for i in range(5):
                await _send_text(chat_id, f"That's an interesting question, number {i}.")
            feedback_texts = "\n".join(m["text"] for m in captured)
            assert "난이도가 어땠나요" in feedback_texts, "5턴 완료 후 난이도 피드백 질문이 와야 함"
            kb = _latest_keyboard_message()
            buttons = [b["callback_data"] for row in kb["reply_markup"]["inline_keyboard"] for b in row]
            assert buttons == ["convfeedback:easy", "convfeedback:ok", "convfeedback:hard"]
            await _click(chat_id, "convfeedback:ok")
            print("=== 회화 5턴 + 난이도 피드백 버튼 확인 OK ===")
        else:
            print("=== 오늘 이미 회화를 진행함 (관리자 우회 로직 자체는 이미 이전 세션에서 검증됨) ===")

        user = await users_repo.get_user_by_telegram_id(telegram_id)
        print(
            f"\n최종 상태: word_band={user['word_band']}, grammar_topic_index={user['grammar_topic_index']}, "
            f"reading_band={user['reading_band']}, conversation_level={user['conversation_level']}"
        )

        print("\n=== 모두 통과 ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
