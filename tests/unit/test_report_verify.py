"""Fact-checking labelling + metrics — pure, no DB (#17)."""

from __future__ import annotations

from limen.report.verify import summarize_build


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
