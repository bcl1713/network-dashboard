from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ENGINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Path("/data/filters.db")
    ring_size: int = 750
    allow_sid_only: bool = False
    log_level: str = "INFO"

    api_token: str = Field(default="dev-token-change-me", alias="ENGINE_API_TOKEN")

    loki_url: str = "http://loki:3100"
    loki_tenant: str = "filtered"
    loki_push_timeout_s: float = 5.0
    loki_retry_max: int = 5

    audit_ttl_days: int = 30
    audit_prune_interval_s: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
