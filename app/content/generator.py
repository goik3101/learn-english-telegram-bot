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

# M14: CHILD_BRIDGE(11세) 모드 전용 톤 지침 — 콘텐츠뱅크(단어/문법/해석)와 세션 중 생성되는
# AI 응답(회화/피드백/힌트 등) 프롬프트에 공통으로 덧붙여, 같은 레벨이라도 어린이에게 맞게 조정한다.
CHILD_BRIDGE_TONE_INSTRUCTION = (
    "[중요] 학습자는 11세 어린이다. 어려운 단어나 표현은 11세가 이해하기 쉬운 쉬운 말로 풀어 설명하고, "
    "이모티콘을 1~2개 섞어 친근하고 다정한 톤으로 작성하라. 실제 난이도도 같은 레벨의 성인용보다 한 단계 쉽게 조정하라. "
    "폭력적이거나 선정적이거나 무섭거나 위험한 주제는 절대 다루지 마라."
)


def tone_note(learning_mode: str) -> str:
    return f"\n{CHILD_BRIDGE_TONE_INSTRUCTION}\n" if learning_mode == "CHILD_BRIDGE" else ""

# M18(개인 맞춤 난이도): frequency_rank는 콘텐츠뱅크 단어(M4)에만 요구한다. 문법/텍스트에서
# 추출되는 보조 단어(key_vocabulary)까지 강제하면 기존 프롬프트를 전부 바꿔야 해서 범위를 좁혔다
# — 그 단어들은 frequency_rank가 NULL로 남고, 조회 시 정렬 맨 뒤로 밀리는 정도로만 처리된다.
_WORD_REQUIRED_FIELDS = {
    "word",
    "meaning_ko",
    "part_of_speech",
    "pronunciation",
    "example_sentence",
    "example_translation",
    "frequency_rank",
}
_KEY_VOCAB_REQUIRED_FIELDS = {
    "word",
    "meaning_ko",
    "part_of_speech",
    "pronunciation",
    "example_sentence",
    "example_translation",
}

_GRAMMAR_REQUIRED_FIELDS = {"topic", "concept_intro", "prompt", "choices", "correct_index", "explanation"}
_READING_REQUIRED_FIELDS = {
    "passage",
    "model_translation_ko",
    "avg_sentence_length",
    "vocab_level",
    "grammar_complexity",
    "difficulty_band",
}

_WORD_PROMPT_TEMPLATE = """너는 영어 학습 콘텐츠 제작자다. {level}({level_desc}) 난이도의 서로 다른 영어 단어 {count}개를 만들어라.
각 단어에는 실제 영어 사용빈도 순위(frequency_rank)를 Oxford 3000/5000 및 COCA(Corpus of Contemporary
American English) 빈도 자료를 참고해 정수로 추정해서 함께 제공하라(1에 가까울수록 매우 흔한 단어,
숫자가 클수록 드물고 어려운 단어 — 예: "important"는 500 전후, "inexorable"은 10000 이상).
{tone_note}아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라.
[
  {{
    "word": "영어단어",
    "meaning_ko": "한국어 뜻",
    "part_of_speech": "품사 (예: noun, verb, adjective)",
    "pronunciation": "IPA 발음기호",
    "example_sentence": "해당 단어가 포함된 영어 예문",
    "example_translation": "예문의 한국어 해석",
    "frequency_rank": 500
  }}
]"""

