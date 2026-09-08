from typing import Any

from psycopg.types.json import Jsonb

from app.db import get_pool


async def insert_content(stage: int, items: list[dict]) -> int:
    if not items:
        return 0

    pool = get_pool()
    inserted = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for item in items:
                await cur.execute(
                    """
                    insert into child_beginner_content
                        (stage, passage_text, prompt, meaning_ko, choices, correct_index)
                    values (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        stage,
                        item.get("passage_text"),
                        item["prompt"],
                        item["meaning_ko"],
                        Jsonb(item["choices"]),
                        item["correct_index"],
                    ),
                )
                inserted += 1
    return inserted


async def get_content_for_stage(stage: int, limit: int) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select id, stage, passage_text, prompt, meaning_ko, choices, correct_index
                from child_beginner_content
                where stage = %s
                order by random()
                limit %s
                """,
                (stage, limit),
            )
            return await cur.fetchall()


async def count_by_stage() -> dict[int, int]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select stage, count(*) as n from child_beginner_content group by stage")
            rows = await cur.fetchall()
            return {row["stage"]: row["n"] for row in rows}


async def mark_stage_completed(user_id: int, stage: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into child_beginner_progress (user_id, stage)
                values (%s, %s)
                on conflict (user_id, stage) do nothing
                """,
                (user_id, stage),
            )
