from app.handlers import router
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import FakeUserWordsRepo, _setup_general_user, _word_row


class FakeConversationRepo:
    def __init__(self, already_done=False):
        self.already_done = already_done
        self.sessions: dict[int, dict] = {}
        self._next_id = 1
        self.messages: list[tuple] = []

    async def has_completed_today(self, user_id):
        return self.already_done

    async def create_session(self, user_id, level, topic=None, preview_word_ids=None):
        session_id = self._next_id
        self._next_id += 1
        self.sessions[session_id] = {
            "user_id": user_id,
            "level": level,
            "topic": topic,
            "preview_word_ids": preview_word_ids or [],
            "completed": False,
            "turn_count": 0,
        }
        return session_id

    async def add_message(self, session_id, role, content):
        self.messages.append((session_id, role, content))

    async def complete_session(self, session_id, turn_count):
        self.sessions[session_id]["completed"] = True
        self.sessions[session_id]["turn_count"] = turn_count


class FakeContentRepo:
    """회화 사전 단어학습용 — 기본으로 주제 단어가 이미 콘텐츠뱅크에 충분히 있는 것으로 취급해
    (get_topic_words가 5개 이상 반환) AI 생성 경로를 타지 않게 한다. 생성 폴백을 검증하는 테스트는
    topic_word_rows=[]로 준비해 별도로 호출한다."""

    def __init__(self, topic_word_rows=None):
        self.topic_word_rows = topic_word_rows if topic_word_rows is not None else _default_topic_words()
        self.inserted_words: list[tuple] = []
        self.linked: list[tuple] = []
        self._next_id = 900

    async def get_topic_words(self, topic, level, learning_mode, limit):
        return self.topic_word_rows[:limit]

    async def insert_words(self, level, words, learning_mode="GENERAL"):
        self.inserted_words.append((level, words))
        return len(words)

    async def get_word_ids(self, words, learning_mode="GENERAL"):
        ids = {}
        for w in words:
            ids[w] = self._next_id
            self._next_id += 1
        return ids

    async def insert_conversation_topic_words(self, topic, level, learning_mode, word_ids):
        self.linked.append((topic, level, learning_mode, word_ids))
        self.topic_word_rows = [
            _word_row(word_id, f"word{word_id}", f"뜻{word_id}") for word_id in word_ids
        ]

    async def get_frequency_ranks(self, words):
        return {}


def _default_topic_words():
    return [_word_row(200 + i, f"topicword{i}", f"주제단어{i}") for i in range(5)]


def _wire(monkeypatch, already_done=False, topic_word_rows=None):
    fake_users = FakeUsersRepo()
    fake_conversation = FakeConversationRepo(already_done=already_done)
    fake_content = FakeContentRepo(topic_word_rows=topic_word_rows)
    fake_user_words = FakeUserWordsRepo()
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "conversation_repo", fake_conversation)
    monkeypatch.setattr(router, "content_repo", fake_content)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
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
    return fake_users, fake_conversation, fake_content, sent


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


def _complete_topic_word_preview(telegram_id: int, word_rows: list[dict]) -> None:
    """오늘의 주제 단어카드를 전부 "아는단어"로 눌러 넘긴다 — 실제 회화 시작 직전 단계."""
    for row in word_rows:
        run(router.handle_update(_callback_update(telegram_id, f"vocab:known:{row['word_id']}")))


async def _fake_opening(
    level, learning_mode="GENERAL", conversation_level=2, extra_instruction="", topic=None, preview_words=None
):
    return "Hi! What did you do today?"


def test_conversation_blocked_if_already_done_today(monkeypatch):
    fake_users, fake_conversation, fake_content, sent = _wire(monkeypatch, already_done=True)
    telegram_id = "1101"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 1101}, "text": "/회화"}}))
    assert "이미 완료" in sent[-1][1]


def test_admin_bypasses_daily_limit(monkeypatch):
    fake_users, fake_conversation, fake_content, sent = _wire(monkeypatch, already_done=True)
    telegram_id = "1104"
    _setup_general_user(fake_users, telegram_id)
    fake_users.users[telegram_id]["role"] = "admin"

    monkeypatch.setattr(router.conversation_chat, "generate_opening", _fake_opening)

    run(router.handle_update({"message": {"chat": {"id": 1104}, "text": "/회화"}}))
    # 하루 1회 제한과 무관하게, 먼저 오늘의 주제 단어카드부터 시작된다.
    assert any("오늘의 회화 주제" in m[1] for m in sent)

    sent.clear()
    _complete_topic_word_preview(1104, fake_content.topic_word_rows)
    assert "Hi! What did you do today?" in sent[-1][1]


