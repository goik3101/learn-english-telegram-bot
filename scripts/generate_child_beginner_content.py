"""M15: CHILD_BEGINNER Stage2(기초단어)~Stage5(짧은지문) 콘텐츠뱅크 사전생성 (섹션16, 1회성).

Stage0(알파벳)/Stage1(파닉스)은 app/child_beginner/curriculum.py에 고정 데이터로 이미 있어 생성 불필요.

사용법:
    python scripts/generate_child_beginner_content.py --count-per-stage 10
"""

import argparse
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.append(".")

from app.child_beginner.generator import generate_content  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.repo import child_beginner as child_beginner_repo  # noqa: E402

STAGES = [2, 3, 4, 5]


async def main(count_per_stage: int) -> None:
    await init_db_pool()
    try:
        for stage in STAGES:
            items = await generate_content(stage, count_per_stage)
            inserted = await child_beginner_repo.insert_content(stage, items)
            print(f"[stage{stage}] generated={len(items)} inserted={inserted}")

        print("totals:", await child_beginner_repo.count_by_stage())
    finally:
        await close_db_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count-per-stage", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(main(args.count_per_stage))
