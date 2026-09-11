import asyncio

from app.handlers import router


class FakeUsersRepo:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self._next_id = 1
        self.activity_counts: dict[str, int] = {}

    async def get_user_by_telegram_id(self, telegram_id):
        return self.users.get(telegram_id)

    async def create_pending_user(self, telegram_id):
        if telegram_id in self.users:
            return None
        record = {
            "id": self._next_id,
            "telegram_id": telegram_id,
            "approved": False,
            "role": "user",
            "age": None,
            "learning_mode": None,
            "placement_level": None,
            "daily_new_word_limit": 5,
            "word_band": 0,
            "reading_band": 0,
            "target_use_case": None,
            "child_stage": 0,
            "created_at": "now",
            "last_active_at": None,
        }
        self._next_id += 1
        self.users[telegram_id] = record
        return record

    async def approve_user(self, telegram_id):
        self.users[telegram_id]["approved"] = True

    async def set_role(self, telegram_id, role):
        self.users[telegram_id]["role"] = role

    async def set_age_and_mode(self, telegram_id, age, learning_mode):
        self.users[telegram_id]["age"] = age
        self.users[telegram_id]["learning_mode"] = learning_mode

    async def set_placement_level(self, telegram_id, placement_level):
        self.users[telegram_id]["placement_level"] = placement_level

    async def set_daily_new_word_limit(self, telegram_id, limit):
        self.users[telegram_id]["daily_new_word_limit"] = limit

    async def set_child_stage(self, telegram_id, stage):
        self.users[telegram_id]["child_stage"] = stage

    async def set_word_band(self, telegram_id, band):
        self.users[telegram_id]["word_band"] = band

    async def set_reading_band(self, telegram_id, band):
        self.users[telegram_id]["reading_band"] = band

    async def touch_last_active(self, telegram_id):
        pass

    async def list_pending_users(self):
        return [u for u in self.users.values() if not u["approved"]]

    async def list_approved_users_with_activity(self):
        return [
            {**u, "today_activity_count": self.activity_counts.get(u["telegram_id"], 0)}
            for u in self.users.values()
            if u["approved"]
        ]


class FakePlacementRepo:
    def __init__(self):
        self.saved: list[tuple] = []

    async def save_result(self, user_id, word_correct, word_total, grammar_correct, grammar_total, level):
        self.saved.append((user_id, word_correct, word_total, grammar_correct, grammar_total, level))


def run(coro):
    return asyncio.run(coro)


def _wire(monkeypatch):
    fake_users = FakeUsersRepo()
    fake_placement = FakePlacementRepo()
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "placement_repo", fake_placement)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    return fake_users, fake_placement, sent


def test_new_user_start_registers_pending(monkeypatch):
    fake_users, _, sent = _wire(monkeypatch)

    run(router.handle_update({"message": {"chat": {"id": 111}, "text": "/start"}}))

    assert fake_users.users["111"]["approved"] is False
    assert "승인 대기" in sent[-1][1]


def test_unapproved_user_other_message_is_blocked(monkeypatch):
    fake_users, _, sent = _wire(monkeypatch)
    run(router.handle_update({"message": {"chat": {"id": 111}, "text": "/start"}}))

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 111}, "text": "hello"}}))

    assert "승인 대기" in sent[-1][1]


def test_full_flow_start_approve_age_mode(monkeypatch):
    fake_users, _, sent = _wire(monkeypatch)

    run(router.handle_update({"message": {"chat": {"id": 222}, "text": "/start"}}))
    run(fake_users.approve_user("222"))

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 222}, "text": "/start"}}))
    assert "나이" in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 222}, "text": "9"}}))
    assert "CHILD_BEGINNER" in sent[0][1]
    assert fake_users.users["222"]["age"] == 9


def test_age_boundaries_map_to_expected_modes(monkeypatch):
    fake_users, _, sent = _wire(monkeypatch)

    for telegram_id, age, expected_mode in [
        ("301", "10", "CHILD_BEGINNER"),
        ("302", "11", "CHILD_BRIDGE"),
        ("303", "12", "GENERAL"),
    ]:
        run(router.handle_update({"message": {"chat": {"id": int(telegram_id)}, "text": "/start"}}))
        run(fake_users.approve_user(telegram_id))
        run(router.handle_update({"message": {"chat": {"id": int(telegram_id)}, "text": "/start"}}))
        sent.clear()
        run(router.handle_update({"message": {"chat": {"id": int(telegram_id)}, "text": age}}))
        assert expected_mode in sent[0][1]
        assert fake_users.users[telegram_id]["learning_mode"] == expected_mode
