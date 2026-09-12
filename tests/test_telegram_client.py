import asyncio

from app import telegram_client


def run(coro):
    return asyncio.run(coro)


def test_split_long_text_leaves_short_text_untouched():
    text = "짧은 메시지"
    assert telegram_client._split_long_text(text) == [text]


def test_split_long_text_splits_on_newline_boundary_under_limit():
    # 4096자를 넘는 텍스트 — 줄바꿈 경계에서 잘려야 문장이 중간에 끊기지 않는다.
    line = "가" * 100
    text = "\n".join([line] * 50)  # 100*50 + 줄바꿈 49개 = 5049자 > 4096
    chunks = telegram_client._split_long_text(text)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= telegram_client.TELEGRAM_MAX_MESSAGE_LENGTH
    # 원문 내용이 전부 보존되어야 한다(줄 단위로만 잘렸으므로 다시 합치면 원문과 같음).
    assert "\n".join(chunks) == text


def test_send_message_over_limit_sends_multiple_calls_with_keyboard_only_on_last(monkeypatch):
    calls: list[dict] = []

    async def fake_post(method, payload):
        calls.append(payload)

    monkeypatch.setattr(telegram_client, "_post", fake_post)

    long_text = "x" * 5000
    keyboard = {"inline_keyboard": [[{"text": "ok", "callback_data": "x"}]]}
    run(telegram_client.send_message(123, long_text, reply_markup=keyboard))

    assert len(calls) >= 2
    assert "reply_markup" not in calls[0]
    assert calls[-1]["reply_markup"] == keyboard
    assert sum(len(c["text"]) for c in calls) == len(long_text)


def test_send_message_under_limit_sends_single_call(monkeypatch):
    calls: list[dict] = []

    async def fake_post(method, payload):
        calls.append(payload)

    monkeypatch.setattr(telegram_client, "_post", fake_post)

    run(telegram_client.send_message(123, "짧은 메시지", reply_markup={"inline_keyboard": []}))

    assert len(calls) == 1
    assert calls[0]["text"] == "짧은 메시지"
    assert calls[0]["reply_markup"] == {"inline_keyboard": []}
