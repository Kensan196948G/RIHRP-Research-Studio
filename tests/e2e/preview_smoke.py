#!/usr/bin/env python3
"""配備済みプレビュー（またはローカル）に対するスモークテスト。

秘密は環境変数で渡す（リポジトリに書かない）。

    RIHRP_BASE_URL=http://127.0.0.1:18110 \
    RIHRP_SMOKE_EMAIL=editor@example.local \
    RIHRP_SMOKE_PASSWORD='***' \
    .venv/bin/python tests/e2e/preview_smoke.py

終了コード: 0=成功 / 1=失敗 / 2=環境変数不足でスキップ
"""

from __future__ import annotations

import os
import sys

import httpx

BASE_URL = os.environ.get("RIHRP_BASE_URL", "http://127.0.0.1:18110")
EMAIL = os.environ.get("RIHRP_SMOKE_EMAIL", "")
PASSWORD = os.environ.get("RIHRP_SMOKE_PASSWORD", "")


def fail(message: str) -> None:
    print(f"NG: {message}")
    raise SystemExit(1)


def main() -> int:
    if not EMAIL or not PASSWORD:
        print("SKIP: RIHRP_SMOKE_EMAIL / RIHRP_SMOKE_PASSWORD が未設定です")
        return 2

    client = httpx.Client(base_url=BASE_URL, timeout=15)

    health = client.get("/healthz")
    if health.status_code != 200 or health.json().get("status") != "ok":
        fail(f"/healthz: {health.status_code} {health.text[:120]}")
    print("OK /healthz")

    ready = client.get("/readyz")
    if ready.status_code != 200 or ready.json().get("status") != "ready":
        fail(f"/readyz: {ready.status_code} {ready.text[:120]}")
    print(f"OK /readyz (migration={ready.json().get('migration')})")

    login = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if login.status_code != 200:
        fail(f"login: {login.status_code} {login.text[:120]}")
    user = login.json()["user"]
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    print(f"OK login ({user['role']})")

    csrf_probe = client.post(
        "/api/projects", json={"title": "smoke", "summary": ""}, headers={"X-CSRF-Token": "invalid"}
    )
    if csrf_probe.status_code != 403:
        fail(f"CSRF probe: expected 403, got {csrf_probe.status_code}")
    print("OK CSRF rejection")

    projects = client.get("/api/projects").json()["projects"]
    if not projects:
        fail("テーマが 0 件です（seed またはデータ投入を確認してください）")
    project = projects[0]
    print(f"OK projects ({len(projects)}件): {project['title']}")

    sources = client.get(f"/api/projects/{project['id']}/sources").json()["sources"]
    claims = client.get(f"/api/projects/{project['id']}/claims").json()["claims"]
    reports = client.get(f"/api/projects/{project['id']}/reports").json()["reports"]
    if not claims:
        fail("主張が 0 件です")
    print(f"OK project data: sources={len(sources)} claims={len(claims)} reports={len(reports)}")

    if any(source.get("tampered") for source in sources):
        fail("改竄された出典があります")
    print("OK source digests")

    if reports:
        export = client.get(f"/api/reports/{reports[0]['id']}/export")
        if export.status_code != 200 or "[検証済]" not in export.text:
            fail(f"export: {export.status_code} / markers missing")
        print("OK report export")

    if user["role"] in {"reviewer", "admin"}:
        audit = client.get("/api/audit?limit=20")
        if audit.status_code != 200 or not audit.json()["events"]:
            fail("監査ログが取得できません")
        print("OK audit")

    print("preview smoke: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
