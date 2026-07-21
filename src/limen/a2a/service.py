"""A2A service — routes a message to a skill and manages the task lifecycle.

Skills are fast read-only DB queries, so a task is created and completed within
the same request; streaming still emits the full ``submitted → working →
artifact → completed`` sequence for spec-compliant clients. Push notifications
(if configured) POST the terminal Task to the client's webhook, best-effort.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
from tenacity import RetryError

from limen.a2a.models import (
    ERR_TASK_NOT_CANCELABLE,
    ERR_TASK_NOT_FOUND,
    A2AError,
    Artifact,
    DataPart,
    Message,
    MessageSendParams,
    PushNotificationConfig,
    Task,
    TaskArtifactUpdateEvent,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
    is_terminal,
)
from limen.a2a.skills import SKILLS, resolve_invocation
from limen.a2a.store import A2ATaskStore
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

_PUSH_DEGRADE: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _agent_message(context_id: str, text: str) -> Message:
    return Message(
        role="agent",
        parts=[TextPart(text=text)],
        message_id=uuid.uuid4().hex,
        context_id=context_id,
    )


def _artifact(skill_id: str, result: Any) -> Artifact:
    data = result if isinstance(result, dict) else {"items": result}
    parts: list[Any] = [DataPart(data=data)]
    # national_report ships a ready Italian rendering — surface it as text too.
    if isinstance(result, dict) and isinstance(result.get("report_it"), str):
        parts.insert(0, TextPart(text=result["report_it"]))
    return Artifact(artifact_id=uuid.uuid4().hex, name=f"{skill_id}-result", parts=parts)


class A2AService:
    def __init__(self, store: A2ATaskStore | None = None) -> None:
        self._store = store or A2ATaskStore()

    async def _build_task(self, params: MessageSendParams) -> Task:
        skill_id, sparams = resolve_invocation(params.message)
        task_id = params.message.task_id or uuid.uuid4().hex
        context_id = params.message.context_id or uuid.uuid4().hex
        try:
            result = await SKILLS[skill_id].handler(sparams)
            status = TaskStatus(state="completed", timestamp=_now())
            task = Task(
                id=task_id,
                context_id=context_id,
                status=status,
                artifacts=[_artifact(skill_id, result)],
                history=[params.message],
                metadata={"skill": skill_id},
            )
        except Exception as exc:
            log.warning("a2a.skill.failed", skill=skill_id, error=str(exc))
            status = TaskStatus(
                state="failed",
                timestamp=_now(),
                message=_agent_message(context_id, f"{skill_id} failed: {exc}"),
            )
            task = Task(
                id=task_id,
                context_id=context_id,
                status=status,
                history=[params.message],
                metadata={"skill": skill_id},
            )
        return task

    async def message_send(self, params: MessageSendParams) -> Task:
        task = await self._build_task(params)
        await self._store.save(task)
        await self._register_push(task.id, params)
        await self._maybe_push(task)
        return task

    async def message_stream(self, params: MessageSendParams) -> AsyncIterator[Any]:
        skill_id, _ = resolve_invocation(params.message)
        task_id = params.message.task_id or uuid.uuid4().hex
        context_id = params.message.context_id or uuid.uuid4().hex
        submitted = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(state="submitted", timestamp=_now()),
            history=[params.message],
            metadata={"skill": skill_id},
        )
        await self._store.save(submitted)
        await self._register_push(task_id, params)
        yield submitted
        yield TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state="working", timestamp=_now()),
        )
        # Re-run through _build_task to reuse the handler + failure handling,
        # then replay its outcome as stream events (ids stay stable).
        final = await self._build_task(params)
        final = final.model_copy(update={"id": task_id, "context_id": context_id})
        if final.artifacts:
            for art in final.artifacts:
                yield TaskArtifactUpdateEvent(
                    task_id=task_id, context_id=context_id, artifact=art, last_chunk=True
                )
        await self._store.save(final)
        await self._maybe_push(final)
        yield TaskStatusUpdateEvent(
            task_id=task_id, context_id=context_id, status=final.status, final=True
        )

    async def tasks_get(self, params: TaskQueryParams) -> Task:
        task = await self._store.get(params.id)
        if task is None:
            raise A2AError(ERR_TASK_NOT_FOUND, f"task {params.id!r} not found")
        if params.history_length == 0:
            task = task.model_copy(update={"history": None})
        return task

    async def tasks_cancel(self, params: TaskIdParams) -> Task:
        task = await self._store.get(params.id)
        if task is None:
            raise A2AError(ERR_TASK_NOT_FOUND, f"task {params.id!r} not found")
        if is_terminal(task.status.state):
            raise A2AError(
                ERR_TASK_NOT_CANCELABLE,
                f"task {params.id!r} is {task.status.state} and cannot be canceled",
            )
        task = task.model_copy(update={"status": TaskStatus(state="canceled", timestamp=_now())})
        await self._store.save(task)
        return task

    async def push_config_set(
        self, params: TaskPushNotificationConfig
    ) -> TaskPushNotificationConfig:
        ok = await self._store.set_push_config(params.task_id, params.push_notification_config)
        if not ok:
            raise A2AError(ERR_TASK_NOT_FOUND, f"task {params.task_id!r} not found")
        return params

    async def push_config_get(self, params: TaskIdParams) -> TaskPushNotificationConfig:
        cfg = await self._store.get_push_config(params.id)
        if cfg is None:
            raise A2AError(ERR_TASK_NOT_FOUND, f"no push config for task {params.id!r}")
        return TaskPushNotificationConfig(task_id=params.id, push_notification_config=cfg)

    async def _register_push(self, task_id: str, params: MessageSendParams) -> None:
        cfg = params.configuration.push_notification_config if params.configuration else None
        if cfg is not None:
            await self._store.set_push_config(task_id, cfg)

    async def _maybe_push(self, task: Task) -> None:
        if not is_terminal(task.status.state):
            return
        cfg = await self._store.get_push_config(task.id)
        if cfg is None:
            return
        await self._push(cfg, task)

    async def _push(self, cfg: PushNotificationConfig, task: Task) -> None:
        headers = {"Authorization": f"Bearer {cfg.token}"} if cfg.token else None
        try:
            client = await SharedHttpClient.get()
            await fetch_with_retry(
                "POST",
                cfg.url,
                client=client,
                json=task.model_dump(mode="json", by_alias=True, exclude_none=True),
                headers=headers,
            )
        except _PUSH_DEGRADE as exc:
            log.warning("a2a.push.degraded", task=task.id, error=str(exc))
            return
        log.info("a2a.push.sent", task=task.id, url=cfg.url)
