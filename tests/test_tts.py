from app import tts
from app.repo import tts_cache as tts_cache_repo
from tests.test_router import run


def test_cache_key_is_deterministic_and_mode_sensitive():
    a = tts_cache_repo.cache_key("apple", "en-US", "en-US-Standard-C")
    b = tts_cache_repo.cache_key("apple", "en-US", "en-US-Standard-C")
    c = tts_cache_repo.cache_key("apple", "en-GB", "en-US-Standard-C")
    assert a == b
    assert a != c


class FakeTtsCacheRepo:
    def __init__(self, cached: bytes | None = None):
        self.cached = cached
        self.saved: list[tuple] = []

    def cache_key(self, text, language_code, voice_name):
        return f"{language_code}:{voice_name}:{text}"

    async def get_cached_audio(self, key):
        return self.cached

    async def save_cached_audio(self, key, audio_data):
        self.saved.append((key, audio_data))


def test_get_speech_audio_returns_cached_without_calling_tts_client(monkeypatch):
    fake_repo = FakeTtsCacheRepo(cached=b"cached-audio")
    monkeypatch.setattr(tts, "tts_cache_repo", fake_repo)

    called = False

    async def fake_synthesize(text, language_code, voice_name):
        nonlocal called
        called = True
        return b"fresh-audio"

    monkeypatch.setattr(tts.tts_client, "synthesize_speech", fake_synthesize)

    result = run(tts.get_speech_audio("apple"))
    assert result == b"cached-audio"
    assert called is False
    assert fake_repo.saved == []


def test_get_speech_audio_synthesizes_and_caches_on_miss(monkeypatch):
    fake_repo = FakeTtsCacheRepo(cached=None)
    monkeypatch.setattr(tts, "tts_cache_repo", fake_repo)

    async def fake_synthesize(text, language_code, voice_name):
        assert text == "apple"
        return b"fresh-audio"

    monkeypatch.setattr(tts.tts_client, "synthesize_speech", fake_synthesize)

    result = run(tts.get_speech_audio("apple"))
    assert result == b"fresh-audio"
    assert fake_repo.saved == [(fake_repo.cache_key("apple", tts.DEFAULT_LANGUAGE, tts.DEFAULT_VOICE), b"fresh-audio")]
