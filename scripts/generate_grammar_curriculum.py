"""개인 맞춤 난이도 시스템(문법): app/grammar/curriculum.py에 정의된 레벨별 고정 주제 순서를
따라, 주제마다 문제를 생성해 콘텐츠뱅크에 채운다 (1회성 스크립트).

기존 generate_content_bank.py는 레벨당 무작위 여러 주제를 한꺼번에 생성했지만, 이 스크립트는
`/문법학습`의 새 주제-게이팅 진행(주제별 최소 10문제, 정답률 80% 이상 시 다음 주제)을 지원하기
위해 주제 하나당 정확히 --count-per-topic개씩 생성한다.

사용법:
    python scripts/generate_grammar_curriculum.py --count-per-topic 10
"""

import argparse
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.content.generator import generate_grammar_questions_for_topic  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.grammar.curriculum import GRAMMAR_CURRICULUM  # noqa: E402
from app.repo import content as content_repo  # noqa: E402


async def main(count_per_topic: int, learning_mode: str) -> None:
    await init_db_pool()
    try:
        previous_topic = None
        for topic, level in GRAMMAR_CURRICULUM:
            try:
                questions = await generate_grammar_questions_for_topic(
                    level, topic, count_per_topic, learning_mode=learning_mode, previous_topic=previous_topic
                )
            except Exception as exc:
                print(f"[{level}:{learning_mode}] '{topic}' 생성 실패, 건너뜀: {exc}")
                previous_topic = topic  # 커리큘럼상 순서는 생성 성공 여부와 무관
                continue

            inserted = await content_repo.insert_grammar_questions(level, questions, learning_mode=learning_mode)
            inserted_vocab = await content_repo.insert_key_vocabulary_from_grammar(
                level, questions, learning_mode=learning_mode
            )
            print(f"[{level}:{learning_mode}] '{topic}' generated={len(questions)} inserted={inserted} vocab={inserted_vocab}")
            previous_topic = topic

        print("grammar totals:", await content_repo.count_grammar_questions_by_level())
    finally:
        await close_db_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count-per-topic", type=int, default=10)
    parser.add_argument("--mode", choices=["GENERAL", "CHILD_BRIDGE"], default="GENERAL")
    args = parser.parse_args()
    asyncio.run(main(args.count_per_topic, args.mode))
