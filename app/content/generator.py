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
#
# 사용자 피드백(단어 암기 효율, 기억연구 근거): mnemonic(2단계 키워드 연상법)과 example_sentences
# (복습 회차마다 다른 예문을 보여주기 위한 여러 예문), emoji(이중부호화 — 텍스트+이미지 병행 제시)를
# 추가했다. example_sentence/example_translation(단일) 필드는 AI에게 별도로 다시 요청하지 않고
# example_sentences[0]에서 그대로 파생시킨다(불일치 위험 제거) — 아래 generate_words()/
# generate_topic_words() 참고.
_WORD_REQUIRED_FIELDS = {
    "word",
    "meaning_ko",
    "part_of_speech",
    "pronunciation",
    "mnemonic",
    "example_sentences",
    "frequency_rank",
    "emoji",
}

# 사용자 피드백: 키워드 연상법(keyword mnemonic) — 2단계로 만들 것. 1단계(소리 연결) 영단어와
# 발음이 비슷한 한국어 단어/표현을 찾고, 2단계(이미지 연결) 그 한국어 키워드와 실제 뜻이 함께
# 등장하는 생생하고 구체적인(가능하면 약간 과장되거나 우스꽝스러운) 장면을 묘사한다. 세 프롬프트
# (전체 생성/주제별 생성/기존 콘텐츠 소급 백필)가 이 지침을 공유한다.
_MNEMONIC_STYLE_INSTRUCTION = """mnemonic(연상법) 작성 방식 — 2단계 키워드 연상법, 반드시 이 방식을 따를 것:
1단계(소리 연결): 영단어와 발음이 비슷한 한국어 단어/표현을 찾아라.
2단계(이미지 연결): 그 한국어 키워드와 실제 뜻이 함께 등장하는, 생생하고 구체적인(가능하면 약간
과장되거나 우스꽝스러운) 장면을 한두 문장으로 묘사하라.
예: "important(중요한) → '임포턴트'는 '임금님 텐트'처럼 들림 → 임금님이 가장 중요한 물건만 넣어두는
특별한 텐트를 상상해보세요."
"~라는 뜻이다" 식의 단순 뜻풀이 반복은 안 된다.
또한 이 단어의 의미를 한눈에 떠올리게 해줄 이모지(emoji)를 정확히 1개 골라라(텍스트와 이미지를
함께 제시하면 기억에 더 잘 남는다는 이중부호화 원리)."""
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
""" + _MNEMONIC_STYLE_INSTRUCTION + """
또한 서로 다른 문맥의 예문(example_sentences) 2~3개를 만들어라 — 나중에 이 단어를 복습할 때마다 매번
다른 문장을 보여줘서 문맥 다양성으로 기억을 돕기 위함이다.
{tone_note}아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라.
[
  {{
    "word": "영어단어",
    "meaning_ko": "한국어 뜻",
    "part_of_speech": "품사 (예: noun, verb, adjective)",
    "pronunciation": "IPA 발음기호",
    "mnemonic": "1단계(소리): ~처럼 들림. 2단계(이미지): ~하는 장면을 상상해보세요.",
    "emoji": "🏰",
    "example_sentences": [
      {{"sentence": "영어 예문 1", "translation": "한국어 해석 1"}},
      {{"sentence": "영어 예문 2 (문맥이 다른 문장)", "translation": "한국어 해석 2"}}
    ],
    "frequency_rank": 500
  }}
]"""

# 사용자 피드백: "가정법 과거완료는 ... if+주어+had p.p. ..." 식으로 문법 용어와 공식만 나열하면
# 이해가 안 된다는 지적을 반영한 concept_intro 작성 지침. 두 프롬프트(전체 무작위 생성/주제별 생성)가
# 공유한다.
_CONCEPT_INTRO_STYLE_INSTRUCTION = """concept_intro 작성 방식(중요, 반드시 지킬 것):
- 문법 용어(주어, 목적어, 구조 등) 나열이나 공식 설명으로 시작하지 말고, 먼저 친숙한 예시 상황을
  한두 문장으로 제시한 뒤, 그 상황에서 왜 이런 표현을 쓰는지 이야기하듯 설명하라.
- 영어 구조 공식은 반드시 짧은 예시 문장과 함께 보여주고, 그 문장이 실제로 어떤 뉘앙스인지
  한국어로 풀어서 설명하라(예: "이미 벌어진 일과 반대되는 상상을 할 때 쓰는 표현이에요").
