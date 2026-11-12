"""実AI由来の主張でレポートを組み、承認ゲートの実挙動を実測する。"""
from __future__ import annotations

import os
import json, re, sys
from pathlib import Path
import httpx

BASE = "http://127.0.0.1:18120"
ROOT = Path(__file__).resolve().parent
WS = re.compile(r"\s+")
def norm(t): return WS.sub(" ", t).strip()

def login(email, password):
    c = httpx.Client(base_url=BASE, timeout=30.0)
    r = c.post("/api/auth/login", json={"email": email, "password": password}); r.raise_for_status()
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c

def main() -> int:
    base = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    pid = base["project_id"]
    src = {"JMA":"jma.txt","STAT":"stat.txt","ARXIV":"arxiv.txt"}
    texts = {k: (ROOT/"sources"/v).read_text(encoding="utf-8") for k,v in src.items()}
    editor = login("editor@rihrp.local", os.environ["RIHRP_AI_TEST_PASSWORD"])
    claims = editor.get(f"/api/projects/{pid}/claims").json()["claims"]
    by_text = {c["text"]: c for c in claims}

    free = json.loads((ROOT / "claims_free.json").read_text(encoding="utf-8"))
    out = {"model": free["model"], "groups": []}
    for g in free["groups"]:
        rows = []
        for it in g["items"]:
            c = by_text[it["claim"]]
            rows.append({"id": it["id"], "source": it["source"],
                         "quote_verbatim": bool(it["quote"]) and norm(it["quote"]) in norm(texts[it["source"]]),
                         "evidence_accepted": c["evidence_count"] > 0,
                         "verdict": c["last_verdict"], "claim": it["claim"], "quote": it["quote"],
                         "missing_numbers": (c.get("last_details") or {}).get("missing_numbers")})
        out["groups"].append({"id": g["id"], "style": g["instruction_style"], "total": len(rows),
                              "accepted": sum(r["evidence_accepted"] for r in rows), "rows": rows})

    # レポート R1: 実AI出力（verified4 + unverified4 + 捏造引用4 + 根拠なし4）
    part_a = base["results"]
    pick = lambda t, n: [r["claim"] for r in part_a if r["expected"] == t][:n]
    r1_texts = pick("verified",4) + pick("wrong_number",4) + pick("fake_quote",4) + pick("no_anchor",4)

    def build(title, texts):
        resp = editor.post(f"/api/projects/{pid}/reports", json={"title": title})
        resp.raise_for_status()
        rep = resp.json()["report"]
        rid = rep["id"]
        content = {"sections":[{"heading":"実AI検証","paragraphs":[
            {"text": f"段落{i+1}: 実AI生成の主張を参照する。", "claimIds":[by_text[t]["id"]]} for i,t in enumerate(texts)]}]}
        editor.put(f"/api/reports/{rid}", json={"content": content, "note": "real-ai", "expected_version": rep["version"]}).raise_for_status()
        editor.post(f"/api/reports/{rid}/verify").raise_for_status()
        editor.post(f"/api/reports/{rid}/submit").raise_for_status()
        return rid

    reviewer = login("reviewer@rihrp.local", os.environ["RIHRP_AI_TEST_PASSWORD"])
    gate = {}
    r1 = build("R1 実AI出力（捏造引用4件を含む）", r1_texts)
    a1 = reviewer.post(f"/api/reports/{r1}/review", json={"decision":"approved","comment":""})
    gate["R1"] = {"claims": len(r1_texts), "http": a1.status_code,
                  "status": a1.json().get("report",{}).get("status") if a1.status_code==200 else None,
                  "error": a1.json().get("detail") if a1.status_code!=200 else None}

    t1 = next(t for t in by_text if "2024年の観測値は42.5%" in t)
    r2_texts = pick("verified",3) + [t1]
    r2 = build("R2 改竄由来の contradicted を含む", r2_texts)
    a2 = reviewer.post(f"/api/reports/{r2}/review", json={"decision":"approved","comment":""})
    gate["R2"] = {"claims": len(r2_texts), "http": a2.status_code,
                  "status": a2.json().get("report",{}).get("status") if a2.status_code==200 else None,
                  "error": a2.json().get("detail") if a2.status_code!=200 else None}

    # R1 の検証サマリ（未検証・根拠不足の件数）を取得
    full = editor.get(f"/api/reports/{r1}").json()["report"]
    out["gate"] = gate
    out["r1_integrity"] = {k: full.get("integrity", {}).get(k) for k in ("verified","unverified","contradicted","insufficient","unchecked")}
    (ROOT / "free_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"groups": [{k:v for k,v in g.items() if k!="rows"} for g in out["groups"]], "gate": gate, "r1_integrity": out["r1_integrity"]}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
