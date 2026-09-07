import json
import logging
from typing import Any

from app.ai.gemini_client import generate_json

logger = logging.getLogger(__name__)

LEVEL_DESCRIPTIONS = {
    "beginner": "중학교 기초 수준",
    "intermediate": "고등학교~일상회화 수준",
    "advanced": "유학 준비생이 알아야 할 학술/시사 수준",
}

_WORD_REQUIRED_FIELDS = {
    "word",
    "meaning_ko",
    "part_of_speech",
    "pronunciation",
    "example_sentence",
    "example_translation",
}

_GRAMMAR_REQUIRED_FIELDS = {"topic", "concept_intro", "prompt", "choices", "correct_index", "explanation"}
_KEY_VOCAB_REQUIRED_FIELDS = _WORD_REQUIRED_FIELDS
_READING_REQUIRED_FIELDS = {"passage", "model_translation_ko"}

_WORD_PROMPT_TEMPLATE = """너는 영어 학습 콘텐츠 제작자다. {level}({level_desc}) 난이도의 서로 다른 영어 단어 {count}개를 만들어라.
아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라.
[
  {{
    "word": "영어단어",
    "meaning_ko": "한국어 뜻",
    "part_of_speech": "품사 (예: noun, verb, adjective)",
    "pronunciation": "IPA 발음기호",
    "example_sentence": "해당 단어가 포함된 영어 예문",
    "example_translation": "예문의 한국어 해석"
  }}
]"""

_GRAMMAR_PROMPT_TEMPLATE = """너는 영어 문법 문제 출제자다. {level}({level_desc}) 난이도의 4지선다 영어 문법 객관식 문제 {count}개를 만들어라.
학습자가 문제를 풀기 전에 해당 문법 개념을 먼저 이해할 수 있도록, 각 문제마다 짧은 개념 설명(concept_intro)도 함께 만들어라.
또한 문제 문장(prompt)에 등장하는 단어 중 학습자가 몰라서 문법 이해를 방해할 만한 핵심 단어를 2~4개 뽑아 key_vocabulary로 제공하라
(문법과 무관한 쉬운 단어는 제외, 각 단어는 문법 문제와 같은 {level} 난이도 기준).
아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. correct_index는 0부터 시작하는 정수다.
[
  {{
    "topic": "문법 주제 (예: 현재완료, 관계대명사)",
    "concept_intro": "본 문제를 풀기 전에 보여줄 해당 문법 개념에 대한 2~3문장 한국어 설명",
    "prompt": "빈칸이 ___ 로 표시된 영어 문장",
    "choices": ["선택지1", "선택지2", "선택지3", "선택지4"],
    "correct_index": 0,
    "explanation": "정답 이유에 대한 한국어 설명",
    "key_vocabulary": [
      {{
        "word": "영어단어",
        "meaning_ko": "한국어 뜻",
        "part_of_speech": "품사",
        "pronunciation": "IPA 발음기호",
        "example_sentence": "위 문제 문장을 그대로 사용해도 됨",
        "example_translation": "예문의 한국어 해석"
      }}
    ]
  }}
]"""

_READING_PROMPT_TEMPLATE = """너는 영어 학습 콘텐츠 제작자다. {level}({level_desc}) 난이도의 영어 짧은 지문(3~5문장) {count}개를 만들어라.
각 지문에는 자연스러운 한국어 모범 번역도 함께 제공하라.
아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라.
[
  {{
    "passage": "영어 지문 (3~5문장, 하나의 완결된 글)",
    "model_translation_ko": "지문 전체를 자연스럽게 옮긴 한국어 모범 번역"
  }}
]"""


def _is_valid_word(item: Any) -> bool:
    return isinstance(item, dict) and _WORD_REQUIRED_FIELDS.issubset(item.keys())


def _valid_key_vocabulary(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and _KEY_VOCAB_REQUIRED_FIELDS.issubset(item.keys())]


def _is_valid_grammar(item: Any) -> bool:
    if not isinstance(item, dict) or not _GRAMMAR_REQUIRED_FIELDS.issubset(item.keys()):
        return False
    choices = item["choices"]
    correct_index = item["correct_index"]
    return (
        isinstance(choices, list)
        and len(choices) == 4
        and isinstance(correct_index, int)
        and 0 <= correct_index < 4
    )


def _is_valid_reading(item: Any) -> bool:
    return isinstance(item, dict) and _READING_REQUIRED_FIELDS.issubset(item.keys())


def _parse_json_array(raw: str) -> list[Any]:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array response")
    return data


async def generate_words(level: str, count: int) -> list[dict]:
    prompt = _WORD_PROMPT_TEMPLATE.format(level=level, level_desc=LEVEL_DESCRIPTIONS[level], count=count)
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [item for item in items if _is_valid_word(item)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed word items", len(items) - len(valid))
    return valid


async def generate_grammar_questions(level: str, count: int) -> list[dict]:
    prompt = _GRAMMAR_PROMPT_TEMPLATE.format(level=level, level_desc=LEVEL_DESCRIPTIONS[level], count=count)
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [item for item in items if _is_valid_grammar(item)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed grammar items", len(items) - len(valid))

    # key_vocabulary는 보조 데이터라 형식이 어긋나도 문제 자체는 버리지 않고 빈 목록으로 대체.
    for item in valid:
        item["key_vocabulary"] = _valid_key_vocabulary(item.get("key_vocabulary"))
    return valid


async def generate_reading_passages(level: str, count: int) -> list[dict]:
    prompt = _READING_PROMPT_TEMPLATE.format(level=level, level_desc=LEVEL_DESCRIPTIONS[level], count=count)
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [item for item in items if _is_valid_reading(item)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed reading items", len(items) - len(valid))
    return valid
