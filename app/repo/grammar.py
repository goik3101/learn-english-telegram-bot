from typing import Any, Optional

from app.db import get_pool


async def get_random_questions(level: str, limit: int) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select id, topic, concept_intro, prompt, choices, correct_index, explanation
                from grammar_questions
                where level = %s
                order by random()
                limit %s
                """,
                (level, limit),
            )
            return await cur.fetchall()


async def has_completed_new_session_today(user_id: int) -> bool:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select 1 from user_grammar_answers
                where user_id = %s and is_review = false and answered_at::date = current_date
                limit 1
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            return row is not None


async def get_weak_topics(user_id: int, limit: int) -> list[str]:
    """오답이 잦은 문법 주제를 빈도순으로 반환 (Planner AI 보정용, 섹션8-2/16)."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select error_tag, count(*) as n
                from user_grammar_answers
                where user_id = %s and error_tag is not null
                group by error_tag
                order by n desc
                limit %s
                """,
                (user_id, limit),
            )
            rows = await cur.fetchall()
            return [row["error_tag"] for row in rows]


async def get_overall_accuracy(user_id: int) -> Optional[float]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select count(*) filter (where is_correct) as correct, count(*) as total
                from user_grammar_answers
                where user_id = %s
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            if row is None or not row["total"]:
                return None
            return row["correct"] / row["total"]


async def record_answer(
    user_id: int,
    question_id: int,
    is_correct: bool,
    error_tag: Optional[str],
    is_review: bool,
) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into user_grammar_answers (user_id, question_id, is_correct, error_tag, is_review)
                values (%s, %s, %s, %s, %s)
                """,
                (user_id, question_id, is_correct, error_tag, is_review),
            )
