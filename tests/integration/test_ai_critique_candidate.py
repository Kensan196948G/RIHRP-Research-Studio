"""AI 批判・候補提案（Phase 3 C）の結合テスト。実キーは使わずローカルスタブで検証する。"""

from __future__ import annotations

import json
import threading
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
VARS = ["根固め工の重量", "洗掘深", "流速"]


class AssistStub:
    """任意の JSON（items）を返す最小スタブ。テストごとに payload を差し替える。"""

    def __init__(self) -> None:
        self.payload: dict[str, Any] = {"items": []}
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
                        "body": body,
                    }
                )
                content = json.dumps(stub.payload, ensure_ascii=False)
                if self.path.endswith("/messages"):
                    stub._send(
                        self,
                        200,
                        {
                            "content": [{"type": "text", "text": content}],
                            "usage": {"input_tokens": 90, "output_tokens": 30},
                        },
                    )
                    return
                stub._send(
                    self,
                    200,
                    {
                        "choices": [{"message": {"content": content}}],
                        "usage": {"prompt_tokens": 90, "completion_tokens": 30},
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

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> AssistStub:
    provider = AssistStub()
    monkeypatch.setenv("RIHRP_LLM_BASE_URL", provider.base_url)
    monkeypatch.setenv("RIHRP_LLM_MODEL", "stub-model")
    monkeypatch.setenv("RIHRP_LLM_API_KEY", API_KEY)
    monkeypatch.setenv("RIHRP_LLM_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("RIHRP_LLM_RATE_LIMIT", "100")
    get_settings.cache_clear()
    llm.reset_draft_rate()
    try:
        yield provider
    finally:
        provider.close()
        get_settings.cache_clear()


def _project_with_research(
    client: TestClient, *, analysis: dict | None = None
) -> tuple[dict, dict]:
    project = create_project(client, "AI提案")
    payload: dict[str, Any] = {
        "title": "AI提案",
        "hypothesis": HYPOTHESIS,
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
    if analysis is not None:
        payload["analysis"] = analysis
    saved = client.put(
        f"/api/projects/{project['id']}/research",
        json={"expected_version": 0, "payload": payload},
    )
    assert saved.status_code == 200, saved.text
    return project, payload


def _analysis_payload() -> dict:
    return {
        "field": "river",
        "vars": VARS,
        "inferred": [],
        "nums": [],
        "vague": [],
        "iv": VARS[0],
        "dv": VARS[1],
        "dir": "増やすと低減する",
        "quality": 3,
        "hasNum": True,
        "hasMech": True,
        "hasCond": True,
        "hasComp": False,
    }


def _post(client: TestClient, project: dict, kind: str):
    return client.post(f"/api/projects/{project['id']}/ai/{kind}")


# ---------------------------------------------------------------- 批判


def test_critiques_return_items_without_saving(editor_client: TestClient, stub: AssistStub) -> None:
    project, _ = _project_with_research(editor_client)
    before = editor_client.get(f"/api/projects/{project['id']}/research").json()
    stub.payload = {
        "items": [
            {
                "cat": "外的妥当性",
                "text": "相似則の違いにより実規模への適用範囲が限られる可能性がある。",
                "sug": "現地観測との比較で適用範囲を確認する。",
                "evidenceIds": ["ev-1"],
            },
            {
                "cat": "測定",
                "text": "洗掘深の測定方法が条件によって異なる可能性がある。",
                "sug": "",
                "evidenceIds": [],
            },
        ]
    }
    response = _post(editor_client, project, "critiques")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["evidenceIds"] == ["ev-1"]
    assert "sev" not in body["items"][0]
    assert body["meta"]["model"] == "stub-model"
    assert body["meta"]["prompt_version"] == "studio-critique-v1"
    assert body["meta"]["tokens"] == {"input": 90, "output": 30}
    assert API_KEY not in response.text

    after = editor_client.get(f"/api/projects/{project['id']}/research").json()
    assert after["version"] == before["version"], "生成は保存してはいけない"


def test_critiques_drop_unknown_evidence_ids(editor_client: TestClient, stub: AssistStub) -> None:
    project, _ = _project_with_research(editor_client)
    stub.payload = {
        "items": [
            {
                "cat": "妥当性",
                "text": "有効な根拠を引く批判です。",
                "sug": "",
                "evidenceIds": ["ev-1"],
            },
            {
                "cat": "妥当性",
                "text": "存在しない資料を引く批判です。",
                "sug": "",
                "evidenceIds": ["missing"],
            },
        ]
    }
    response = _post(editor_client, project, "critiques")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["text"] == "有効な根拠を引く批判です。"
    assert "missing" not in json.dumps(items)


def test_critiques_all_invalid_becomes_502(editor_client: TestClient, stub: AssistStub) -> None:
    project, _ = _project_with_research(editor_client)
    stub.payload = {
        "items": [
            {"cat": "妥当性", "text": "存在しない資料を引く批判です。", "evidenceIds": ["missing"]}
        ]
    }
    response = _post(editor_client, project, "critiques")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_invalid_output"


def test_critiques_invalid_output_becomes_502(editor_client: TestClient, stub: AssistStub) -> None:
    project, _ = _project_with_research(editor_client)
    stub.payload = {"items": "not-a-list"}
    response = _post(editor_client, project, "critiques")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_invalid_output"


def test_assist_rate_limit_is_shared(
    editor_client: TestClient, stub: AssistStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _project_with_research(editor_client, analysis=_analysis_payload())
    stub.payload = {
        "items": [{"cat": "妥当性", "text": "レート制限の確認用の批判です。", "evidenceIds": []}]
    }
    monkeypatch.setenv("RIHRP_LLM_RATE_LIMIT", "1")
    get_settings.cache_clear()
    llm.reset_draft_rate()
    first = _post(editor_client, project, "critiques")
    second = _post(editor_client, project, "candidates")
    get_settings.cache_clear()
    assert first.status_code == 200, first.text
    assert second.status_code == 429, second.text
    assert second.json()["error"]["code"] == "rate_limited"


def test_critiques_audited_without_text_or_key(
    client: TestClient, editor_client: TestClient, stub: AssistStub
) -> None:
    project, _ = _project_with_research(editor_client)
    stub.payload = {
        "items": [
            {
                "cat": "妥当性",
                "text": "監査に残してはいけない批判本文です。",
                "evidenceIds": ["ev-1"],
            }
        ]
    }
    response = _post(editor_client, project, "critiques")
    assert response.status_code == 200, response.text
    assert login(client, "admin")
    audit = client.get(f"/api/audit?project_id={project['id']}").json()["events"]
    matches = [event for event in audit if event["action"] == "ai.critique_requested"]
    assert matches, "生成操作が監査に残っていない"
    serialized = json.dumps(matches, ensure_ascii=False)
    assert API_KEY not in serialized
    assert "監査に残してはいけない" not in serialized
    details = matches[0]["details"]
    assert details["provider"]
    assert details["model"] == "stub-model"
    assert details["prompt_version"] == "studio-critique-v1"
    assert details["items"] == 1
    assert isinstance(details["latency_ms"], int) and details["latency_ms"] >= 0


# ---------------------------------------------------------------- 候補


def test_candidates_return_items_without_scores(
    editor_client: TestClient, stub: AssistStub
) -> None:
    project, _ = _project_with_research(editor_client, analysis=_analysis_payload())
    stub.payload = {
        "items": [
            {
                "type": "交互作用",
                "text": "重量の効果は流速条件に依存し、一定以上でのみ洗掘深が低減する。",
                "vars": [VARS[0], VARS[1], VARS[2]],
                "evidenceIds": ["ev-1"],
                "scores": {"evidence": 99},
                "total": 99,
                "status": "採択",
            }
        ]
    }
    response = _post(editor_client, project, "candidates")
    assert response.status_code == 200, response.text
    body = response.json()
    item = body["items"][0]
    assert item["type"] == "交互作用"
    assert item["vars"] == VARS
    # AI の採点値は破棄され、応答に含まれない（採点は採用後に既存ロジック）。
    assert "scores" not in item and "total" not in item and "status" not in item
    assert body["meta"]["prompt_version"] == "studio-candidates-v1"


def test_candidates_drop_unknown_type_and_vars(editor_client: TestClient, stub: AssistStub) -> None:
    project, _ = _project_with_research(editor_client, analysis=_analysis_payload())
    stub.payload = {
        "items": [
            {
                "type": "交互作用",
                "text": "既知の変数だけを使う有効な候補です。",
                "vars": [VARS[0], VARS[1]],
                "evidenceIds": [],
            },
            {
                "type": "未知の類型",
                "text": "未知の type を持つ候補です。",
                "vars": [VARS[0]],
                "evidenceIds": [],
            },
            {
                "type": "閾値",
                "text": "未知の変数を含む候補です。",
                "vars": ["存在しない変数"],
                "evidenceIds": [],
            },
        ]
    }
    response = _post(editor_client, project, "candidates")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["text"] == "既知の変数だけを使う有効な候補です。"


def test_candidates_require_analysis(editor_client: TestClient, stub: AssistStub) -> None:
    project, _ = _project_with_research(editor_client)
    stub.payload = {"items": []}
    response = _post(editor_client, project, "candidates")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_candidates_are_capped_at_five(editor_client: TestClient, stub: AssistStub) -> None:
    project, _ = _project_with_research(editor_client, analysis=_analysis_payload())
    stub.payload = {
        "items": [
            {
                "type": "交互作用",
                "text": f"上限確認用の有効な候補 {i} です。",
                "vars": [VARS[0]],
                "evidenceIds": [],
            }
            for i in range(6)
        ]
    }
    response = _post(editor_client, project, "candidates")
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 5


# ---------------------------------------------------------------- 共通の境界


def test_assist_requires_authentication(editor_client: TestClient) -> None:
    project, _ = _project_with_research(editor_client)
    anonymous = TestClient(app)
    for kind in ("critiques", "candidates"):
        response = anonymous.post(f"/api/projects/{project['id']}/ai/{kind}")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


def test_assist_is_editor_only(editor_client: TestClient, viewer_client: TestClient) -> None:
    project, _ = _project_with_research(editor_client)
    for kind in ("critiques", "candidates"):
        response = viewer_client.post(f"/api/projects/{project['id']}/ai/{kind}")
        assert response.status_code == 403


def test_assist_without_key_fails_closed(
    editor_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _project_with_research(editor_client)
    monkeypatch.setenv("RIHRP_LLM_API_KEY", "")
    get_settings.cache_clear()
    try:
        for kind in ("critiques", "candidates"):
            response = editor_client.post(f"/api/projects/{project['id']}/ai/{kind}")
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "ai_not_configured"
    finally:
        get_settings.cache_clear()
