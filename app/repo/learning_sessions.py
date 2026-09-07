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


async def mark_completed(user_id: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "update learning_sessions set completed_at = now() where user_id = %s and session_date = current_date",
                (user_id,),
            )
