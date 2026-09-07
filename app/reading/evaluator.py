import json

from app.ai.gemini_client import generate_json

_PROMPT_TEMPLATE = """너는 영어 학습 코치다. 학습자가 아래 영어 지문을 한국어로 직접 해석했다.
학습자의 해석이 지문의 핵심 의미를 정확하게 담고 있는지 평가하라.
**정답(모범 번역)은 절대 직접 알려주지 마라** — 부족하다면 어느 부분을 다시 봐야 하는지 힌트만 줘라.

지문: {passage}
학습자의 해석: {translation}

아래 JSON 형식으로만 응답하라. 다른 설명은 절대 추가하지 마라.
{{
  "is_adequate": true 또는 false,
  "feedback_ko": "학습자에게 보여줄 1~2문장 한국어 피드백. is_adequate가 true면 짧은 칭찬, false면 정답을 알려주지 않는 선에서 어디를 다시 봐야 할지 힌트"
}}"""


async def evaluate(passage_text: str, user_translation: str) -> tuple[bool, str]:
    prompt = _PROMPT_TEMPLATE.format(passage=passage_text, translation=user_translation)
    raw = await generate_json(prompt)
    data = json.loads(raw)
    is_adequate = bool(data.get("is_adequate"))
    feedback = str(data.get("feedback_ko") or "").strip()
    return is_adequate, feedback
