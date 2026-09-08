"""M15 Stage2(기초단어)~Stage5(짧은지문) 콘텐츠 AI 생성.

Stage0/1(알파벳/파닉스)은 curriculum.py의 고정 데이터를 쓰고, 이 파일은 그보다 어휘/문장이
다양해야 하는 Stage2~5만 담당한다. CHILD_BRIDGE(M14)보다도 더 쉬운 톤(초등 저학년 대상)을 쓴다.
"""

import json
import logging
from typing import Any

from app.ai.gemini_client import generate_json

logger = logging.getLogger(__name__)

_TONE_INSTRUCTION = (
    "[매우 중요] 학습자는 영어를 이제 막 시작하는 초등학교 저학년(10세 이하) 어린이다. "
    "아주 쉬운 단어와 문장만 사용하고, 이모티콘을 1~2개 섞어 아주 다정하고 쉬운 말로 설명하라. "
    "폭력적이거나 무섭거나 위험하거나 어른스러운 주제는 절대 다루지 말고, 동물/가족/음식/색깔/숫자 같은 "
    "친숙하고 안전한 주제만 사용하라."
)

_REQUIRED_FIELDS = {"prompt", "meaning_ko", "choices", "correct_index"}

_STAGE_PROMPTS = {
    2: """{tone}
초등 저학년 어린이를 위한 아주 쉬운 영어 단어 카드 {count}개를 만들어라. 각 단어는 4지선다 객관식으로
뜻을 맞히는 문제로 만든다. (예: 색깔, 동물, 가족, 음식, 숫자 같은 쉬운 단어)
아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. correct_index는 0부터 시작하는 정수다.
[
  {{
    "prompt": "영어 단어 (예: cat)",
    "meaning_ko": "한국어 뜻 (예: 고양이)",
    "choices": ["뜻1", "뜻2", "뜻3", "뜻4"],
    "correct_index": 0
  }}
]""",
    3: """{tone}
초등 저학년 어린이를 위한 아주 쉬운 영어 짧은 문장(3~5단어) {count}개를 만들어라. 각 문장은 4지선다
객관식으로 뜻을 맞히는 문제로 만든다.
아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. correct_index는 0부터 시작하는 정수다.
[
  {{
    "prompt": "영어 짧은 문장 (예: I like dogs.)",
    "meaning_ko": "한국어 뜻 (예: 나는 개를 좋아해.)",
    "choices": ["뜻1", "뜻2", "뜻3", "뜻4"],
    "correct_index": 0
  }}
]""",
    4: """{tone}
초등 저학년 어린이를 위한 아주 쉬운 영어 질문-답 짝 {count}개를 만들어라 (예: "What is your name?" 같은
일상적인 질문). 질문을 보여주고 4지선다 중 알맞은 대답을 고르는 문제로 만든다.
아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. correct_index는 0부터 시작하는 정수다.
[
  {{
    "prompt": "영어 질문 (예: What is your name?)",
    "meaning_ko": "질문의 한국어 뜻 (예: 네 이름이 뭐야?)",
    "choices": ["알맞은 대답(영어)", "어색한 대답1", "어색한 대답2", "어색한 대답3"],
    "correct_index": 0
  }}
]""",
    5: """{tone}
초등 저학년 어린이를 위한 아주 짧은 영어 지문(2~3문장) {count}개를 만들어라. 각 지문마다 내용을 이해했는지
확인하는 아주 쉬운 4지선다 문제(한국어로 질문)를 하나씩 만든다.
아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. correct_index는 0부터 시작하는 정수다.
[
  {{
    "passage_text": "영어 지문 (2~3문장)",
    "prompt": "지문 내용에 대한 한국어 이해도 질문",
    "meaning_ko": "정답에 대한 한 줄 한국어 설명",
    "choices": ["선택지1", "선택지2", "선택지3", "선택지4"],
    "correct_index": 0
  }}
]""",
}


def _is_valid(item: Any, stage: int) -> bool:
    if not isinstance(item, dict) or not _REQUIRED_FIELDS.issubset(item.keys()):
        return False
    if stage == 5 and not isinstance(item.get("passage_text"), str):
        return False
    choices = item["choices"]
    correct_index = item["correct_index"]
    return isinstance(choices, list) and len(choices) == 4 and isinstance(correct_index, int) and 0 <= correct_index < 4


async def generate_content(stage: int, count: int) -> list[dict]:
    if stage not in _STAGE_PROMPTS:
        raise ValueError(f"Stage2~5만 AI로 생성한다 (Stage0/1은 curriculum.py 고정 데이터 사용): got {stage}")

    prompt = _STAGE_PROMPTS[stage].format(tone=_TONE_INSTRUCTION, count=count)
    raw = await generate_json(prompt)
    items = json.loads(raw)
    if not isinstance(items, list):
        return []

    valid = [item for item in items if _is_valid(item, stage)]
    if len(valid) < len(items):
        logger.warning("dropped %d malformed child_beginner stage%d items", len(items) - len(valid), stage)
    return valid
