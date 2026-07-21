"""A2A Agent Card — the public capability descriptor.

Served at ``/.well-known/agent-card.json`` (and the legacy ``agent.json``).
Declares the JSON-RPC endpoint, streaming + push capabilities, and the skills
from :mod:`limen.a2a.skills`. The absolute URL is derived from the request base
(or ``A2A_PUBLIC_URL`` behind a reverse proxy).
"""

from __future__ import annotations

from typing import Any

from limen import __version__
from limen.a2a.skills import SKILLS

PROTOCOL_VERSION = "0.2.5"


def build_agent_card(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "name": "Limen",
        "description": (
            "Monitoraggio multi-fattore del rischio frane e inondazioni "
            "(fiumi, laghi, mare) sul territorio italiano. Espone query di sola "
            "lettura sull'ultimo assessment deterministico: quadro nazionale, "
            "sintesi per regione, celle a rischio, scomposizione per cella, allerte."
        ),
        "url": f"{base}/a2a",
        "preferredTransport": "JSONRPC",
        "version": __version__,
        "provider": {
            "organization": "Agent Engineering Studio",
            "url": "https://github.com/agent-engineering-studio/limen",
        },
        "capabilities": {
            "streaming": True,
            "pushNotifications": True,
            "stateTransitionHistory": False,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["application/json", "text/plain"],
        "documentationUrl": (
            "https://github.com/agent-engineering-studio/limen/blob/main/docs/openclaw.md"
        ),
        "skills": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "tags": list(s.tags),
                "examples": list(s.examples),
            }
            for s in SKILLS.values()
        ],
    }
