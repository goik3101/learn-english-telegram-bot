from app.handlers import router
from tests.test_router import FakeUsersRepo, NullGrammarRepo, run
from tests.test_vocab_flow import (
    FakeContentGenerator,
    FakeContentRepo,
    FakeLearningSessionsRepo,
    FakeUserWordsRepo,
)


class FakeReadingRepo:
    """attempt_number=1인 최근 기록을 실제로 누적해 get_recent_band_results가 반영하도록 만든 버전."""

    def __init__(self, passage_rows_by_band=None):
        self.passage_rows_by_band = passage_rows_by_band or {}
        self.recorded: list[tuple] = []
        self.band_calls: list[int | None] = []

    async def get_random_passage(self, level, learning_mode="GENERAL", band=None):
        self.band_calls.append(band)
        rows = self.passage_rows_by_band.get(band, [])
        return rows[0] if rows else None

    async def record_attempt(self, user_id, passage_id, user_translation, ai_feedback, attempt_number, is_adequate, is_review):
        self.recorded.append((user_id, passage_id, attempt_number, is_adequate, is_review))

    async def get_recent_band_results(self, user_id, band, limit):
        results = [
            is_adequate
            for uid, pid, attempt_number, is_adequate, is_review in reversed(self.recorded)
            if uid == user_id and attempt_number == 1 and not is_review and self._band_of(pid) == band
        ]
        return results[:limit]

    def _band_of(self, passage_id):
        for band, rows in self.passage_rows_by_band.items():
            for row in rows:
                if row["id"] == passage_id:
                    return band
        return None


def _passage_row(pid, band, text="The cat sat on the mat."):
    return {
        "id": pid,
        "level": "beginner",
        "passage_text": f"{text} ({pid})",
        "model_translation_ko": "고양이가 매트 위에 앉았다.",
        "difficulty_band": band,
    }


def _wire(monkeypatch, passage_rows_by_band=None):
    fake_users = FakeUsersRepo()
    fake_reading = FakeReadingRepo(passage_rows_by_band=passage_rows_by_band)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "reading_repo", fake_reading)
    monkeypatch.setattr(router, "user_words_repo", FakeUserWordsRepo())
    monkeypatch.setattr(router, "learning_sessions_repo", FakeLearningSessionsRepo())
    monkeypatch.setattr(router, "content_repo", FakeContentRepo())
    monkeypatch.setattr(router, "content_generator", FakeContentGenerator())
    monkeypatch.setattr(router, "grammar_repo", NullGrammarRepo())
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text))

    monkeypatch.setattr(router, "send_message", fake_send)
    return fake_users, fake_reading, sent


def _setup_general_user(fake_users, telegram_id):
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "GENERAL"
    fake_users.users[telegram_id]["placement_level"] = "beginner"


def test_reading_session_selects_from_current_band_first(monkeypatch):
    fake_users, fake_reading, sent = _wire(monkeypatch, passage_rows_by_band={0: [_passage_row(1, 0)]})
    telegram_id = "9201"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 9201}, "text": "/해석"}}))

    assert fake_reading.band_calls[0] == 0  # 1차 시도: 밴드 필터


def test_reading_session_falls_back_when_band_has_no_passage(monkeypatch):
    fake_users, fake_reading, sent = _wire(monkeypatch, passage_rows_by_band={None: [_passage_row(2, None)]})
    telegram_id = "9202"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 9202}, "text": "/해석"}}))

    assert fake_reading.band_calls == [0, None]  # 1차 실패 -> 2차 폴백(밴드 없음)
    assert "cat" in sent[-1][1]


def test_first_attempt_adequate_records_band_result(monkeypatch):
    fake_users, fake_reading, sent = _wire(monkeypatch, passage_rows_by_band={0: [_passage_row(3, 0)]})
    telegram_id = "9203"
    _setup_general_user(fake_users, telegram_id)

    async def fake_evaluate(passage_text, translation, learning_mode="GENERAL"):
        return True, "좋아요"

    monkeypatch.setattr(router.reading_evaluator, "evaluate", fake_evaluate)

    run(router.handle_update({"message": {"chat": {"id": 9203}, "text": "/해석"}}))
    run(router.handle_update({"message": {"chat": {"id": 9203}, "text": "고양이가 매트에 앉았다."}}))

    assert fake_reading.recorded[-1][2:4] == (1, True)  # attempt_number=1, is_adequate=True


def test_second_attempt_does_not_double_count_band(monkeypatch):
    fake_users, fake_reading, sent = _wire(monkeypatch, passage_rows_by_band={0: [_passage_row(4, 0)]})
    telegram_id = "9204"
    _setup_general_user(fake_users, telegram_id)

    calls = {"n": 0}

    async def fake_evaluate(passage_text, translation, learning_mode="GENERAL"):
        calls["n"] += 1
        return False, "다시 시도"

    monkeypatch.setattr(router.reading_evaluator, "evaluate", fake_evaluate)

    run(router.handle_update({"message": {"chat": {"id": 9204}, "text": "/해석"}}))
    run(router.handle_update({"message": {"chat": {"id": 9204}, "text": "틀린 해석 1"}}))  # attempt 1 (오답)
    run(router.handle_update({"message": {"chat": {"id": 9204}, "text": "틀린 해석 2"}}))  # attempt 2 (오답, 종료)

    # 밴드 판단에는 attempt_number=1인 기록만 반영되어야 한다.
    band_signals = [r for r in fake_reading.recorded if r[2] == 1]
    assert len(band_signals) == 1


def test_reading_band_advances_after_ten_adequate_first_attempts(monkeypatch):
    passage_rows_by_band = {0: [_passage_row(500 + i, 0) for i in range(10)]}
    fake_users, fake_reading, sent = _wire(monkeypatch, passage_rows_by_band=passage_rows_by_band)
    telegram_id = "9205"
    _setup_general_user(fake_users, telegram_id)

    async def fake_evaluate(passage_text, translation, learning_mode="GENERAL"):
        return True, "좋아요"

    monkeypatch.setattr(router.reading_evaluator, "evaluate", fake_evaluate)

    for _ in range(10):
        run(router.handle_update({"message": {"chat": {"id": 9205}, "text": "/해석"}}))
        run(router.handle_update({"message": {"chat": {"id": 9205}, "text": "정답 해석"}}))

    assert fake_users.users[telegram_id]["reading_band"] == 1
