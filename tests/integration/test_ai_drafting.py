"""AI 下書き（生成経路）の結合テスト。ADR-0006。

実キーは使わず、ローカルの OpenAI 互換スタブに対して検証する。
"""

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
from tests.conftest import login
from tests.integration.test_flow_integrity import (
    create_claim,
    create_project,
    create_source,
)

API_KEY = "test-key-not-a-real-secret"  # noqa: S105 - スタブ用のダミー


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
                content_text = json.dumps(
                    {
                        "claims": [
                            {
                                "claim": "導入可能量は 1,240 MW と試算された。",
                                "quote": "導入可能量は 1,240 MW",
                            },
                            {
                                "claim": "実証事業は 5 件である。",
                                "quote": "実証事業は 5 件である",
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
                if self.path.endswith("/messages"):
                    stub._send(
                        self,
                        200,
                        {"content": [{"type": "text", "text": content_text}]},
                    )
                    return
                stub._send(
                    self,
                    200,
                    {"choices": [{"message": {"content": content_text}}]},
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


def _project_with_source(client: TestClient) -> tuple[dict, dict]:
    project = create_project(client, "AI下書き")
    source = create_source(client, project["id"])
    return project, source


def test_draft_returns_candidates_without_saving(
    editor_client: TestClient, stub: StubProvider
) -> None:
    project, source = _project_with_source(editor_client)
    before = editor_client.get(f"/api/projects/{project['id']}/claims").json()["claims"]

    response = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["candidates"]) == 2
    assert body["candidates"][0]["valid"] is True
    assert body["candidates"][1]["valid"] is False
    assert body["candidates"][1]["reason"] == "quote_not_found"
    assert body["meta"]["model"] == "stub-model"
    assert API_KEY not in response.text

    after = editor_client.get(f"/api/projects/{project['id']}/claims").json()["claims"]
    assert len(after) == len(before), "生成は保存してはいけない"

    adopted = create_claim(editor_client, project["id"], body["candidates"][0]["claim"])
    evidence = editor_client.post(
        f"/api/claims/{adopted['id']}/evidence",
        json={"source_id": source["id"], "quote": body["candidates"][0]["quote"]},
    )
    assert evidence.status_code == 201, evidence.text
    verified = editor_client.post(f"/api/claims/{adopted['id']}/verify")
    assert verified.json()["result"]["verdict"] == "verified"


def test_draft_is_editor_only(editor_client: TestClient, viewer_client: TestClient) -> None:
    project, source = _project_with_source(editor_client)
    response = viewer_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    assert response.status_code == 403


def test_draft_without_key_fails_closed(
    editor_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, source = _project_with_source(editor_client)
    monkeypatch.setenv("RIHRP_LLM_API_KEY", "")
    get_settings.cache_clear()
    response = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    get_settings.cache_clear()
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "ai_not_configured"


def test_upstream_401_becomes_502_without_leaking_key(
    editor_client: TestClient, stub: StubProvider
) -> None:
    project, source = _project_with_source(editor_client)
    stub.mode = "401"
    response = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "ai_upstream_error"
    assert API_KEY not in response.text
    assert stub.requests[-1]["authorization"] == f"Bearer {API_KEY}"


def test_invalid_output_becomes_502(editor_client: TestClient, stub: StubProvider) -> None:
    project, source = _project_with_source(editor_client)
    stub.mode = "invalid"
    response = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "ai_invalid_output"


def test_timeout_becomes_504(editor_client: TestClient, stub: StubProvider) -> None:
    project, source = _project_with_source(editor_client)
    stub.mode = "timeout"
    response = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    assert response.status_code == 504, response.text
    assert response.json()["error"]["code"] == "ai_timeout"


def test_oversized_source_is_rejected(
    editor_client: TestClient, stub: StubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, source = _project_with_source(editor_client)
    monkeypatch.setenv("RIHRP_LLM_MAX_SOURCE_CHARS", "10")
    get_settings.cache_clear()
    response = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    get_settings.cache_clear()
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "source_too_large"


def test_rate_limit(
    editor_client: TestClient, stub: StubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, source = _project_with_source(editor_client)
    monkeypatch.setenv("RIHRP_LLM_RATE_LIMIT", "1")
    get_settings.cache_clear()
    llm.reset_draft_rate()
    first = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    second = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    get_settings.cache_clear()
    assert first.status_code == 200, first.text
    assert second.status_code == 429, second.text


def test_draft_is_audited_without_prompt_or_key(
    client: TestClient, editor_client: TestClient, stub: StubProvider
) -> None:
    project, source = _project_with_source(editor_client)
    response = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    assert response.status_code == 200, response.text
    admin = login(client, "admin")
    assert admin
    audit = client.get("/api/audit").json()["events"]
    matches = [event for event in audit if event["action"] == "ai.draft_requested"]
    assert matches, "生成操作が監査に残っていない"
    serialized = json.dumps(matches, ensure_ascii=False)
    assert API_KEY not in serialized
    assert "SOURCE:" not in serialized


def test_anthropic_provider_uses_messages_api(
    editor_client: TestClient, stub: StubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RIHRP_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("RIHRP_LLM_API_KEY", "sk-ant-test-value")
    get_settings.cache_clear()
    llm.reset_draft_rate()
    project, source = _project_with_source(editor_client)
    response = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    get_settings.cache_clear()
    assert response.status_code == 200, response.text
    assert response.json()["meta"]["provider"] == "anthropic"
    last = stub.requests[-1]
    assert last["path"] == "/v1/messages"
    assert last["x_api_key"] == "sk-ant-test-value"
    assert last["authorization"] is None


def test_unknown_provider_is_not_configured(
    editor_client: TestClient, stub: StubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RIHRP_LLM_PROVIDER", "other")
    get_settings.cache_clear()
    llm.reset_draft_rate()
    project, source = _project_with_source(editor_client)
    response = editor_client.post(
        f"/api/projects/{project['id']}/ai/draft-claims", json={"source_id": source["id"]}
    )
    get_settings.cache_clear()
    assert response.status_code == 503, response.text
