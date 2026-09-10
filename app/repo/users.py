from typing import Any, Optional

from app.db import get_pool


async def get_user_by_telegram_id(telegram_id: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select * from users where telegram_id = %s", (telegram_id,))
            return await cur.fetchone()


async def create_pending_user(telegram_id: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into users (telegram_id, approved, role)
                values (%s, false, 'user')
                on conflict (telegram_id) do nothing
                returning *
                """,
                (telegram_id,),
            )
            return await cur.fetchone()


async def approve_user(telegram_id: str) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("update users set approved = true where telegram_id = %s", (telegram_id,))


async def set_role(telegram_id: str, role: str) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("update users set role = %s where telegram_id = %s", (role, telegram_id))


async def set_placement_level(telegram_id: str, placement_level: str) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "update users set placement_level = %s where telegram_id = %s",
                (placement_level, telegram_id),
            )


async def set_word_band(telegram_id: str, band: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("update users set word_band = %s where telegram_id = %s", (band, telegram_id))


async def set_conversation_level(telegram_id: str, level: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("update users set conversation_level = %s where telegram_id = %s", (level, telegram_id))


async def set_reading_band(telegram_id: str, band: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("update users set reading_band = %s where telegram_id = %s", (band, telegram_id))


async def set_grammar_topic_index(telegram_id: str, index: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("update users set grammar_topic_index = %s where telegram_id = %s", (index, telegram_id))


async def set_child_stage(telegram_id: str, stage: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("update users set child_stage = %s where telegram_id = %s", (stage, telegram_id))


async def set_daily_new_word_limit(telegram_id: str, limit: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "update users set daily_new_word_limit = %s where telegram_id = %s",
                (limit, telegram_id),
            )


async def set_age_and_mode(telegram_id: str, age: int, learning_mode: str) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "update users set age = %s, learning_mode = %s where telegram_id = %s",
                (age, learning_mode, telegram_id),
            )


async def touch_last_active(telegram_id: str) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("update users set last_active_at = now() where telegram_id = %s", (telegram_id,))


async def list_pending_users() -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select * from users where approved = false order by created_at")
            return await cur.fetchall()


async def list_all_users() -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select * from users order by created_at")
            return await cur.fetchall()


async def list_approved_users_with_activity() -> list[dict[str, Any]]:
    """관리자용 사용자 목록 — 아이디/나이/모드/오늘 활동 횟수 (섹션4-2 "사용자 관리")."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select
                    u.id, u.telegram_id, u.role, u.age, u.learning_mode, u.placement_level, u.last_active_at,
                    (
                        coalesce((select count(*) from user_grammar_answers g
                                  where g.user_id = u.id and g.answered_at::date = current_date), 0)
                        + coalesce((select count(*) from user_reading_attempts r
                                    where r.user_id = u.id and r.attempted_at::date = current_date), 0)
                        + coalesce((select count(*) from conversation_messages cm
                                    join conversation_sessions cs on cs.id = cm.session_id
                                    where cs.user_id = u.id and cm.role = 'user'
                                      and cm.created_at::date = current_date), 0)
                        + coalesce((select count(*) from user_words w
                                    where w.user_id = u.id and w.last_reviewed_at::date = current_date), 0)
                    ) as today_activity_count
                from users u
                where u.approved = true
                order by u.created_at
                """
            )
            return await cur.fetchall()
