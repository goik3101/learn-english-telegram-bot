"""CEFR 기반 문법 커리큘럼(grammar_topics/grammar_parts, scripts/seed_grammar_curriculum.py로 먼저
시딩해야 함)의 파트마다 문제를 생성해 콘텐츠뱅크에 채운다 (1회성 스크립트).

파트마다 grammar_parts.target_question_count개씩 생성한다(exam_focus 토픽은 시딩 단계에서 이미
더 큰 값으로 설정됨). 이미 목표 수만큼 문제가 있는 파트는 기본적으로 건너뛴다 — 콘텐츠를 더
늘리고 싶으면 --force로 무시하고 추가 생성(중복 삽입, 해롭지 않음) 가능.

--start-index/--end-index로 범위를 좁혀서 나눠 돌릴 수 있다(전체를 한 번에 돌리면 무료 티어
일일 한도를 넘거나 오래 걸릴 수 있음 — HANDOFF.md 참고).

사용법:
    python scripts/generate_grammar_curriculum.py --start-index 0 --end-index 10
"""

import argparse
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.content.generator import generate_grammar_questions_for_part  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.grammar.curriculum_data import CEFR_TO_LEGACY_LEVEL  # noqa: E402
from app.repo import content as content_repo  # noqa: E402
from app.repo import grammar as grammar_repo  # noqa: E402


async def main(start_index: int, end_index: int | None, learning_mode: str, force: bool) -> None:
    await init_db_pool()
    try:
        parts = await grammar_repo.get_all_parts_ordered()
        if not parts:
            print("grammar_parts가 비어있습니다. 먼저 scripts/seed_grammar_curriculum.py를 실행하세요.")
            return

        previous_part_label: str | None = None
        for part in parts:
            if part["global_order_index"] < start_index:
                previous_part_label = part["name"]
                continue
            if end_index is not None and part["global_order_index"] > end_index:
                break

            legacy_level = CEFR_TO_LEGACY_LEVEL[part["cefr_level"]]
            existing = await grammar_repo.count_questions_for_part(part["id"])
            if existing >= part["target_question_count"] and not force:
                print(
                    f"[{part['global_order_index']}][{part['cefr_level']}] {part['topic_name']} / {part['name']}"
                    f" — 이미 {existing}개 있음, 건너뜀"
                )
                previous_part_label = part["name"]
                continue

            try:
                questions = await generate_grammar_questions_for_part(
                    part["cefr_level"],
                    legacy_level,
                    part["topic_name"],
                    part["name"],
                    part["description"] or "",
                    part["target_question_count"],
                    learning_mode=learning_mode,
                    previous_part_label=previous_part_label,
                )
            except Exception as exc:
                print(f"[{part['global_order_index']}] '{part['name']}' 생성 실패, 건너뜀: {exc}")
                previous_part_label = part["name"]
                continue

            inserted = await content_repo.insert_grammar_questions(
                legacy_level, questions, learning_mode=learning_mode, part_id=part["id"]
            )
            inserted_vocab = await content_repo.insert_key_vocabulary_from_grammar(
                legacy_level, questions, learning_mode=learning_mode
            )
            focus_tag = " [EXAM_FOCUS]" if part["is_exam_focus"] else ""
            print(
                f"[{part['global_order_index']}][{part['cefr_level']}]{focus_tag} {part['topic_name']} / {part['name']}"
                f" generated={len(questions)} inserted={inserted} vocab={inserted_vocab}"
            )
            previous_part_label = part["name"]

        print("grammar totals:", await content_repo.count_grammar_questions_by_level())
    finally:
        await close_db_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-index", type=int, default=0, help="global_order_index 시작(포함)")
    parser.add_argument("--end-index", type=int, default=None, help="global_order_index 끝(포함), 생략 시 끝까지")
    parser.add_argument("--mode", choices=["GENERAL", "CHILD_BRIDGE"], default="GENERAL")
    parser.add_argument("--force", action="store_true", help="이미 목표 수만큼 있어도 추가 생성")
    args = parser.parse_args()
    asyncio.run(main(args.start_index, args.end_index, args.mode, args.force))
