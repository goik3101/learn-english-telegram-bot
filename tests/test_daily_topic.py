"""오늘의 주제 기반 통합 학습: 단어/해석/회화가 같은 주제·단어 풀을 공유하는지 검증."""

from app import topics as daily_topics
from app.handlers import router
from tests.test_conversation_flow import FakeConversationRepo
from tests.test_grammar_difficulty import FakeGrammarRepo
from tests.test_grammar_flow import _question_row
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


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


def _wire(monkeypatch, new_rows=None, passage_row=None, questions_by_topic=None):
    fake_users = FakeUsersRepo()
    fake_user_words = FakeUserWordsRepo(new_rows=new_rows)
    fake_learning_sessions = FakeLearningSessionsRepo()
    fake_content = FakeContentRepo(topic_word_rows=new_rows)
    fake_reading = FakeReadingRepo(passage_row=passage_row)
    fake_conversation = FakeConversationRepo(already_done=False)
    fake_grammar = FakeGrammarRepo(questions_by_topic=questions_by_topic)

    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "learning_sessions_repo", fake_learning_sessions)
    monkeypatch.setattr(router, "content_repo", fake_content)
    monkeypatch.setattr(router, "content_generator", FakeContentGenerator())
    monkeypatch.setattr(router, "reading_repo", fake_reading)
    monkeypatch.setattr(router, "conversation_repo", fake_conversation)
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
        "conversation": fake_conversation,
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


def test_conversation_skips_preview_cards_when_vocab_already_done_today(monkeypatch):
    """단어학습을 먼저 마쳤으면(오늘의 주제 단어를 이미 배웠으면), 회화는 같은 단어를 다시
    카드로 가르치지 않고 곧바로 대화로 들어가야 한다("두 번 따로 만들지 않음")."""
    new_rows = [_word_row(3, "apple", "사과")]
    f = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "9503"
    _setup_general_user(f["users"], telegram_id)

    async def fake_opening(level, learning_mode="GENERAL", conversation_level=2, extra_instruction="", topic=None, preview_words=None):
        assert preview_words == ["apple"]  # 프롬프트에는 여전히 오늘의 단어가 전달됨
        return "Hi!"

    monkeypatch.setattr(router.conversation_chat, "generate_opening", fake_opening)

    run(router.handle_update({"message": {"chat": {"id": 9503}, "text": "/단어학습"}}))
    run(router.handle_update(_callback_update(9503, "vocab:known:3")))  # 단어학습 완료(stages_completed에 vocab 기록)

    f["sent"].clear()
    run(router.handle_update({"message": {"chat": {"id": 9503}, "text": "/회화"}}))

    # 단어 카드(뜻/예문 포함)가 아니라 곧바로 회화 시작 메시지가 와야 한다.
    assert "회화 연습을 시작합니다" in f["sent"][-1][1]


def test_conversation_teaches_topic_cards_first_when_vocab_not_done_today(monkeypatch):
    new_rows = [_word_row(4, "apple", "사과")]
    f = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "9504"
    _setup_general_user(f["users"], telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 9504}, "text": "/회화"}}))

    assert any("오늘의 대화 주제" in m[1] for m in f["sent"])
    assert "apple" in f["sent"][-1][1]  # 단어 카드가 먼저 옴


def test_grammar_session_does_not_touch_daily_topic(monkeypatch):
    """문법은 오늘의 주제 시스템과 무관하게 자기 순서(order_index+숙달기준)를 그대로 따른다."""
    questions = {"현재시제": [_question_row(1, "현재시제", "She ___ to school.", ["go", "goes", "going", "went"], 1)]}
    f = _wire(monkeypatch, questions_by_topic=questions)
    telegram_id = "9505"
    _setup_general_user(f["users"], telegram_id)
    user_id = f["users"].users[telegram_id]["id"]

    run(router.handle_update({"message": {"chat": {"id": 9505}, "text": "/문법학습"}}))

    assert user_id not in f["learning_sessions"].rows  # learning_sessions 행 자체가 생성되지 않음
    assert f["grammar"].topic_calls == ["현재시제"]
