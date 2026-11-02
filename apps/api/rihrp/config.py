"""アプリ設定。秘密は環境変数からのみ読む（既定値に秘密を埋めない）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RIHRP_",
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    database_url: str = "postgresql+psycopg://rihrp_app:CHANGE_ME@127.0.0.1:5432/rihrp"
    cookie_secure: bool = False
    session_ttl_minutes: int = 480
    seed_demo: bool = True
    login_rate_limit: int = 10
    trust_cf_access: bool = False
    audit_retention_days: int = 365
    web_dist: Path = REPO_ROOT / "apps/web/dist"

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_test(self) -> bool:
        return self.env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
