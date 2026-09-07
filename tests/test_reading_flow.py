from app.handlers import router
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import _setup_general_user


class FakeReadingRepo:
    def __init__(self, passage_row=None):
        self.passage_row = passage_row
        self.recorded: list[tuple] = []

    async def get_random_passage(self, level):
        return self.passage_row

    async def record_attempt(
        self, user_id, passage_id, user_translation, ai_feedback, attempt_number, is_adequate, is_review
    ):
        self.recorded.append(
            (user_id, passage_id, user_translation, ai_feedback, attempt_number, is_adequate, is_review)
        )


def _passage_row(pid=1, text="The cat sat on the mat.", translation="고양이가 매트 위에 앉았다.", level="beginner"):
    return {"id": pid, "level": level, "passage_text": text, "model_translation_ko": translation}


def _wire(monkeypatch, passage_row=None):
    fake_users = FakeUsersRepo()
    fake_reading = FakeReadingRepo(passage_row=passage_row)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "reading_repo", fake_reading)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text))

    monkeypatch.setattr(router, "send_message", fake_send)
    return fake_users, fake_reading, sent


def test_reading_session_finishes_immediately_when_adequate(monkeypatch):
    fake_users, fake_reading, sent = _wire(monkeypatch, passage_row=_passage_row())
    telegram_id = "1001"
    _setup_general_user(fake_users, telegram_id)

    async def fake_evaluate(passage_text, translation):
        return True, "잘했어요!"

    monkeypatch.setattr(router.reading_evaluator, "evaluate", fake_evaluate)

    run(router.handle_update({"message": {"chat": {"id": 1001}, "text": "/해석"}}))
    assert "The cat sat" in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1001}, "text": "고양이가 매트에 앉았다."}}))
    assert "잘했어요" in sent[-1][1]
    assert "모범 번역" in sent[-1][1]
    assert fake_reading.recorded[0][4] == 1  # attempt_number
    assert fake_reading.recorded[0][5] is True  # is_adequate


def test_reading_gives_hint_then_reveals_on_second_attempt_without_leaking_answer(monkeypatch):
    fake_users, fake_reading, sent = _wire(monkeypatch, passage_row=_passage_row())
    telegram_id = "1002"
    _setup_general_user(fake_users, telegram_id)

    calls: list[str] = []

    async def fake_evaluate(passage_text, translation):
        calls.append(translation)
        if len(calls) == 1:
            return False, "주어를 다시 확인해보세요."
        return False, "여전히 아쉬워요."

    monkeypatch.setattr(router.reading_evaluator, "evaluate", fake_evaluate)

    run(router.handle_update({"message": {"chat": {"id": 1002}, "text": "/해석"}}))

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1002}, "text": "엉뚱한 해석"}}))
    assert "다시 한 번" in sent[-1][1]
    assert "모범 번역" not in sent[-1][1]  # 정답을 바로 공개하지 않음

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1002}, "text": "다시 엉뚱한 해석"}}))
    assert "모범 번역" in sent[-1][1]  # 최대 시도 횟수(2회)에서는 공개
    assert fake_reading.recorded[-1][4] == 2


def test_no_passage_available(monkeypatch):
    fake_users, fake_reading, sent = _wire(monkeypatch, passage_row=None)
    telegram_id = "1003"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 1003}, "text": "/해석"}}))
    assert "지문이 없습니다" in sent[-1][1]


def test_evaluation_failure_fails_open_and_reveals_translation(monkeypatch):
    fake_users, fake_reading, sent = _wire(monkeypatch, passage_row=_passage_row())
    telegram_id = "1004"
    _setup_general_user(fake_users, telegram_id)

    async def failing_evaluate(passage_text, translation):
        raise RuntimeError("boom")

    monkeypatch.setattr(router.reading_evaluator, "evaluate", failing_evaluate)

    run(router.handle_update({"message": {"chat": {"id": 1004}, "text": "/해석"}}))
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1004}, "text": "아무 해석"}}))

    assert "모범 번역" in sent[-1][1]
