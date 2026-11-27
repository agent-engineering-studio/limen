"""I rapporti radar di ``copernicus-ems`` sulle mappe EMS, letti come file (#713).

Accanto a ogni coppia Sentinel-1 di un prodotto la libreria scrive
``<stem>_quality.json`` (il verdetto: «coherent», «to check», «not
assessable») e ``<stem>_agreement.json`` con il suo ``.geojson`` (dove mappa e
radar concordano, per classe). La versione della libreria fissata in Limen non
ha ancora quei moduli: qui si legge il **formato dei file**, non si importa
niente.

Le regole del proprietario della libreria, che valgono anche qui:

* il verdetto è uno screening: «to check» vuol dire «riguardala», mai «è
  sbagliata»;
* ``candidate`` è acqua possibile e non mappata: mai verità, mai un allarme
  mancato;
* ``map_only`` non è un errore della mappa;
* con ``independent`` falso, ``confirmed`` e i punteggi non provano niente.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, shape
from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger

log = get_logger(__name__)

VERDETTI = ("coherent", "to check", "not assessable")
DA_RIGUARDARE = "to check"

#: Le due classi dell'accordo che Limen conserva. ``map_only`` resta solo nei
#: km² del rapporto: non è un errore della mappa e non serve a nessuna misura.
CONFERMATA = "confirmed"
POSSIBILE = "candidate"

_QUALITA = "_quality.json"
_ACCORDO = "_agreement.json"
_PRODOTTO = re.compile(r"^AOI(\d+)_([A-Z]+)_(?:PRODUCT|MONIT(\d+))$")


def mask_id(activation_code: str, product: str) -> str | None:
    """L'id della maschera (``EMSR664-aoi01-GRA0``) da un'etichetta di prodotto.

    È l'etichetta di ``copernicus_ems.Product.label`` (``AOI01_GRA_PRODUCT``,
    ``AOI01_DEL_MONIT03``) riscritta come ``client._mask_id``: la stessa chiave
    di ``flood_observation_masks.id`` e del prefisso degli id di
    ``flood_events``. ``None`` se l'etichetta non ha quella forma.
    """
    m = _PRODOTTO.match(product.strip().upper())
    if m is None:
        return None
    aoi, tipo, monit = m.groups()
    return f"{activation_code.upper()}-aoi{int(aoi):02d}-{tipo}{int(monit or 0)}"


def aoi_label(product: str) -> str:
    return product.split("_", 1)[0].upper()


def _finito(value: Any) -> Any:
    """I non finiti diventano ``None``, anche dentro dizionari e liste."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _finito(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finito(v) for v in value]
    return value


