from app.db import get_pool


async def save(
    user_id: int,
    level: str,
    source_text: str,
    extracted_word_count: int,
    user_translation: str,
    ai_feedback: str,
) -> None:
    # 섹션3-2: 원문 전체는 저장하지 않고 앞부분 일부만 남긴다.
    excerpt = source_text[:200]
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into custom_texts
                    (user_id, level, source_excerpt, source_char_count, extracted_word_count,
                     user_translation, ai_feedback)
                values (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, level, excerpt, len(source_text), extracted_word_count, user_translation, ai_feedback),
            )
