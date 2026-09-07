"""학교 시험 관리(M13) 플로우를 실제 DB/실제 Gemini로 자동 시뮬레이션 (1회성 스크립트).

시험 등록 -> (수행평가 자료가 자동으로 그 시험에 연결됨, 일부러 오답을 내서 오답노트 생성) -> 시험직전복습까지 확인.
"""

import asyncio
import sys
from datetime import date, timedelta

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
    "Deforestation in tropical regions has accelerated over the past decade, driven largely by agricultural "
    "expansion. Conservationists warn that if current trends continue, many endemic species could lose their "
    "habitats entirely within a generation, disrupting ecosystems that took centuries to develop."
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
        exam_date = (date.today() + timedelta(days=7)).isoformat()

        # 1) 시험 등록
        await _send_text("/시험등록")
        await _send_text("생물")
        await _send_text(exam_date)
        await _send_text("6단원 생태계와 상호작용")
        await _send_text("먹이사슬 관련 문제 꼭 나온다고 강조하심")
        assert any("등록되었습니다" in m["text"] for m in captured), "시험 등록 완료 메시지가 와야 함"
        assert any("D-7" in m["text"] for m in captured), "D-7 표시가 있어야 함"
        print("=== 시험 등록 OK ===")

        # 2) 시험 목록 확인
        await _send_text("/시험목록")
        assert any("생물" in m["text"] and "D-7" in m["text"] for m in captured)
        print("=== 시험 목록 OK ===")

        # 3) 수행평가 자료 학습 (등록된 시험이 1개뿐이므로 자동 연결되어야 함)
        await _send_text("/수행평가")
        assert any("생물" in m["text"] and "연결합니다" in m["text"] for m in captured), "단일 시험 자동연결 안내가 와야 함"
        print("=== 수행평가 시험 자동연결 OK ===")

        await _send_text(SAMPLE_TEXT)

        # 단어 카드가 있으면 전부 [아는단어]로 넘어가 예상문제 1번까지 진행
        for _ in range(20):
            if any("예상문제 1" in m["text"] for m in captured):
                break
            kb_msg = _latest_keyboard_message()
            if kb_msg is None:
                break
            buttons = [b for row in kb_msg["reply_markup"]["inline_keyboard"] for b in row]
            cb_data = next((b["callback_data"] for b in buttons if b["callback_data"].startswith("vocab:known:")), buttons[0]["callback_data"])
            await _click(cb_data)

        assert any("예상문제 1" in m["text"] for m in captured), "예상문제 1번에 도달해야 함"
        print("=== 문법해설 + 예상문제 도달 OK ===")

        # 예상문제는 일부러 전부 오답(두 번째 선택지)으로 골라 오답노트를 만든다
        for _ in range(10):
            kb_msg = _latest_keyboard_message()
            if kb_msg is None:
                break
            buttons = [b for row in kb_msg["reply_markup"]["inline_keyboard"] for b in row]
            wrong_button = buttons[1] if len(buttons) > 1 else buttons[0]
            await _click(wrong_button["callback_data"])
            if any("학교 수행평가 학습 완료" in m["text"] for m in captured):
                break

        assert any("학교 수행평가 학습 완료" in m["text"] for m in captured)
        print("=== 수행평가 자료 학습 완료(오답 유도) OK ===")

        # 4) 시험직전복습 — 방금 만든 오답들이 다시 나와야 한다
        await _send_text("/시험직전복습")
        assert any("생물" in m["text"] and "D-7" in m["text"] for m in captured)
        assert any("먹이사슬" in m["text"] for m in captured), "선생님강조사항이 노출되어야 함"
        assert any("복습 1" in m["text"] for m in captured), "오답 복습 문항이 나와야 함"
        print("=== 시험직전복습 시작(오답 재출제) OK ===")

        # 복습 문제는 전부 정답(정답 인덱스 활용 불가하므로 첫 버튼 선택 후 결과만 확인)
        for _ in range(10):
            kb_msg = _latest_keyboard_message()
            if kb_msg is None:
                break
            buttons = [b for row in kb_msg["reply_markup"]["inline_keyboard"] for b in row]
            await _click(buttons[0]["callback_data"])
            if any("시험직전복습 완료" in m["text"] for m in captured):
                break

        assert any("시험직전복습 완료" in m["text"] for m in captured)
        print("=== 시험직전복습 완료 OK ===")

        print("\n=== 모두 통과 ===")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
