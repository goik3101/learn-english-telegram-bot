from app.handlers import router
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import _setup_general_user


class FakeUserWordsProgressRepo:
    def __init__(self, counts=None):
        self.counts = counts or {}

    async def get_progress_counts(self, user_id):
        return self.counts


class FakeGrammarProgressRepo:
    def __init__(self, accuracy=None, weak_topics=None):
        self.accuracy = accuracy
        self.weak_topics = weak_topics or []

    async def get_overall_accuracy(self, user_id):
        return self.accuracy

    async def get_weak_topics(self, user_id, limit):
        return self.weak_topics[:limit]


class FakeReadingProgressRepo:
    def __init__(self, total=0, adequate=0):
        self.total = total
        self.adequate = adequate

    async def get_progress_stats(self, user_id):
        return {"total": self.total, "adequate": self.adequate}


class FakeConversationProgressRepo:
    def __init__(self, completed=0):
        self.completed = completed

    async def get_completed_session_count(self, user_id):
        return self.completed


def _wire(monkeypatch, **kwargs):
    fake_users = FakeUsersRepo()
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", FakeUserWordsProgressRepo(kwargs.get("word_counts")))
    monkeypatch.setattr(
        router, "grammar_repo", FakeGrammarProgressRepo(kwargs.get("accuracy"), kwargs.get("weak_topics"))
    )
    monkeypatch.setattr(
        router, "reading_repo", FakeReadingProgressRepo(kwargs.get("reading_total", 0), kwargs.get("reading_adequate", 0))
    )
    monkeypatch.setattr(router, "conversation_repo", FakeConversationProgressRepo(kwargs.get("conversation_completed", 0)))
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text))

    monkeypatch.setattr(router, "send_message", fake_send)
    return fake_users, sent


def test_progress_report_with_full_data(monkeypatch):
    fake_users, sent = _wire(
        monkeypatch,
        word_counts={"known": 12, "learning": 3},
        accuracy=0.75,
        weak_topics=["가정법"],
        reading_total=4,
        reading_adequate=2,
        conversation_completed=1,
    )
    telegram_id = "1201"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 1201}, "text": "/진도"}}))

    report = sent[-1][1]
    assert "완전히 익힘 12개" in report
    assert "학습중 3개" in report
    assert "75%" in report
    assert "가정법" in report
    assert "4회 시도" in report
    assert "적절 판정 2회" in report
    assert "완료한 세션 1회" in report


def test_progress_report_handles_no_data_gracefully(monkeypatch):
    fake_users, sent = _wire(monkeypatch)
    telegram_id = "1202"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 1202}, "text": "/진도"}}))

    report = sent[-1][1]
    assert "아직 학습 기록 없음" in report


def test_admin_users_list_shows_id_age_and_daily_activity(monkeypatch):
    fake_users, sent = _wire(monkeypatch)
    monkeypatch.setattr(router.settings, "admin_telegram_id", "9999")

    admin_id = "9999"
    run(fake_users.create_pending_user(admin_id))
    run(fake_users.approve_user(admin_id))
    fake_users.users[admin_id]["age"] = 30
    fake_users.users[admin_id]["learning_mode"] = "GENERAL"
    fake_users.users[admin_id]["placement_level"] = "advanced"
    fake_users.activity_counts[admin_id] = 7

    run(router.handle_update({"message": {"chat": {"id": int(admin_id)}, "text": "/사용자목록"}}))

    report = sent[-1][1]
    assert "9999" in report
    assert "30세" in report
    assert "오늘 활동 7회" in report
