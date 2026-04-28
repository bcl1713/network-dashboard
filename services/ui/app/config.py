from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="UI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    engine_base_url: str = "http://engine:8000"
    engine_api_token: str = Field(default="dev-token-change-me", alias="UI_ENGINE_API_TOKEN")
    log_level: str = "INFO"
    page_size: int = 50
    request_timeout_s: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
