from psycopg.types.json import Jsonb

from app.db import get_pool


async def start_today(user_id: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into learning_sessions (user_id, session_date)
                values (%s, current_date)
                on conflict (user_id, session_date) do nothing
                """,
                (user_id,),
            )


async def mark_stage_complete(user_id: int, stage: str) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                update learning_sessions
                set stages_completed = stages_completed || %s
                where user_id = %s and session_date = current_date
                """,
                (Jsonb([stage]), user_id),
            )


async def increment_ai_call_count(user_id: int, by: int = 1) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                update learning_sessions
                set ai_call_count = ai_call_count + %s
                where user_id = %s and session_date = current_date
                """,
                (by, user_id),
            )


async def get_today_row(user_id: int) -> dict | None:
    """오늘의 주제 통합 학습: 오늘 이미 정해둔 주제/단어풀/지문이 있는지 확인할 때 사용."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select * from learning_sessions where user_id = %s and session_date = current_date",
                (user_id,),
            )
            return await cur.fetchone()


async def set_today_topic(user_id: int, topic: str, word_ids: list[int]) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                update learning_sessions
                set today_topic = %s, today_topic_word_ids = %s
                where user_id = %s and session_date = current_date
                """,
                (topic, word_ids, user_id),
            )


async def set_today_reading_passage(user_id: int, passage_id: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                update learning_sessions set today_reading_passage_id = %s
                where user_id = %s and session_date = current_date
                """,
                (passage_id, user_id),
            )


async def get_recent_topics(user_id: int, days: int) -> list[str]:
    """오늘의 주제 통합 학습: 최근 N일 안에 이미 썼던 주제는 오늘 다시 고르지 않기 위한 조회."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select distinct today_topic from learning_sessions
                where user_id = %s and today_topic is not null
                  and session_date >= current_date - %s::int and session_date < current_date
                """,
                (user_id, days),
            )
            rows = await cur.fetchall()
            return [row["today_topic"] for row in rows]


async def mark_completed(user_id: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "update learning_sessions set completed_at = now() where user_id = %s and session_date = current_date",
                (user_id,),
            )
