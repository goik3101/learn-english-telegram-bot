from app.handlers import router
from app.vocab import service as vocab_service
from tests.test_grammar_difficulty import FakeGrammarRepo, _setup_general_user as _setup_grammar_user
from tests.test_grammar_flow import _question_row
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import FakeUserWordsRepo, _setup_general_user, _word_row


def _wire_vocab(monkeypatch, new_rows=None):
    fake_users = FakeUsersRepo()
    fake_user_words = FakeUserWordsRepo(new_rows=new_rows)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    return fake_users, fake_user_words, sent


def test_stop_learning_clears_vocab_session_and_returns_to_menu(monkeypatch):
    new_rows = [_word_row(1, "apple", "사과"), _word_row(2, "book", "책")]
    fake_users, fake_user_words, sent = _wire_vocab(monkeypatch, new_rows=new_rows)
    telegram_id = "8001"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 8001}, "text": "/단어학습"}}))
    assert vocab_service.has_session(telegram_id)

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 8001}, "text": "/학습중단"}}))

    assert not vocab_service.has_session(telegram_id)
    assert "중단" in sent[-1][1]

    # 중단 이후 아무 텍스트를 보내도 더 이상 "주관식 답변"으로 삼켜지지 않아야 한다.
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 8001}, "text": "안녕"}}))
    assert "중단" not in sent[-1][1]


def test_stop_learning_button_label_also_works(monkeypatch):
    new_rows = [_word_row(3, "apple", "사과")]
    fake_users, fake_user_words, sent = _wire_vocab(monkeypatch, new_rows=new_rows)
    telegram_id = "8002"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 8002}, "text": "/단어학습"}}))
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 8002}, "text": "🛑 학습중단"}}))

    assert not vocab_service.has_session(telegram_id)
    assert "중단" in sent[-1][1]


def test_stop_learning_when_nothing_active(monkeypatch):
    fake_users, fake_user_words, sent = _wire_vocab(monkeypatch)
    telegram_id = "8003"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 8003}, "text": "/학습중단"}}))
    assert "진행 중인 학습이 없습니다" in sent[-1][1]


def _wire_grammar(monkeypatch, questions_by_topic=None):
    fake_users = FakeUsersRepo()
    fake_grammar = FakeGrammarRepo(questions_by_topic=questions_by_topic)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "grammar_repo", fake_grammar)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    return fake_users, fake_grammar, sent


def test_stop_learning_clears_grammar_session(monkeypatch):
    from app.grammar import service as grammar_service

    questions = {"현재시제": [_question_row(1, "현재시제", "She ___ to school.", ["go", "goes", "going", "went"], 1)]}
    fake_users, fake_grammar, sent = _wire_grammar(monkeypatch, questions_by_topic=questions)
    telegram_id = "8004"
    _setup_grammar_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 8004}, "text": "/문법학습"}}))
    assert grammar_service.is_active(telegram_id)

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 8004}, "text": "/학습중단"}}))

    assert not grammar_service.is_active(telegram_id)
    assert "중단" in sent[-1][1]
