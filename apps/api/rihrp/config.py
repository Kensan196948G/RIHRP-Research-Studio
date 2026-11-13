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
    # AI 下書き（ADR-0006）。鍵が空なら機能だけ 503 で無効化する（fail closed）。
    # openai（OpenAI 互換 /chat/completions）または anthropic（/messages）。
    llm_provider: str = "openai"
    llm_base_url: str = ""  # 空ならプロバイダ既定（anthropic は https://api.anthropic.com/v1）
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout_seconds: float = 30.0
    llm_max_claims: int = 8
    llm_max_source_chars: int = 12000
    llm_rate_limit: int = 5
    # カンマ区切りのプロジェクトID。空なら制限なし（既定）。限定パイロット用。
    llm_allowed_projects: str = ""
    web_dist: Path = REPO_ROOT / "apps/web/dist"

    @property
    def llm_base(self) -> str:
        if self.llm_base_url:
            return self.llm_base_url.rstrip("/")
        if self.llm_provider == "anthropic":
            return "https://api.anthropic.com/v1"
        return "https://api.openai.com/v1"

    @property
    def llm_configured(self) -> bool:
        return bool(
            self.llm_model and self.llm_api_key and self.llm_provider in {"openai", "anthropic"}
        )

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_test(self) -> bool:
        return self.env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
