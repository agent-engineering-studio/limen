"""A2A (Agent2Agent) protocol types — JSON-RPC 2.0 wire models.

Python fields are snake_case; the wire format is camelCase (``messageId``,
``contextId``, …) via a ``to_camel`` alias generator. Serialise with
``by_alias=True`` and parse with ``populate_by_name=True`` so both spellings
are accepted on input.

Only the parts of the spec Limen actually uses are modelled: text/data parts
(no file parts — the skills take/return structured data, not uploads),
message/task/artifact, the streaming status/artifact update events, push
config, and the JSON-RPC envelopes. See ``docs/openclaw.md`` for the surface.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Role = Literal["user", "agent"]
TaskState = Literal[
    "submitted",
    "working",
    "input-required",
    "completed",
    "canceled",
    "failed",
    "rejected",
    "auth-required",
    "unknown",
]
_TERMINAL_STATES: frozenset[str] = frozenset({"completed", "canceled", "failed", "rejected"})


def is_terminal(state: str) -> bool:
    return state in _TERMINAL_STATES


class _A2ABase(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TextPart(_A2ABase):
    kind: Literal["text"] = "text"
    text: str
    metadata: dict[str, Any] | None = None


class DataPart(_A2ABase):
    kind: Literal["data"] = "data"
    data: dict[str, Any]
    metadata: dict[str, Any] | None = None


Part = Annotated[TextPart | DataPart, Field(discriminator="kind")]


class Message(_A2ABase):
    role: Role
    parts: list[Part]
    message_id: str
    kind: Literal["message"] = "message"
    task_id: str | None = None
    context_id: str | None = None
    metadata: dict[str, Any] | None = None


class Artifact(_A2ABase):
    artifact_id: str
    parts: list[Part]
    name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None


class TaskStatus(_A2ABase):
    state: TaskState
    message: Message | None = None
    timestamp: str | None = None


class Task(_A2ABase):
    id: str
    context_id: str
    status: TaskStatus
    kind: Literal["task"] = "task"
    artifacts: list[Artifact] | None = None
    history: list[Message] | None = None
    metadata: dict[str, Any] | None = None


class TaskStatusUpdateEvent(_A2ABase):
    task_id: str
    context_id: str
    status: TaskStatus
    kind: Literal["status-update"] = "status-update"
    final: bool = False
    metadata: dict[str, Any] | None = None


class TaskArtifactUpdateEvent(_A2ABase):
    task_id: str
    context_id: str
    artifact: Artifact
    kind: Literal["artifact-update"] = "artifact-update"
    append: bool = False
    last_chunk: bool = False


class PushNotificationConfig(_A2ABase):
    url: str
    token: str | None = None
    id: str | None = None


class TaskPushNotificationConfig(_A2ABase):
    task_id: str
    push_notification_config: PushNotificationConfig


class MessageSendConfiguration(_A2ABase):
    accepted_output_modes: list[str] | None = None
    blocking: bool | None = None
    push_notification_config: PushNotificationConfig | None = None


class MessageSendParams(_A2ABase):
    message: Message
    configuration: MessageSendConfiguration | None = None
    metadata: dict[str, Any] | None = None


class TaskIdParams(_A2ABase):
    id: str
    metadata: dict[str, Any] | None = None


class TaskQueryParams(_A2ABase):
    id: str
    history_length: int | None = None


class JsonRpcError(_A2ABase):
    code: int
    message: str
    data: Any | None = None


class JsonRpcRequest(_A2ABase):
    method: str
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    params: dict[str, Any] | None = None


class JsonRpcResponse(_A2ABase):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: JsonRpcError | None = None


# JSON-RPC + A2A error codes (subset the server can raise).
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603
ERR_TASK_NOT_FOUND = -32001
ERR_TASK_NOT_CANCELABLE = -32002
ERR_PUSH_NOT_SUPPORTED = -32003


class A2AError(Exception):
    """Carries a JSON-RPC error code so the endpoint can map it to a response."""

    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data
