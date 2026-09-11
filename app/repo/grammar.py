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


# ─────────────────────────────────────────────────────────────────────────
# CEFR 파트 기반 커리큘럼 진행 (그래마 재구성 2026-09) — 토픽 하나가 너무 커서 숙달 기준에
# 영원히 도달하지 못하던 버그를, 더 작은 파트 단위 + "최소 5문제 시도 + 최근 5문제 80%"로 해결.
# 기존 topic 문자열 기반 함수(위)는 /복습 가중치 계산에 계속 쓰이므로 그대로 둔다.
# ─────────────────────────────────────────────────────────────────────────


async def upsert_topic(cefr_level: str, order_index: int, name: str, description: str, is_exam_focus: bool) -> int:
    """scripts/seed_grammar_curriculum.py 전용 — order_index를 키로 idempotent하게 채운다."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into grammar_topics (cefr_level, order_index, name, description, is_exam_focus)
                values (%s, %s, %s, %s, %s)
                on conflict (order_index) do update
                    set cefr_level = excluded.cefr_level, name = excluded.name,
                        description = excluded.description, is_exam_focus = excluded.is_exam_focus
                returning id
                """,
                (cefr_level, order_index, name, description, is_exam_focus),
            )
            row = await cur.fetchone()
            return row["id"]


async def upsert_part(
    topic_id: int, order_index: int, global_order_index: int, name: str, description: str, target_question_count: int
) -> int:
    """scripts/seed_grammar_curriculum.py 전용 — global_order_index를 키로 idempotent하게 채운다."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into grammar_parts (topic_id, order_index, global_order_index, name, description, target_question_count)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (global_order_index) do update
                    set topic_id = excluded.topic_id, order_index = excluded.order_index,
                        name = excluded.name, description = excluded.description,
                        target_question_count = excluded.target_question_count
                returning id
                """,
                (topic_id, order_index, global_order_index, name, description, target_question_count),
            )
            row = await cur.fetchone()
            return row["id"]


async def get_all_parts_ordered() -> list[dict[str, Any]]:
    """scripts/generate_grammar_curriculum.py 전용 — 전체 파트를 절대 순서대로."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select gp.id, gp.topic_id, gp.global_order_index, gp.name, gp.description,
                       gp.target_question_count, gt.name as topic_name, gt.cefr_level, gt.is_exam_focus
                from grammar_parts gp
                join grammar_topics gt on gt.id = gp.topic_id
                order by gp.global_order_index
                """
            )
            return await cur.fetchall()


async def count_questions_for_part(part_id: int) -> int:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select count(*) as n from grammar_questions where part_id = %s", (part_id,))
            row = await cur.fetchone()
            return row["n"]


async def get_first_part() -> Optional[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select gp.id, gp.topic_id, gp.global_order_index, gp.name, gp.description,
                       gp.target_question_count, gt.name as topic_name, gt.cefr_level, gt.is_exam_focus
                from grammar_parts gp
                join grammar_topics gt on gt.id = gp.topic_id
                order by gp.global_order_index
                limit 1
                """
            )
            return await cur.fetchone()


async def get_part_by_id(part_id: int) -> Optional[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select gp.id, gp.topic_id, gp.global_order_index, gp.name, gp.description,
                       gp.target_question_count, gt.name as topic_name, gt.cefr_level, gt.is_exam_focus
                from grammar_parts gp
                join grammar_topics gt on gt.id = gp.topic_id
                where gp.id = %s
                """,
                (part_id,),
            )
            return await cur.fetchone()


async def get_next_part_after(part_id: int) -> Optional[dict[str, Any]]:
    """part_id 다음 순서의 파트(전체 커리큘럼 절대 순서 기준). 마지막 파트면 None."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select gp.id, gp.topic_id, gp.global_order_index, gp.name, gp.description,
                       gp.target_question_count, gt.name as topic_name, gt.cefr_level, gt.is_exam_focus
                from grammar_parts gp
                join grammar_topics gt on gt.id = gp.topic_id
                where gp.global_order_index > (select global_order_index from grammar_parts where id = %s)
                order by gp.global_order_index
                limit 1
                """,
                (part_id,),
            )
            return await cur.fetchone()


async def get_user_progress(user_id: int) -> Optional[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select user_id, current_topic_id, current_part_id from user_grammar_progress where user_id = %s",
                (user_id,),
            )
            return await cur.fetchone()


