"""A2A (Agent2Agent) server surface for Limen.

Exposes the read-only ``limen-ops`` skills to other agents over JSON-RPC 2.0
with streaming (SSE) and push notifications. Agent Card at
``/.well-known/agent-card.json``; JSON-RPC endpoint at ``/a2a``. Scores are
never altered here — A2A is query interop, mutating stays MCP + admin token.
"""

from limen.a2a.card import build_agent_card
from limen.a2a.service import A2AService
from limen.a2a.skills import SKILLS

__all__ = ["SKILLS", "A2AService", "build_agent_card"]
