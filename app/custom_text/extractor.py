import json

from app.ai.gemini_client import generate_json
from app.content.generator import LEVEL_DESCRIPTIONS, _valid_key_vocabulary

_PROMPT_TEMPLATE = """너는 영어 학습 콘텐츠 제작자다. 아래는 학습자가 직접 붙여넣은 영어 텍스트다.
학습자 레벨: {level} ({level_desc})
이 텍스트에서 학습자가 몰라서 이해를 방해할 만한 핵심 단어를 최대 {max_words}개 뽑아라
({level} 난이도 기준으로 너무 쉬운 단어는 제외).

텍스트:
{text}

아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라.
[
  {{
    "word": "영어단어",
    "meaning_ko": "한국어 뜻",
    "part_of_speech": "품사",
    "pronunciation": "IPA 발음기호",
    "example_sentence": "본문에서 그 단어가 쓰인 문장을 그대로 사용해도 됨",
    "example_translation": "그 문장의 한국어 해석"
  }}
]"""


async def extract_key_vocabulary(text: str, level: str, max_words: int = 8) -> list[dict]:
    prompt = _PROMPT_TEMPLATE.format(
        level=level, level_desc=LEVEL_DESCRIPTIONS.get(level, ""), text=text, max_words=max_words
    )
    raw = await generate_json(prompt)
    items = json.loads(raw)
    if not isinstance(items, list):
        return []
    return _valid_key_vocabulary(items)
