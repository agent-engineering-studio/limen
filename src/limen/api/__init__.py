"""FastAPI HTTP host for Limen.

A thin shell over the Prompt-4 workflow and the Prompt-1 repos: no
business logic lives in endpoints. The :func:`build_app` factory takes
an optional :class:`AppDependencies` so tests can inject doubles
(e.g. a :class:`StubLlmClientFactory`).
"""

from limen.api.dependencies import AppDependencies
from limen.api.main import build_app, build_app_with_deps

__all__ = ["AppDependencies", "build_app", "build_app_with_deps"]
