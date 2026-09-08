from app.conversation import difficulty as conversation_difficulty
from app.handlers import router
from tests.test_conversation_flow import FakeContentRepo, _complete_topic_word_preview
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import FakeUserWordsRepo


def test_tokenize_lowercases_and_strips_punctuation():
    assert conversation_difficulty.tokenize("Hello, World! It's great.") == ["hello", "world", "it's", "great"]


def test_candidate_forms_includes_base_form_for_inflections():
    forms = conversation_difficulty.candidate_forms("importantly")
    assert "importantly" in forms
    assert "important" in forms


def test_candidate_forms_does_not_over_strip_short_words():
    # "is"에서 접미사 "s"를 떼면 "i"가 되는데 길이 조건(>=3)에 안 맞아 후보에서 제외되어야 한다.
    forms = conversation_difficulty.candidate_forms("is")
    assert forms == ["is"]


def test_is_too_difficult_false_when_no_words_found():
    assert conversation_difficulty.is_too_difficult("Hello there, how are you?", 2, {}) is False


def test_is_too_difficult_true_when_enough_hard_words_matched():
    text = "That situation is quite inexorable and obfuscated."
    rank_by_word = {"inexorable": 15000, "obfuscated": 12000}
    assert conversation_difficulty.is_too_difficult(text, 2, rank_by_word) is True


def test_is_too_difficult_false_when_only_one_hard_word():
    text = "That situation is quite inexorable."
    rank_by_word = {"inexorable": 15000}
    assert conversation_difficulty.is_too_difficult(text, 2, rank_by_word) is False


def test_is_too_difficult_false_when_words_within_level_threshold():
    text = "I feel happy today."
    rank_by_word = {"happy": 300, "today": 200}
    assert conversation_difficulty.is_too_difficult(text, 0, rank_by_word) is False


def test_adjust_level_easy_increases_and_clamps_at_max():
    assert conversation_difficulty.adjust_level(2, "easy") == 3
    assert conversation_difficulty.adjust_level(conversation_difficulty.MAX_LEVEL, "easy") == conversation_difficulty.MAX_LEVEL


def test_adjust_level_hard_decreases_and_clamps_at_min():
    assert conversation_difficulty.adjust_level(2, "hard") == 1
    assert conversation_difficulty.adjust_level(conversation_difficulty.MIN_LEVEL, "hard") == conversation_difficulty.MIN_LEVEL


def test_adjust_level_ok_holds():
    assert conversation_difficulty.adjust_level(2, "ok") == 2


# --- 라우터 통합 ---


class FakeConversationRepo:
    def __init__(self):
        self.sessions: dict[int, dict] = {}
        self._next_id = 1

    async def has_completed_today(self, user_id):
        return False

    async def create_session(self, user_id, level, topic=None, preview_word_ids=None):
        session_id = self._next_id
        self._next_id += 1
        self.sessions[session_id] = {"user_id": user_id, "level": level, "messages": [], "completed": False}
        return session_id

    async def add_message(self, session_id, role, text):
        self.sessions[session_id]["messages"].append((role, text))

    async def complete_session(self, session_id, turn_count):
        self.sessions[session_id]["completed"] = True
        self.sessions[session_id]["turn_count"] = turn_count


def _wire(monkeypatch):
    fake_users = FakeUsersRepo()
    fake_conversation = FakeConversationRepo()
    fake_content = FakeContentRepo()
    fake_user_words = FakeUserWordsRepo()
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "conversation_repo", fake_conversation)
    monkeypatch.setattr(router, "content_repo", fake_content)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text, reply_markup))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    return fake_users, fake_conversation, fake_content, sent


def _setup_general_user(fake_users, telegram_id):
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "GENERAL"
    fake_users.users[telegram_id]["placement_level"] = "beginner"


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


