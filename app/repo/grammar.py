from typing import Any, Optional

from app.db import get_pool


async def get_random_questions(level: str, limit: int, learning_mode: str = "GENERAL") -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select id, topic, concept_intro, prompt, choices, correct_index, explanation
                from grammar_questions
                where level = %s and learning_mode = %s
                order by random()
                limit %s
                """,
                (level, learning_mode, limit),
            )
            return await cur.fetchall()


async def get_questions_for_topic(level: str, topic: str, limit: int, learning_mode: str = "GENERAL") -> list[dict[str, Any]]:
    """개인 맞춤 난이도(문법): 신규 세트(`/문법학습`)는 커리큘럼상 현재 주제만 출제한다."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select id, topic, concept_intro, prompt, choices, correct_index, explanation
                from grammar_questions
                where level = %s and learning_mode = %s and topic = %s
                order by random()
                limit %s
                """,
                (level, learning_mode, topic, limit),
            )
            return await cur.fetchall()


async def get_topic_accuracy_map(user_id: int, min_attempts: int = 3) -> dict[str, float]:
    """주제별 정답률 — 복습(review) 출제 가중치 계산용. 최소 시도횟수 미만인 주제는 신뢰도가
    낮아 제외한다."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select gq.topic as topic,
                       count(*) filter (where uga.is_correct) as correct,
                       count(*) as total
                from user_grammar_answers uga
                join grammar_questions gq on gq.id = uga.question_id
                where uga.user_id = %s and gq.topic is not null
                group by gq.topic
                having count(*) >= %s
                """,
                (user_id, min_attempts),
            )
            rows = await cur.fetchall()
            return {row["topic"]: row["correct"] / row["total"] for row in rows}


async def get_topic_recent_results(user_id: int, topic: str, limit: int) -> list[bool]:
    """신규 세트(`/문법학습`, is_review=false)만 집계 — 복습 응답은 커리큘럼 진행에 영향을 주지 않는다."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select uga.is_correct
                from user_grammar_answers uga
                join grammar_questions gq on gq.id = uga.question_id
                where uga.user_id = %s and gq.topic = %s and uga.is_review = false
                order by uga.answered_at desc
                limit %s
                """,
                (user_id, topic, limit),
            )
            rows = await cur.fetchall()
            return [row["is_correct"] for row in rows]


async def get_weighted_review_questions(
    level: str, limit: int, learning_mode: str, weak_topics: list[str]
) -> list[dict[str, Any]]:
    """복습(`/복습`) 출제 — 정답률 낮은 주제(weak_topics)에서 우선(최대 70%) 뽑고 나머지는
    전체에서 무작위로 채운다. weak_topics가 없으면 기존과 동일하게 완전 무작위."""
    if not weak_topics:
        return await get_random_questions(level, limit, learning_mode)

    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            weak_count = min(limit, max(1, round(limit * 0.7)))
            await cur.execute(
                """
                select id, topic, concept_intro, prompt, choices, correct_index, explanation
                from grammar_questions
                where level = %s and learning_mode = %s and topic = any(%s)
                order by random()
                limit %s
                """,
                (level, learning_mode, weak_topics, weak_count),
            )
            weak_rows = await cur.fetchall()

            remaining = limit - len(weak_rows)
            if remaining <= 0:
                return weak_rows

            exclude_ids = [r["id"] for r in weak_rows] or [0]
            await cur.execute(
                """
                select id, topic, concept_intro, prompt, choices, correct_index, explanation
                from grammar_questions
                where level = %s and learning_mode = %s and not (id = any(%s))
                order by random()
                limit %s
                """,
                (level, learning_mode, exclude_ids, remaining),
            )
            fill_rows = await cur.fetchall()
            return weak_rows + fill_rows


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
