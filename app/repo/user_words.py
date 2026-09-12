from datetime import date
from typing import Any

from app.db import get_pool


async def get_due_review_words(user_id: int, today: date, limit: int | None = None) -> list[dict[str, Any]]:
    """limit을 주면(app.srs.DAILY_REVIEW_LIMIT) 가장 오래 밀린 것부터 그만큼만 반환한다 —
    복습 대상이 하루치를 훨씬 넘게 쌓여도(예: 테스트를 여러 날에 걸쳐 함) 한 번에 전부 쏟아지지
    않게 하기 위함(사용자 버그리포트). 그날 못 나간 나머지는 next_review_date가 그대로라 다음날
    다시 조회 시 자연히 최우선으로 다시 포함된다 — 데이터 유실 없음."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select uw.word_id, uw.ease, uw.interval_days, uw.review_count,
                       uw.mastery, uw.consecutive_correct,
                       w.word, w.meaning_ko, w.pronunciation, w.example_sentence, w.example_translation, w.level,
                       w.mnemonic, w.example_sentences, w.emoji
                from user_words uw
                join words w on w.id = uw.word_id
                where uw.user_id = %s and uw.next_review_date <= %s and uw.status != 'new'
                order by uw.next_review_date
                limit %s
                """,
                (user_id, today, limit),
            )
            return await cur.fetchall()


async def get_new_words(
    user_id: int,
    level: str,
    limit: int,
    learning_mode: str = "GENERAL",
    min_rank: int | None = None,
    max_rank: int | None = None,
) -> list[dict[str, Any]]:
    """min_rank/max_rank를 주면 개인 맞춤 난이도 밴드(frequency_rank) 범위로 후보를 좁힌다.

    frequency_rank가 없는(NULL) 단어는 밴드 필터에 걸리지 않지만, 정렬 시 항상 맨 뒤로
    밀려 자주 쓰이는 단어가 우선 노출되게 한다(둘 다 없을 때는 기존과 동일하게 id 순).
    """
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            conditions = ["w.level = %s", "w.learning_mode = %s"]
            params: list[Any] = [level, learning_mode]
            if min_rank is not None and max_rank is not None:
                conditions.append("w.frequency_rank between %s and %s")
                params.extend([min_rank, max_rank])

            where_clause = " and ".join(conditions)
            await cur.execute(
                f"""
                select w.id as word_id, w.word, w.meaning_ko, w.pronunciation,
                       w.example_sentence, w.example_translation, w.level, w.frequency_rank,
                       w.mnemonic, w.example_sentences, w.emoji
                from words w
                where {where_clause}
                  and not exists (
                      select 1 from user_words uw where uw.user_id = %s and uw.word_id = w.id
                  )
                order by coalesce(w.frequency_rank, 999999) asc, w.id asc
                limit %s
                """,
                (*params, user_id, limit),
            )
            return await cur.fetchall()


async def get_learned_word_ids(user_id: int, word_ids: list[int]) -> set[int]:
    """오늘의 주제 통합 학습: 오늘의 단어 풀 중 이미 user_words에 있는(복습중이거나 완료된) 단어는
    "신규"로 다시 보여주지 않기 위한 조회."""
    if not word_ids:
        return set()
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select word_id from user_words where user_id = %s and word_id = any(%s)",
                (user_id, word_ids),
            )
            rows = await cur.fetchall()
            return {row["word_id"] for row in rows}


async def get_known_topic_words(user_id: int, topic: str, level: str, learning_mode: str) -> list[dict[str, Any]]:
    """오늘의 주제 통합 학습: 이 주제로 그동안(오늘 새로 뽑은 목록뿐 아니라 topic_words에 누적된
    전체) 생성됐던 단어 중, 사용자가 이미 학습 완료(status='known')한 것 — 있으면 해석 지문 생성 시
    신규 단어와 함께 쓸 수 있는 어휘 풀에 포함한다(없으면 빈 목록, 정상)."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select w.id as word_id, w.word, w.meaning_ko
                from topic_words tw
                join words w on w.id = tw.word_id
                join user_words uw on uw.word_id = w.id
                where tw.topic = %s and tw.level = %s and tw.learning_mode = %s
                  and uw.user_id = %s and uw.status = 'known'
                """,
                (topic, level, learning_mode, user_id),
            )
            return await cur.fetchall()


