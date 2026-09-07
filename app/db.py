import logging
from typing import Optional

from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

from app.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[AsyncConnectionPool] = None


async def init_db_pool() -> None:
    global _pool
    if not settings.database_url:
        return
    _pool = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    await _pool.open(wait=True, timeout=10)


async def close_db_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool is not initialized (DATABASE_URL missing or connection failed)")
    return _pool


def db_available() -> bool:
    return _pool is not None
