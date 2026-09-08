import base64
import logging

import httpx

from app.config import settings
from app.repo import ai_usage as ai_usage_repo

logger = logging.getLogger(__name__)

TTS_API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"


def is_available() -> bool:
    return bool(settings.google_tts_api_key)


async def _log_usage() -> None:
    """M17: 프로젝트 전체 TTS 호출량 추적 — 실패해도 본 기능에는 영향 없게 fail-open."""
    try:
        await ai_usage_repo.log_call("google_tts")
    except Exception:
        logger.exception("failed to log tts usage")


async def synthesize_speech(text: str, language_code: str = "en-US", voice_name: str = "en-US-Standard-C") -> bytes:
    """Google Cloud TTS로 텍스트를 음성으로 합성한다.

    OGG_OPUS로 인코딩해 텔레그램 sendVoice(음성메시지)와 별도 변환 없이 바로 호환되게 한다.
    """
    if not settings.google_tts_api_key:
        raise RuntimeError("GOOGLE_TTS_API_KEY not configured")

    payload = {
        "input": {"text": text},
        "voice": {"languageCode": language_code, "name": voice_name},
        "audioConfig": {"audioEncoding": "OGG_OPUS"},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(TTS_API_URL, params={"key": settings.google_tts_api_key}, json=payload)
        response.raise_for_status()
        data = response.json()

    await _log_usage()
    return base64.b64decode(data["audioContent"])