async def get_mastered_word_stats(user_id: int) -> tuple[float | None, int]:
    """V2 학습 엔진(app/vocab/level.py): 이 사용자가 실제로 mastered 상태까지 확인한 단어들의
    frequency_rank 중앙값과 표본 크기를 반환한다 — 어휘 레벨을 문법 진행도가 아니라 실제 학습
    기록에서 독립적으로 추정하기 위함(frequency_rank는 어디까지나 보조자료)."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select percentile_cont(0.5) within group (order by w.frequency_rank) as median_rank,
                       count(*) as n
                from user_words uw
                join words w on w.id = uw.word_id
                where uw.user_id = %s and uw.mastery = 'mastered' and w.frequency_rank is not null
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            return (float(row["median_rank"]) if row and row["median_rank"] is not None else None), (
                row["n"] if row else 0
            )


async def record_word_attempt(user_id: int, word_id: int, band: int, is_correct: bool) -> None:
    """신규 단어(첫 학습)를 완료했을 때만 기록 — SRS 복습은 대상이 아니다."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "insert into user_word_attempts (user_id, word_id, band, is_correct) values (%s, %s, %s, %s)",
                (user_id, word_id, band, is_correct),
            )


async def get_recent_band_results(user_id: int, band: int, limit: int) -> list[bool]:
    """최신순으로 정렬된 최근 N개 정오답 — 밴드 승급/강등 판단용."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select is_correct from user_word_attempts
                where user_id = %s and band = %s
                order by attempted_at desc
                limit %s
                """,
                (user_id, band, limit),
            )
            rows = await cur.fetchall()
            return [row["is_correct"] for row in rows]


async def get_distractor_meanings(
    level: str, exclude_word_id: int, count: int, learning_mode: str = "GENERAL"
) -> list[str]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select meaning_ko from words
                where level = %s and learning_mode = %s and id != %s
                order by random()
                limit %s
                """,
                (level, learning_mode, exclude_word_id, count),
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
    mastery: str,
    consecutive_correct: int,
    is_correct: bool,
) -> None:
    """V2 학습 엔진(단어 암기): status/ease/interval_days는 기존 SRS 그대로 쓰고, mastery/
    consecutive_correct(app.vocab.mastery.apply_answer가 계산한 최종값을 그대로 받음)와
    correct_count/wrong_count/first_exposed_at/last_wrong_at(누적 통계, 여기서 증분)을 함께 기록한다."""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into user_words
                    (user_id, word_id, status, ease, interval_days, next_review_date, last_reviewed_at,
                     review_count, mastery, consecutive_correct, correct_count, wrong_count,
                     first_exposed_at, last_wrong_at)
                values (%(user_id)s, %(word_id)s, %(status)s, %(ease)s, %(interval_days)s, %(next_review_date)s, now(),
                        1, %(mastery)s, %(consecutive_correct)s,
                        case when %(is_correct)s then 1 else 0 end,
                        case when %(is_correct)s then 0 else 1 end,
                        now(),
                        case when %(is_correct)s then null else now() end)
                on conflict (user_id, word_id) do update set
                    status = excluded.status,
                    ease = excluded.ease,
                    interval_days = excluded.interval_days,
                    next_review_date = excluded.next_review_date,
                    last_reviewed_at = now(),
                    review_count = user_words.review_count + 1,
                    mastery = excluded.mastery,
                    consecutive_correct = excluded.consecutive_correct,
                    correct_count = user_words.correct_count + (case when %(is_correct)s then 1 else 0 end),
                    wrong_count = user_words.wrong_count + (case when %(is_correct)s then 0 else 1 end),
                    first_exposed_at = coalesce(user_words.first_exposed_at, now()),
                    last_wrong_at = case when %(is_correct)s then user_words.last_wrong_at else now() end
                """,
                {
                    "user_id": user_id,
                    "word_id": word_id,
                    "status": status,
                    "ease": ease,
                    "interval_days": interval_days,
                    "next_review_date": next_review_date,
                    "mastery": mastery,
                    "consecutive_correct": consecutive_correct,
                    "is_correct": is_correct,
                },
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
