from app.handlers import router
from app.placement.questions import ALL_QUESTIONS
from tests.test_router import FakePlacementRepo, FakeUsersRepo, run


def _wire(monkeypatch):
    fake_users = FakeUsersRepo()
    fake_placement = FakePlacementRepo()
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "placement_repo", fake_placement)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    async def fake_delete_message(chat_id, message_id):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    monkeypatch.setattr(router, "delete_message", fake_delete_message)
    return fake_users, fake_placement, sent


def _callback_update(telegram_id: int, question_id: str, choice_index: int) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": f"placement:{question_id}:{choice_index}",
        }
    }


def test_full_placement_quiz_all_correct_yields_advanced(monkeypatch):
    fake_users, fake_placement, sent = _wire(monkeypatch)
    telegram_id = 999

    run(router.handle_update({"message": {"chat": {"id": telegram_id}, "text": "/start"}}))
    run(fake_users.approve_user(str(telegram_id)))
    run(router.handle_update({"message": {"chat": {"id": telegram_id}, "text": "/start"}}))
    run(router.handle_update({"message": {"chat": {"id": telegram_id}, "text": "12"}}))  # -> GENERAL

    for question in ALL_QUESTIONS:
        sent.clear()
        run(router.handle_update(_callback_update(telegram_id, question.id, question.correct_index)))

    assert "advanced" in sent[-1][1]
    assert fake_users.users[str(telegram_id)]["placement_level"] == "advanced"
    assert len(fake_placement.saved) == 1
    saved_user_id, word_c, word_t, grammar_c, grammar_t, level = fake_placement.saved[0]
    assert (word_c, word_t, grammar_c, grammar_t, level) == (5, 5, 5, 5, "advanced")


def test_placement_all_wrong_yields_beginner(monkeypatch):
    fake_users, fake_placement, sent = _wire(monkeypatch)
    telegram_id = 777

    run(router.handle_update({"message": {"chat": {"id": telegram_id}, "text": "/start"}}))
    run(fake_users.approve_user(str(telegram_id)))
    run(router.handle_update({"message": {"chat": {"id": telegram_id}, "text": "/start"}}))
    run(router.handle_update({"message": {"chat": {"id": telegram_id}, "text": "13"}}))  # -> GENERAL

    for question in ALL_QUESTIONS:
        wrong_index = (question.correct_index + 1) % len(question.choices)
        sent.clear()
        run(router.handle_update(_callback_update(telegram_id, question.id, wrong_index)))

    assert "beginner" in sent[-1][1]
    assert fake_users.users[str(telegram_id)]["placement_level"] == "beginner"


def test_placement_unknown_question_id_is_ignored(monkeypatch):
    fake_users, _, sent = _wire(monkeypatch)
    telegram_id = 888

    run(router.handle_update({"message": {"chat": {"id": telegram_id}, "text": "/start"}}))
    run(fake_users.approve_user(str(telegram_id)))
    run(router.handle_update({"message": {"chat": {"id": telegram_id}, "text": "/start"}}))
    run(router.handle_update({"message": {"chat": {"id": telegram_id}, "text": "12"}}))

    sent.clear()
    run(router.handle_update(_callback_update(telegram_id, "does-not-exist", 0)))
    assert "이미 처리" in sent[-1][1] or "만료" in sent[-1][1]
