from app.db import get_pool


async def save_result(
    user_id: int,
    word_correct: int,
    word_total: int,
    grammar_correct: int,
    grammar_total: int,
    level: str,
) -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into placement_test_results
                    (user_id, word_correct, word_total, grammar_correct, grammar_total, level)
                values (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, word_correct, word_total, grammar_correct, grammar_total, level),
            )
