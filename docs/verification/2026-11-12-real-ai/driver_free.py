"""自然な引用／厳密引用の実AI出力を処理し、レポート承認ゲートまで実測する。"""
from __future__ import annotations

import os
import json, re, sys
from pathlib import Path
import httpx

BASE = "http://127.0.0.1:18120"
ROOT = Path(__file__).resolve().parent
WS = re.compile(r"\s+")
def norm(t): return WS.sub(" ", t).strip()

def login(email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=30.0)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c

def main() -> int:
    base = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    pid, sid = base["project_id"], base["source_ids"]
    src_text = {k: (ROOT / f"sources/{v}").read_text(encoding="utf-8") for k, v in {"JMA":"jma.txt","STAT":"stat.txt","ARXIV":"arxiv.txt"}.items()}
    editor = login("editor@rihrp.local", os.environ["RIHRP_AI_TEST_PASSWORD"])
    free = json.loads((ROOT / "claims_free.json").read_text(encoding="utf-8"))

    out = {"model": free["model"], "groups": []}
    created: dict[str, str] = {}
    for group in free["groups"]:
        rows = []
        for item in group["items"]:
            cr = editor.post(f"/api/projects/{pid}/claims", json={"text": item["claim"]})
            cr.raise_for_status()
            cid = cr.json()["claim"]["id"]
            created[item["id"]] = cid
            q = item["quote"]
            q_in = bool(q) and norm(q) in norm(src_text[item["source"]])
            ev = editor.post(f"/api/claims/{cid}/evidence", json={"source_id": sid[item["source"]], "quote": q})
            status = "registered" if ev.status_code == 201 else "rejected"
            v = editor.post(f"/api/claims/{cid}/verify").json()["result"]
            rows.append({"id": item["id"], "source": item["source"], "quote_verbatim": q_in,
                         "evidence": status, "http": ev.status_code, "verdict": v["verdict"],
                         "reasons": v["reasons"], "claim": item["claim"], "quote": q})
            print(f'{item["id"]:9} quote_verbatim={q_in!s:5} evidence={status:10} verdict={v["verdict"]}')
        accepted = sum(1 for r in rows if r["evidence"] == "registered")
        out["groups"].append({"id": group["id"], "style": group["instruction_style"],
                              "total": len(rows), "accepted": accepted, "rows": rows})

    # --- レポート承認ゲート ---
    listing = {c["text"]: c["id"] for c in editor.get(f"/api/projects/{pid}/claims").json()["claims"]}
    part_a = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))["results"]
    def cid_of(text):
        return listing[text]
    blocked_group = [r for r in part_a if r["expected"] == "fake_quote"][:4]
    unver = [r for r in part_a if r["expected"] == "wrong_number"][:4]
    ver = [r for r in part_a if r["expected"] == "verified"][:4]
    noanchor = [r for r in part_a if r["expected"] == "no_anchor"][:4]

    def make_report(title, claim_texts):
        rep = editor.post(f"/api/projects/{pid}/reports", json={"title": title}).json()
        rid = rep["id"]
        content = {"sections": [{"heading": "実AI検証", "paragraphs": [
            {"text": f"段落{i+1}: 実AI生成の主張を参照する。", "claimIds": [cid_of(t)]} for i, t in enumerate(claim_texts)
        ]}]}
        upd = editor.put(f"/api/reports/{rid}", json={"content": content, "note": "real-ai"})
        upd.raise_for_status()
        editor.post(f"/api/reports/{rid}/verify").raise_for_status()
        return rid

    r1_texts = [r["claim"] for r in (ver + unver + blocked_group + noanchor)]
    r1 = make_report("R1 実AI出力（捏造引用4件を含む）", r1_texts)
    editor.post(f"/api/reports/{r1}/submit").raise_for_status()
    reviewer = login("reviewer@rihrp.local", os.environ["RIHRP_AI_TEST_PASSWORD"])
    a1 = reviewer.post(f"/api/reports/{r1}/review", json={"decision": "approved", "comment": ""})
    gate = {"R1": {"claims": len(r1_texts), "approve_http": a1.status_code,
                   "status": a1.json().get("report", {}).get("status") if a1.status_code == 200 else None,
                   "detail": a1.json().get("detail") if a1.status_code != 200 else None}}

    tamper = json.loads((ROOT / "tamper_results.json").read_text(encoding="utf-8"))
    t1_text = next(t for t in listing if "2024年の観測値は42.5%" in t)
    r2_texts = r1_texts + [t1_text]
    r2 = make_report("R2 改竄で contradicted を含む", r2_texts[:8] + [t1_text])
    editor.post(f"/api/reports/{r2}/submit").raise_for_status()
    a2 = reviewer.post(f"/api/reports/{r2}/review", json={"decision": "approved", "comment": ""})
    gate["R2"] = {"claims": 9, "approve_http": a2.status_code,
                  "status": a2.json().get("report", {}).get("status") if a2.status_code == 200 else None,
                  "detail": a2.json().get("detail") if a2.status_code != 200 else None}
    out["gate"] = gate
    out["claim_ids"] = created
    (ROOT / "free_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("GATE", json.dumps(gate, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
