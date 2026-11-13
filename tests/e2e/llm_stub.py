"""E2E 用の OpenAI 互換スタブ（実キー不要）。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 18130

CLAIMS = json.dumps(
    {
        "claims": [
            {
                "claim": "導入可能量は 1,240 MW と試算された。",
                "quote": "導入可能量は 1,240 MW",
            },
            {
                "claim": "実証事業は 9 件である。",
                "quote": "実証事業は 9 件である",
            },
        ]
    },
    ensure_ascii=False,
)


DEBATE = json.dumps(
    {
        "messages": [
            {"agent": "fac", "kind": "進行", "text": "E2E スタブの討論を開始します。"},
            {"agent": "lit", "kind": "根拠", "text": "E2E スタブの根拠発言です。"},
            {"agent": "cri", "kind": "反論", "text": "E2E スタブの反論です。"},
        ]
    },
    ensure_ascii=False,
)

CRITIQUES = json.dumps(
    {
        "items": [
            {
                "cat": "外的妥当性",
                "text": "E2E スタブの批判です。適用範囲の確認が必要です。",
                "sug": "現地観測と比較する。",
                "evidenceIds": ["ev-1"],
            },
            {
                "cat": "測定",
                "text": "E2E スタブの測定に関する批判です。",
                "sug": "",
                "evidenceIds": [],
            },
        ]
    },
    ensure_ascii=False,
)

CANDIDATES = json.dumps(
    {
        "items": [
            {
                "type": "交互作用",
                "text": "E2E スタブの候補です。重量の効果は流速条件に依存する。",
                "vars": ["根固め工の重量", "洗掘深", "流速"],
                "evidenceIds": ["ev-1"],
            }
        ]
    },
    ensure_ascii=False,
)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        prompt = ""
        try:
            data = json.loads(raw or b"{}")
            messages = data.get("messages") or []
            if messages:
                prompt = str(messages[-1].get("content") or "")
        except ValueError:
            pass
        if "critique items" in prompt:
            content = CRITIQUES
        elif "(candidates)" in prompt:
            content = CANDIDATES
        elif "EVIDENCE_IDS" in prompt or "debate" in prompt.lower():
            content = DEBATE
        else:
            content = CLAIMS
        body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
