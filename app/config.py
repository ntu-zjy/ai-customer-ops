from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI客户经营系统"
    database_url: str = "postgresql+psycopg://event_crm:event_crm@localhost:5432/event_crm"

    hermes_home: Path = Path("/opt/event-crm/hermes-home")
    hermes_state_db: Path | None = None
    hermes_platform: str = "wecom"
    hermes_bot_id: str = "wecom-bot"
    hermes_source_filter: str = "wecom"
    hermes_api_base_url: str = "http://127.0.0.1:8642/v1"
    hermes_api_key: str = ""
    hermes_model_name: str = "hermes-agent"

    sync_batch_size: int = Field(default=500, ge=1, le=5000)
    analyze_due_limit: int = Field(default=50, ge=1, le=500)
    admin_page_size: int = Field(default=100, ge=10, le=500)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def resolved_hermes_state_db(self) -> Path:
        return self.hermes_state_db or self.hermes_home / "state.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
