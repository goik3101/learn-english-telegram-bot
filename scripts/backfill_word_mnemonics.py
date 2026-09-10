"""단어 암기 효율 개선(사용자 피드백, 기억연구 근거): 2단계 키워드 연상법(mnemonic)/
example_sentences(복습회차별 다른 예문)/emoji(이중부호화) 도입 이전에 만들어진 기존 콘텐츠뱅크
단어에 소급 부여한다 (1회성 스크립트). mnemonic은 있지만 emoji가 없는 단어(구버전 스타일)도
대상에 포함해 최신 스타일로 다시 채운다.

사용법:
    python scripts/backfill_word_mnemonics.py
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.append(".")

from app.content.generator import estimate_mnemonics_and_examples  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.repo import content as content_repo  # noqa: E402

BATCH_SIZE = 15  # mnemonic+예문까지 요청하면 응답이 커서 frequency_rank 백필보다 배치를 작게 잡음


async def main() -> None:
    await init_db_pool()
    try:
        rows = await content_repo.get_words_missing_mnemonic()
        print(f"mnemonic/emoji 없는 단어 {len(rows)}개")

        total_updated = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            try:
                estimates = await estimate_mnemonics_and_examples(
                    [{"word": r["word"], "meaning_ko": r["meaning_ko"]} for r in batch]
                )
            except Exception as exc:
                print(f"batch {i // BATCH_SIZE + 1}: 생성 실패, 건너뜀 ({exc})")
                continue

            by_word = {e["word"]: e for e in estimates}
            updated = 0
            for row in batch:
                estimate = by_word.get(row["word"])
                if estimate is not None:
                    await content_repo.update_mnemonic_and_examples(
                        row["id"], estimate["mnemonic"], estimate["example_sentences"], estimate.get("emoji")
                    )
                    updated += 1
            total_updated += updated
            print(f"batch {i // BATCH_SIZE + 1}: {updated}/{len(batch)} 업데이트")

        print(f"총 {total_updated}/{len(rows)}개 단어에 mnemonic/example_sentences/emoji 부여")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