async def set_user_progress(user_id: int, topic_id: int, part_id: int) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into user_grammar_progress (user_id, current_topic_id, current_part_id, updated_at)
                values (%s, %s, %s, now())
                on conflict (user_id) do update
                    set current_topic_id = excluded.current_topic_id,
                        current_part_id = excluded.current_part_id,
                        updated_at = now()
                """,
                (user_id, topic_id, part_id),
            )


async def get_part_progress(user_id: int, part_id: int) -> Optional[dict[str, Any]]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select status, attempt_count, correct_count from user_grammar_part_progress "
                "where user_id = %s and part_id = %s",
                (user_id, part_id),
            )
            return await cur.fetchone()


async def record_part_attempt(user_id: int, part_id: int, is_correct: bool) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into user_grammar_part_progress (user_id, part_id, status, attempt_count, correct_count, updated_at)
                values (%s, %s, 'in_progress', 1, %s, now())
                on conflict (user_id, part_id) do update
                    set attempt_count = user_grammar_part_progress.attempt_count + 1,
                        correct_count = user_grammar_part_progress.correct_count + excluded.correct_count,
                        updated_at = now()
                """,
                (user_id, part_id, 1 if is_correct else 0),
            )


async def set_part_status(user_id: int, part_id: int, status: str) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into user_grammar_part_progress (user_id, part_id, status, attempt_count, correct_count, updated_at)
                values (%s, %s, %s, 0, 0, now())
                on conflict (user_id, part_id) do update
                    set status = excluded.status, updated_at = now()
                """,
                (user_id, part_id, status),
            )


async def get_part_recent_results(user_id: int, part_id: int, limit: int, is_review: bool = False) -> list[bool]:
    """최근 N개 정오답(part_id 기준) — is_review=False면 신규 세트만(파트 숙달 판정용),
    True면 복습 응답만(이미 숙달한 파트가 다시 약해졌는지 판정용, "역행" 로직)."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select uga.is_correct
                from user_grammar_answers uga
                join grammar_questions gq on gq.id = uga.question_id
                where uga.user_id = %s and gq.part_id = %s and uga.is_review = %s
                order by uga.answered_at desc
                limit %s
                """,
                (user_id, part_id, is_review, limit),
            )
            rows = await cur.fetchall()
            return [row["is_correct"] for row in rows]


async def get_questions_for_part(
    part_id: int, limit: int, learning_mode: str = "GENERAL", prioritize_error_types: Optional[list[str]] = None
) -> list[dict[str, Any]]:
    """신규 세트(`/문법학습`)는 현재 파트의 문제만 출제한다. prioritize_error_types가 있으면(파트
    반복 시 취약 오답유형 우선 재출제, 사용자 요청) 그 유형을 최대 70%까지 우선 뽑는다."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            if prioritize_error_types:
                weak_count = min(limit, max(1, round(limit * 0.7)))
                await cur.execute(
                    """
                    select id, topic, concept_intro, prompt, choices, correct_index, explanation, part_id, error_type
                    from grammar_questions
                    where part_id = %s and learning_mode = %s and error_type = any(%s)
                    order by random()
                    limit %s
                    """,
                    (part_id, learning_mode, prioritize_error_types, weak_count),
                )
                weak_rows = await cur.fetchall()
                remaining = limit - len(weak_rows)
                if remaining > 0:
                    exclude_ids = [r["id"] for r in weak_rows] or [0]
                    await cur.execute(
                        """
                        select id, topic, concept_intro, prompt, choices, correct_index, explanation, part_id, error_type
                        from grammar_questions
                        where part_id = %s and learning_mode = %s and not (id = any(%s))
                        order by random()
                        limit %s
                        """,
                        (part_id, learning_mode, exclude_ids, remaining),
                    )
                    weak_rows += await cur.fetchall()
                return weak_rows

            await cur.execute(
                """
                select id, topic, concept_intro, prompt, choices, correct_index, explanation, part_id, error_type
                from grammar_questions
                where part_id = %s and learning_mode = %s
                order by random()
                limit %s
                """,
                (part_id, learning_mode, limit),
            )
            return await cur.fetchall()


async def get_weak_error_types_for_part(user_id: int, part_id: int, limit: int) -> list[str]:
    """이 파트에서 최근에 자주 틀린 error_type 상위 N개 — 파트 반복 시 우선 재출제용."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select gq.error_type as error_type, count(*) as n
                from user_grammar_answers uga
                join grammar_questions gq on gq.id = uga.question_id
                where uga.user_id = %s and gq.part_id = %s and uga.is_correct = false and gq.error_type is not null
                group by gq.error_type
                order by n desc
                limit %s
                """,
                (user_id, part_id, limit),
            )
            rows = await cur.fetchall()
            return [row["error_type"] for row in rows]


async def get_topic_names_up_to(global_order_index: int) -> list[str]:
    """해석(Reading) 지문 생성 시 "이미 노출된 문법 범위"를 안내하기 위한 토픽 이름 목록
    (현재 파트보다 앞선 파트들의 토픽, 중복 제거, 순서 보존)."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select distinct gt.name, min(gp.global_order_index) as first_index
                from grammar_parts gp
                join grammar_topics gt on gt.id = gp.topic_id
                where gp.global_order_index <= %s
                group by gt.name
                order by first_index
                """,
                (global_order_index,),
            )
            rows = await cur.fetchall()
            return [row["name"] for row in rows]


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
