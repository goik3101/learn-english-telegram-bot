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


async def get_random_passage(level: str, learning_mode: str = "GENERAL", band: Optional[int] = None) -> Optional[dict[str, Any]]:
    """band를 주면 개인 맞춤 난이도(독해) 밴드로 좁혀서 시도한다 — 호출측에서 후보가 없으면
    band=None으로 다시 불러 기존 방식(레벨 전체 무작위)으로 폴백한다."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            conditions = ["level = %s", "learning_mode = %s"]
            params: list[Any] = [level, learning_mode]
            if band is not None:
                conditions.append("difficulty_band = %s")
                params.append(band)

            where_clause = " and ".join(conditions)
            await cur.execute(
                f"""
                select id, level, passage_text, model_translation_ko, difficulty_band
                from reading_passages
                where {where_clause}
                order by random()
                limit 1
                """,
                params,
            )
            return await cur.fetchone()


async def get_passage_by_id(passage_id: int) -> Optional[dict[str, Any]]:
    """오늘의 주제 통합 학습: 하루 동안 같은(오늘의 주제 제약으로 생성된) 지문을 재사용할 때 조회."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select id, level, passage_text, model_translation_ko, difficulty_band from reading_passages where id = %s",
                (passage_id,),
            )
            return await cur.fetchone()


async def get_recent_band_results(user_id: int, band: int, limit: int) -> list[bool]:
    """해당 밴드 지문에 대한 최근 첫 시도(attempt_number=1) 적절 여부 — 밴드 승급/강등 판단용."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select ura.is_adequate
                from user_reading_attempts ura
                join reading_passages rp on rp.id = ura.passage_id
                where ura.user_id = %s and rp.difficulty_band = %s
                  and ura.is_review = false and ura.attempt_number = 1
                order by ura.attempted_at desc
                limit %s
                """,
                (user_id, band, limit),
            )
            rows = await cur.fetchall()
            return [row["is_adequate"] for row in rows]


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
