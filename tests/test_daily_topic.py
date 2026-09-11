"""오늘의 주제 기반 통합 학습: 단어/해석이 같은 주제·단어 풀을 공유하는지 검증."""

from app import topics as daily_topics
from app.handlers import router
from tests.test_grammar_difficulty import FakeGrammarRepo, _part, _part_question
from tests.test_reading_flow import FakeReadingRepo, _passage_row
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import (
    FakeContentGenerator,
    FakeContentRepo,
    FakeLearningSessionsRepo,
    FakeUserWordsRepo,
    _setup_general_user,
    _word_row,
)


def _wire(monkeypatch, new_rows=None, passage_row=None, questions_by_topic=None, parts=None, questions=None):
    fake_users = FakeUsersRepo()
    fake_user_words = FakeUserWordsRepo(new_rows=new_rows)
    fake_learning_sessions = FakeLearningSessionsRepo()
    fake_content = FakeContentRepo(topic_word_rows=new_rows)
    fake_reading = FakeReadingRepo(passage_row=passage_row)
    fake_grammar = FakeGrammarRepo(questions_by_topic=questions_by_topic, parts=parts, questions=questions)

    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "learning_sessions_repo", fake_learning_sessions)
    monkeypatch.setattr(router, "content_repo", fake_content)
    monkeypatch.setattr(router, "content_generator", FakeContentGenerator())
    monkeypatch.setattr(router, "reading_repo", fake_reading)
    monkeypatch.setattr(router, "grammar_repo", fake_grammar)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    async def fake_delete_message(chat_id, message_id):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    monkeypatch.setattr(router, "delete_message", fake_delete_message)
    return {
        "users": fake_users,
        "user_words": fake_user_words,
        "learning_sessions": fake_learning_sessions,
        "content": fake_content,
        "reading": fake_reading,
        "grammar": fake_grammar,
        "sent": sent,
    }


def test_vocab_session_picks_and_persists_todays_topic(monkeypatch):
    new_rows = [_word_row(1, "apple", "사과")]
    f = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "9501"
    _setup_general_user(f["users"], telegram_id)
    user_id = f["users"].users[telegram_id]["id"]

    run(router.handle_update({"message": {"chat": {"id": 9501}, "text": "/단어학습"}}))

    row = f["learning_sessions"].rows[user_id]
    assert row["today_topic"] in daily_topics.DAILY_TOPICS
    assert row["today_topic_word_ids"] == [1]
    assert f["sent"][0][1].startswith(f"오늘의 주제: {row['today_topic']}")


def test_reading_reuses_same_topic_word_pool_as_vocab(monkeypatch):
    new_rows = [_word_row(2, "suitcase", "여행 가방")]
    f = _wire(monkeypatch, new_rows=new_rows, passage_row=_passage_row())
    telegram_id = "9502"
    _setup_general_user(f["users"], telegram_id)
    user_id = f["users"].users[telegram_id]["id"]

    run(router.handle_update({"message": {"chat": {"id": 9502}, "text": "/단어학습"}}))
    vocab_topic = f["learning_sessions"].rows[user_id]["today_topic"]

    run(router.handle_update({"message": {"chat": {"id": 9502}, "text": "/해석"}}))
    reading_topic = f["learning_sessions"].rows[user_id]["today_topic"]

    assert vocab_topic == reading_topic
    assert f["sent"][-1][1].startswith(f"오늘의 주제: {vocab_topic}")


def test_grammar_session_does_not_touch_daily_topic(monkeypatch):
    """문법은 오늘의 주제 시스템과 무관하게 자기 순서(파트 단위 순차 진행+숙달기준)를 그대로 따른다."""
    parts = [_part(1, 10, "현재시제", "3인칭단수 -s", 0)]
    questions = [_part_question(1, 1, "현재시제", "She ___ to school.", ["go", "goes", "going", "went"], 1)]
    f = _wire(monkeypatch, parts=parts, questions=questions)
    telegram_id = "9505"
    _setup_general_user(f["users"], telegram_id)
    user_id = f["users"].users[telegram_id]["id"]

    run(router.handle_update({"message": {"chat": {"id": 9505}, "text": "/문법학습"}}))

    assert user_id not in f["learning_sessions"].rows  # learning_sessions 행 자체가 생성되지 않음
    assert f["grammar"].part_question_calls == [1]
