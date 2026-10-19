"""La griglia di scuotimento di una ShakeMap INGV, letta per punto (#284).

`grid.xml` (formato ShakeMap 4, verificato il 19 ottobre 2026 su tre eventi):
un ``<grid_specification>`` con estremi e passo — che cambia da evento a
evento, da ~90 m ai Campi Flegrei a ~1 km altrove — e un ``<grid_data>`` di
righe ``LON LAT MMI PGA PGV …``, dal bordo nord verso sud, longitudine più
veloce. La PGA è in **percento di g**: qui diventa frazione di g.

È lo scuotimento che INGV stima con le stazioni e le sue leggi di
attenuazione: Limen non ne inventa una sua.
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from typing import Any

import numpy as np

_NS = re.compile(r"\{[^}]*\}")


@dataclass(frozen=True, slots=True)
class GrigliaPga:
    lon_min: float
    lat_max: float
    passo_lon: float
    passo_lat: float
    nlon: int
    nlat: int
    #: PGA in g, righe da nord a sud.
    pga_g: Any

    def pga_in(self, lon: float, lat: float) -> float | None:
        """La PGA del punto di griglia più vicino; ``None`` fuori dalla griglia."""
        colonna = round((lon - self.lon_min) / self.passo_lon)
        riga = round((self.lat_max - lat) / self.passo_lat)
        if not (0 <= colonna < self.nlon and 0 <= riga < self.nlat):
            return None
        return float(self.pga_g[riga, colonna])

    @property
    def riquadro(self) -> tuple[float, float, float, float]:
        """Ovest, sud, est, nord."""
        lon_max = self.lon_min + (self.nlon - 1) * self.passo_lon
        lat_min = self.lat_max - (self.nlat - 1) * self.passo_lat
        return (self.lon_min, lat_min, lon_max, self.lat_max)


class GrigliaNonValidaError(ValueError):
    """Il file non è una griglia ShakeMap leggibile."""


def leggi_griglia(xml: bytes) -> GrigliaPga:
    """Solleva solo :class:`GrigliaNonValidaError`: una griglia storta non deve
    fermare la sincronizzazione degli altri eventi."""
    try:
        return _leggi(xml)
    except GrigliaNonValidaError:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise GrigliaNonValidaError(f"griglia illeggibile: {exc}") from exc


#: Come ShakeMap scrive l'unità della PGA: percento di g.
_UNITA_PGA = {"%g", "pctg"}


def _leggi(xml: bytes) -> GrigliaPga:
    import xml.etree.ElementTree as ET

    try:
        radice = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise GrigliaNonValidaError("XML non valido") from exc
    figli = {_NS.sub("", el.tag): el for el in radice}
    spec = figli.get("grid_specification")
    dati = figli.get("grid_data")
    if spec is None or dati is None or not dati.text:
        raise GrigliaNonValidaError("manca grid_specification o grid_data")
    campi: dict[str, tuple[int, str]] = {
        el.get("name", ""): (int(el.get("index", "0")) - 1, el.get("units", ""))
        for el in radice
        if _NS.sub("", el.tag) == "grid_field"
    }
    if "PGA" not in campi or "LON" not in campi or "LAT" not in campi:
        raise GrigliaNonValidaError("mancano LON, LAT o PGA")
    if campi["PGA"][1] not in _UNITA_PGA:
        raise GrigliaNonValidaError(f"PGA in {campi['PGA'][1]!r}, attesa in percento di g")
    nlon, nlat = int(spec.get("nlon", "")), int(spec.get("nlat", ""))
    lon_min, lon_max = float(spec.get("lon_min", "")), float(spec.get("lon_max", ""))
    lat_min, lat_max = float(spec.get("lat_min", "")), float(spec.get("lat_max", ""))
    if (
        nlon < 2
        or nlat < 2
        or not all(math.isfinite(v) for v in (lon_min, lon_max, lat_min, lat_max))
    ):
        raise GrigliaNonValidaError("grid_specification non valida")
    valori = np.loadtxt(io.StringIO(dati.text), dtype=float, ndmin=2)
    if valori.shape[0] != nlon * nlat:
        raise GrigliaNonValidaError(f"{valori.shape[0]} righe, attese {nlon * nlat}")
    # Il formato dice: dal bordo nord, longitudine più veloce. Lo si controlla
    # invece di presumerlo, perché un ordine diverso sposterebbe ogni valore.
    i_lon, i_lat = campi["LON"][0], campi["LAT"][0]
    passo_lon = (lon_max - lon_min) / (nlon - 1)
    passo_lat = (lat_max - lat_min) / (nlat - 1)
    if not (
        math.isclose(valori[0, i_lon], lon_min, abs_tol=passo_lon / 2)
        and math.isclose(valori[0, i_lat], lat_max, abs_tol=passo_lat / 2)
        and math.isclose(valori[1, i_lon], lon_min + passo_lon, abs_tol=passo_lon / 2)
    ):
        raise GrigliaNonValidaError("righe non nell'ordine nord→sud, ovest→est")
    return GrigliaPga(
        lon_min=lon_min,
        lat_max=lat_max,
        passo_lon=passo_lon,
        passo_lat=passo_lat,
        nlon=nlon,
        nlat=nlat,
        pga_g=valori[:, campi["PGA"][0]].reshape(nlat, nlon) / 100.0,
    )


__all__ = ["GrigliaNonValidaError", "GrigliaPga", "leggi_griglia"]
