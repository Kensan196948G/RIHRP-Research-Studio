"""改竄・引用消失の経路を、実データで検証する。"""
from __future__ import annotations

import os
import hashlib, json, sys
from pathlib import Path
import httpx, psycopg

BASE = "http://127.0.0.1:18120"
DSN = "postgresql://rihrp_app:rihrp_dev_password@127.0.0.1:5432/rihrp_test_ai_20261112"
ROOT = Path(__file__).resolve().parent

def sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()

def main() -> int:
    results = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    pid = results["project_id"]
    client = httpx.Client(base_url=BASE, timeout=30.0)
    r = client.post("/api/auth/login", json={"email": "editor@rihrp.local", "password": os.environ["RIHRP_AI_TEST_PASSWORD"]})
    r.raise_for_status()
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]

    out = []
    texts = {
        "T1": "定点観測の記録。2024年の観測値は 42.5% であり、対象期間は 2019年から 2023年 までである。",
        "T2": "別の観測記録。平均値は 18.2℃ で、標本数は 240 件である。",
    }
    ids = {}
    for key, text in texts.items():
        resp = client.post(f"/api/projects/{pid}/sources", json={"title": f"改竄試験 {key}", "kind": "text", "origin": "", "content": text})
        resp.raise_for_status()
        ids[key] = resp.json()["source"]["id"]

    claims = [
        ("T1", "2024年の観測値は42.5%である。", "2024年の観測値は 42.5% であり"),
        ("T2", "標本数は240件、平均値は18.2℃である。", "平均値は 18.2℃ で、標本数は 240 件である。"),
    ]
    for key, text, quote in claims:
        cr = client.post(f"/api/projects/{pid}/claims", json={"text": text})
        cr.raise_for_status()
        cid = cr.json()["claim"]["id"]
        ev = client.post(f"/api/claims/{cid}/evidence", json={"source_id": ids[key], "quote": quote})
        assert ev.status_code == 201, ev.text
        v1 = client.post(f"/api/claims/{cid}/verify").json()["result"]
        out.append({"id": key, "stage": "before_tamper", "verdict": v1["verdict"], "reasons": v1["reasons"]})

    # T1: 本文だけ改竄（sha は元のまま）→ evidence_tampered
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("UPDATE sources SET content = %s WHERE id = %s", ("改竄されたテキスト。数値は 0.0% である。", ids["T1"]))
    # T2: 本文と sha を同時に更新（善意の編集で引用が消えた状況）→ quote_not_found
    new_text = "更新後の記録。平均値は 20.1℃ で、標本数は 260 件である。"
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("UPDATE sources SET content = %s, content_sha256 = %s WHERE id = %s", (new_text, sha(new_text), ids["T2"]))

    for key, text, _ in claims:
        # claim id を引き直す
        listing = client.get(f"/api/projects/{pid}/claims").json()["claims"]
        cid = next(c["id"] for c in listing if c["text"] == text)
        v = client.post(f"/api/claims/{cid}/verify").json()["result"]
        out.append({"id": key, "stage": "after_tamper", "verdict": v["verdict"], "reasons": v["reasons"]})

    (ROOT / "tamper_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in out:
        print(row)
    return 0

if __name__ == "__main__":
    sys.exit(main())