def _numero(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _stem(path: Path, suffisso: str) -> str:
    return path.name[: -len(suffisso)]


@dataclass(frozen=True, slots=True)
class Qualita:
    activation_code: str
    product: str
    stem: str
    verdict: str
    reason: str | None
    flags: list[dict[str, Any]]
    measurements: dict[str, Any]
    thresholds: dict[str, Any] | None
    gap_hours: float | None
    resolution_m: float | None
    file: str

    @property
    def flag_codes(self) -> tuple[str, ...]:
        return tuple(str(f.get("code")) for f in self.flags if f.get("code"))


@dataclass(frozen=True, slots=True)
class Accordo:
    activation_code: str
    product: str
    stem: str
    computed: bool
    reason: str | None
    independent: bool | None
    km2: dict[str, Any]
    scores: dict[str, Any]
    quality_verdict: str | None
    gap_hours: float | None
    resolution_m: float | None
    file: str
    geojson: str | None


def leggi_qualita(path: Path, *, activation_code: str | None = None) -> Qualita:
    """Un ``_quality.json``. Un verdetto fuori dai tre noti è un errore del file."""
    d = json.loads(path.read_text())
    verdict = str(d.get("verdict") or "")
    if verdict not in VERDETTI:
        raise ValueError(f"verdetto sconosciuto {verdict!r} in {path.name}")
    return Qualita(
        activation_code=str(d.get("activation") or activation_code or "").upper(),
        product=str(d["product"]),
        stem=_stem(path, _QUALITA),
        verdict=verdict,
        reason=d.get("reason"),
        flags=_finito(list(d.get("flags") or [])),
        measurements=_finito(dict(d.get("measurements") or {})),
        thresholds=_finito(d.get("thresholds")),
        gap_hours=_numero(d.get("gap_hours")),
        resolution_m=_numero(d.get("resolution_m")),
        file=path.name,
    )


def leggi_accordo(path: Path, *, activation_code: str | None = None) -> Accordo:
    """Un ``_agreement.json``. Con ``computed`` falso non ci sono tif né geojson."""
    d = json.loads(path.read_text())
    computed = bool(d.get("computed"))
    files = d.get("files") or {}
    geojson = files.get("geojson") if computed else None
    independent = d.get("independent")
    quality_verdict = d.get("quality_verdict")
    return Accordo(
        activation_code=str(d.get("activation") or activation_code or "").upper(),
        product=str(d["product"]),
        stem=_stem(path, _ACCORDO),
        computed=computed,
        reason=d.get("reason"),
        independent=bool(independent) if independent is not None else None,
        km2=_finito(dict(d.get("km2") or {})),
        scores=_finito(dict(d.get("scores") or {})),
        quality_verdict=quality_verdict if quality_verdict in VERDETTI else None,
        gap_hours=_numero(d.get("gap_hours")),
        resolution_m=_numero(d.get("resolution_m")),
        file=path.name,
        geojson=str(geojson) if geojson else None,
    )


@dataclass(frozen=True, slots=True)
class Classe:
    """Un poligono di classe dell'accordo, in EPSG:4326."""

    classe: str
    area_km2: float | None
    geom: BaseGeometry


def leggi_classi(path: Path) -> dict[str, Classe]:
    """``confirmed`` e ``candidate`` dal ``.geojson`` dell'accordo.

    Le due restano separate per costruzione: chi chiede la verità prende
    ``confirmed``, ``candidate`` non è mai verità. Una classe vuota manca.
    """
    d = json.loads(path.read_text())
    out: dict[str, Classe] = {}
    for feature in d.get("features") or []:
        props = feature.get("properties") or {}
        classe = props.get("class")
        if classe not in (CONFERMATA, POSSIBILE) or feature.get("geometry") is None:
            continue
        geom = shape(feature["geometry"])
        if geom.is_empty:
            continue
        if not isinstance(geom, MultiPolygon):
            geom = MultiPolygon([geom])
        out[classe] = Classe(classe=classe, area_km2=_numero(props.get("km2")), geom=geom)
    return out


@dataclass(slots=True)
class Rapporto:
    """Ciò che si sa di un prodotto: verdetto, accordo e le sue classi."""

    activation_code: str
    product: str
    mask_id: str
    stem: str
    qualita: Qualita | None = None
    accordo: Accordo | None = None
    classi: dict[str, Classe] = field(default_factory=dict)

    @property
    def verdict(self) -> str | None:
        if self.qualita is not None:
            return self.qualita.verdict
        return self.accordo.quality_verdict if self.accordo is not None else None

    @property
    def independent(self) -> bool | None:
        return self.accordo.independent if self.accordo is not None else None


def _scegli_stem(file_per_stem: dict[str, list[Path]]) -> str:
    """Il più recente: una coppia rifatta sostituisce quella di prima."""
    return max(file_per_stem, key=lambda s: (max(p.stat().st_mtime for p in file_per_stem[s]), s))


def raccogli(radice: Path) -> list[Rapporto]:
    """Tutti i rapporti sotto ``<radice>/*/sentinel-1/``, uno per prodotto.

    Un prodotto con più coppie tiene la più recente, e lo si dice nel log. Un
    file illeggibile o con un'etichetta di prodotto sconosciuta si salta e si
    dice: mai una mappa tolta in silenzio, ma nemmeno un rapporto inventato.
    """
    gruppi: dict[tuple[str, str], dict[str, list[Path]]] = {}
    for cartella in sorted(radice.glob("*/sentinel-1")):
        codice = cartella.parent.name.upper()
        for path in sorted([*cartella.glob(f"*{_QUALITA}"), *cartella.glob(f"*{_ACCORDO}")]):
            suffisso = _QUALITA if path.name.endswith(_QUALITA) else _ACCORDO
            stem = _stem(path, suffisso)
            product = stem.split("_40m_")[0] if "_40m_" in stem else _prodotto_da_stem(stem)
            gruppi.setdefault((codice, product), {}).setdefault(stem, []).append(path)

    out: list[Rapporto] = []
    for (codice, product), file_per_stem in sorted(gruppi.items()):
        stem = _scegli_stem(file_per_stem)
        if len(file_per_stem) > 1:
            log.info(
                "ems_verdetti.piu_coppie",
                activation=codice,
                product=product,
                stems=sorted(file_per_stem),
                tenuta=stem,
            )
        rapporto = _leggi_coppia(codice, product, stem, file_per_stem[stem])
        if rapporto is not None:
            out.append(rapporto)
    return out


def _prodotto_da_stem(stem: str) -> str:
    """``AOI01_GRA_PRODUCT_20m_x`` → ``AOI01_GRA_PRODUCT``: le prime tre parti."""
    return "_".join(stem.split("_")[:3])


def _leggi_coppia(codice: str, product: str, stem: str, paths: Sequence[Path]) -> Rapporto | None:
    qualita: Qualita | None = None
    accordo: Accordo | None = None
    for path in paths:
        try:
            if path.name.endswith(_QUALITA):
                qualita = leggi_qualita(path, activation_code=codice)
            else:
                accordo = leggi_accordo(path, activation_code=codice)
        except (OSError, ValueError, KeyError) as exc:
            log.warning("ems_verdetti.file_illeggibile", file=str(path), error=str(exc)[:200])
    letto = qualita or accordo
    if letto is None:
        return None
    mid = mask_id(letto.activation_code, letto.product)
    if mid is None:
        log.warning("ems_verdetti.prodotto_sconosciuto", activation=codice, product=product)
        return None
    classi: dict[str, Classe] = {}
    if accordo is not None and accordo.geojson:
        gj = paths[0].parent / accordo.geojson
        try:
            classi = leggi_classi(gj)
        except (OSError, ValueError, KeyError) as exc:
            log.warning("ems_verdetti.geojson_illeggibile", file=str(gj), error=str(exc)[:200])
    return Rapporto(
        activation_code=letto.activation_code,
        product=letto.product,
        mask_id=mid,
        stem=stem,
        qualita=qualita,
        accordo=accordo,
        classi=classi,
    )


__all__ = [
    "CONFERMATA",
    "DA_RIGUARDARE",
    "POSSIBILE",
    "VERDETTI",
    "Accordo",
    "Classe",
    "Qualita",
    "Rapporto",
    "aoi_label",
    "leggi_accordo",
    "leggi_classi",
    "leggi_qualita",
    "mask_id",
    "raccogli",
]
