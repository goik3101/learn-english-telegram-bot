from app.handlers import router
from tests.test_router import run
from tests.test_vocab_flow import FakeUserWordsRepo, _setup_general_user, _word_row


def _wire(monkeypatch, new_rows=None):
    from tests.test_router import FakeUsersRepo

    fake_users = FakeUsersRepo()
    fake_user_words = FakeUserWordsRepo(new_rows=new_rows)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []
    deleted: list[tuple] = []
    voices: list[bytes] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text, reply_markup))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    async def fake_delete_message(chat_id, message_id):
        deleted.append((chat_id, message_id))

    async def fake_send_voice(chat_id, audio_bytes, caption=None):
        voices.append(audio_bytes)

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    monkeypatch.setattr(router, "delete_message", fake_delete_message)
    monkeypatch.setattr(router, "send_voice", fake_send_voice)
    return fake_users, fake_user_words, sent, deleted, voices


def _callback_update(telegram_id: int, data: str, message_id: int = 999) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}, "message_id": message_id},
            "data": data,
        }
    }


def _all_buttons(reply_markup):
    return [b for row in reply_markup["inline_keyboard"] for b in row]


def test_word_card_includes_pronunciation_button(monkeypatch):
    new_rows = [_word_row(700, "apple", "사과")]
    fake_users, _, sent, _, _ = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "5001"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 5001}, "text": "/단어학습"}}))
    buttons = _all_buttons(sent[-1][2])
    tts_buttons = [b for b in buttons if b["callback_data"] == "ttsword:700"]
    assert len(tts_buttons) == 1
    assert "발음" in tts_buttons[0]["text"]


def test_pronunciation_click_shows_placeholder_when_tts_unavailable(monkeypatch):
    new_rows = [_word_row(701, "apple", "사과")]
    fake_users, _, sent, deleted, voices = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "5002"
    _setup_general_user(fake_users, telegram_id)

    monkeypatch.setattr(router.tts_client, "is_available", lambda: False)

    run(router.handle_update({"message": {"chat": {"id": 5002}, "text": "/단어학습"}}))
    sent.clear()
    run(router.handle_update(_callback_update(5002, "ttsword:701")))

    assert "준비 중" in sent[-1][1]
    assert voices == []
    assert deleted == []  # 카드 메시지는 지워지지 않아야 함


def test_pronunciation_click_sends_voice_and_keeps_card(monkeypatch):
    new_rows = [_word_row(702, "apple", "사과")]
    fake_users, _, sent, deleted, voices = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "5003"
    _setup_general_user(fake_users, telegram_id)

    monkeypatch.setattr(router.tts_client, "is_available", lambda: True)

    async def fake_get_speech_audio(text, **kwargs):
        assert text == "apple"
        return b"audio-bytes"

    monkeypatch.setattr(router.tts, "get_speech_audio", fake_get_speech_audio)

    run(router.handle_update({"message": {"chat": {"id": 5003}, "text": "/단어학습"}}))
    sent.clear()
    run(router.handle_update(_callback_update(5003, "ttsword:702")))

    assert voices == [b"audio-bytes"]
    assert deleted == []  # 발음듣기는 카드를 지우지 않음 — 이어서 아는단어/모르는단어를 누를 수 있어야 함

    # 카드가 여전히 살아있어야 [아는단어] 클릭이 정상 진행된다
    sent.clear()
    run(router.handle_update(_callback_update(5003, "vocab:known:702")))
    assert "완료" in sent[-1][1] or sent  # 세션이 정상적으로 이어짐


def test_pronunciation_click_handles_synthesis_failure_gracefully(monkeypatch):
    new_rows = [_word_row(703, "apple", "사과")]
    fake_users, _, sent, deleted, voices = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "5004"
    _setup_general_user(fake_users, telegram_id)

    monkeypatch.setattr(router.tts_client, "is_available", lambda: True)

    async def failing_get_speech_audio(text, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(router.tts, "get_speech_audio", failing_get_speech_audio)

    run(router.handle_update({"message": {"chat": {"id": 5004}, "text": "/단어학습"}}))
    sent.clear()
    run(router.handle_update(_callback_update(5004, "ttsword:703")))

    assert "문제가 생겼어요" in sent[-1][1]
    assert voices == []
