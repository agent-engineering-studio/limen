"""Thin async client over the KG sidecar's ``POST /query`` endpoint.

The sidecar exposes both REST and MCP — Limen consumes REST for
simplicity (one less moving piece). Every error path returns an
**empty** :class:`GroundingResult` rather than raising — the
BriefingAgent treats empty as "no citations".

The client uses the shared :class:`SharedHttpClient` so timeouts and
connection pooling stay consistent across integrations.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from pydantic import ValidationError

from limen.config.settings import KgSettings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient
from limen.knowledge.schema import GroundingQuery, GroundingResult, Passage

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


def _empty_result(query: GroundingQuery) -> GroundingResult:
    return GroundingResult(query=query, passages=())


class KgClient:
    """Async REST client for the KG sidecar's ``POST /query`` endpoint."""

    def __init__(self, settings: KgSettings) -> None:
        self._settings = settings

    @property
    def settings(self) -> KgSettings:
        return self._settings

    async def query(self, query: GroundingQuery) -> GroundingResult:
        """Ask the sidecar; return an empty result on any failure.

        The timeout is the per-call budget — the briefing must NEVER
        stall waiting for the KG, so this short ceiling is non-negotiable.
        """
        if not self._settings.enabled:
            return _empty_result(query)

        url = f"{self._settings.base_url.rstrip('/')}/query"
        api_token = (
            self._settings.api_token.get_secret_value()
            if self._settings.api_token is not None
            else None
        )
        headers: dict[str, str] = {"content-type": "application/json"}
        if api_token:
            headers["authorization"] = f"Bearer {api_token}"

        payload: dict[str, Any] = {
            "thread_id": self._settings.thread_id,
            "query": query.model_dump(mode="json"),
        }

        client = await SharedHttpClient.get()
        try:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=self._settings.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            _log.warning(
                "kg.query.timeout",
                error=str(exc),
                timeout_s=self._settings.timeout_seconds,
            )
            return _empty_result(query)
        except httpx.HTTPError as exc:
            _log.warning(
                "kg.query.http_error",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return _empty_result(query)
        except Exception as exc:
            _log.warning(
                "kg.query.unexpected_error",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return _empty_result(query)

        try:
            body = response.json()
        except (ValueError, httpx.DecodingError) as exc:
            _log.warning("kg.query.decode_error", error=str(exc))
            return _empty_result(query)

        return _coerce_passages(query, body)


def _coerce_passages(query: GroundingQuery, body: Any) -> GroundingResult:
    """Map the sidecar response into a typed :class:`GroundingResult`.

    The sidecar may evolve; we narrowly read the ``passages`` list +
    accept any item shape Pydantic can validate. Extra fields are
    discarded by the schema's ``extra=forbid`` per-item validator,
    so we filter known fields before constructing.
    """
    if not isinstance(body, dict):
        return _empty_result(query)
    items = body.get("passages") or []
    if not isinstance(items, list):
        return _empty_result(query)
    out: list[Passage] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = {
            "source": str(item.get("source", "")),
            "title": str(item.get("title", "")),
            "snippet": str(item.get("snippet", "")),
            "citation": str(item.get("citation", "")),
            "score": float(item.get("score", 0.0)),
        }
        try:
            out.append(Passage.model_validate(candidate))
        except ValidationError as exc:
            _log.debug("kg.query.passage_validation_error", error=str(exc))
            continue
    return GroundingResult(query=query, passages=tuple(out[: query.top_k]))


__all__ = ["KgClient"]
