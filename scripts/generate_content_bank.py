"""M4/M8: 단어/문법/해석 콘텐츠뱅크 사전생성 (섹션16: 콘텐츠뱅크는 최초 1회만 AI 호출, 이후 캐싱 재사용).

사용법:
    python scripts/generate_content_bank.py --words-per-level 15 --grammar-per-level 10 --reading-per-level 5
"""

import argparse
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.append(".")

from app.content.generator import generate_grammar_questions, generate_reading_passages, generate_words  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.repo import content as content_repo  # noqa: E402

LEVELS = ["beginner", "intermediate", "advanced"]


async def main(words_per_level: int, grammar_per_level: int, reading_per_level: int) -> None:
    await init_db_pool()
    try:
        for level in LEVELS:
            words = await generate_words(level, words_per_level)
            inserted = await content_repo.insert_words(level, words)
            print(f"[words:{level}] generated={len(words)} inserted={inserted}")

            questions = await generate_grammar_questions(level, grammar_per_level)
            inserted_q = await content_repo.insert_grammar_questions(level, questions)
            print(f"[grammar:{level}] generated={len(questions)} inserted={inserted_q}")

            inserted_vocab = await content_repo.insert_key_vocabulary_from_grammar(level, questions)
            print(f"[grammar-vocab:{level}] inserted={inserted_vocab}")

            passages = await generate_reading_passages(level, reading_per_level)
            inserted_r = await content_repo.insert_reading_passages(level, passages)
            print(f"[reading:{level}] generated={len(passages)} inserted={inserted_r}")

        print("word totals:", await content_repo.count_words_by_level())
        print("grammar totals:", await content_repo.count_grammar_questions_by_level())
        print("reading totals:", await content_repo.count_reading_passages_by_level())
    finally:
        await close_db_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--words-per-level", type=int, default=15)
    parser.add_argument("--grammar-per-level", type=int, default=10)
    parser.add_argument("--reading-per-level", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(main(args.words_per_level, args.grammar_per_level, args.reading_per_level))
