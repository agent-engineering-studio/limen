"""A2A server — skills routing, card, model wire-format, task lifecycle (#3).

No DB: the service is exercised with an in-memory store and the read tools are
monkeypatched (skills call ``limen.mcp.tools`` by attribute, so patching the
module functions is enough).
"""

from __future__ import annotations

from typing import Any

import pytest

from limen.a2a.card import build_agent_card
from limen.a2a.models import (
    A2AError,
    DataPart,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    PushNotificationConfig,
    Task,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
    TextPart,
)
from limen.a2a.service import A2AService
from limen.a2a.skills import DEFAULT_SKILL, SKILLS, resolve_invocation


class _FakeStore:
    def __init__(self) -> None:
        self.tasks: dict[str, Task] = {}
        self.push: dict[str, PushNotificationConfig] = {}

    async def save(self, task: Task) -> None:
        self.tasks[task.id] = task

    async def get(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    async def set_push_config(self, task_id: str, cfg: PushNotificationConfig) -> bool:
        if task_id not in self.tasks:
            return False
        self.push[task_id] = cfg
        return True

    async def get_push_config(self, task_id: str) -> PushNotificationConfig | None:
        return self.push.get(task_id)


def _msg(parts: list[Any], metadata: dict[str, Any] | None = None) -> Message:
    return Message(role="user", parts=parts, message_id="m1", metadata=metadata)


@pytest.fixture(autouse=True)
def _stub_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    from limen.mcp import tools

    async def _nat() -> dict[str, Any]:
        return {"report_it": "Nessuna zona a rischio.", "totals": {"regions": 20}}

    async def _summary(aoi_id: str | None = None) -> list[dict[str, Any]]:
        return [{"aoi_id": aoi_id or "it-puglia", "high_or_above": 0}]

    monkeypatch.setattr(tools, "national_report", _nat)
    monkeypatch.setattr(tools, "risk_summary", _summary)


def test_resolve_invocation_prefers_datapart() -> None:
    msg = _msg([DataPart(data={"skill": "risk_summary", "params": {"aoi_id": "it-lazio"}})])
    assert resolve_invocation(msg) == ("risk_summary", {"aoi_id": "it-lazio"})


def test_resolve_invocation_falls_back_to_metadata_then_default() -> None:
    assert resolve_invocation(_msg([TextPart(text="ciao")], {"skill": "risk_summary"})) == (
        "risk_summary",
        {},
    )
    assert resolve_invocation(_msg([TextPart(text="ciao")])) == (DEFAULT_SKILL, {})


def test_agent_card_declares_streaming_push_and_skills() -> None:
    card = build_agent_card("https://limen.example.com/")
    assert card["url"] == "https://limen.example.com/a2a"
    assert card["capabilities"]["streaming"] is True
    assert card["capabilities"]["pushNotifications"] is True
    ids = {s["id"] for s in card["skills"]}
    assert set(SKILLS) == ids


def test_message_wire_format_is_camel_case() -> None:
    dumped = _msg([TextPart(text="x")]).model_dump(by_alias=True, exclude_none=True)
    assert dumped["messageId"] == "m1"
    assert dumped["parts"][0]["kind"] == "text"


async def test_message_send_completes_with_artifact() -> None:
    svc = A2AService(store=_FakeStore())
    task = await svc.message_send(MessageSendParams(message=_msg([TextPart(text="situazione?")])))
    assert task.status.state == "completed"
    assert task.artifacts is not None
    # national_report → text part (report_it) + data part
    kinds = [p.kind for p in task.artifacts[0].parts]
    assert kinds == ["text", "data"]


async def test_tasks_get_and_cancel_terminal_raises() -> None:
    store = _FakeStore()
    svc = A2AService(store=store)
    task = await svc.message_send(MessageSendParams(message=_msg([TextPart(text="x")])))

    got = await svc.tasks_get(TaskQueryParams(id=task.id))
    assert got.id == task.id

    with pytest.raises(A2AError) as exc:
        await svc.tasks_cancel(TaskIdParams(id=task.id))
    assert exc.value.code == -32002  # completed → not cancelable

    with pytest.raises(A2AError) as missing:
        await svc.tasks_get(TaskQueryParams(id="nope"))
    assert missing.value.code == -32001


async def test_message_stream_emits_full_lifecycle() -> None:
    svc = A2AService(store=_FakeStore())
    params = MessageSendParams(
        message=_msg([DataPart(data={"skill": "risk_summary"})]),
    )
    events = [e async for e in svc.message_stream(params)]
    kinds = [getattr(e, "kind", None) for e in events]
    assert kinds[0] == "task"  # initial submitted Task
    assert "status-update" in kinds
    assert "artifact-update" in kinds
    assert events[-1].final is True
    assert events[-1].status.state == "completed"


async def test_push_config_set_requires_existing_task() -> None:
    store = _FakeStore()
    svc = A2AService(store=store)
    cfg = PushNotificationConfig(url="https://hook.example/x")
    with pytest.raises(A2AError):
        await svc.push_config_set(
            TaskPushNotificationConfig(task_id="ghost", push_notification_config=cfg)
        )
    # a real task accepts the config and round-trips through get
    task = await svc.message_send(
        MessageSendParams(
            message=_msg([TextPart(text="x")]),
            configuration=MessageSendConfiguration(push_notification_config=cfg),
        )
    )
    fetched = await svc.push_config_get(TaskIdParams(id=task.id))
    assert fetched.push_notification_config.url == "https://hook.example/x"
