from psycopg.types.json import Json

from app.db import get_pool


async def insert_words(level: str, words: list[dict], learning_mode: str = "GENERAL") -> int:
    if not words:
        return 0

    pool = get_pool()
    inserted = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for w in words:
                example_sentences = w.get("example_sentences")
                await cur.execute(
                    """
                    insert into words
                        (word, meaning_ko, part_of_speech, pronunciation, example_sentence, example_translation,
                         level, learning_mode, frequency_rank, mnemonic, example_sentences)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (word, learning_mode) do nothing
                    """,
                    (
                        w["word"],
                        w["meaning_ko"],
                        w["part_of_speech"],
                        w["pronunciation"],
                        w["example_sentence"],
                        w["example_translation"],
                        level,
                        learning_mode,
                        w.get("frequency_rank"),
                        w.get("mnemonic"),
                        Json(example_sentences) if example_sentences else None,
                    ),
                )
                inserted += cur.rowcount
    return inserted


async def get_frequency_ranks(words: list[str]) -> dict[str, int]:
    """개인 맞춤 난이도(회화): 주어진 단어(원형 후보 포함, 소문자)들의 frequency_rank를 조회한다.

    콘텐츠뱅크(words)에 있는 단어만 걸리므로 회화에 쓰인 모든 단어를 판단하지는 못하지만,
    문자열 단순대조가 아니라 실제 사용빈도 구간으로 판단한다는 목적은 충족한다.
    """
    if not words:
        return {}
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select word, frequency_rank from words where lower(word) = any(%s) and frequency_rank is not null",
                (words,),
            )
            rows = await cur.fetchall()
            return {row["word"].lower(): row["frequency_rank"] for row in rows}


async def get_words_missing_frequency_rank() -> list[dict]:
    """기존(구세대) 콘텐츠뱅크 단어 소급 백필용 — scripts/backfill_word_frequency_rank.py."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select id, word from words where frequency_rank is null")
            return await cur.fetchall()


async def update_frequency_rank(word_id: int, frequency_rank: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("update words set frequency_rank = %s where id = %s", (frequency_rank, word_id))


async def get_words_missing_mnemonic() -> list[dict]:
    """단어 암기 효율 개선(연상법/예문다양화) 소급 백필용 — scripts/backfill_word_mnemonics.py."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select id, word, meaning_ko from words where mnemonic is null")
            return await cur.fetchall()


async def update_mnemonic_and_examples(word_id: int, mnemonic: str, example_sentences: list[dict]) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "update words set mnemonic = %s, example_sentences = %s where id = %s",
                (mnemonic, Json(example_sentences), word_id),
            )


async def get_word_ids(words: list[str], learning_mode: str = "GENERAL") -> dict[str, int]:
    """단어 텍스트 -> id 매핑 (신규/기존 여부와 무관하게 조회, M11 텍스트학습 카드 구성용).

    같은 단어라도 모드별(M14)로 별도 행을 가질 수 있으므로 learning_mode로 반드시 좁혀서 조회한다.
    """
    if not words:
        return {}

    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select id, word from words where word = any(%s) and learning_mode = %s", (words, learning_mode)
            )
            rows = await cur.fetchall()
            return {row["word"]: row["id"] for row in rows}


async def insert_grammar_questions(level: str, questions: list[dict], learning_mode: str = "GENERAL") -> int:
    if not questions:
        return 0

    pool = get_pool()
    inserted = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for q in questions:
                await cur.execute(
                    """
                    insert into grammar_questions
                        (level, topic, concept_intro, prompt, choices, correct_index, explanation, learning_mode)
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        level,
                        q["topic"],
                        q.get("concept_intro"),
                        q["prompt"],
                        Json(q["choices"]),
                        q["correct_index"],
                        q["explanation"],
                        learning_mode,
                    ),
                )
                inserted += 1
    return inserted


async def insert_key_vocabulary_from_grammar(level: str, questions: list[dict], learning_mode: str = "GENERAL") -> int:
    """생성된 문법 문제들의 key_vocabulary를 단어뱅크(words)에 합류시킨다.

    사용자 피드백: 문법 문장에 모르는 단어가 섞여 나오면 그 단어들도 자연스럽게
    단어학습(/단어학습)에서 만나도록, 같은 레벨의 words 테이블에 그대로 추가한다.
    """
    all_vocab = [word for q in questions for word in q.get("key_vocabulary", [])]
    return await insert_words(level, all_vocab, learning_mode)


async def insert_reading_passages(level: str, passages: list[dict], learning_mode: str = "GENERAL") -> int:
    if not passages:
        return 0

    pool = get_pool()
    inserted = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for p in passages:
                await cur.execute(
                    """
                    insert into reading_passages
                        (level, passage_text, model_translation_ko, learning_mode,
                         avg_sentence_length, vocab_level, grammar_complexity, difficulty_band)
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        level,
                        p["passage"],
                        p["model_translation_ko"],
                        learning_mode,
                        p.get("avg_sentence_length"),
                        p.get("vocab_level"),
                        p.get("grammar_complexity"),
                        p.get("difficulty_band"),
                    ),
                )
                inserted += 1
    return inserted


async def insert_conversation_topic_words(topic: str, level: str, learning_mode: str, word_ids: list[int]) -> None:
    """회화 사전 단어학습: 생성된 단어들을 words에 합류시킨 뒤(insert_words), 그 id들을 주제와 연결한다."""
    if not word_ids:
        return

    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for word_id in word_ids:
                await cur.execute(
                    """
                    insert into conversation_topic_words (topic, level, learning_mode, word_id)
                    values (%s, %s, %s, %s)
                    on conflict (topic, level, learning_mode, word_id) do nothing
                    """,
                    (topic, level, learning_mode, word_id),
                )


async def get_topic_words(topic: str, level: str, learning_mode: str, limit: int) -> list[dict]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select w.id as word_id, w.word, w.meaning_ko, w.pronunciation,
                       w.example_sentence, w.example_translation, w.level
                from conversation_topic_words ctw
                join words w on w.id = ctw.word_id
                where ctw.topic = %s and ctw.level = %s and ctw.learning_mode = %s
                order by random()
                limit %s
                """,
                (topic, level, learning_mode, limit),
            )
            return await cur.fetchall()


async def count_words_by_level() -> dict[str, int]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select level, learning_mode, count(*) as n from words group by level, learning_mode")
            rows = await cur.fetchall()
            return {f"{row['level']}/{row['learning_mode']}": row["n"] for row in rows}


async def count_grammar_questions_by_level() -> dict[str, int]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select level, learning_mode, count(*) as n from grammar_questions group by level, learning_mode"
            )
            rows = await cur.fetchall()
            return {f"{row['level']}/{row['learning_mode']}": row["n"] for row in rows}


async def count_reading_passages_by_level() -> dict[str, int]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select level, learning_mode, count(*) as n from reading_passages group by level, learning_mode"
            )
            rows = await cur.fetchall()
            return {f"{row['level']}/{row['learning_mode']}": row["n"] for row in rows}
