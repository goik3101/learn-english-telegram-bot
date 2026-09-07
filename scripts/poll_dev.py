"""로컬 개발용: webhook/ngrok 없이 getUpdates(long polling)로 실제 텔레그램과 대화 테스트.

주의: webhook이 등록되어 있으면 getUpdates가 실패한다. 배포 시에는 이 스크립트 대신
webhook(app/main.py)을 사용한다. Windows에서 psycopg 비동기 모드를 쓰기 위해
run_local.py와 동일하게 이벤트루프 정책을 최상단에서 바꾼다.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Windows 콘솔(cp949)이 이모지 등 일부 유니코드를 출력하지 못해 죽는 것을 방지.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx

sys.path.append(".")

from app.commands import register_bot_commands  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import close_db_pool, init_db_pool  # noqa: E402
from app.handlers.router import handle_update  # noqa: E402

TELEGRAM_API_BASE = "https://api.telegram.org"


async def main() -> None:
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN이 설정되어 있지 않습니다.")

    await init_db_pool()
    await register_bot_commands()
    print("DB pool ready. Polling for Telegram updates... (Ctrl+C to stop)")

    offset = 0
    try:
        async with httpx.AsyncClient(timeout=35) as client:
            while True:
                resp = await client.get(
                    f"{TELEGRAM_API_BASE}/bot{settings.bot_token}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                )
                data = resp.json()
                if not data.get("ok"):
                    print("getUpdates error:", data)
                    await asyncio.sleep(2)
                    continue

                for update in data["result"]:
                    offset = update["update_id"] + 1
                    print("update:", update)
                    try:
                        await handle_update(update)
                    except Exception:
                        import traceback

                        traceback.print_exc()
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
