"""APScheduler `geodata-export` job — gated, fail-soft."""

from __future__ import annotations

from typing import Any

import pytest

from limen.api.jobs.geodata_export import run_geodata_export_job


class _Settings:
    """Minimal duck-typed settings — only the fields the job reads."""

    def __init__(self, *, enabled: bool, dsn: str = "postgresql://op:op@localhost/op"):
        from dataclasses import dataclass

        @dataclass
        class _Geodata:
            enable_periodic_export: bool = enabled
            export_features_hours: int = 168

        @dataclass
        class _Db:
            connection_string: str = dsn

        self.geodata = _Geodata()
        self.db = _Db()


class _Deps:
    def __init__(self, *, enabled: bool):
        self.settings = _Settings(enabled=enabled)


@pytest.mark.asyncio
async def test_job_no_op_when_disabled() -> None:
    rc = await run_geodata_export_job(_Deps(enabled=False))  # type: ignore[arg-type]
    assert rc == 0


@pytest.mark.asyncio
async def test_job_invokes_exporter_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When enabled, the job calls the geodata exporter with the operational DSN."""
    calls: list[dict[str, Any]] = []

    async def _fake_export(*, operational_dsn: str) -> int:
        calls.append({"dsn": operational_dsn})
        return 0

    # Patch the lazy import path the job uses.
    import geodata.exports.features as features_mod

    monkeypatch.setattr(features_mod, "export_cell_features", _fake_export)

    rc = await run_geodata_export_job(_Deps(enabled=True))  # type: ignore[arg-type]
    assert rc == 0
    assert calls == [{"dsn": "postgresql://op:op@localhost/op"}]


@pytest.mark.asyncio
async def test_job_swallows_exporter_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A crashing exporter must NOT propagate up to the scheduler."""

    async def _broken(*, operational_dsn: str) -> int:
        raise RuntimeError("geodata DB unreachable")

    import geodata.exports.features as features_mod

    monkeypatch.setattr(features_mod, "export_cell_features", _broken)

    rc = await run_geodata_export_job(_Deps(enabled=True))  # type: ignore[arg-type]
    # Failure logged + counted, but the job returns 0 so APScheduler keeps
    # the schedule alive for the next tick.
    assert rc == 0
