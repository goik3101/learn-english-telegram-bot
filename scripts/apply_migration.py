"""psql이 없는 로컬 환경에서 마이그레이션 SQL 파일을 실제 DB에 적용하는 1회성 스크립트."""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.append(".")

from app.db import close_db_pool, get_pool, init_db_pool  # noqa: E402


async def main(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        sql = f.read()

    await init_db_pool()
    try:
        pool = get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
        print(f"applied: {path}")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
