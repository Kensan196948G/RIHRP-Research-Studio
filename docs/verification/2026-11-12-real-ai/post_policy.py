"""ADR-0003 改訂後の承認ゲートを、実 AI 出力の主張で再確認する。"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:18120"
ROOT = Path(__file__).resolve().parent
PASSWORD = os.environ["RIHRP_AI_TEST_PASSWORD"]


def login(email: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE, timeout=30.0)
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


def main() -> int:
    import json

    base = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    pid = base["project_id"]
    editor = login("editor@rihrp.local")
    reviewer = login("reviewer@rihrp.local")
    listing = {c["text"]: c["id"] for c in editor.get(f"/api/projects/{pid}/claims").json()["claims"]}
    fake = [r["claim"] for r in base["results"] if r["expected"] == "fake_quote"][:4]
    good = [r["claim"] for r in base["results"] if r["expected"] == "verified"][:2]
    texts = good + fake

    def build(title: str) -> str:
        created = editor.post(f"/api/projects/{pid}/reports", json={"title": title}).raise_for_status().json()["report"]
        content = {
            "sections": [
                {
                    "heading": "改訂後の再試験",
                    "paragraphs": [
                        {"text": f"段落{i + 1}: 実 AI 生成の主張を参照する。", "claimIds": [listing[t]]}
                        for i, t in enumerate(texts)
                    ],
                }
            ]
        }
        editor.put(
            f"/api/reports/{created['id']}",
            json={"content": content, "expected_version": created["version"], "note": "post-policy"},
        ).raise_for_status()
        editor.post(f"/api/reports/{created['id']}/verify").raise_for_status()
        return created["id"]

    out = {}
    r3 = build("R3 改訂後・AI支援として提出")
    editor.post(f"/api/reports/{r3}/submit", json={"ai_assisted": True}).raise_for_status()
    a3 = reviewer.post(f"/api/reports/{r3}/review", json={"decision": "approved", "comment": ""})
    out["R3_ai_assisted"] = {
        "http": a3.status_code,
        "code": (a3.json().get("error") or {}).get("code") if a3.status_code != 200 else None,
        "details": (a3.json().get("error") or {}).get("details") if a3.status_code != 200 else None,
    }

    r4 = build("R4 改訂後・通常提出（対照）")
    editor.post(f"/api/reports/{r4}/submit").raise_for_status()
    a4 = reviewer.post(f"/api/reports/{r4}/review", json={"decision": "approved", "comment": ""})
    out["R4_default"] = {"http": a4.status_code, "status": a4.json().get("report", {}).get("status") if a4.status_code == 200 else None}

    (ROOT / "post_policy_recheck.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
