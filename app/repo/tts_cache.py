import hashlib
from typing import Optional

from app.db import get_pool


def cache_key(text: str, language_code: str, voice_name: str) -> str:
    raw = f"{language_code}:{voice_name}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def get_cached_audio(key: str) -> Optional[bytes]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("select audio_data from tts_cache where cache_key = %s", (key,))
            row = await cur.fetchone()
            return bytes(row["audio_data"]) if row else None


async def save_cached_audio(key: str, audio_data: bytes) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "insert into tts_cache (cache_key, audio_data) values (%s, %s) on conflict (cache_key) do nothing",
                (key, audio_data),
            )
