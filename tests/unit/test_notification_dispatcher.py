"""NotificationDispatcher — parallel + per-channel exception isolation."""

from __future__ import annotations

from datetime import UTC, datetime

from limen.config.settings import NotificationsSettings
from limen.core.models.risk import RiskLevel
from limen.notifications.base import AlertPayload, NotificationChannel
from limen.notifications.dispatcher import (
    NotificationDispatcher,
    build_default_dispatcher,
)


def _payload() -> AlertPayload:
    return AlertPayload(
        aoi_id="it-puglia",
        max_level=RiskLevel.High,
        max_score=0.7,
        cells=[],
        summary_it="x",
        map_url=None,
        pipeline_version="v1-deterministic",
        dispatched_at=datetime.now(UTC),
    )


class _OkChannel(NotificationChannel):
    name = "ok"
    is_enabled = True

    def __init__(self) -> None:
        self.calls = 0

    async def send(self, payload: AlertPayload) -> bool:
        self.calls += 1
        return True


class _FailChannel(NotificationChannel):
    name = "fail"
    is_enabled = True

    async def send(self, payload: AlertPayload) -> bool:
        return False


class _RaisingChannel(NotificationChannel):
    name = "raises"
    is_enabled = True

    async def send(self, payload: AlertPayload) -> bool:
        raise RuntimeError("boom")


async def test_dispatcher_runs_every_channel_and_collects_outcomes() -> None:
    ok = _OkChannel()
    dispatcher = NotificationDispatcher([ok, _FailChannel()])
    outcomes = await dispatcher.dispatch(_payload())
    assert outcomes == {"ok": True, "fail": False}
    assert ok.calls == 1


async def test_dispatcher_isolates_raising_channel() -> None:
    """Acceptance criterion §1: one channel raising MUST NOT abort the others."""
    ok = _OkChannel()
    dispatcher = NotificationDispatcher([ok, _RaisingChannel()])
    outcomes = await dispatcher.dispatch(_payload())
    assert outcomes == {"ok": True, "raises": False}
    assert ok.calls == 1


async def test_dispatcher_with_no_channels_returns_empty() -> None:
    dispatcher = NotificationDispatcher([])
    outcomes = await dispatcher.dispatch(_payload())
    assert outcomes == {}


async def test_build_default_dispatcher_empty_settings() -> None:
    """No enabled_channels → empty dispatcher (silent fallback per §3)."""
    dispatcher = build_default_dispatcher(NotificationsSettings())
    assert dispatcher.channel_names == []


async def test_build_default_dispatcher_constructs_listed_channels() -> None:
    settings = NotificationsSettings.model_validate({"enabled_channels": ["telegram", "mqtt"]})
    dispatcher = build_default_dispatcher(settings)
    assert sorted(dispatcher.channel_names) == ["mqtt", "telegram"]
    # No creds configured → both report is_enabled=False (silent no-op)
    assert dispatcher.enabled_names == []
