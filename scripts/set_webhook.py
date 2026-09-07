"""배포된 서버 URL로 Telegram webhook을 등록하는 1회성 스크립트.

사용법:
    python scripts/set_webhook.py https://your-app.up.railway.app
"""

import asyncio
import sys

import httpx

sys.path.append(".")

from app.config import settings  # noqa: E402


async def main(base_url: str) -> None:
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN이 .env에 설정되어 있지 않습니다.")

    webhook_url = base_url.rstrip("/") + "/telegram/webhook"
    payload = {"url": webhook_url}
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret

    api_url = f"https://api.telegram.org/bot{settings.bot_token}/setWebhook"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(api_url, json=payload)
        print(response.status_code, response.text)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("사용법: python scripts/set_webhook.py <base_url>")
    asyncio.run(main(sys.argv[1]))
