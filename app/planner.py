"""오늘의 학습 Planner의 "AI 보정" (기획서 섹션8-2/16: 규칙기반이 우선, AI는 하루 보정만).

문항 구성 자체는 규칙기반(app/today_session.py)이 그대로 결정하고, 여기서는 사용자의 최근
문법 오답 데이터를 바탕으로 오늘 학습을 시작하기 전에 보여줄 짧은 포커스 메시지만 만든다.
취약 주제가 없으면(데이터가 없거나 전부 정답) AI를 호출하지 않는다 — 불필요한 호출을 피한다.
"""

from app.ai.gemini_client import generate_text

_PROMPT_TEMPLATE = """너는 영어 학습 코치다. 학습자의 최근 문법 학습 기록을 보고,
오늘의 학습을 시작하기 전에 보여줄 1~2문장짜리 한국어 격려/포커스 메시지를 만들어라.

학습자 레벨: {level}
최근 문법 정답률: {accuracy}
자주 틀리는 문법 주제: {weak_topics}

말투 예시: "최근 가정법 문제에서 자주 틀리고 있어요. 오늘은 특히 집중해봐요!"
메시지만 출력하고 다른 설명은 절대 추가하지 마라."""


async def build_focus_message(level: str, weak_topics: list[str], accuracy: float | None) -> str | None:
    if not weak_topics:
        return None

    accuracy_text = f"{accuracy:.0%}" if accuracy is not None else "정보 없음"
    prompt = _PROMPT_TEMPLATE.format(level=level, accuracy=accuracy_text, weak_topics=", ".join(weak_topics))
    try:
        text = await generate_text(prompt)
    except Exception:
        return None
    return text.strip() or None
