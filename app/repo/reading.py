from typing import Any, Optional

from app.db import get_pool


async def get_progress_stats(user_id: int) -> dict[str, int]:
    """/진도 표시용: 지문 시도 수 + 최종 적절 판정 수 (섹션12)."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select count(*) as total, count(*) filter (where is_adequate) as adequate
                from user_reading_attempts
                where user_id = %s
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            return {"total": row["total"] or 0, "adequate": row["adequate"] or 0}


async def get_random_passage(level: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select id, level, passage_text, model_translation_ko
                from reading_passages
                where level = %s
                order by random()
                limit 1
                """,
                (level,),
            )
            return await cur.fetchone()


async def record_attempt(
    user_id: int,
    passage_id: int,
    user_translation: str,
    ai_feedback: str,
    attempt_number: int,
    is_adequate: bool,
    is_review: bool,
) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into user_reading_attempts
                    (user_id, passage_id, user_translation, ai_feedback, attempt_number, is_adequate, is_review)
                values (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, passage_id, user_translation, ai_feedback, attempt_number, is_adequate, is_review),
            )
