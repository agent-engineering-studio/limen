"""Sequential workflow builder with conditional edges.

Compared to real MAF, this builder only handles **linear** + optional
**conditional** edges (one branch decision: include-or-skip). That's
exactly the shape Limen's V1 pipeline needs; concurrent sub-workflows
(e.g. an escalation fan-out) are explicit follow-ons gated outside the
linear pipeline.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from limen.agents.workflow_runtime.executor import Executor
from limen.agents.workflow_runtime.types import NodeExecutionRecord, WorkflowResult
from limen.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class _Step:
    executor: Executor
    predicate: Callable[[object], bool] | None = None  # None = always run


class WorkflowBuilder:
    """Build a sequential workflow node-by-node.

    Usage::

        wf = (WorkflowBuilder("landslide")
              .add(area_resolver)
              .add(static_factors)
              .add_if(lambda ctx: ctx.enable_insitu, sensor_fetch)
              .add(risk_scoring)
              .build())
        result = await wf.run(monitoring_ctx)
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._steps: list[_Step] = []

    def add(self, executor: Executor) -> WorkflowBuilder:
        self._steps.append(_Step(executor))
        return self

    def add_if(
        self,
        predicate: Callable[[object], bool],
        executor: Executor,
    ) -> WorkflowBuilder:
        """Add ``executor`` to be run only when ``predicate(ctx)`` is truthy."""
        self._steps.append(_Step(executor, predicate))
        return self

    def build(self) -> Workflow:
        return Workflow(self._name, tuple(self._steps))


class Workflow:
    """Compiled, immutable workflow ready to execute."""

    def __init__(self, name: str, steps: tuple[_Step, ...]) -> None:
        self._name = name
        self._steps = steps

    @property
    def name(self) -> str:
        return self._name

    @property
    def step_count(self) -> int:
        return len(self._steps)

    async def run(self, ctx: object) -> WorkflowResult:
        records: list[NodeExecutionRecord] = []
        current = ctx
        for step in self._steps:
            if step.predicate is not None and not step.predicate(current):
                log.debug("workflow.step.skip", workflow=self._name, node=step.executor.name)
                continue

            started_at = datetime.now(UTC)
            log.info(
                "workflow.step.start",
                workflow=self._name,
                node=step.executor.name,
            )
            try:
                returned = await step.executor.run(current)
                if returned is not None:
                    current = returned
                ok = True
                err: str | None = None
            except Exception as exc:  # pragma: no cover - exercised in error tests
                ok = False
                err = f"{type(exc).__name__}: {exc}"
                log.error(
                    "workflow.step.error",
                    workflow=self._name,
                    node=step.executor.name,
                    error=err,
                )
                finished_at = datetime.now(UTC)
                records.append(
                    NodeExecutionRecord(
                        name=step.executor.name,
                        started_at=started_at,
                        finished_at=finished_at,
                        duration_seconds=(finished_at - started_at).total_seconds(),
                        ok=False,
                        error=err,
                    )
                )
                raise
            finished_at = datetime.now(UTC)
            records.append(
                NodeExecutionRecord(
                    name=step.executor.name,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_seconds=(finished_at - started_at).total_seconds(),
                    ok=ok,
                    error=err,
                )
            )
            log.info(
                "workflow.step.done",
                workflow=self._name,
                node=step.executor.name,
                duration_s=records[-1].duration_seconds,
            )
        return WorkflowResult(context=current, nodes=records)


# Convenience type alias for documentation
ExecutorFactory = Callable[[], Awaitable[Executor]]
