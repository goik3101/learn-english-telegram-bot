import logging

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

# gemini-3.6/3.7/3.8-flash 등 최신 모델은 무료 티어 일일 한도가 프로젝트당 20회로 매우 낮음(실측 확인).
# gemini-3.1-flash-lite는 같은 세대의 구형 모델이라 표준 무료 티어(하루 1,500회)를 그대로 받는다.
_configured = False


def _ensure_configured() -> None:
    global _configured
    if not _configured and settings.gemini_api_key:
        genai.configure(api_key=settings.gemini_api_key)
        _configured = True


def is_available() -> bool:
    return bool(settings.gemini_api_key)


async def generate_text(prompt: str, model: str = "gemini-3.1-flash-lite") -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    _ensure_configured()
    gen_model = genai.GenerativeModel(model)
    response = await gen_model.generate_content_async(prompt)
    return response.text


async def generate_json(prompt: str, model: str = "gemini-3.1-flash-lite") -> str:
    """콘텐츠뱅크 대량생성처럼 구조화된 응답이 필요한 경우 사용 (섹션16: 콘텐츠뱅크는 최초 1회만 AI 호출)."""
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    _ensure_configured()
    gen_model = genai.GenerativeModel(model, generation_config={"response_mime_type": "application/json"})
    response = await gen_model.generate_content_async(prompt)
    return response.text
