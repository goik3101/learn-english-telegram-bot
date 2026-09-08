from app.db import get_pool


async def log_call(provider: str) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("insert into ai_usage_log (provider) values (%s)", (provider,))


async def get_today_counts() -> dict[str, int]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "select provider, count(*) as n from ai_usage_log where called_at::date = current_date group by provider"
            )
            rows = await cur.fetchall()
            return {row["provider"]: row["n"] for row in rows}


async def get_month_counts() -> dict[str, int]:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                select provider, count(*) as n from ai_usage_log
                where date_trunc('month', called_at) = date_trunc('month', current_date)
                group by provider
                """
            )
            rows = await cur.fetchall()
            return {row["provider"]: row["n"] for row in rows}