_GRAMMAR_PROMPT_TEMPLATE = """너는 영어 문법 문제 출제자다. {level}({level_desc}) 난이도의 4지선다 영어 문법 객관식 문제 {count}개를 만들어라.
학습자가 문제를 풀기 전에 해당 문법 개념을 먼저 이해할 수 있도록, 각 문제마다 짧은 개념 설명(concept_intro)도 함께 만들어라.
또한 문제 문장(prompt)에 등장하는 단어 중 학습자가 몰라서 문법 이해를 방해할 만한 핵심 단어를 2~4개 뽑아 key_vocabulary로 제공하라
(문법과 무관한 쉬운 단어는 제외, 각 단어는 문법 문제와 같은 {level} 난이도 기준).
{tone_note}아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. correct_index는 0부터 시작하는 정수다.
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
또한 각 지문마다 아래 난이도 메타데이터를 함께 매겨라:
- avg_sentence_length: 지문의 평균 문장당 단어 수(정수)
- vocab_level: 어휘 수준을 한 단어로("basic"/"intermediate"/"advanced" 중 하나)
- grammar_complexity: 포함된 문법 구조를 간단히 설명(예: "단순 현재/과거 시제", "관계대명사와 분사구문 포함")
- difficulty_band: 위 요소를 종합한 난이도를 0(매우 쉬움)~5(매우 어려움) 정수로 표현
{tone_note}아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라.
[
  {{
    "passage": "영어 지문 (3~5문장, 하나의 완결된 글)",
    "model_translation_ko": "지문 전체를 자연스럽게 옮긴 한국어 모범 번역",
    "avg_sentence_length": 10,
    "vocab_level": "basic",
    "grammar_complexity": "단순 현재/과거 시제",
    "difficulty_band": 1
  }}
]"""


def _is_valid_word(item: Any) -> bool:
    if not (isinstance(item, dict) and _WORD_REQUIRED_FIELDS.issubset(item.keys())):
        return False
    rank = item["frequency_rank"]
    return isinstance(rank, int) and not isinstance(rank, bool) and rank > 0


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
    if not (isinstance(item, dict) and _READING_REQUIRED_FIELDS.issubset(item.keys())):
        return False
    band = item["difficulty_band"]
    return isinstance(band, int) and not isinstance(band, bool) and 0 <= band <= 5


def _parse_json_array(raw: str) -> list[Any]:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array response")
    return data


_FREQUENCY_BACKFILL_PROMPT = """다음은 이미 만들어진 영어 단어 목록이다. 각 단어의 실제 영어 사용빈도 순위(frequency_rank)를
Oxford 3000/5000 및 COCA(Corpus of Contemporary American English) 빈도 자료를 참고해 정수로 추정하라
(1에 가까울수록 흔한 단어, 숫자가 클수록 드물고 어려운 단어).

단어 목록: {words}

아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. 입력된 단어 개수와 정확히 같은 개수로 응답하라.
[
  {{"word": "영어단어", "frequency_rank": 500}}
]"""


async def estimate_frequency_ranks(words: list[str]) -> list[dict]:
    """기존(구세대) 콘텐츠뱅크 단어 소급 백필용 — scripts/backfill_word_frequency_rank.py."""
    prompt = _FREQUENCY_BACKFILL_PROMPT.format(words=", ".join(words))
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [
        item
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("word"), str)
        and isinstance(item.get("frequency_rank"), int)
        and not isinstance(item.get("frequency_rank"), bool)
        and item["frequency_rank"] > 0
    ]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed frequency estimate items", len(items) - len(valid))
    return valid


