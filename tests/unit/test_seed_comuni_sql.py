"""seed-comuni: the SELECT against the GeoServer source is well-formed."""

from __future__ import annotations

from limen.cli.seed_comuni import _SRC_SQL


def test_src_sql_selects_expected_columns() -> None:
    s = _SRC_SQL.lower()
    assert "pro_com_t" in s and "comune" in s
    assert "st_asbinary" in s and "st_multi" in s
    assert "com01012023_g" in s