def test_opening_passes_conversation_level_to_prompt(monkeypatch):
    fake_users, fake_conversation, fake_content, sent = _wire(monkeypatch)
    telegram_id = "9301"
    _setup_general_user(fake_users, telegram_id)
    fake_users.users[telegram_id]["conversation_level"] = 4

    captured = {}

    async def fake_opening(level, learning_mode="GENERAL", conversation_level=2, extra_instruction="", topic=None, preview_words=None):
        captured["conversation_level"] = conversation_level
        return "Hi!"

    async def fake_not_difficult(text, level):
        return False

    monkeypatch.setattr(router.conversation_chat, "generate_opening", fake_opening)
    monkeypatch.setattr(router, "_is_reply_too_difficult", fake_not_difficult)

    run(router.handle_update({"message": {"chat": {"id": 9301}, "text": "/회화"}}))
    _complete_topic_word_preview(9301, fake_content.topic_word_rows)
    assert captured["conversation_level"] == 4


def test_too_difficult_opening_triggers_one_regeneration(monkeypatch):
    fake_users, fake_conversation, fake_content, sent = _wire(monkeypatch)
    telegram_id = "9302"
    _setup_general_user(fake_users, telegram_id)

    calls = []

    async def fake_opening(level, learning_mode="GENERAL", conversation_level=2, extra_instruction="", topic=None, preview_words=None):
        calls.append(extra_instruction)
        return "simpler hi" if extra_instruction else "hard opening"

    async def fake_check(text, level):
        return text == "hard opening"

    monkeypatch.setattr(router.conversation_chat, "generate_opening", fake_opening)
    monkeypatch.setattr(router, "_is_reply_too_difficult", fake_check)

    run(router.handle_update({"message": {"chat": {"id": 9302}, "text": "/회화"}}))
    sent.clear()
    _complete_topic_word_preview(9302, fake_content.topic_word_rows)

    assert len(calls) == 2
    assert calls[0] == ""
    assert calls[1] != ""
    assert any("simpler hi" in m[1] for m in sent)


def test_difficulty_feedback_updates_conversation_level(monkeypatch):
    fake_users, fake_conversation, fake_content, sent = _wire(monkeypatch)
    telegram_id = "9303"
    _setup_general_user(fake_users, telegram_id)
    fake_users.users[telegram_id]["conversation_level"] = 2

    run(router.handle_update(_callback_update(9303, "convfeedback:easy")))

    assert fake_users.users[telegram_id]["conversation_level"] == 3
    assert "B2" in sent[-1][1]


def test_difficulty_feedback_hard_decreases_level(monkeypatch):
    fake_users, fake_conversation, fake_content, sent = _wire(monkeypatch)
    telegram_id = "9304"
    _setup_general_user(fake_users, telegram_id)
    fake_users.users[telegram_id]["conversation_level"] = 2

    run(router.handle_update(_callback_update(9304, "convfeedback:hard")))

    assert fake_users.users[telegram_id]["conversation_level"] == 1


def test_feedback_keyboard_shown_after_five_turns(monkeypatch):
    fake_users, fake_conversation, fake_content, sent = _wire(monkeypatch)
    telegram_id = "9305"
    _setup_general_user(fake_users, telegram_id)

    async def fake_opening(level, learning_mode="GENERAL", conversation_level=2, extra_instruction="", topic=None, preview_words=None):
        return "Hi!"

    async def fake_reply(
        level, history, user_message, learning_mode="GENERAL", conversation_level=2,
        extra_instruction="", topic=None, preview_words=None,
    ):
        return "Nice, tell me more?"

    async def fake_not_difficult(text, level):
        return False

    monkeypatch.setattr(router.conversation_chat, "generate_opening", fake_opening)
    monkeypatch.setattr(router.conversation_chat, "generate_reply", fake_reply)
    monkeypatch.setattr(router, "_is_reply_too_difficult", fake_not_difficult)

    run(router.handle_update({"message": {"chat": {"id": 9305}, "text": "/회화"}}))
    _complete_topic_word_preview(9305, fake_content.topic_word_rows)
    for i in range(5):
        run(router.handle_update({"message": {"chat": {"id": 9305}, "text": f"answer {i}"}}))

    buttons = [b["callback_data"] for row in sent[-1][2]["inline_keyboard"] for b in row]
    assert buttons == ["convfeedback:easy", "convfeedback:ok", "convfeedback:hard"]
