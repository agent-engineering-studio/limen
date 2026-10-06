"""Ogni ora, il bollettino di criticità della Protezione Civile.

Esce entro le 16:00 e a volte si aggiorna dopo: un controllo orario costa tre
chiamate piccole a GitHub e non riscrive niente se il bollettino non è
cambiato.
"""

from __future__ import annotations

from typing import Any

from limen.api.dependencies import AppDependencies
from limen.integrations.dpc.sync_bollettini import run_sync_bollettini


async def run_dpc_bollettini(deps: AppDependencies) -> dict[str, Any]:  # noqa: ARG001
    return await run_sync_bollettini()
