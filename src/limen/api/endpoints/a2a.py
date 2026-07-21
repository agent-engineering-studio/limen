"""A2A (Agent2Agent) HTTP surface — Agent Card + JSON-RPC 2.0 endpoint.

``GET /.well-known/agent-card.json`` (legacy alias ``agent.json``) serves the
capability descriptor. ``POST /a2a`` dispatches JSON-RPC methods
(``message/send``, ``message/stream`` via SSE, ``tasks/get``, ``tasks/cancel``,
``tasks/pushNotificationConfig/{set,get}``). Read-only, no auth — same posture
as the public risk API and the MCP read tools.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ValidationError

from limen.a2a.card import build_agent_card
from limen.a2a.models import (
    ERR_INTERNAL,
    ERR_INVALID_PARAMS,
    ERR_INVALID_REQUEST,
    ERR_METHOD_NOT_FOUND,
    ERR_PARSE,
    A2AError,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    MessageSendParams,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
)
from limen.a2a.service import A2AService
from limen.core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["a2a"])
_SERVICE = A2AService()


def _base_url(request: Request) -> str:
    return os.getenv("A2A_PUBLIC_URL") or str(request.base_url).rstrip("/")


@router.get("/.well-known/agent-card.json")
@router.get("/.well-known/agent.json")
async def agent_card(request: Request) -> JSONResponse:
    return JSONResponse(build_agent_card(_base_url(request)))


def _dump(model: BaseModel) -> Any:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def _ok(req_id: str | int | None, result: BaseModel) -> JSONResponse:
    return JSONResponse(_dump(JsonRpcResponse(id=req_id, result=_dump(result))))


def _err(req_id: str | int | None, code: int, message: str, data: Any = None) -> JSONResponse:
    resp = JsonRpcResponse(id=req_id, error=JsonRpcError(code=code, message=message, data=data))
    return JSONResponse(_dump(resp))


@router.post("/a2a")
async def a2a_rpc(request: Request) -> Any:
    try:
        raw = await request.json()
    except (json.JSONDecodeError, ValueError):
        return _err(None, ERR_PARSE, "invalid JSON")
    try:
        req = JsonRpcRequest.model_validate(raw)
    except ValidationError as exc:
        return _err(None, ERR_INVALID_REQUEST, "invalid JSON-RPC request", exc.errors())

    params = req.params or {}
    try:
        if req.method == "message/stream":
            send = MessageSendParams.model_validate(params)
            return StreamingResponse(_sse(req.id, send), media_type="text/event-stream")
        if req.method == "message/send":
            send = MessageSendParams.model_validate(params)
            return _ok(req.id, await _SERVICE.message_send(send))
        if req.method == "tasks/get":
            return _ok(req.id, await _SERVICE.tasks_get(TaskQueryParams.model_validate(params)))
        if req.method == "tasks/cancel":
            return _ok(req.id, await _SERVICE.tasks_cancel(TaskIdParams.model_validate(params)))
        if req.method == "tasks/pushNotificationConfig/set":
            return _ok(
                req.id,
                await _SERVICE.push_config_set(TaskPushNotificationConfig.model_validate(params)),
            )
        if req.method == "tasks/pushNotificationConfig/get":
            return _ok(req.id, await _SERVICE.push_config_get(TaskIdParams.model_validate(params)))
    except ValidationError as exc:
        return _err(req.id, ERR_INVALID_PARAMS, "invalid params", exc.errors())
    except A2AError as exc:
        return _err(req.id, exc.code, str(exc), exc.data)
    except Exception as exc:  # never leak a stack trace to the caller
        log.warning("a2a.rpc.failed", method=req.method, error=str(exc))
        return _err(req.id, ERR_INTERNAL, "internal error")

    return _err(req.id, ERR_METHOD_NOT_FOUND, f"method not found: {req.method}")


async def _sse(req_id: str | int | None, params: MessageSendParams) -> AsyncIterator[str]:
    try:
        async for event in _SERVICE.message_stream(params):
            frame = _dump(JsonRpcResponse(id=req_id, result=_dump(event)))
            yield f"data: {json.dumps(frame)}\n\n"
    except Exception as exc:  # emit a terminal JSON-RPC error frame, then stop
        log.warning("a2a.stream.failed", error=str(exc))
        err = JsonRpcError(code=ERR_INTERNAL, message="stream error")
        frame = _dump(JsonRpcResponse(id=req_id, error=err))
        yield f"data: {json.dumps(frame)}\n\n"
