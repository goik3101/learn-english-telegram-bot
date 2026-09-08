"""개인 맞춤 난이도 시스템(단어): 기존 콘텐츠뱅크 단어 중 frequency_rank가 없는 단어에
실제 사용빈도 순위를 소급 부여한다 (1회성 스크립트).

사용법:
    python scripts/backfill_word_frequency_rank.py
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.content.generator import estimate_frequency_ranks  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.repo import content as content_repo  # noqa: E402

BATCH_SIZE = 30


async def main() -> None:
    await init_db_pool()
    try:
        rows = await content_repo.get_words_missing_frequency_rank()
        print(f"frequency_rank 없는 단어 {len(rows)}개")

        total_updated = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            words = [r["word"] for r in batch]
            try:
                estimates = await estimate_frequency_ranks(words)
            except Exception:
                print(f"batch {i // BATCH_SIZE + 1}: 추정 실패, 건너뜀")
                continue

            rank_by_word = {e["word"]: e["frequency_rank"] for e in estimates}
            updated = 0
            for row in batch:
                rank = rank_by_word.get(row["word"])
                if rank is not None:
                    await content_repo.update_frequency_rank(row["id"], rank)
                    updated += 1
            total_updated += updated
            print(f"batch {i // BATCH_SIZE + 1}: {updated}/{len(batch)} 업데이트")

        print(f"총 {total_updated}/{len(rows)}개 단어에 frequency_rank 부여")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
