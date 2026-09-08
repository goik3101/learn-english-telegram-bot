"""회화 사전 단어학습: app/conversation/topics.py의 고정 주제 목록을 따라, 주제마다 핵심 단어를
미리 생성해 콘텐츠뱅크에 채운다 (1회성 스크립트, generate_grammar_curriculum.py와 동일한 목적).

라우터(app/handlers/router.py)에도 "없으면 최초 1회 생성 후 캐싱" 폴백이 있어 이 스크립트 없이도
동작하지만, 실사용 전에 미리 돌려두면 사용자가 첫 회화 시작 시 생성 대기 시간 없이 바로 단어카드를
받는다.

사용법:
    python scripts/generate_conversation_topic_words.py --count-per-topic 8
"""

import argparse
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.content.generator import generate_topic_words  # noqa: E402
from app.conversation.topics import CONVERSATION_TOPICS  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.repo import content as content_repo  # noqa: E402

LEVELS = ["beginner", "intermediate", "advanced"]


async def main(count_per_topic: int, learning_mode: str) -> None:
    await init_db_pool()
    try:
        for level in LEVELS:
            for topic in CONVERSATION_TOPICS:
                try:
                    words = await generate_topic_words(level, topic, count_per_topic, learning_mode=learning_mode)
                except Exception as exc:
                    print(f"[{level}:{learning_mode}] '{topic}' 생성 실패, 건너뜀: {exc}")
                    continue

                await content_repo.insert_words(level, words, learning_mode=learning_mode)
                word_ids = await content_repo.get_word_ids([w["word"] for w in words], learning_mode=learning_mode)
                await content_repo.insert_conversation_topic_words(
                    topic, level, learning_mode, list(word_ids.values())
                )
                print(f"[{level}:{learning_mode}] '{topic}' generated={len(words)} linked={len(word_ids)}")

        print("word totals:", await content_repo.count_words_by_level())
    finally:
        await close_db_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count-per-topic", type=int, default=8)
    parser.add_argument("--mode", choices=["GENERAL", "CHILD_BRIDGE"], default="GENERAL")
    args = parser.parse_args()
    asyncio.run(main(args.count_per_topic, args.mode))
