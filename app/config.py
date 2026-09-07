from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: Optional[str] = None
    admin_telegram_id: Optional[str] = None
    database_url: Optional[str] = None
    gemini_api_key: Optional[str] = None
    telegram_webhook_secret: Optional[str] = None
    port: int = 8000


settings = Settings()
