"""A2A HTTP layer — JSON-RPC dispatch, error codes, SSE framing (no DB).

The service is stubbed (its own logic is covered in ``test_a2a.py``); this
exercises the endpoint: agent card, JSON-RPC envelope, error-code mapping and
the ``text/event-stream`` framing of ``message/stream``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from limen.a2a.models import (
    ERR_TASK_NOT_FOUND,
    A2AError,
    Artifact,
    DataPart,
    MessageSendParams,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from limen.api.endpoints import a2a


def _task(state: str = "completed") -> Task:
    return Task(
        id="t1",
        context_id="c1",
        status=TaskStatus(state=state),  # type: ignore[arg-type]
        artifacts=[Artifact(artifact_id="a1", parts=[DataPart(data={"ok": True})])],
    )


class _StubService:
    async def message_send(self, params: MessageSendParams) -> Task:
        return _task()

    async def message_stream(self, params: MessageSendParams) -> AsyncIterator[Any]:
        t = _task("submitted")
        yield t
        yield TaskStatusUpdateEvent(
            task_id="t1", context_id="c1", status=TaskStatus(state="working")
        )
        yield TaskArtifactUpdateEvent(
            task_id="t1",
            context_id="c1",
            artifact=t.artifacts[0],  # type: ignore[index]
        )
        yield TaskStatusUpdateEvent(
            task_id="t1", context_id="c1", status=TaskStatus(state="completed"), final=True
        )

    async def tasks_get(self, params: Any) -> Task:
        raise A2AError(ERR_TASK_NOT_FOUND, "nope")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(a2a, "_SERVICE", _StubService())
    app = FastAPI()
    app.include_router(a2a.router)
    return TestClient(app)


def _send(msg_text: str = "ciao") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": "m1",
                "parts": [{"kind": "text", "text": msg_text}],
            }
        },
    }


def test_agent_card_is_served(client: TestClient) -> None:
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["url"].endswith("/a2a")
    assert card["capabilities"]["streaming"] is True


def test_message_send_returns_task_result(client: TestClient) -> None:
    resp = client.post("/a2a", json=_send())
    body = resp.json()
    assert body["id"] == "1"
    assert body["result"]["kind"] == "task"
    assert body["result"]["status"]["state"] == "completed"


def test_unknown_method_and_task_not_found_map_to_codes(client: TestClient) -> None:
    unknown = client.post("/a2a", json={"jsonrpc": "2.0", "id": "2", "method": "bogus"}).json()
    assert unknown["error"]["code"] == -32601
    missing = client.post(
        "/a2a", json={"jsonrpc": "2.0", "id": "3", "method": "tasks/get", "params": {"id": "x"}}
    ).json()
    assert missing["error"]["code"] == ERR_TASK_NOT_FOUND


def test_invalid_params_map_to_minus_32602(client: TestClient) -> None:
    bad = client.post(
        "/a2a", json={"jsonrpc": "2.0", "id": "4", "method": "message/send", "params": {}}
    ).json()
    assert bad["error"]["code"] == -32602


def test_message_stream_is_sse_with_terminal_frame(client: TestClient) -> None:
    body = dict(_send())
    body["method"] = "message/stream"
    resp = client.post("/a2a", json=body)
    assert resp.headers["content-type"].startswith("text/event-stream")
    frames = [
        json.loads(line[len("data: ") :])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    kinds = [f["result"]["kind"] for f in frames]
    assert kinds[0] == "task"
    assert "artifact-update" in kinds
    assert frames[-1]["result"]["final"] is True
