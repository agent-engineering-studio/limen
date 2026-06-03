"""Shared HTTP utilities for external integrations.

All outbound HTTP must go through:

* :class:`SharedHttpClient` — a singleton-style ``httpx.AsyncClient`` with
  sensible defaults for read/connect timeouts and connection pooling.
* :data:`RETRY_POLICY` — a ``tenacity`` async retry policy: 4 attempts,
  exponential backoff with multiplier=2 and cap=60 s, retrying on
  network errors and 5xx / 429 responses.
* :func:`degrade_gracefully` — a decorator that, on terminal failure,
  logs the incident and returns the caller-supplied *neutral result*
  (e.g. an empty list, ``None``, an "unknown" enum value) instead of
  re-raising. Use it on *operations* that the scoring workflow can
  tolerate the loss of — not on writes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from limen.core.logging import get_logger

log = get_logger(__name__)

# Retryable HTTP failures: transport errors, timeouts, and server-side 5xx / 429.
_RETRYABLE_EXC: tuple[type[BaseException], ...] = (
    httpx.TransportError,
    httpx.TimeoutException,
    httpx.HTTPStatusError,
)


def _is_retryable_status(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status >= 500 or status == 429
    return True


def make_retry_policy(
    *,
    max_attempts: int = 4,
    multiplier: float = 2.0,
    max_wait: float = 60.0,
) -> AsyncRetrying:
    """Build an :class:`AsyncRetrying` policy with Limen's defaults.

    Per Phase-2 spec: 4 attempts total, exponential backoff capped at 60 s,
    retries on transport / timeout errors and 5xx / 429 responses.
    """
    return AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=multiplier, max=max_wait),
        retry=retry_if_exception_type(_RETRYABLE_EXC),
        reraise=True,
    )


RETRY_POLICY = make_retry_policy()


class SharedHttpClient:
    """Lazily-initialised shared ``httpx.AsyncClient``.

    Held at module level so all integrations share connection pooling.
    Call :meth:`aclose` once at process shutdown.
    """

    _instance: httpx.AsyncClient | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def get(cls) -> httpx.AsyncClient:
        if cls._instance is not None:
            return cls._instance
        async with cls._lock:
            if cls._instance is None:
                cls._instance = httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0),
                    limits=httpx.Limits(
                        max_connections=64,
                        max_keepalive_connections=16,
                        keepalive_expiry=30.0,
                    ),
                    follow_redirects=True,
                    headers={
                        "User-Agent": "Limen/0.1 (+https://github.com/agent-engineering-studio/limen)"
                    },
                )
            return cls._instance

    @classmethod
    async def aclose(cls) -> None:
        if cls._instance is not None:
            await cls._instance.aclose()
            cls._instance = None


async def fetch_with_retry(
    method: str,
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """HTTP request wrapped in :data:`RETRY_POLICY`.

    Raises ``httpx.HTTPStatusError`` on 4xx (non-retryable) only after the
    retry policy has given up — callers can therefore distinguish "client
    bug" from "transient server hiccup".
    """
    cli = client or await SharedHttpClient.get()

    async for attempt in make_retry_policy():
        with attempt:
            response = await cli.request(method, url, **kwargs)
            if response.status_code >= 400:
                # raise_for_status produces an HTTPStatusError; we then let
                # the retry policy decide whether to retry (5xx/429) or give up.
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    if _is_retryable_status(e):
                        raise
                    return response
            return response

    raise RuntimeError("fetch_with_retry: retry loop exited without returning")


def degrade_gracefully[T, **P](
    *,
    neutral: T,
    label: str,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorate an async function so that terminal failures return ``neutral``.

    Use on *reads* that the workflow can tolerate losing — never on writes.
    A structured ``integration.degraded`` log line records the failure for
    observability so silent degradation is still visible.

    Args:
        neutral: Value to return on terminal failure (e.g. ``[]``, ``None``).
        label:   Short identifier of the operation (e.g. ``"openmeteo.snapshot"``).
    """

    def decorator(fn: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return await fn(*args, **kwargs)
            except (httpx.HTTPError, RetryError, TimeoutError, OSError) as exc:
                log.warning(
                    "integration.degraded",
                    label=label,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                return neutral

        wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
        wrapper.__name__ = getattr(fn, "__name__", "wrapper")
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator
