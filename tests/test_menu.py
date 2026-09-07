from app import menu
from app.handlers import router
from tests.test_vocab_flow import FakeUserWordsRepo, _setup_general_user, _wire, _word_row
from tests.test_router import run


def test_menu_command_shows_keyboard(monkeypatch):
    fake_users, _, sent = _wire(monkeypatch)
    telegram_id = "701"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 701}, "text": "/메뉴"}}))
    assert "메뉴" in sent[-1][1]


def test_vocab_study_button_starts_same_flow_as_command(monkeypatch):
    new_rows = [_word_row(50, "apple", "사과")]
    fake_users, _, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "702"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 702}, "text": menu.VOCAB_STUDY}}))
    assert "apple" in sent[-1][1]


def test_all_menu_buttons_are_implemented(monkeypatch):
    # M11 완료 시점 기준 메인 메뉴의 모든 버튼이 구현되어 NOT_YET_IMPLEMENTED는 비어있어야 한다.
    assert menu.NOT_YET_IMPLEMENTED == {}


def test_unrecognized_text_falls_back_to_menu(monkeypatch):
    fake_users, _, sent = _wire(monkeypatch)
    telegram_id = "703"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 703}, "text": "asdkfjalskdjf"}}))
    assert "이해하지 못했어요" in sent[-1][1]


def test_admin_button_hidden_action_for_non_admin_falls_through_to_menu(monkeypatch):
    fake_users, _, sent = _wire(monkeypatch)
    telegram_id = "704"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 704}, "text": menu.ADMIN}}))
    # 관리자가 아니므로 관리자 메뉴 대신 일반 fallback 메시지를 받는다
    assert "이해하지 못했어요" in sent[-1][1]


def test_callback_query_deletes_the_answered_message(monkeypatch):
    new_rows = [_word_row(60, "apple", "사과")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "705"
    _setup_general_user(fake_users, telegram_id)

    deleted: list[tuple] = []

    async def fake_delete_message(chat_id, message_id):
        deleted.append((chat_id, message_id))

    monkeypatch.setattr(router, "delete_message", fake_delete_message)

    run(router.handle_update({"message": {"chat": {"id": 705}, "text": "/단어학습"}}))
    run(
        router.handle_update(
            {
                "callback_query": {
                    "id": "cb1",
                    "from": {"id": 705},
                    "message": {"chat": {"id": 705}, "message_id": 999},
                    "data": "vocab:known:60",
                }
            }
        )
    )

    assert deleted == [(705, 999)]
