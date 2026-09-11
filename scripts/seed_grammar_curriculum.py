"""CEFR 기반 문법 커리큘럼(app/grammar/curriculum_data.py)의 토픽/파트 구조를 grammar_topics/
grammar_parts 테이블에 채운다 (1회성, AI 호출 없음 — 순서/이름/설명만 DB에 반영).

idempotent: order_index/global_order_index를 키로 upsert하므로 몇 번을 다시 실행해도 안전하다
(curriculum_data.py를 수정한 뒤 다시 실행하면 이름/설명/exam_focus가 최신 내용으로 갱신된다).

exam_focus 토픽은 파트당 목표 문제 수(target_question_count)를 10~15개로, 일반 토픽은 5~8개로
차등 설정한다(한국 학교 시험 빈출 구문이라 반복 연습량을 더 확보하기 위함 — 순서를 앞당기지는
않는다).

사용법:
    python scripts/seed_grammar_curriculum.py
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.grammar.curriculum_data import CURRICULUM  # noqa: E402
from app.repo import grammar as grammar_repo  # noqa: E402

EXAM_FOCUS_TARGET_QUESTIONS = 12
NORMAL_TARGET_QUESTIONS = 6


async def main() -> None:
    await init_db_pool()
    try:
        global_order_index = 0
        topic_count = 0
        part_count = 0

        for topic_order_index, topic in enumerate(CURRICULUM):
            topic_id = await grammar_repo.upsert_topic(
                topic.cefr_level, topic_order_index, topic.name, topic.description, topic.is_exam_focus
            )
            topic_count += 1
            target = EXAM_FOCUS_TARGET_QUESTIONS if topic.is_exam_focus else NORMAL_TARGET_QUESTIONS

            for part_order_index, part in enumerate(topic.parts):
                await grammar_repo.upsert_part(
                    topic_id, part_order_index, global_order_index, part.name, part.description, target
                )
                part_count += 1
                global_order_index += 1

            focus_tag = " [EXAM_FOCUS]" if topic.is_exam_focus else ""
            print(f"[{topic.cefr_level}] {topic.name}{focus_tag} — {len(topic.parts)}개 파트")

        print(f"\n총 {topic_count}개 토픽, {part_count}개 파트 시딩 완료.")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
