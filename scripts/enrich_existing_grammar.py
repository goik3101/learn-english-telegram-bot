"""M4/M6 콘텐츠뱅크에 이미 저장된 문법 문제에 concept_intro/key_vocabulary를 소급 추가.

generate_content_bank.py가 처음 만든 문법 문제들은 concept_intro(개념 설명)와
key_vocabulary(핵심 단어) 필드가 생기기 전에 저장된 것이라, 1회성으로 채워 넣는다.
새로 생성되는 문법 문제는 generate_content_bank.py에서 처음부터 두 필드를 포함한다.

사용법:
    python scripts/enrich_existing_grammar.py
"""

import asyncio
import json
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.append(".")

from app.ai.gemini_client import generate_json  # noqa: E402
from app.content.generator import LEVEL_DESCRIPTIONS, _valid_key_vocabulary  # noqa: E402
from app.db import close_db_pool, get_pool, init_db_pool  # noqa: E402
from app.repo import content as content_repo  # noqa: E402

LEVELS = ["beginner", "intermediate", "advanced"]

_ENRICH_PROMPT_TEMPLATE = """너는 영어 문법 문제 편집자다. 아래는 {level}({level_desc}) 난이도로 이미 만들어진
영어 문법 문제 문장들이다. 각 문제(id로 구분)에 대해 다음 두 가지를 만들어라:
1. concept_intro: 이 문제를 풀기 전에 보여줄, 해당 문법 개념에 대한 2~3문장 한국어 설명
2. key_vocabulary: 문제 문장(prompt)에서 학습자가 몰라서 문법 이해를 방해할 만한 핵심 단어 2~4개
   (문법과 무관한 쉬운 단어는 제외, {level} 난이도 기준)

문제 목록:
{question_list}

아래 JSON 배열 형식으로만 응답하고, 다른 설명은 절대 추가하지 마라. id는 입력받은 것과 정확히 같아야 한다.
[
  {{
    "id": 123,
    "concept_intro": "...",
    "key_vocabulary": [
      {{
        "word": "영어단어",
        "meaning_ko": "한국어 뜻",
        "part_of_speech": "품사",
        "pronunciation": "IPA 발음기호",
        "example_sentence": "문제 문장을 그대로 사용해도 됨",
        "example_translation": "예문의 한국어 해석"
      }}
    ]
  }}
]"""


async def _fetch_questions_needing_enrichment(level: str) -> list[dict]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select id, topic, prompt from grammar_questions where level = %s and concept_intro is null",
                (level,),
            )
            return await cur.fetchall()


async def _update_concept_intro(question_id: int, concept_intro: str) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "update grammar_questions set concept_intro = %s where id = %s",
                (concept_intro, question_id),
            )


async def main() -> None:
    await init_db_pool()
    try:
        for level in LEVELS:
            rows = await _fetch_questions_needing_enrichment(level)
            if not rows:
                print(f"[{level}] enrich 대상 없음")
                continue

            question_list = "\n".join(f"- id={r['id']}: {r['prompt']}" for r in rows)
            prompt = _ENRICH_PROMPT_TEMPLATE.format(
                level=level, level_desc=LEVEL_DESCRIPTIONS[level], question_list=question_list
            )
            raw = await generate_json(prompt)
            items = json.loads(raw)
            if not isinstance(items, list):
                print(f"[{level}] 응답 형식 오류, 건너뜀")
                continue

            all_vocab: list[dict] = []
            updated = 0
            for item in items:
                if not isinstance(item, dict) or "id" not in item or "concept_intro" not in item:
                    continue
                await _update_concept_intro(item["id"], item["concept_intro"])
                updated += 1
                all_vocab.extend(_valid_key_vocabulary(item.get("key_vocabulary")))

            inserted_vocab = await content_repo.insert_words(level, all_vocab)
            print(f"[{level}] concept_intro 갱신={updated}/{len(rows)}, key_vocabulary 삽입={inserted_vocab}")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
