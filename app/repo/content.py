from psycopg.types.json import Json

from app.db import get_pool


async def insert_words(level: str, words: list[dict]) -> int:
    if not words:
        return 0

    pool = get_pool()
    inserted = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for w in words:
                await cur.execute(
                    """
                    insert into words
                        (word, meaning_ko, part_of_speech, pronunciation, example_sentence, example_translation, level)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    on conflict (word) do nothing
                    """,
                    (
                        w["word"],
                        w["meaning_ko"],
                        w["part_of_speech"],
                        w["pronunciation"],
                        w["example_sentence"],
                        w["example_translation"],
                        level,
                    ),
                )
                inserted += cur.rowcount
    return inserted


async def get_word_ids(words: list[str]) -> dict[str, int]:
    """단어 텍스트 -> id 매핑 (신규/기존 여부와 무관하게 조회, M11 텍스트학습 카드 구성용)."""
    if not words:
        return {}

    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select id, word from words where word = any(%s)", (words,))
            rows = await cur.fetchall()
            return {row["word"]: row["id"] for row in rows}


async def insert_grammar_questions(level: str, questions: list[dict]) -> int:
    if not questions:
        return 0

    pool = get_pool()
    inserted = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for q in questions:
                await cur.execute(
                    """
                    insert into grammar_questions (level, topic, concept_intro, prompt, choices, correct_index, explanation)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        level,
                        q["topic"],
                        q.get("concept_intro"),
                        q["prompt"],
                        Json(q["choices"]),
                        q["correct_index"],
                        q["explanation"],
                    ),
                )
                inserted += 1
    return inserted


async def insert_key_vocabulary_from_grammar(level: str, questions: list[dict]) -> int:
    """생성된 문법 문제들의 key_vocabulary를 단어뱅크(words)에 합류시킨다.

    사용자 피드백: 문법 문장에 모르는 단어가 섞여 나오면 그 단어들도 자연스럽게
    단어학습(/단어학습)에서 만나도록, 같은 레벨의 words 테이블에 그대로 추가한다.
    """
    all_vocab = [word for q in questions for word in q.get("key_vocabulary", [])]
    return await insert_words(level, all_vocab)


async def insert_reading_passages(level: str, passages: list[dict]) -> int:
    if not passages:
        return 0

    pool = get_pool()
    inserted = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for p in passages:
                await cur.execute(
                    "insert into reading_passages (level, passage_text, model_translation_ko) values (%s, %s, %s)",
                    (level, p["passage"], p["model_translation_ko"]),
                )
                inserted += 1
    return inserted


async def count_words_by_level() -> dict[str, int]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select level, count(*) as n from words group by level")
            rows = await cur.fetchall()
            return {row["level"]: row["n"] for row in rows}


async def count_grammar_questions_by_level() -> dict[str, int]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select level, count(*) as n from grammar_questions group by level")
            rows = await cur.fetchall()
            return {row["level"]: row["n"] for row in rows}


async def count_reading_passages_by_level() -> dict[str, int]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select level, count(*) as n from reading_passages group by level")
            rows = await cur.fetchall()
            return {row["level"]: row["n"] for row in rows}
