import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from app.commands import register_bot_commands
from app.config import settings
from app.db import close_db_pool, init_db_pool
from app.handlers.router import handle_update

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.database_url:
        try:
            await init_db_pool()
            logger.info("DB pool initialized")
        except Exception:
            logger.exception("Failed to initialize DB pool — DB features disabled")
    else:
        logger.warning("DATABASE_URL not set — DB features disabled")

    if not settings.bot_token:
        logger.warning("BOT_TOKEN not set — Telegram sending disabled")
    else:
        try:
            await register_bot_commands()
        except Exception:
            logger.exception("Failed to register bot commands")
    if not settings.admin_telegram_id:
        logger.warning("ADMIN_TELEGRAM_ID not set — admin auto-registration disabled")
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — AI features disabled")

    yield

    await close_db_pool()


app = FastAPI(title="English Learning Bot", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    if settings.telegram_webhook_secret:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header != settings.telegram_webhook_secret:
            raise HTTPException(status_code=401, detail="invalid secret token")

    update = await request.json()
    await handle_update(update)
    return {"ok": True}
