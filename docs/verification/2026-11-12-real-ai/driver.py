"""実AI生成の主張を隔離 RIHRP に登録し、検証エンジンの判定を記録する。"""
from __future__ import annotations

import os

import json, os, re, sys, time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:18120"
EMAIL = "editor@rihrp.local"
PASSWORD = os.environ["RIHRP_AI_TEST_PASSWORD"]
ROOT = Path(__file__).resolve().parent
SOURCES = {
    "JMA": ("気象庁 日本の年平均気温（2026-11-12取得）", "https://www.data.jma.go.jp/cpdinfo/temp/an_jpn.html"),
    "STAT": ("総務省統計局 人口推計（2026年10月公表）", "https://www.stat.go.jp/data/jinsui/new.html"),
    "ARXIV": ("arXiv:2005.14165 Language Models are Few-Shot Learners (GPT-3)", "https://arxiv.org/abs/2005.14165"),
}
FILE = {"JMA": "sources/jma.txt", "STAT": "sources/stat.txt", "ARXIV": "sources/arxiv.txt"}
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*%?")
WS = re.compile(r"\s+")

def norm(t: str) -> str:
    return WS.sub(" ", t).strip()

def numbers(t: str) -> list[str]:
    return NUMBER_RE.findall(t)

def number_in(number: str, text: str) -> bool:
    pattern = re.compile(r"(?<![\d.,])" + re.escape(number) + r"(?![\d.,])")
    return pattern.search(text) is not None

def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30.0)
    r = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]

    project = client.post("/api/projects", json={"title": "実AI検証 2026-11-12", "summary": "実LLM生成の主張を検証エンジンに通す実地試験"}).json()["project"]
    pid = project["id"]

    source_ids: dict[str, str] = {}
    source_texts: dict[str, str] = {}
    for key, path in FILE.items():
        content = (ROOT / path).read_text(encoding="utf-8")
        source_texts[key] = content
        title, origin = SOURCES[key]
        resp = client.post(f"/api/projects/{pid}/sources", json={"title": title, "kind": "url", "origin": origin, "content": content})
        if resp.status_code == 409:
            sid = resp.json()["detail"]["details"]["source_id"] if isinstance(resp.json().get("detail"), dict) else resp.json()["source_id"]
            source_ids[key] = sid
        else:
            resp.raise_for_status()
            source_ids[key] = resp.json()["source"]["id"]

    items = json.loads((ROOT / "claims.json").read_text(encoding="utf-8"))
    results = []
    for item in items["items"]:
        claim_resp = client.post(f"/api/projects/{pid}/claims", json={"text": item["claim"]})
        claim_resp.raise_for_status()
        claim = claim_resp.json()["claim"]
        cid = claim["id"]

        evidence = {"status": "none", "http": None, "code": None}
        if item["quote"]:
            ev = client.post(f"/api/claims/{cid}/evidence", json={"source_id": source_ids[item["source"]], "quote": item["quote"]})
            evidence["http"] = ev.status_code
            if ev.status_code == 201:
                evidence["status"] = "registered"
            else:
                evidence["status"] = "rejected"
                try:
                    body = ev.json()
                    evidence["code"] = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")
                except Exception:
                    evidence["code"] = "unparsed"

        ver = client.post(f"/api/claims/{cid}/verify")
        ver.raise_for_status()
        vj = ver.json()
        verdict = vj["result"]["verdict"]
        reasons = vj["result"]["reasons"]

        src = source_texts[item["source"]]
        quote_present = bool(item["quote"]) and norm(item["quote"]) in norm(src)
        missing = [n for n in numbers(item["claim"]) if not number_in(n, src)]
        independent = (
            "contradicted" if (item["quote"] and not quote_present)
            else "unverified" if missing
            else "verified" if (item["quote"] and quote_present)
            else "insufficient"
        )
        results.append({
            "id": item["id"], "source": item["source"], "expected": item["type"],
            "claim": item["claim"], "quote": item["quote"],
            "evidence": evidence, "verdict": verdict, "reasons": reasons,
            "independent": independent, "missing_numbers": missing,
            "numbers": numbers(item["claim"]),
        })
        print(f'{item["id"]:6} expected={item["type"]:12} evidence={evidence["status"]:10} verdict={verdict:13} reasons={reasons}')

    (ROOT / "results.json").write_text(json.dumps({"project_id": pid, "source_ids": source_ids, "generator": items.get("model"), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__":
    sys.exit(main())
