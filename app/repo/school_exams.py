from datetime import date
from typing import Any, Optional

from app.db import get_pool


async def create(user_id: int, subject: str, exam_date: date, unit_info: str, teacher_notes: str) -> int:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into school_exams (user_id, subject, exam_date, unit_info, teacher_notes)
                values (%s, %s, %s, %s, %s)
                returning id
                """,
                (user_id, subject, exam_date, unit_info, teacher_notes),
            )
            row = await cur.fetchone()
            return row["id"]


async def list_upcoming(user_id: int, today: date) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select id, subject, exam_date, unit_info, teacher_notes
                from school_exams
                where user_id = %s and exam_date >= %s
                order by exam_date asc
                """,
                (user_id, today),
            )
            return await cur.fetchall()


async def list_all(user_id: int) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select id, subject, exam_date, unit_info, teacher_notes
                from school_exams
                where user_id = %s
                order by exam_date asc
                """,
                (user_id,),
            )
            return await cur.fetchall()


async def get_by_id(exam_id: int, user_id: int) -> Optional[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select id, subject, exam_date, unit_info, teacher_notes
                from school_exams
                where id = %s and user_id = %s
                """,
                (exam_id, user_id),
            )
            return await cur.fetchone()


async def record_review(exam_id: int, user_id: int, question_count: int, correct_count: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into school_exam_reviews (exam_id, user_id, question_count, correct_count)
                values (%s, %s, %s, %s)
                """,
                (exam_id, user_id, question_count, correct_count),
            )
