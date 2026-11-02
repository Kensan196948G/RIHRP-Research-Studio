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
    # Cloudflare Access の ID をアプリのセッションへ引き継ぐ（自動ログイン）。
    # 有効時は Cf-Access-Jwt-Assertion の署名・iss・aud・期限を検証する（cf_access.py）。
    trust_cf_access: bool = False
    cf_access_team_domain: str = ""
    cf_access_aud: str = ""
    # 自動ログインを許可する email（カンマ区切り）。空なら全拒否（fail closed）。
    cf_access_allowed_emails: str = ""
    # ループバック接続だけを許可する追加防御。uvicorn は既定で proxy headers を信頼するため
    # Tunnel 経由の request.client.host は実 IP になる（--no-proxy-headers のときだけ有効）。
    cf_access_loopback_only: bool = False
    # 未登録ユーザーの自動作成（既定は無効）。
    cf_access_provision: bool = False
    cf_access_default_role: str = "viewer"
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
