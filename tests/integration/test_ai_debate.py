"""AI 討論（Phase 3 B PoC）の結合テスト。実キーは使わずローカルスタブで検証する。"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient

from rihrp import llm
from rihrp.config import get_settings
from rihrp.main import app
from tests.conftest import login
from tests.integration.test_flow_integrity import create_project

API_KEY = "test-key-not-a-real-secret"  # noqa: S105 - スタブ用のダミー

HYPOTHESIS = (
    "河道湾曲部の外岸側で根固め工の重量を従来比1.5倍にすると、"
    "計画高水時の護岸基礎部の洗掘深は30%以上低減する。"
)

DEBATE = {
    "messages": [
        {"agent": "fac", "kind": "進行", "text": "本日の議題は護岸基礎の洗掘対策です。"},
        {
            "agent": "lit",
            "kind": "根拠",
            "text": "外岸側の流速減衰を示す資料があります。",
            "evidenceIds": ["ev-1"],
        },
        {
            "agent": "cri",
            "kind": "反論",
            "text": "相似則の違いにより適用範囲が限定される可能性があります。",
        },
    ]
}


class StubProvider:
    """OpenAI 互換の最小スタブ。mode で応答を切り替える。"""

    def __init__(self) -> None:
        self.mode = "ok"
        self.requests: list[dict[str, Any]] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                stub.requests.append(
                    {
                        "path": self.path,
                        "authorization": self.headers.get("Authorization"),
                        "x_api_key": self.headers.get("x-api-key"),
                        "body": body,
                    }
                )
                if stub.mode == "timeout":
                    time.sleep(1.2)
                if stub.mode == "401":
                    stub._send(self, 401, {"error": "unauthorized"})
                    return
                if stub.mode == "invalid":
                    stub._send_raw(self, 200, "not-json")
                    return
                payload = DEBATE
                if stub.mode == "unknown":
                    payload = {
                        "messages": [
                            {
                                "agent": "lit",
                                "kind": "根拠",
                                "text": "存在しない資料を引用します。",
                                "evidenceIds": ["missing"],
                            }
                        ]
                    }
                if stub.mode == "mixed":
                    payload = {
                        "messages": DEBATE["messages"]
                        + [
                            {
                                "agent": "lit",
                                "kind": "根拠",
                                "text": "存在しない資料を引用します。",
                                "evidenceIds": ["missing"],
                            }
                        ]
                    }
                if stub.mode == "schema":
                    payload = {
                        "messages": [
                            {
                                "agent": "lit",
                                "kind": "根拠",
                                "text": "有効な発言です（スキーマ確認用）。",
                                "evidenceIds": ["ev-1"],
                            },
                            {
                                "agent": "bogus",
                                "kind": "根拠",
                                "text": "不正なエージェント名の発言です。",
                                "evidenceIds": ["ev-1"],
                            },
                            {
                                "agent": "lit",
                                "kind": "根拠",
                                "text": "短い",
                                "evidenceIds": ["ev-1"],
                            },
                            {
                                "agent": "lit",
                                "kind": "根拠",
                                "text": "evidenceIds が配列でない発言です。",
                                "evidenceIds": "ev-1",
                            },
                        ]
                    }
                content_text = json.dumps(payload, ensure_ascii=False)
                if self.path.endswith("/messages"):
                    stub._send(
                        self,
                        200,
                        {
                            "content": [{"type": "text", "text": content_text}],
                            "usage": {"input_tokens": 120, "output_tokens": 60},
                        },
                    )
                    return
                stub._send(
                    self,
                    200,
                    {
                        "choices": [{"message": {"content": content_text}}],
                        "usage": {"prompt_tokens": 120, "completion_tokens": 60},
                    },
                )

            def log_message(self, *args: Any) -> None:  # noqa: A003
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    @staticmethod
    def _send(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    @staticmethod
    def _send_raw(handler: BaseHTTPRequestHandler, status: int, text: str) -> None:
        data = text.encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "text/plain")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> StubProvider:
    provider = StubProvider()
    monkeypatch.setenv("RIHRP_LLM_BASE_URL", provider.base_url)
    monkeypatch.setenv("RIHRP_LLM_MODEL", "stub-model")
    monkeypatch.setenv("RIHRP_LLM_API_KEY", API_KEY)
    monkeypatch.setenv("RIHRP_LLM_TIMEOUT_SECONDS", "0.5")
    monkeypatch.setenv("RIHRP_LLM_RATE_LIMIT", "100")
    get_settings.cache_clear()
    llm.reset_draft_rate()
    try:
        yield provider
    finally:
        provider.close()
        get_settings.cache_clear()


def _project_with_research(
    client: TestClient, *, hypothesis: str = HYPOTHESIS
) -> tuple[dict, dict]:
    project = create_project(client, "AI討論")
    payload = {
        "title": "AI討論",
        "hypothesis": hypothesis,
        "evidence": [
            {
                "id": "ev-1",
                "title": "護岸基礎の洗掘に関する現地観測",
                "stance": "support",
                "reliability": 78,
                "summary": "重量を増した区間で洗掘深が低減した。",
            }
        ],
        "critiques": [{"cat": "外的妥当性", "sev": "高", "text": "相似則の違いに注意が必要。"}],
    }
    saved = client.put(
        f"/api/projects/{project['id']}/research",
        json={"expected_version": 0, "payload": payload},
    )
    assert saved.status_code == 200, saved.text
    return project, payload


def test_debate_returns_messages_without_saving(
    editor_client: TestClient, stub: StubProvider
) -> None:
    project, payload = _project_with_research(editor_client)
    before = editor_client.get(f"/api/projects/{project['id']}/research").json()

    response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["messages"]) == 3
    assert body["messages"][1]["evidenceIds"] == ["ev-1"]
    assert body["meta"]["model"] == "stub-model"
    assert body["meta"]["prompt_version"] == "studio-debate-v1"
    assert body["meta"]["tokens"] == {"input": 120, "output": 60}
    assert API_KEY not in response.text

    after = editor_client.get(f"/api/projects/{project['id']}/research").json()
    assert after["version"] == before["version"], "生成は保存してはいけない"
    assert after["payload"] == payload


def test_debate_respects_project_allowlist(
    editor_client: TestClient, stub: StubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _project_with_research(editor_client)
    monkeypatch.setenv("RIHRP_LLM_ALLOWED_PROJECTS", "another-project")
    get_settings.cache_clear()
    try:
        response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ai_not_allowed"

        monkeypatch.setenv("RIHRP_LLM_ALLOWED_PROJECTS", project["id"])
        get_settings.cache_clear()
        response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
        assert response.status_code == 200, response.text
    finally:
        get_settings.cache_clear()


def test_debate_is_editor_only(editor_client: TestClient, viewer_client: TestClient) -> None:
    project, _ = _project_with_research(editor_client)
    response = viewer_client.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 403


def test_debate_requires_authentication(editor_client: TestClient) -> None:
    project, _ = _project_with_research(editor_client)
    anonymous = TestClient(app)
    response = anonymous.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "unauthorized"


def test_debate_without_key_fails_closed(
    editor_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _project_with_research(editor_client)
    monkeypatch.setenv("RIHRP_LLM_API_KEY", "")
    get_settings.cache_clear()
    response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    get_settings.cache_clear()
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "ai_not_configured"


def test_debate_without_hypothesis_is_rejected(
    editor_client: TestClient, stub: StubProvider
) -> None:
    project = create_project(editor_client, "AI討論（仮説なし）")
    response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_evidence_ids_are_rejected(editor_client: TestClient, stub: StubProvider) -> None:
    project, _ = _project_with_research(editor_client)
    stub.mode = "unknown"
    response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "ai_invalid_output"


def test_mixed_evidence_ids_keep_only_valid_messages(
    editor_client: TestClient, stub: StubProvider
) -> None:
    project, _ = _project_with_research(editor_client)
    stub.mode = "mixed"
    response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 200, response.text
    messages = response.json()["messages"]
    assert len(messages) == 3
    # 落とすのは「存在しない ID を引く発言」だけ。有効な発言の欠落・並び替えは許容しない。
    assert [item["text"] for item in messages] == [item["text"] for item in DEBATE["messages"]]
    assert all("missing" not in item["evidenceIds"] for item in messages)


def test_invalid_message_schema_is_dropped(editor_client: TestClient, stub: StubProvider) -> None:
    project, _ = _project_with_research(editor_client)
    stub.mode = "schema"
    response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 200, response.text
    messages = response.json()["messages"]
    # 未知 agent・短すぎる本文・evidenceIds が配列でない発言は破棄され、有効な 1 件だけが残る。
    assert len(messages) == 1
    assert messages[0]["text"] == "有効な発言です（スキーマ確認用）。"


def test_upstream_401_becomes_502_without_leaking_key(
    editor_client: TestClient, stub: StubProvider
) -> None:
    project, _ = _project_with_research(editor_client)
    stub.mode = "401"
    response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "ai_upstream_error"
    assert API_KEY not in response.text
    assert stub.requests[-1]["authorization"] == f"Bearer {API_KEY}"


def test_invalid_output_becomes_502(editor_client: TestClient, stub: StubProvider) -> None:
    project, _ = _project_with_research(editor_client)
    stub.mode = "invalid"
    response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "ai_invalid_output"


def test_timeout_becomes_504(editor_client: TestClient, stub: StubProvider) -> None:
    project, _ = _project_with_research(editor_client)
    stub.mode = "timeout"
    response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 504, response.text
    assert response.json()["error"]["code"] == "ai_timeout"


def test_rate_limit_is_enforced(
    editor_client: TestClient, stub: StubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _project_with_research(editor_client)
    monkeypatch.setenv("RIHRP_LLM_RATE_LIMIT", "1")
    get_settings.cache_clear()
    llm.reset_draft_rate()
    first = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    second = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    get_settings.cache_clear()
    assert first.status_code == 200, first.text
    assert second.status_code == 429, second.text
    assert second.json()["error"]["code"] == "rate_limited"


def test_debate_is_audited_without_prompt_or_key(
    client: TestClient, editor_client: TestClient, stub: StubProvider
) -> None:
    project, _ = _project_with_research(editor_client)
    response = editor_client.post(f"/api/projects/{project['id']}/ai/debate")
    assert response.status_code == 200, response.text
    admin = login(client, "admin")
    assert admin
    audit = client.get(f"/api/audit?project_id={project['id']}").json()["events"]
    matches = [event for event in audit if event["action"] == "ai.debate_requested"]
    assert matches, "生成操作が監査に残っていない"
    serialized = json.dumps(matches, ensure_ascii=False)
    assert API_KEY not in serialized
    assert "EVIDENCE_IDS:" not in serialized
    assert "本日の議題" not in serialized, "生成本文は監査に残してはいけない"
    # 監査には運用に必要なメタデータだけが残る（欠落すると追跡不能になる）
    details = matches[0]["details"]
    assert details["provider"]
    assert details["model"] == "stub-model"
    assert details["prompt_version"] == "studio-debate-v1"
    assert details["messages"] == 3
    assert isinstance(details["latency_ms"], int) and details["latency_ms"] >= 0
