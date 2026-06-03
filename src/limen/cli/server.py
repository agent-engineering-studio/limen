"""``limen serve`` — start uvicorn around the FastAPI app."""

from __future__ import annotations

from limen.config.settings import get_settings
from limen.core.logging import get_logger

log = get_logger(__name__)


async def run() -> int:
    """Start uvicorn programmatically (Async-friendly).

    Returns 0 when the server exits cleanly. ``limen serve`` is a thin
    wrapper around this so the CLI dispatcher (which uses
    :func:`asyncio.run`) can manage signals consistently.
    """
    import uvicorn

    settings = get_settings()
    log.info(
        "serve.start",
        host=settings.api.host,
        port=settings.api.port,
        log_level=settings.log_level,
        llm_provider_hint="resolved at lifespan",
    )

    config = uvicorn.Config(
        "limen.api.main:factory",
        factory=True,
        host=settings.api.host,
        port=settings.api.port,
        log_level=settings.log_level.lower(),
        access_log=True,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    server = uvicorn.Server(config)
    await server.serve()
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
