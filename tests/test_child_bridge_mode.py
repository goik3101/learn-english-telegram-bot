from app.content.generator import tone_note
from app.handlers import router
from app.modes import determine_learning_mode
from tests.test_conversation_flow import FakeContentRepo, _complete_topic_word_preview
from tests.test_grammar_flow import FakeGrammarRepo, _question_row
from tests.test_reading_flow import FakeReadingRepo, _passage_row
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import FakeUserWordsRepo, _word_row


def test_age_11_maps_to_child_bridge_10_and_below_beginner_12_and_above_general():
    assert determine_learning_mode(10) == "CHILD_BEGINNER"
    assert determine_learning_mode(11) == "CHILD_BRIDGE"
    assert determine_learning_mode(12) == "GENERAL"


def test_tone_note_empty_for_general_mode():
    assert tone_note("GENERAL") == ""


def test_tone_note_present_for_child_bridge_mode():
    note = tone_note("CHILD_BRIDGE")
    assert "11세" in note
    assert "이모티콘" in note
    assert "위험한 주제" in note


def _setup_child_bridge_user(fake_users, telegram_id: str) -> None:
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "CHILD_BRIDGE"
    fake_users.users[telegram_id]["placement_level"] = "beginner"


def _wire(monkeypatch, new_rows=None, questions=None, passage_row=None):
    fake_users = FakeUsersRepo()
    fake_user_words = FakeUserWordsRepo(new_rows=new_rows)
    fake_grammar = FakeGrammarRepo(questions=questions)
    fake_reading = FakeReadingRepo(passage_row=passage_row)

    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "grammar_repo", fake_grammar)
    monkeypatch.setattr(router, "reading_repo", fake_reading)
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
    return fake_users, fake_user_words, fake_grammar, fake_reading, sent


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


def test_vocab_unknown_word_uses_child_bridge_distractor_pool(monkeypatch):
    new_rows = [_word_row(910, "apple", "사과")]
    fake_users, fake_user_words, _, _, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "2001"
    _setup_child_bridge_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 2001}, "text": "/단어학습"}}))
    assert "apple" in sent[-1][1]

    sent.clear()
    run(router.handle_update(_callback_update(2001, "vocab:unknown:910")))
    # 오답 선택지가 정상적으로 만들어졌다면(distractor 조회가 CHILD_BRIDGE 모드로도 정상 동작했다는 뜻) MCQ 질문이 온다.
    assert "뜻은 무엇일까요" in sent[-1][1]


def test_vocab_new_words_query_uses_child_bridge_mode(monkeypatch):
    calls: list[str] = []
    new_rows = [_word_row(911, "apple", "사과")]

    class RecordingRepo(FakeUserWordsRepo):
        async def get_new_words(self, user_id, level, limit, learning_mode="GENERAL", min_rank=None, max_rank=None):
            calls.append(learning_mode)
            return await super().get_new_words(user_id, level, limit, learning_mode, min_rank, max_rank)

    fake_users = FakeUsersRepo()
    fake_user_words = RecordingRepo(new_rows=new_rows)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "db_available", lambda: True)

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)

    telegram_id = "2002"
    _setup_child_bridge_user(fake_users, telegram_id)
    run(router.handle_update({"message": {"chat": {"id": 2002}, "text": "/단어학습"}}))

    assert calls == ["CHILD_BRIDGE"]


def test_grammar_session_scopes_questions_to_child_bridge(monkeypatch):
    questions = [_question_row(1, "현재완료", "I ___ finished.", ["have", "has", "had", "having"], 0)]
    fake_users, _, fake_grammar, _, sent = _wire(monkeypatch, questions=questions)
    telegram_id = "2003"
    _setup_child_bridge_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 2003}, "text": "/문법학습"}}))
    assert fake_grammar.mode_calls == ["CHILD_BRIDGE"]


def test_reading_session_scopes_passage_to_child_bridge(monkeypatch):
    fake_users, _, _, fake_reading, sent = _wire(monkeypatch, passage_row=_passage_row())
    telegram_id = "2004"
    _setup_child_bridge_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 2004}, "text": "/해석"}}))
    assert fake_reading.mode_calls == ["CHILD_BRIDGE"]


def test_conversation_opening_passes_child_bridge_mode(monkeypatch):
    fake_users = FakeUsersRepo()
    fake_content = FakeContentRepo()
    fake_user_words = FakeUserWordsRepo()
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "content_repo", fake_content)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "db_available", lambda: True)

    calls: list[str] = []

    async def fake_opening(level, learning_mode="GENERAL", conversation_level=2, extra_instruction="", topic=None, preview_words=None):
        calls.append(learning_mode)
        return "Hi! Let's practice English together! 🙂"

    async def fake_create_session(user_id, level, topic=None, preview_word_ids=None):
        return 1

    async def fake_add_message(session_id, role, text):
        pass

    monkeypatch.setattr(router.conversation_chat, "generate_opening", fake_opening)
    monkeypatch.setattr(router.conversation_repo, "create_session", fake_create_session)
    monkeypatch.setattr(router.conversation_repo, "add_message", fake_add_message)
    async def fake_has_completed_today(user_id):
        return False

    monkeypatch.setattr(router.conversation_repo, "has_completed_today", fake_has_completed_today)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)

    telegram_id = "2005"
    _setup_child_bridge_user(fake_users, telegram_id)
    run(router.handle_update({"message": {"chat": {"id": 2005}, "text": "/회화"}}))
    _complete_topic_word_preview(2005, fake_content.topic_word_rows)

    assert calls == ["CHILD_BRIDGE"]
