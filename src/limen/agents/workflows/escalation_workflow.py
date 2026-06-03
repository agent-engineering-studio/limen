"""Escalation sub-workflow placeholder (V1.5+).

In V1.5 the EscalationGate will branch a *concurrent* sub-workflow
when at least one cell crosses the High/VeryHigh threshold: a second
RiskAnalyst peer reviews the diagnosis, an evidence-collector persists
corroborating snapshots (most-recent INGV event, most-recent IFFI
near-by, EFFIS perimeters within X km), and an authority-routing
executor decides downstream channels.

For V1 this module exposes a no-op factory so callers can already
``from limen.agents.workflows.escalation_workflow import
build_escalation_workflow`` without crashing — the function returns
``None`` and the gate stays a pass-through.
"""

from __future__ import annotations


def build_escalation_workflow() -> None:
    """Placeholder; returns ``None`` in V1."""
    return None
