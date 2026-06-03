"""Runtime types used by the workflow builder + executors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class NodeExecutionRecord:
    """Per-executor record kept so callers can audit each step."""

    name: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    ok: bool
    error: str | None = None
    notes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowResult:
    """Outcome of one workflow execution."""

    context: Any  # MonitoringContext — circular-import-safe via Any
    nodes: list[NodeExecutionRecord]

    @property
    def ok(self) -> bool:
        return all(n.ok for n in self.nodes)
