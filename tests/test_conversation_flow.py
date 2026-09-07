from app.handlers import router
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import _setup_general_user


class FakeConversationRepo:
    def __init__(self, already_done=False):
        self.already_done = already_done
        self.sessions: dict[int, dict] = {}
        self._next_id = 1
        self.messages: list[tuple] = []

    async def has_completed_today(self, user_id):
        return self.already_done

    async def create_session(self, user_id, level):
        session_id = self._next_id
        self._next_id += 1
        self.sessions[session_id] = {"user_id": user_id, "level": level, "completed": False, "turn_count": 0}
        return session_id

    async def add_message(self, session_id, role, content):
        self.messages.append((session_id, role, content))

    async def complete_session(self, session_id, turn_count):
        self.sessions[session_id]["completed"] = True
        self.sessions[session_id]["turn_count"] = turn_count


def _wire(monkeypatch, already_done=False):
    fake_users = FakeUsersRepo()
    fake_conversation = FakeConversationRepo(already_done=already_done)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "conversation_repo", fake_conversation)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text))

    monkeypatch.setattr(router, "send_message", fake_send)
    return fake_users, fake_conversation, sent


def test_conversation_blocked_if_already_done_today(monkeypatch):
    fake_users, fake_conversation, sent = _wire(monkeypatch, already_done=True)
    telegram_id = "1101"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 1101}, "text": "/회화"}}))
    assert "이미 완료" in sent[-1][1]


def test_admin_bypasses_daily_limit(monkeypatch):
    fake_users, fake_conversation, sent = _wire(monkeypatch, already_done=True)
    telegram_id = "1104"
    _setup_general_user(fake_users, telegram_id)
    fake_users.users[telegram_id]["role"] = "admin"

    async def fake_opening(level):
        return "Hi again! Ready for another round?"

    monkeypatch.setattr(router.conversation_chat, "generate_opening", fake_opening)

    run(router.handle_update({"message": {"chat": {"id": 1104}, "text": "/회화"}}))
    assert "Hi again" in sent[-1][1]  # 하루 1회 제한과 무관하게 바로 시작됨


def test_conversation_runs_five_turns_then_completes(monkeypatch):
    fake_users, fake_conversation, sent = _wire(monkeypatch)
    telegram_id = "1102"
    _setup_general_user(fake_users, telegram_id)

    async def fake_opening(level):
        return "Hi! What did you do today?"

    reply_calls: list[tuple] = []

    async def fake_reply(level, history, user_message):
        reply_calls.append((level, len(history), user_message))
        return f"That's great! Turn {len(reply_calls)} — tell me more?"

    monkeypatch.setattr(router.conversation_chat, "generate_opening", fake_opening)
    monkeypatch.setattr(router.conversation_chat, "generate_reply", fake_reply)

    run(router.handle_update({"message": {"chat": {"id": 1102}, "text": "/회화"}}))
    assert "Hi! What did you do today?" in sent[-1][1]

    for i in range(5):
        sent.clear()
        run(router.handle_update({"message": {"chat": {"id": 1102}, "text": f"My answer {i}"}}))

    assert "회화 연습 완료" in sent[-1][1]
    assert len(reply_calls) == 5
    session = list(fake_conversation.sessions.values())[0]
    assert session["completed"] is True
    assert session["turn_count"] == 5


def test_conversation_ai_failure_does_not_break_flow(monkeypatch):
    fake_users, fake_conversation, sent = _wire(monkeypatch)
    telegram_id = "1103"
    _setup_general_user(fake_users, telegram_id)

    async def fake_opening(level):
        return "Hello! Ready to chat?"

    async def failing_reply(level, history, user_message):
        raise RuntimeError("boom")

    monkeypatch.setattr(router.conversation_chat, "generate_opening", fake_opening)
    monkeypatch.setattr(router.conversation_chat, "generate_reply", failing_reply)

    run(router.handle_update({"message": {"chat": {"id": 1103}, "text": "/회화"}}))
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1103}, "text": "hi there"}}))

    assert sent  # 뭔가 응답은 옴 (대화가 끊기지 않음)
