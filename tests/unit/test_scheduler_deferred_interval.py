"""The interval jobs must not fire at boot (event-loop stampede → slow /ready)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from limen.api.jobs.registration import _deferred_interval


def test_first_fire_is_one_interval_out_not_immediate() -> None:
    before = datetime.now(UTC)
    trigger = _deferred_interval(minutes=60)
    first = trigger.next()
    assert first is not None
    # first fire is a full interval in the future, i.e. NOT at boot
    assert first >= before + timedelta(minutes=60)


def test_cadence_is_preserved_after_the_deferred_first_fire() -> None:
    trigger = _deferred_interval(minutes=60)
    first = trigger.next()
    second = trigger.next()
    assert first is not None and second is not None
    assert second - first == timedelta(minutes=60)


def test_seconds_unit_defers_too() -> None:
    before = datetime.now(UTC)
    trigger = _deferred_interval(seconds=30)
    first = trigger.next()
    assert first is not None
    assert first >= before + timedelta(seconds=30)
