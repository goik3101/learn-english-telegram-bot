from app.db import get_pool


async def has_completed_today(user_id: int) -> bool:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select 1 from conversation_sessions
                where user_id = %s and completed_at is not null and started_at::date = current_date
                limit 1
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            return row is not None


async def create_session(user_id: int, level: str) -> int:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "insert into conversation_sessions (user_id, level) values (%s, %s) returning id",
                (user_id, level),
            )
            row = await cur.fetchone()
            return row["id"]


async def add_message(session_id: int, role: str, content: str) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "insert into conversation_messages (session_id, role, content) values (%s, %s, %s)",
                (session_id, role, content),
            )


async def complete_session(session_id: int, turn_count: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "update conversation_sessions set completed_at = now(), turn_count = %s where id = %s",
                (turn_count, session_id),
            )


async def get_completed_session_count(user_id: int) -> int:
    """/진도 표시용: 완료한 회화 세션 수 (섹션12)."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select count(*) as n from conversation_sessions where user_id = %s and completed_at is not null",
                (user_id,),
            )
            row = await cur.fetchone()
            return row["n"] or 0
