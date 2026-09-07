from datetime import date
from typing import Any

from app.db import get_pool


async def get_due_review_words(user_id: int, today: date) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select uw.word_id, uw.ease, uw.interval_days,
                       w.word, w.meaning_ko, w.pronunciation, w.example_sentence, w.example_translation, w.level
                from user_words uw
                join words w on w.id = uw.word_id
                where uw.user_id = %s and uw.next_review_date <= %s and uw.status != 'new'
                order by uw.next_review_date
                """,
                (user_id, today),
            )
            return await cur.fetchall()


async def get_new_words(user_id: int, level: str, limit: int) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select w.id as word_id, w.word, w.meaning_ko, w.pronunciation,
                       w.example_sentence, w.example_translation, w.level
                from words w
                where w.level = %s
                  and not exists (
                      select 1 from user_words uw where uw.user_id = %s and uw.word_id = w.id
                  )
                order by w.id
                limit %s
                """,
                (level, user_id, limit),
            )
            return await cur.fetchall()


async def get_distractor_meanings(level: str, exclude_word_id: int, count: int) -> list[str]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select meaning_ko from words
                where level = %s and id != %s
                order by random()
                limit %s
                """,
                (level, exclude_word_id, count),
            )
            rows = await cur.fetchall()
            return [r["meaning_ko"] for r in rows]


async def upsert_word_progress(
    user_id: int,
    word_id: int,
    status: str,
    ease: float,
    interval_days: int,
    next_review_date: date,
) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into user_words (user_id, word_id, status, ease, interval_days, next_review_date, last_reviewed_at)
                values (%s, %s, %s, %s, %s, %s, now())
                on conflict (user_id, word_id) do update set
                    status = excluded.status,
                    ease = excluded.ease,
                    interval_days = excluded.interval_days,
                    next_review_date = excluded.next_review_date,
                    last_reviewed_at = now()
                """,
                (user_id, word_id, status, ease, interval_days, next_review_date),
            )


async def get_progress_counts(user_id: int) -> dict[str, int]:
    """/진도 표시용: 상태별 학습 단어 수 (섹션12)."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select status, count(*) as n from user_words where user_id = %s group by status",
                (user_id,),
            )
            rows = await cur.fetchall()
            return {row["status"]: row["n"] for row in rows}


async def get_learned_words_sample(user_id: int, limit: int) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select w.id as word_id, w.word, w.meaning_ko, w.level
                from user_words uw
                join words w on w.id = uw.word_id
                where uw.user_id = %s and uw.status != 'new'
                order by random()
                limit %s
                """,
                (user_id, limit),
            )
            return await cur.fetchall()