- 딱딱한 문법 교과서 말투 대신, 옆에서 설명해주는 것처럼 자연스러운 톤으로 써라."""

_GRAMMAR_PROMPT_TEMPLATE = """너는 영어 문법 문제 출제자다. {level}({level_desc}) 난이도의 4지선다 영어 문법 객관식 문제 {count}개를 만들어라.
학습자가 문제를 풀기 전에 해당 문법 개념을 먼저 이해할 수 있도록, 각 문제마다 짧은 개념 설명(concept_intro)도 함께 만들어라.
""" + _CONCEPT_INTRO_STYLE_INSTRUCTION + """
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
    if not (isinstance(rank, int) and not isinstance(rank, bool) and rank > 0):
        return False
    if not (isinstance(item["mnemonic"], str) and item["mnemonic"].strip()):
        return False
    if not (isinstance(item["emoji"], str) and item["emoji"].strip()):
        return False
    examples = item["example_sentences"]
    return (
        isinstance(examples, list)
        and len(examples) >= 2
        and all(
            isinstance(e, dict) and isinstance(e.get("sentence"), str) and isinstance(e.get("translation"), str)
            for e in examples
        )
    )


def _derive_singular_example(item: dict) -> None:
    """example_sentence/example_translation(단일)은 다른 코드(insert_words 등)와의 호환을 위해
    example_sentences[0]에서 그대로 파생시킨다 — AI에게 두 번 묻지 않아 서로 어긋날 일이 없다."""
    first = item["example_sentences"][0]
    item["example_sentence"] = first["sentence"]
    item["example_translation"] = first["translation"]


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


_MNEMONIC_BACKFILL_PROMPT = """다음은 이미 만들어진 영어 단어와 뜻 목록이다.
""" + _MNEMONIC_STYLE_INSTRUCTION + """
또한 서로 다른 문맥의 예문(example_sentences)도 2개씩 만들어라.

단어 목록: {words}

아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. 입력된 단어 개수와 정확히 같은
개수로, 입력 순서와 무관하게 word 필드로 매칭되도록 응답하라.
[
  {{
    "word": "영어단어",
    "mnemonic": "1단계(소리): ~처럼 들림. 2단계(이미지): ~하는 장면을 상상해보세요.",
    "emoji": "🏰",
    "example_sentences": [
      {{"sentence": "영어 예문 1", "translation": "한국어 해석 1"}},
      {{"sentence": "영어 예문 2 (문맥이 다른 문장)", "translation": "한국어 해석 2"}}
    ]
  }}
]"""


