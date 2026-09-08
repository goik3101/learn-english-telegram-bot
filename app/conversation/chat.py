from app.ai.gemini_client import generate_text
from app.content.generator import LEVEL_DESCRIPTIONS, tone_note
from app.conversation.difficulty import DEFAULT_LEVEL, level_name

_PROMPT_TEMPLATE = """너는 학습자와 영어로 짧은 대화 연습을 하는 친근한 회화 파트너다.
학습자 레벨: {level} ({level_desc}) — 이 수준에서 이해할 수 있는 어휘/문장 구조로만 대화하라.
회화 난이도(CEFR): {cefr_level} — 이 수준을 크게 벗어나는 어휘·문법은 꼭 필요한 경우가 아니면 쓰지 말고,
꼭 써야 한다면 괄호로 쉬운 뜻을 함께 제공하라(예: "I feel exhausted (= very tired) today.").
매번 영어로 1~2문장만 짧게 응답하고, 대화가 자연스럽게 이어지도록 후속 질문을 함께 던져라.
문법 교정이나 정답 제공은 하지 말고, 자연스러운 대화 상대 역할에만 집중하라.
{tone_note}{topic_instruction}{extra_instruction}
지금까지의 대화:
{transcript}
학습자: {user_message}

너의 응답 (영어로 1~2문장만, 다른 설명 없이):"""


def _format_transcript(history: list[tuple[str, str]]) -> str:
    if not history:
        return "(대화 시작 전)"
    lines = [f"{'학습자' if role == 'user' else '너'}: {content}" for role, content in history]
    return "\n".join(lines)


def _topic_instruction(topic: str | None, preview_words: list[str] | None) -> str:
    """회화 사전 단어학습: 오늘의 주제와, 그 주제로 미리 학습시킨 단어를 대화에서 우선 활용하도록 지시."""
    lines = []
    if topic:
        lines.append(f"오늘 대화 주제는 '{topic}'이다. 이 주제를 중심으로 대화를 이어가라.")
    if preview_words:
        word_list = ", ".join(preview_words)
        lines.append(f"학습자가 오늘 학습한 이 단어들({word_list})을 대화에서 우선적으로 활용할 것.")
    return "\n" + "\n".join(lines) + "\n" if lines else ""


async def generate_opening(
    level: str,
    learning_mode: str = "GENERAL",
    conversation_level: int = DEFAULT_LEVEL,
    extra_instruction: str = "",
    topic: str | None = None,
    preview_words: list[str] | None = None,
) -> str:
    level_desc = LEVEL_DESCRIPTIONS.get(level, "")
    prompt = _PROMPT_TEMPLATE.format(
        level=level,
        level_desc=level_desc,
        cefr_level=level_name(conversation_level),
        tone_note=tone_note(learning_mode),
        topic_instruction=_topic_instruction(topic, preview_words),
        extra_instruction=extra_instruction,
        transcript="(대화 시작 전)",
        user_message="(대화를 처음 시작해줘. 짧게 인사하고 흥미로운 질문을 하나 던져줘.)",
    )
    text = await generate_text(prompt)
    return text.strip()


async def generate_reply(
    level: str,
    history: list[tuple[str, str]],
    user_message: str,
    learning_mode: str = "GENERAL",
    conversation_level: int = DEFAULT_LEVEL,
    extra_instruction: str = "",
    topic: str | None = None,
    preview_words: list[str] | None = None,
) -> str:
    level_desc = LEVEL_DESCRIPTIONS.get(level, "")
    prompt = _PROMPT_TEMPLATE.format(
        level=level,
        level_desc=level_desc,
        cefr_level=level_name(conversation_level),
        tone_note=tone_note(learning_mode),
        topic_instruction=_topic_instruction(topic, preview_words),
        extra_instruction=extra_instruction,
        transcript=_format_transcript(history),
        user_message=user_message,
    )
    text = await generate_text(prompt)
    return text.strip()
