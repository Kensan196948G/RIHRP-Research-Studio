"""リクエスト相関 ID。監査ログの追跡に使う。"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("rihrp_request_id", default="")