async def generate_words(level: str, count: int, learning_mode: str = "GENERAL") -> list[dict]:
    prompt = _WORD_PROMPT_TEMPLATE.format(
        level=level, level_desc=LEVEL_DESCRIPTIONS[level], count=count, tone_note=tone_note(learning_mode)
    )
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [item for item in items if _is_valid_word(item)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed word items", len(items) - len(valid))
    return valid


async def generate_grammar_questions(level: str, count: int, learning_mode: str = "GENERAL") -> list[dict]:
    prompt = _GRAMMAR_PROMPT_TEMPLATE.format(
        level=level, level_desc=LEVEL_DESCRIPTIONS[level], count=count, tone_note=tone_note(learning_mode)
    )
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [item for item in items if _is_valid_grammar(item)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed grammar items", len(items) - len(valid))

    # key_vocabulary는 보조 데이터라 형식이 어긋나도 문제 자체는 버리지 않고 빈 목록으로 대체.
    for item in valid:
        item["key_vocabulary"] = _valid_key_vocabulary(item.get("key_vocabulary"))
    return valid


_TOPIC_WORD_PROMPT_TEMPLATE = """너는 영어 학습 콘텐츠 제작자다. 아래 회화 주제와 관련된 핵심 영어 단어를
{level}({level_desc}) 난이도로 서로 다른 단어 {count}개 만들어라.

회화 주제: {topic}

이 주제로 실제 대화할 때 자주 쓰일 법한 단어 위주로 골라라(품사 제한 없음). 각 단어에는 실제 영어
사용빈도 순위(frequency_rank)를 Oxford 3000/5000 및 COCA(Corpus of Contemporary American English)
빈도 자료를 참고해 정수로 추정해서 함께 제공하라(1에 가까울수록 흔한 단어, 숫자가 클수록 드문 단어).
{tone_note}아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라.
[
  {{
    "word": "영어단어",
    "meaning_ko": "한국어 뜻",
    "part_of_speech": "품사 (예: noun, verb, adjective)",
    "pronunciation": "IPA 발음기호",
    "example_sentence": "해당 단어가 포함된 영어 예문",
    "example_translation": "예문의 한국어 해석",
    "frequency_rank": 500
  }}
]"""


async def generate_topic_words(level: str, topic: str, count: int, learning_mode: str = "GENERAL") -> list[dict]:
    """회화 사전 단어학습: 오늘의 대화 주제와 관련된 핵심 단어를 생성한다(최초 1회, 이후 캐싱)."""
    prompt = _TOPIC_WORD_PROMPT_TEMPLATE.format(
        level=level, level_desc=LEVEL_DESCRIPTIONS[level], topic=topic, count=count, tone_note=tone_note(learning_mode)
    )
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [item for item in items if _is_valid_word(item)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed topic word items for topic %s", len(items) - len(valid), topic)
    return valid


_GRAMMAR_TOPIC_PROMPT_TEMPLATE = """너는 영어 문법 문제 출제자다. {level}({level_desc}) 난이도로, 반드시 아래 문법 주제 하나에
대해서만 4지선다 객관식 문제 {count}개를 만들어라 (다른 주제는 섞지 마라).

문법 주제: {topic}

학습자가 문제를 풀기 전에 해당 문법 개념을 먼저 이해할 수 있도록, 각 문제마다 짧은 개념 설명(concept_intro)도 함께 만들어라.
또한 문제 문장(prompt)에 등장하는 단어 중 학습자가 몰라서 문법 이해를 방해할 만한 핵심 단어를 2~4개 뽑아 key_vocabulary로 제공하라
(문법과 무관한 쉬운 단어는 제외, 각 단어는 문법 문제와 같은 {level} 난이도 기준).
{tone_note}아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. correct_index는 0부터 시작하는 정수다.
[
  {{
    "topic": "{topic}",
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


async def generate_grammar_questions_for_topic(
    level: str, topic: str, count: int, learning_mode: str = "GENERAL"
) -> list[dict]:
    """개인 맞춤 난이도(문법): 커리큘럼(app/grammar/curriculum.py)의 특정 주제 하나만 골라 생성.

    AI가 topic 필드를 살짝 다르게 표현할 수 있어, DB 조회 시 정확히 일치하도록 요청한 주제
    문자열로 덮어써서 저장한다.
    """
    prompt = _GRAMMAR_TOPIC_PROMPT_TEMPLATE.format(
        level=level, level_desc=LEVEL_DESCRIPTIONS[level], count=count, topic=topic, tone_note=tone_note(learning_mode)
    )
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [item for item in items if _is_valid_grammar(item)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed grammar items for topic %s", len(items) - len(valid), topic)

    for item in valid:
        item["topic"] = topic
        item["key_vocabulary"] = _valid_key_vocabulary(item.get("key_vocabulary"))
    return valid


async def generate_reading_passages(level: str, count: int, learning_mode: str = "GENERAL") -> list[dict]:
    prompt = _READING_PROMPT_TEMPLATE.format(
        level=level, level_desc=LEVEL_DESCRIPTIONS[level], count=count, tone_note=tone_note(learning_mode)
    )
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [item for item in items if _is_valid_reading(item)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed reading items", len(items) - len(valid))
    return valid
