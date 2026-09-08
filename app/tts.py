"""M16: TTS 캐싱 오케스트레이션 — 같은 텍스트는 재합성하지 않고 캐시를 먼저 확인한다 (섹션16)."""

from app.ai import tts_client
from app.repo import tts_cache as tts_cache_repo

DEFAULT_LANGUAGE = "en-US"
DEFAULT_VOICE = "en-US-Standard-C"


async def get_speech_audio(text: str, language_code: str = DEFAULT_LANGUAGE, voice_name: str = DEFAULT_VOICE) -> bytes:
    key = tts_cache_repo.cache_key(text, language_code, voice_name)

    cached = await tts_cache_repo.get_cached_audio(key)
    if cached is not None:
        return cached

    audio = await tts_client.synthesize_speech(text, language_code, voice_name)
    await tts_cache_repo.save_cached_audio(key, audio)
    return audio
