"""Snapshot mappa per cluster: basemap raster + celle colorate -> PNG.

Fallback SVG puro se Pillow manca o il fetch tile fallisce (degradazione
neutra: il report esce sempre). Attribuzione basemap impressa nel PNG.
"""

from __future__ import annotations

import json
from pathlib import Path

from limen.core.logging import get_logger
from limen.report.geo import (
    TILE,
    lonlat_to_pixel,
    padded_bbox,
    tile_range_for_bbox,
    zoom_for_bbox,
)

log = get_logger(__name__)

_W = 800
_H = 600


def project_ring(
    ring: list[tuple[float, float]],
    *,
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> list[tuple[float, float]]:
    """Proietta un anello lon/lat in pixel del canvas (Web Mercator lineare).

    Lo zoom di riferimento (12) è hardcoded ma irrilevante: ``lonlat_to_pixel``
    è affine nello zoom, quindi la normalizzazione a rapporto è scale-invariant
    — qualunque zoom fisso dà lo stesso risultato e NON deve coincidere con
    quello di ``zoom_for_bbox``.
    """
    minx, miny, maxx, maxy = padded_bbox(bbox)
    x0, y0 = lonlat_to_pixel(minx, maxy, 12)
    x1, y1 = lonlat_to_pixel(maxx, miny, 12)
    span_x = (x1 - x0) or 1.0
    span_y = (y1 - y0) or 1.0
    out: list[tuple[float, float]] = []
    for lon, lat in ring:
        px, py = lonlat_to_pixel(lon, lat, 12)
        out.append(((px - x0) / span_x * width, (py - y0) / span_y * height))
    return out


def cell_svg_fallback(
    cells: list[tuple[list[tuple[float, float]], str]],
    *,
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#eef1f4"/>',
    ]
    for ring, color in cells:
        pts = project_ring(ring, bbox=bbox, width=width, height=height)
        pstr = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(
            f'<polygon points="{pstr}" fill="{color}" fill-opacity="0.65" '
            f'stroke="#333" stroke-width="0.5"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _rings_from_geojson(geom_json: str) -> list[list[tuple[float, float]]]:
    geom = json.loads(geom_json)
    gtype = geom["type"]
    coords = geom["coordinates"]
    if gtype == "Polygon":
        return [[(x, y) for x, y in coords[0]]]
    if gtype == "MultiPolygon":
        return [[(x, y) for x, y in poly[0]] for poly in coords]
    raise ValueError(f"unsupported geometry type: {gtype}")


async def render_cluster_png(
    *,
    out_path: Path,
    bbox: tuple[float, float, float, float],
    colored_cells: list[tuple[str, str]],  # (geom_json, hex_color)
    basemap_url_template: str,
    attribution: str,
) -> bool:
    """Compone basemap raster + celle in un PNG. Ritorna True se PNG scritto,
    False se ha scritto il fallback SVG (accanto, con estensione .svg).
    NON solleva mai: qualunque errore ⇒ fallback SVG."""
    cells_rings: list[tuple[list[tuple[float, float]], str]] = []
    for geom_json, color in colored_cells:
        try:
            rings = _rings_from_geojson(geom_json)
        except (ValueError, KeyError, TypeError) as exc:
            log.info("report.snapshot.bad_geom", error=str(exc), geom=geom_json[:80])
            continue
        for ring in rings:
            cells_rings.append((ring, color))

    try:
        from io import BytesIO

        from PIL import Image, ImageDraw

        from limen.integrations._http import fetch_with_retry

        pb = padded_bbox(bbox)
        zoom = zoom_for_bbox(bbox, width_px=_W, height_px=_H)
        tx0, ty0, tx1, ty1 = tile_range_for_bbox(pb, zoom)
        canvas = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE), "#eef1f4")
        pasted = 0
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                url = basemap_url_template.format(z=zoom, x=tx, y=ty)
                resp = await fetch_with_retry("GET", url)
                if resp.status_code >= 400 or not resp.content:
                    continue
                tile_img = Image.open(BytesIO(resp.content)).convert("RGB")
                canvas.paste(tile_img, ((tx - tx0) * TILE, (ty - ty0) * TILE))
                pasted += 1
        if pasted == 0:
            log.info("report.snapshot.no_basemap", out=str(out_path))

        px_min, py_min = lonlat_to_pixel(pb[0], pb[3], zoom)
        px_max, py_max = lonlat_to_pixel(pb[2], pb[1], zoom)
        left, top = px_min - tx0 * TILE, py_min - ty0 * TILE
        cropped = canvas.crop(
            (int(left), int(top), int(left + (px_max - px_min)), int(top + (py_max - py_min)))
        ).resize((_W, _H))

        overlay = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for ring, color in cells_rings:
            pts = project_ring(ring, bbox=bbox, width=_W, height=_H)
            rgb = (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))
            draw.polygon(pts, fill=(*rgb, 165), outline=(60, 60, 60, 255))
        cropped = cropped.convert("RGBA")
        cropped.alpha_composite(overlay)
        draw2 = ImageDraw.Draw(cropped)
        draw2.text((6, _H - 16), attribution, fill=(60, 60, 60, 255))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.convert("RGB").save(out_path, "PNG")
        return True
    except Exception as exc:  # degradazione neutra: mai sollevare
        log.info("report.snapshot.degraded", error=str(exc), out=str(out_path))
        svg = cell_svg_fallback(cells_rings, bbox=bbox, width=_W, height=_H)
        svg_path = out_path.with_suffix(".svg")
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(svg, encoding="utf-8")
        return False
