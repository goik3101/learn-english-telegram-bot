from typing import Any, Optional

from psycopg.types.json import Jsonb

from app.db import get_pool


async def save(
    user_id: int,
    level: str,
    source_text: str,
    extracted_word_count: int,
    grammar_explanation: str,
    exam_question_count: int,
    exam_correct_count: int,
    exam_id: Optional[int] = None,
    question_details: Optional[list[dict]] = None,
) -> None:
    # 섹션3-2: 원문 전체는 저장하지 않고 앞부분 일부만 남긴다.
    excerpt = source_text[:200]
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into school_assignments
                    (user_id, level, source_excerpt, source_char_count, extracted_word_count,
                     grammar_explanation, exam_question_count, exam_correct_count, exam_id, question_details)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    level,
                    excerpt,
                    len(source_text),
                    extracted_word_count,
                    grammar_explanation,
                    exam_question_count,
                    exam_correct_count,
                    exam_id,
                    Jsonb(question_details) if question_details is not None else None,
                ),
            )


async def get_wrong_questions_for_exam(user_id: int, exam_id: int) -> list[dict[str, Any]]:
    """특정 시험(M13)에 연결된 자료(M12)들에서 오답 문항만 모아 반환 — 시험직전복습용."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select question_details
                from school_assignments
                where user_id = %s and exam_id = %s and question_details is not null
                order by created_at asc
                """,
                (user_id, exam_id),
            )
            rows = await cur.fetchall()

    wrong_questions: list[dict[str, Any]] = []
    for row in rows:
        for question in row["question_details"] or []:
            if not question.get("is_correct", True):
                wrong_questions.append(question)
    return wrong_questions
