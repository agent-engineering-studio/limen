"""``limen mcp-serve`` — start the limen-ops MCP server."""

from __future__ import annotations

import os

from limen.mcp.server import run_mcp_server


async def run() -> int:
    transport = os.getenv("LIMEN_MCP_TRANSPORT", "stdio").strip() or "stdio"
    return await run_mcp_server(transport=transport)


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
