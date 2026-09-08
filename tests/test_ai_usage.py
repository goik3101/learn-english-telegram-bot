from app.ai import gemini_client, tts_client
from app.handlers import router
from tests.test_router import FakeUsersRepo, run


class FakeAiUsageRepo:
    def __init__(self, fail: bool = False):
        self.logged: list[str] = []
        self.fail = fail
        self.today = {}
        self.month = {}

    async def log_call(self, provider):
        if self.fail:
            raise RuntimeError("db down")
        self.logged.append(provider)

    async def get_today_counts(self):
        return self.today

    async def get_month_counts(self):
        return self.month


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeGenerativeModel:
    def __init__(self, model, generation_config=None):
        pass

    async def generate_content_async(self, prompt):
        return FakeResponse("fake response")


def test_generate_text_logs_gemini_usage(monkeypatch):
    fake_usage = FakeAiUsageRepo()
    monkeypatch.setattr(gemini_client, "ai_usage_repo", fake_usage)
    monkeypatch.setattr(gemini_client, "genai", type("genai", (), {"GenerativeModel": FakeGenerativeModel, "configure": lambda **kw: None}))
    monkeypatch.setattr(gemini_client.settings, "gemini_api_key", "fake-key")
    gemini_client._configured = False

    result = run(gemini_client.generate_text("hello"))
    assert result == "fake response"
    assert fake_usage.logged == ["gemini"]


def test_generate_json_logs_gemini_usage(monkeypatch):
    fake_usage = FakeAiUsageRepo()
    monkeypatch.setattr(gemini_client, "ai_usage_repo", fake_usage)
    monkeypatch.setattr(gemini_client, "genai", type("genai", (), {"GenerativeModel": FakeGenerativeModel, "configure": lambda **kw: None}))
    monkeypatch.setattr(gemini_client.settings, "gemini_api_key", "fake-key")
    gemini_client._configured = False

    result = run(gemini_client.generate_json("hello"))
    assert result == "fake response"
    assert fake_usage.logged == ["gemini"]


def test_gemini_usage_logging_failure_does_not_break_generation(monkeypatch):
    fake_usage = FakeAiUsageRepo(fail=True)
    monkeypatch.setattr(gemini_client, "ai_usage_repo", fake_usage)
    monkeypatch.setattr(gemini_client, "genai", type("genai", (), {"GenerativeModel": FakeGenerativeModel, "configure": lambda **kw: None}))
    monkeypatch.setattr(gemini_client.settings, "gemini_api_key", "fake-key")
    gemini_client._configured = False

    result = run(gemini_client.generate_text("hello"))
    assert result == "fake response"  # 로깅 실패해도 본 기능은 정상 동작(fail-open)


class FakeHttpResponse:
    def raise_for_status(self):
        pass

    def json(self):
        import base64

        return {"audioContent": base64.b64encode(b"audio-bytes").decode("ascii")}


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url, params=None, json=None):
        return FakeHttpResponse()


def test_synthesize_speech_logs_tts_usage(monkeypatch):
    fake_usage = FakeAiUsageRepo()
    monkeypatch.setattr(tts_client, "ai_usage_repo", fake_usage)
    monkeypatch.setattr(tts_client.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(tts_client.settings, "google_tts_api_key", "fake-key")

    result = run(tts_client.synthesize_speech("apple"))
    assert result == b"audio-bytes"
    assert fake_usage.logged == ["google_tts"]


def test_synthesize_speech_logging_failure_does_not_break_synthesis(monkeypatch):
    fake_usage = FakeAiUsageRepo(fail=True)
    monkeypatch.setattr(tts_client, "ai_usage_repo", fake_usage)
    monkeypatch.setattr(tts_client.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(tts_client.settings, "google_tts_api_key", "fake-key")

    result = run(tts_client.synthesize_speech("apple"))
    assert result == b"audio-bytes"


# --- 관리자 명령어 ---


def _wire(monkeypatch, today=None, month=None):
    fake_users = FakeUsersRepo()
    fake_usage = FakeAiUsageRepo()
    fake_usage.today = today or {}
    fake_usage.month = month or {}
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "ai_usage_repo", fake_usage)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text))

    monkeypatch.setattr(router, "send_message", fake_send)
    return fake_users, sent


def test_admin_ai_usage_command_shows_counts(monkeypatch):
    fake_users, sent = _wire(monkeypatch, today={"gemini": 12, "google_tts": 3}, month={"gemini": 340, "google_tts": 88})
    admin_id = "9001"
    run(fake_users.create_pending_user(admin_id))
    run(fake_users.approve_user(admin_id))
    fake_users.users[admin_id]["learning_mode"] = "GENERAL"
    fake_users.users[admin_id]["placement_level"] = "beginner"

    monkeypatch.setattr(router.settings, "admin_telegram_id", admin_id)

    run(router.handle_update({"message": {"chat": {"id": int(admin_id)}, "text": "/AI사용량"}}))

    text = sent[-1][1]
    assert "Gemini" in text and "12" in text and "340" in text
    assert "Google Cloud TTS" in text and "3" in text and "88" in text


def test_non_admin_cannot_use_ai_usage_command(monkeypatch):
    fake_users, sent = _wire(monkeypatch)
    telegram_id = "9002"
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "GENERAL"
    fake_users.users[telegram_id]["placement_level"] = "beginner"

    monkeypatch.setattr(router.settings, "admin_telegram_id", "9999")

    run(router.handle_update({"message": {"chat": {"id": 9002}, "text": "/AI사용량"}}))

    # 관리자 명령어가 아니라 일반 메뉴 안내로 빠져야 한다
    assert "Gemini" not in sent[-1][1]
