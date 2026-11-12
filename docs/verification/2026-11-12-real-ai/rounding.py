"""実AIがやりがちな丸め・順序数・単位換算の数値が、どう判定されるかを測る。"""
from __future__ import annotations

import os
import json, sys
from pathlib import Path
import httpx

BASE="http://127.0.0.1:18120"; ROOT=Path(__file__).resolve().parent
CASES=[
 ("JMA","長期的には100年あたり1.44℃の割合で上昇しています","日本の年平均気温は100年あたり約1.4℃の割合で上昇している。"),
 ("JMA","2025年の日本の平均気温の基準値（1991～2020年の30年平均値）からの偏差は+1.23℃で、1898年の統計開始以降、3番目に高い値となりました。","2025年の偏差は約1.2℃で、統計開始以降3番目に高い。"),
 ("STAT","＜総人口＞ 1億2269万人で、前年同月に比べ減少","2026年10月の総人口は約1億2300万人である。"),
 ("STAT","15歳未満人口は 1326万3千人で、前年同月に比べ減少","15歳未満人口は約1330万人である。"),
 ("STAT","65歳以上人口は 3622万7千人で、前年同月に比べ増加","65歳以上人口は約3620万人である。"),
 ("JMA","①2024年（+1.48℃）、②2023年（+1.29℃）、③2025年（+1.23℃）","正偏差が大きかった年の2番目は2023年である。"),
]
def main():
    b=json.loads((ROOT/"results.json").read_text()); pid=b["project_id"]; sid=b["source_ids"]
    c=httpx.Client(base_url=BASE,timeout=30.0)
    r=c.post("/api/auth/login",json={"email":"editor@rihrp.local","password":os.environ["RIHRP_AI_TEST_PASSWORD"]}); r.raise_for_status()
    c.headers["X-CSRF-Token"]=r.json()["csrf_token"]
    rows=[]
    for src,quote,claim in CASES:
        cr=c.post(f"/api/projects/{pid}/claims",json={"text":claim}); cr.raise_for_status(); cid=cr.json()["claim"]["id"]
        ev=c.post(f"/api/claims/{cid}/evidence",json={"source_id":sid[src],"quote":quote}); assert ev.status_code==201, ev.text
        v=c.post(f"/api/claims/{cid}/verify").json()["result"]
        rows.append({"source":src,"claim":claim,"verdict":v["verdict"],"reasons":v["reasons"],
                     "missing":v["details"].get("missing_numbers")})
        print(f'{v["verdict"]:12} missing={v["details"].get("missing_numbers")} :: {claim}')
    (ROOT/"rounding_results.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
main()
