from limen.report.geo import lonlat_to_pixel, tile_range_for_bbox, zoom_for_bbox


def test_lonlat_to_pixel_origin() -> None:
    x, y = lonlat_to_pixel(-180.0, 85.0511287798066, zoom=0)
    assert round(x) == 0
    assert round(y) == 0


def test_lonlat_to_pixel_zoom1_center() -> None:
    x, y = lonlat_to_pixel(0.0, 0.0, zoom=1)
    assert round(x) == 256
    assert round(y) == 256


def test_tile_range_covers_bbox() -> None:
    z = zoom_for_bbox((16.0, 41.0, 16.2, 41.2), width_px=800, height_px=600)
    (x0, y0, x1, y1) = tile_range_for_bbox((16.0, 41.0, 16.2, 41.2), z)
    assert x0 <= x1 and y0 <= y1
    assert 0 <= z <= 19


def test_zoom_for_bbox_clamps_to_zero_for_small_canvas() -> None:
    z = zoom_for_bbox((-180.0, -85.0, 180.0, 85.0), width_px=300, height_px=300)
    assert z == 0
