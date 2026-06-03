"""Executor base + ``@handler`` decorator.

In real MAF, ``@handler`` registers a method with a specific message
type for routing. Limen's sequential workflow only carries one message
type — :class:`MonitoringContext` — so the decorator is a no-op marker
here. Marking the canonical method keeps signatures swap-ready for when
the upstream SDK stabilises.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any


def handler[T: Callable[..., Awaitable[Any]]](fn: T) -> T:
    """Mark a method as the executor's canonical entry point.

    Currently a no-op. Reserved so the same source compiles against a
    future MAF where ``@handler`` attaches dispatch metadata.
    """
    fn.__limen_handler__ = True  # type: ignore[attr-defined]
    return fn


class Executor(ABC):
    """Base class for every workflow node.

    Subclasses MUST implement :meth:`run`. The default ``name`` is the
    subclass's class name; override at construction for clearer logs.
    """

    def __init__(self, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    @handler
    async def run(self, ctx: Any) -> Any:
        """Execute one step over ``ctx`` and return the (possibly updated) context."""