def test_conversation_starts_with_topic_word_preview_then_runs_five_turns(monkeypatch):
    fake_users, fake_conversation, fake_content, sent = _wire(monkeypatch)
    telegram_id = "1102"
    _setup_general_user(fake_users, telegram_id)

    captured_opening_calls: list[dict] = []
    captured_reply_calls: list[dict] = []

    async def fake_opening(level, learning_mode="GENERAL", conversation_level=2, extra_instruction="", topic=None, preview_words=None):
        captured_opening_calls.append({"topic": topic, "preview_words": preview_words})
        return "Hi! What did you do today?"

    async def fake_reply(
        level, history, user_message, learning_mode="GENERAL", conversation_level=2,
        extra_instruction="", topic=None, preview_words=None,
    ):
        captured_reply_calls.append({"topic": topic, "preview_words": preview_words})
        return f"That's great! Turn {len(captured_reply_calls)} — tell me more?"

    monkeypatch.setattr(router.conversation_chat, "generate_opening", fake_opening)
    monkeypatch.setattr(router.conversation_chat, "generate_reply", fake_reply)

    run(router.handle_update({"message": {"chat": {"id": 1102}, "text": "/회화"}}))
    # 회화가 아니라 먼저 오늘의 주제 단어카드가 나온다.
    assert "오늘의 회화 주제" in sent[-2][1] or "오늘의 회화 주제" in sent[-1][1]
    assert fake_conversation.sessions == {}  # 아직 실제 회화 세션은 시작되지 않음

    sent.clear()
    _complete_topic_word_preview(1102, fake_content.topic_word_rows)
    assert "Hi! What did you do today?" in sent[-1][1]
    assert len(fake_conversation.sessions) == 1
    session = list(fake_conversation.sessions.values())[0]
    assert session["topic"]  # 주제가 기록됨
    assert set(session["preview_word_ids"]) == {row["word_id"] for row in fake_content.topic_word_rows}
    assert captured_opening_calls[0]["topic"] == session["topic"]
    assert set(captured_opening_calls[0]["preview_words"]) == {row["word"] for row in fake_content.topic_word_rows}

    for i in range(5):
        sent.clear()
        run(router.handle_update({"message": {"chat": {"id": 1102}, "text": f"My answer {i}"}}))

    assert any("회화 연습 완료" in m[1] for m in sent)
    assert "난이도가 어땠나요" in sent[-1][1]  # 세션 종료 뒤 난이도 피드백 요청이 마지막에 옴
    assert len(captured_reply_calls) == 5
    assert all(call["topic"] == session["topic"] for call in captured_reply_calls)
    session = list(fake_conversation.sessions.values())[0]
    assert session["completed"] is True
    assert session["turn_count"] == 5


def test_conversation_ai_failure_does_not_break_flow(monkeypatch):
    fake_users, fake_conversation, fake_content, sent = _wire(monkeypatch)
    telegram_id = "1103"
    _setup_general_user(fake_users, telegram_id)

    async def failing_reply(
        level, history, user_message, learning_mode="GENERAL", conversation_level=2,
        extra_instruction="", topic=None, preview_words=None,
    ):
        raise RuntimeError("boom")

    monkeypatch.setattr(router.conversation_chat, "generate_opening", _fake_opening)
    monkeypatch.setattr(router.conversation_chat, "generate_reply", failing_reply)

    run(router.handle_update({"message": {"chat": {"id": 1103}, "text": "/회화"}}))
    _complete_topic_word_preview(1103, fake_content.topic_word_rows)
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1103}, "text": "hi there"}}))

    assert sent  # 뭔가 응답은 옴 (대화가 끊기지 않음)


def test_conversation_generates_and_caches_topic_words_when_missing(monkeypatch):
    fake_users, fake_conversation, fake_content, sent = _wire(monkeypatch, topic_word_rows=[])
    telegram_id = "1105"
    _setup_general_user(fake_users, telegram_id)

    generated = [
        {
            "word": "suitcase",
            "meaning_ko": "여행 가방",
            "part_of_speech": "noun",
            "pronunciation": "/ˈsuːtkeɪs/",
            "example_sentence": "I packed my suitcase.",
            "example_translation": "나는 여행 가방을 쌌다.",
            "frequency_rank": 2000,
        }
    ]

    async def fake_generate_topic_words(level, topic, count, learning_mode="GENERAL"):
        return generated

    monkeypatch.setattr(router.content_generator, "generate_topic_words", fake_generate_topic_words)
    monkeypatch.setattr(router.conversation_chat, "generate_opening", _fake_opening)

    run(router.handle_update({"message": {"chat": {"id": 1105}, "text": "/회화"}}))

    assert fake_content.inserted_words  # 생성된 단어가 콘텐츠뱅크에 저장됨
    assert fake_content.linked  # 주제와 연결됨
    assert any("오늘의 회화 주제" in m[1] for m in sent)
