from app.ai.gemini_client import generate_text
from app.content.generator import LEVEL_DESCRIPTIONS

_PROMPT_TEMPLATE = """너는 학습자와 영어로 짧은 대화 연습을 하는 친근한 회화 파트너다.
학습자 레벨: {level} ({level_desc}) — 이 수준에서 이해할 수 있는 어휘/문장 구조로만 대화하라.
매번 영어로 1~2문장만 짧게 응답하고, 대화가 자연스럽게 이어지도록 후속 질문을 함께 던져라.
문법 교정이나 정답 제공은 하지 말고, 자연스러운 대화 상대 역할에만 집중하라.

지금까지의 대화:
{transcript}
학습자: {user_message}

너의 응답 (영어로 1~2문장만, 다른 설명 없이):"""


def _format_transcript(history: list[tuple[str, str]]) -> str:
    if not history:
        return "(대화 시작 전)"
    lines = [f"{'학습자' if role == 'user' else '너'}: {content}" for role, content in history]
    return "\n".join(lines)


async def generate_opening(level: str) -> str:
    level_desc = LEVEL_DESCRIPTIONS.get(level, "")
    prompt = _PROMPT_TEMPLATE.format(
        level=level,
        level_desc=level_desc,
        transcript="(대화 시작 전)",
        user_message="(대화를 처음 시작해줘. 짧게 인사하고 흥미로운 질문을 하나 던져줘.)",
    )
    text = await generate_text(prompt)
    return text.strip()


async def generate_reply(level: str, history: list[tuple[str, str]], user_message: str) -> str:
    level_desc = LEVEL_DESCRIPTIONS.get(level, "")
    prompt = _PROMPT_TEMPLATE.format(
        level=level,
        level_desc=level_desc,
        transcript=_format_transcript(history),
        user_message=user_message,
    )
    text = await generate_text(prompt)
    return text.strip()
