from pathlib import Path

import pytest

from limen.report.snapshot import cell_svg_fallback, project_ring, render_cluster_png


def test_project_ring_maps_into_canvas() -> None:
    ring = [(16.0, 41.0), (16.1, 41.0), (16.1, 41.1), (16.0, 41.1)]
    bbox = (16.0, 41.0, 16.1, 41.1)
    pts = project_ring(ring, bbox=bbox, width=400, height=400)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert min(xs) >= 0 and max(xs) <= 400
    assert min(ys) >= 0 and max(ys) <= 400


def test_svg_fallback_contains_polygon_and_color() -> None:
    svg = cell_svg_fallback(
        [
            (
                [(16.0, 41.0), (16.1, 41.0), (16.1, 41.1), (16.0, 41.1)],
                "#bd0026",
            )
        ],
        bbox=(16.0, 41.0, 16.1, 41.1),
        width=400,
        height=400,
    )
    assert svg.startswith("<svg")
    assert "polygon" in svg
    assert "#bd0026" in svg


async def test_render_falls_back_to_svg_on_fetch_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _boom(method: str, url: str, **kwargs: object) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr("limen.integrations._http.fetch_with_retry", _boom)

    out = tmp_path / "cluster-0.png"
    ok = await render_cluster_png(
        out_path=out,
        bbox=(16.0, 41.0, 16.1, 41.1),
        colored_cells=[
            (
                '{"type":"Polygon","coordinates":'
                "[[[16,41],[16.1,41],[16.1,41.1],[16,41.1],[16,41]]]}",
                "#bd0026",
            )
        ],
        basemap_url_template="https://example.invalid/{z}/{x}/{y}.png",
        attribution="test",
    )
    assert ok is False
    assert not out.exists()
    assert out.with_suffix(".svg").exists()


async def test_render_never_raises_on_malformed_geom(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _boom(method: str, url: str, **kwargs: object) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr("limen.integrations._http.fetch_with_retry", _boom)

    out = tmp_path / "cluster-0.png"
    ok = await render_cluster_png(
        out_path=out,
        bbox=(16.0, 41.0, 16.1, 41.1),
        colored_cells=[
            ("not-json", "#bd0026"),
            ('{"type":"Point","coordinates":[16,41]}', "#bd0026"),
        ],
        basemap_url_template="https://example.invalid/{z}/{x}/{y}.png",
        attribution="test",
    )
    assert isinstance(ok, bool)
    assert out.with_suffix(".svg").exists()
