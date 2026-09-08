import json
from typing import Any

from app.ai.gemini_client import generate_json
from app.content.generator import LEVEL_DESCRIPTIONS, tone_note

_QUESTION_REQUIRED_FIELDS = {"question", "choices", "correct_index", "explanation"}

_PROMPT_TEMPLATE = """너는 학교 수행평가/시험 대비를 돕는 영어 교사다. 아래는 학생이 학교 수행평가 과제로 받은 영어 지문이다.
학습자 레벨: {level} ({level_desc})
{tone_note}
지문:
{text}

다음 두 가지를 생성하라.
1. grammar_explanation: 이 지문에 나오는 핵심 문법 포인트 2~3개를 한국어로 설명 (각 포인트마다 지문에서 실제 쓰인 문장을 예시로 인용).
2. exam_questions: 이 지문의 내용/문법/어휘를 바탕으로 학교 시험에 나올 법한 4지선다 객관식 예상 문제 {count}개.

아래 JSON 객체 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. correct_index는 0부터 시작하는 정수다.
{{
  "grammar_explanation": "핵심 문법 설명 (여러 포인트는 줄바꿈으로 구분)",
  "exam_questions": [
    {{
      "question": "예상 시험 문제 (지문 내용/문법/어휘 기반)",
      "choices": ["선택지1", "선택지2", "선택지3", "선택지4"],
      "correct_index": 0,
      "explanation": "정답 이유에 대한 한국어 설명"
    }}
  ]
}}"""


def _is_valid_question(item: Any) -> bool:
    if not isinstance(item, dict) or not _QUESTION_REQUIRED_FIELDS.issubset(item.keys()):
        return False
    choices = item["choices"]
    correct_index = item["correct_index"]
    return isinstance(choices, list) and len(choices) == 4 and isinstance(correct_index, int) and 0 <= correct_index < 4


async def analyze(text: str, level: str, question_count: int = 3, learning_mode: str = "GENERAL") -> dict:
    prompt = _PROMPT_TEMPLATE.format(
        level=level,
        level_desc=LEVEL_DESCRIPTIONS.get(level, ""),
        text=text,
        count=question_count,
        tone_note=tone_note(learning_mode),
    )
    raw = await generate_json(prompt)
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {"grammar_explanation": "", "questions": []}

    explanation = data.get("grammar_explanation")
    if not isinstance(explanation, str):
        explanation = ""

    raw_questions = data.get("exam_questions")
    questions = [q for q in raw_questions if _is_valid_question(q)] if isinstance(raw_questions, list) else []

    return {"grammar_explanation": explanation, "questions": questions}
