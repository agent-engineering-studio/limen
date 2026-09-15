"""Fact-checking labelling + metrics — pure, no DB (#17)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from limen.report.verify import _read_manifest, _write_report, summarize_build, verify_build


def _summarize(**over: object):
    base: dict[str, object] = {
        "build_id": "2026-03-03T0600Z",
        "valuation_time": "2026-03-03T06:00:00+00:00",
        "horizon_h": 72,
        "shown_level": "High",
        "clusters": [
            {"cluster_id": 0, "aoi_id": "it-puglia", "cell_ids": ["c1", "c2"]},
            {"cluster_id": 1, "aoi_id": "it-puglia", "cell_ids": ["c9"]},
        ],
        "matched_by_cluster": {0: ["e1"]},  # zone 0 hit, zone 1 no match
        "aoi_event_ids": {"e1", "e2"},  # e2 is in the AOI but no zone → miss
        "lead_hours_by_event": {"e1": 30.0},
        "min_dist_by_cluster": {0: 450.0},
        "verified_at": "2026-03-07T06:00:00+00:00",
    }
    return summarize_build(**{**base, **over})  # type: ignore[arg-type]


def test_zone_with_event_is_hit_without_is_false_alarm() -> None:
    out = _summarize()
    by_id = {z.cluster_id: z for z in out.zones}
    assert by_id[0].outcome == "hit"
    assert by_id[0].matched_event_ids == ["e1"]
    assert by_id[0].min_distance_m == 450.0
    assert by_id[1].outcome == "false_alarm"


def test_event_outside_all_zones_is_a_miss() -> None:
    out = _summarize()
    assert out.miss_event_ids == ["e2"]


def test_pod_far_and_lead_time() -> None:
    out = _summarize()
    # POD = detected events (e1) / all AOI events (e1,e2) = 0.5
    assert out.pod == 0.5
    # FAR = false-alarm zones (1) / all zones (2) = 0.5
    assert out.far == 0.5
    assert out.mean_lead_time_h == 30.0


def test_no_events_degrades_to_zero_not_error() -> None:
    out = _summarize(matched_by_cluster={}, aoi_event_ids=set(), lead_hours_by_event={})
    assert out.pod == 0.0
    assert all(z.outcome == "false_alarm" for z in out.zones)
    assert out.miss_event_ids == []
    assert out.mean_lead_time_h is None


def test_verify_settings_defaults() -> None:
    from limen.config.settings import Settings

    v = Settings().verify
    assert v.match_radius_m == 2000.0
    assert v.horizon_hours == 72
    assert v.grace_hours == 24


# ---------------------------------------------------------------------------
# verify_build: la connessione e' un parametro, quindi si prova senza DB (#116)
# ---------------------------------------------------------------------------

T0 = datetime(2026, 3, 3, 6, tzinfo=UTC)


class _FakeConn:
    """Risponde alle due query di `verify_build` con righe preparate.

    La prima (per zona) e' riconoscibile dal raggio fra i parametri; la
    seconda (eventi dell'AOI) no. Basta per esercitare tutto il ramo di
    calcolo senza un PostGIS.
    """

    def __init__(self, zone_rows: list[dict[str, object]], aoi_rows: list[dict[str, object]]):
        self._zone = zone_rows
        self._aoi = aoi_rows
        self.calls = 0

    async def fetch(self, sql: str, *args: object) -> list[dict[str, object]]:
        self.calls += 1
        return self._zone if len(args) == 4 else self._aoi


def _build(tmp_path: Path, manifest: dict[str, object] | None) -> Path:
    build = tmp_path / "2026-03-03T0600Z"
    build.mkdir()
    if manifest is not None:
        (build / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return build


def _manifest(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "valuation_time": T0.isoformat(),
        "shown_level": "High",
        "clusters": [
            {"cluster_id": 0, "aoi_id": "it-puglia", "cell_ids": ["c1"]},
            {"cluster_id": 1, "aoi_id": "it-puglia", "cell_ids": []},
        ],
    }
    base.update(over)
    return base


def test_read_manifest_missing_or_malformed_is_none(tmp_path: Path) -> None:
    assert _read_manifest(tmp_path) is None
    (tmp_path / "manifest.json").write_text("{non json", encoding="utf-8")
    assert _read_manifest(tmp_path) is None


async def test_verify_build_matches_zones_and_writes_the_outcome(tmp_path: Path) -> None:
    build = _build(tmp_path, _manifest())
    conn = _FakeConn(
        zone_rows=[{"event_id": "e1", "dist_m": 320.0, "event_time": T0 + timedelta(hours=30)}],
        aoi_rows=[{"event_id": "e1"}, {"event_id": "e2"}],
    )

    outcome = await verify_build(
        conn, build, horizon_h=72, grace_h=24, radius_m=1000.0, now=T0 + timedelta(days=5)
    )

    assert outcome is not None
    # La zona senza celle non interroga il database: una query per la zona
    # piena, una per gli eventi dell'AOI.
    assert conn.calls == 2
    assert outcome.pod == pytest.approx(0.5)  # e1 visto, e2 mancato
    written = json.loads((build / "verification.json").read_text(encoding="utf-8"))
    assert written["build_id"] == "2026-03-03T0600Z"


async def test_verify_build_is_idempotent(tmp_path: Path) -> None:
    """Un build gia' verificato non si riverifica: il file di esito e' la prova."""
    build = _build(tmp_path, _manifest())
    (build / "verification.json").write_text("{}", encoding="utf-8")
    conn = _FakeConn([], [])
    assert (await verify_build(conn, build, horizon_h=72, grace_h=24, radius_m=1.0, now=T0)) is None
    assert conn.calls == 0


async def test_verify_build_waits_until_the_horizon_has_passed(tmp_path: Path) -> None:
    """Verificare prima che l'orizzonte sia trascorso conterebbe come "mancati"
    eventi che non hanno ancora avuto il tempo di accadere."""
    build = _build(tmp_path, _manifest())
    conn = _FakeConn([], [])
    too_early = T0 + timedelta(hours=72 + 24) - timedelta(minutes=1)
    assert (
        await verify_build(conn, build, horizon_h=72, grace_h=24, radius_m=1.0, now=too_early)
    ) is None
    assert conn.calls == 0


async def test_verify_build_skips_a_manifest_without_valuation_time(tmp_path: Path) -> None:
    build = _build(tmp_path, _manifest(valuation_time=""))
    assert (
        await verify_build(_FakeConn([], []), build, horizon_h=1, grace_h=0, radius_m=1.0, now=T0)
    ) is None


async def test_verify_build_accepts_a_naive_valuation_time(tmp_path: Path) -> None:
    """Un manifest vecchio senza fuso non deve far esplodere il confronto con
    `now`, che e' aware."""
    build = _build(tmp_path, _manifest(valuation_time="2026-03-03T06:00:00"))
    outcome = await verify_build(
        _FakeConn([], []), build, horizon_h=1, grace_h=0, radius_m=1.0, now=T0 + timedelta(days=1)
    )
    assert outcome is not None


def test_write_report_lists_builds_and_handles_none(tmp_path: Path) -> None:
    outcome = _summarize()
    path = _write_report([outcome], out_dir=tmp_path, now=T0)
    text = path.read_text(encoding="utf-8")
    assert path.name == "verification_2026-03-03.md"
    assert "`2026-03-03T0600Z`" in text

    empty = _write_report([], out_dir=tmp_path / "vuoto", now=T0)
    assert "nessun build oltre l'orizzonte" in empty.read_text(encoding="utf-8")