async def estimate_mnemonics_and_examples(words: list[dict]) -> list[dict]:
    """기존(2단계 키워드 연상법/이모지 도입 이전) 콘텐츠뱅크 단어 소급 백필용 —
    scripts/backfill_word_mnemonics.py.

    words: [{"word": ..., "meaning_ko": ...}, ...]
    """
    word_list = ", ".join(f"{w['word']}({w['meaning_ko']})" for w in words)
    prompt = _MNEMONIC_BACKFILL_PROMPT.format(words=word_list)
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = []
    for item in items:
        if not (isinstance(item, dict) and isinstance(item.get("word"), str) and isinstance(item.get("mnemonic"), str)):
            continue
        examples = item.get("example_sentences")
        if not (isinstance(examples, list) and len(examples) >= 1):
            continue
        valid.append(item)
    if len(valid) < len(items):
        logger.warning("dropped %d malformed mnemonic backfill items", len(items) - len(valid))
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
    for item in valid:
        _derive_singular_example(item)
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
""" + _MNEMONIC_STYLE_INSTRUCTION + """
또한 서로 다른 문맥의 예문(example_sentences) 2~3개를 만들어라 — 복습할 때마다 다른 문장을 보여주기
위함이다.
{tone_note}아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라.
[
  {{
    "word": "영어단어",
    "meaning_ko": "한국어 뜻",
    "part_of_speech": "품사 (예: noun, verb, adjective)",
    "pronunciation": "IPA 발음기호",
    "mnemonic": "1단계(소리): ~처럼 들림. 2단계(이미지): ~하는 장면을 상상해보세요.",
    "emoji": "🏰",
    "example_sentences": [
      {{"sentence": "영어 예문 1", "translation": "한국어 해석 1"}},
      {{"sentence": "영어 예문 2 (문맥이 다른 문장)", "translation": "한국어 해석 2"}}
    ],
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
    for item in valid:
        _derive_singular_example(item)
    return valid


_GRAMMAR_TOPIC_PROMPT_TEMPLATE = """너는 영어 문법 문제 출제자다. {level}({level_desc}) 난이도로, 반드시 아래 문법 주제 하나에
대해서만 4지선다 객관식 문제 {count}개를 만들어라 (다른 주제는 섞지 마라).

문법 주제: {topic}
{previous_topic_note}
학습자가 문제를 풀기 전에 해당 문법 개념을 먼저 이해할 수 있도록, 각 문제마다 짧은 개념 설명(concept_intro)도 함께 만들어라.
""" + _CONCEPT_INTRO_STYLE_INSTRUCTION + """
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
    level: str, topic: str, count: int, learning_mode: str = "GENERAL", previous_topic: str | None = None
) -> list[dict]:
    """개인 맞춤 난이도(문법): 커리큘럼(app/grammar/curriculum.py)의 특정 주제 하나만 골라 생성.

    AI가 topic 필드를 살짝 다르게 표현할 수 있어, DB 조회 시 정확히 일치하도록 요청한 주제
    문자열로 덮어써서 저장한다. previous_topic을 주면(전역 순차 커리큘럼상 바로 앞 주제) 사용자
    피드백 반영: "이미 아는 문법과 비교해서 한 단계 더 나간 표현"이라는 식으로 연결해 설명하게 한다.
    """
    previous_topic_note = (
        f"학습자는 바로 앞 단계인 '{previous_topic}'를 이미 통과했다 — 가능하면 그 문법과 비교해서 "
        f"\"'{previous_topic}'에서 한 단계 더 나간 표현\"이라는 식으로 연결해서 설명하라.\n"
        if previous_topic
        else ""
    )
    prompt = _GRAMMAR_TOPIC_PROMPT_TEMPLATE.format(
        level=level,
        level_desc=LEVEL_DESCRIPTIONS[level],
        count=count,
        topic=topic,
        previous_topic_note=previous_topic_note,
        tone_note=tone_note(learning_mode),
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


_GRAMMAR_PART_PROMPT_TEMPLATE = """너는 영어 문법 문제 출제자다. {level}({level_desc}) 난이도(CEFR {cefr_level})로, 반드시
아래 하나의 세부 문법 포인트에 대해서만 4지선다 객관식 문제 {count}개를 만들어라 (다른 문법 포인트는 섞지 마라).

문법 토픽: {topic}
이번에 다룰 세부 포인트: {part_name} — {part_description}
{previous_part_note}
학습자가 문제를 풀기 전에 해당 문법 개념을 먼저 이해할 수 있도록, 각 문제마다 짧은 개념 설명(concept_intro)도 함께 만들어라.
""" + _CONCEPT_INTRO_STYLE_INSTRUCTION + """
또한 각 문제에는 오답 유형 태그(error_type)를 붙여라 — "{part_name}" 안에서도 실수하는 지점을 더 세밀하게
구분하는 짧은 한국어 태그다(예: "부정어 도치_Never 위치 오류", "강조구문_가주어와 구별 실패"). 문제마다 서로 다른
오답 포인트를 다루도록 다양하게 만들어라(같은 태그 반복 지양).
또한 문제 문장(prompt)에 등장하는 단어 중 학습자가 몰라서 문법 이해를 방해할 만한 핵심 단어를 2~4개 뽑아 key_vocabulary로 제공하라
(문법과 무관한 쉬운 단어는 제외, 각 단어는 문법 문제와 같은 {level} 난이도 기준).
{tone_note}아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. correct_index는 0부터 시작하는 정수다.
[
  {{
    "topic": "{topic}",
    "error_type": "이 문제가 다루는 세부 오답 유형 태그",
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


async def generate_grammar_questions_for_part(
    cefr_level: str,
    legacy_level: str,
    topic: str,
    part_name: str,
    part_description: str,
    count: int,
    learning_mode: str = "GENERAL",
    previous_part_label: str | None = None,
) -> list[dict]:
    """CEFR 파트 기반 커리큘럼(app/grammar/curriculum_data.py)의 파트 하나에 대해서만 생성.

    previous_part_label(바로 앞 파트, 같은 토픽 안이거나 이전 토픽의 마지막 파트)을 주면 사용자
    피드백 반영: "이미 통과한 표현과 비교해서 한 단계 더 나간 표현"이라는 식으로 연결해 설명하게 한다
    — generate_grammar_questions_for_topic의 previous_topic 연결과 같은 원리를 파트 단위로 적용.
    """
    previous_part_note = (
        f"학습자는 바로 앞 단계인 '{previous_part_label}'를 이미 통과했다 — 가능하면 그 표현과 비교해서 "
        f"\"'{previous_part_label}'에서 한 단계 더 나간 표현\"이라는 식으로 연결해서 설명하라.\n"
        if previous_part_label
        else ""
    )
    prompt = _GRAMMAR_PART_PROMPT_TEMPLATE.format(
        level=legacy_level,
        level_desc=LEVEL_DESCRIPTIONS[legacy_level],
        cefr_level=cefr_level,
        count=count,
        topic=topic,
        part_name=part_name,
        part_description=part_description,
        previous_part_note=previous_part_note,
        tone_note=tone_note(learning_mode),
    )
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [item for item in items if _is_valid_grammar(item)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed grammar items for part %s", len(items) - len(valid), part_name)

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


# 오늘의 주제 통합 학습(사용자 피드백): 해석 지문이 단어학습/회화와 무관하게 생성되다 보니 학습자
# 수준과 동떨어진 학술 어휘("algorithmic accountability" 등)로 새는 문제가 있었다. 지문을 오늘의
# 주제 단어 풀 위주로만 구성하도록 제약하는 전용 프롬프트.
_TOPIC_READING_PROMPT_TEMPLATE = """너는 영어 학습 콘텐츠 제작자다. {level}({level_desc}) 난이도의 영어 짧은 지문(3~5문장) 1개를
아래 조건에 맞춰 만들어라.

주제: {topic}
이 지문에서 우선적으로 사용해야 할 단어 목록(가능한 한 이 목록 위주로 문장을 구성할 것): {words}
{grammar_note}
- 위 단어 목록에 없는 단어가 꼭 필요하면 최소한으로만 쓰고, 그런 경우 지문 안에서 그 단어 바로
  뒤에 괄호로 쉬운 한국어 뜻을 함께 적어라(예: "The trip was exhausting(매우 피곤한).").
- 자연스러운 한국어 모범 번역도 함께 제공하라.
- 또한 아래 난이도 메타데이터를 함께 매겨라:
  avg_sentence_length(평균 문장당 단어 수, 정수), vocab_level("basic"/"intermediate"/"advanced" 중 하나),
  grammar_complexity(포함된 문법 구조 간단 설명), difficulty_band(0~5 정수).
{tone_note}아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라(배열 안에 지문 1개만).
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


async def generate_reading_passage_for_words(
    level: str,
    topic: str,
    words: list[str],
    mastered_grammar_topics: list[str],
    learning_mode: str = "GENERAL",
    current_part_name: str | None = None,
    current_part_description: str | None = None,
) -> list[dict]:
    """오늘의 주제 통합 학습: 오늘의 단어 풀 + 이미 노출된 문법 범위 안에서만 지문을 생성한다
    (하루 1회, app/handlers/router.py에서 learning_sessions에 캐싱해 재사용).

    해석을 문법 학습과 통합(사용자 요청): current_part_name/description을 주면(오늘 학습 중인
    grammar_part) 그 문법 포인트를 지문에 최소 1문장 이상 자연스럽게 녹여 넣도록 요청한다 —
    단순히 "안 넘게" 제한하는 것을 넘어, 방금 배운 표현을 실제로 다시 만나 복습하게 한다."""
    grammar_note = (
        f"- 문장 구조는 학습자가 이미 배운 다음 문법 범위를 넘지 않게 하라: {', '.join(mastered_grammar_topics)}. "
        "아직 배우지 않은 더 어려운 문법 구조(예: 가정법, 도치구문 등 위 목록에 없는 것)는 쓰지 마라.\n"
        if mastered_grammar_topics
        else "- 문장 구조는 최대한 단순하게(기초 문법 범위 안에서) 유지하라.\n"
    )
    if current_part_name:
        grammar_note += (
            f"- 오늘 학습한 문법 포인트는 '{current_part_name}'({current_part_description or ''})이다. "
            "지문 안에 이 문법이 실제로 쓰인 문장을 최소 1개 이상 자연스럽게 포함시켜라(억지스럽지 않게).\n"
        )
    prompt = _TOPIC_READING_PROMPT_TEMPLATE.format(
        level=level,
        level_desc=LEVEL_DESCRIPTIONS[level],
        topic=topic,
        words=", ".join(words),
        grammar_note=grammar_note,
        tone_note=tone_note(learning_mode),
    )
    raw = await generate_json(prompt)
    items = _parse_json_array(raw)
    valid = [item for item in items if _is_valid_reading(item)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed topic reading items for topic %s", len(items) - len(valid), topic)
    return valid
