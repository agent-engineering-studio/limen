"""Vaglio radar delle mappe EMS (#713): lettura dei file e logica del backtest.

Le regole del proprietario di ``copernicus-ems`` che qui diventano prove: un
verdetto «to check» toglie la mappa **intera** (poligoni e maschera) solo
nella seconda riga, mai in silenzio; ``candidate`` non è mai verità; senza
esclusi la derivazione per prodotto coincide con il backtest di prima.
"""

from __future__ import annotations

import inspect
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from limen.cli import backtest_flood
from limen.cli.backtest_flood import (
    FloodBacktestMetrics,
    Vaglio,
    _metrics,
    _Tally,
    _write_report,
    conta_hit,
    passaggi_senza,
    prodotti_da_riguardare,
    restringi,
    righe_vaglio,
    verita_confermata,
    verita_senza,
)
from limen.cli.ems_verdetti import confronta, versione
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds
from limen.data.repos.ems_verdetti_repo import VerdettoBacktest
from limen.integrations.copernicus_ems.verdetti import (
    CONFERMATA,
    POSSIBILE,
    leggi_accordo,
    leggi_classi,
    leggi_qualita,
    mask_id,
    raccogli,
)

T0 = datetime(2023, 5, 16, 6, tzinfo=UTC)
PASSAGGIO = datetime(2023, 5, 17, 10, tzinfo=UTC)

_QUALITA = {
    "activation": "EMSR664",
    "product": "AOI01_GRA_PRODUCT",
    "verdict": "to check",
    "reason": None,
    "flags": [
        {"code": "possibly_partial", "text": "…", "numbers": {"mapped_extent": 0.0135}},
        {"code": "much_unmapped", "text": "…", "numbers": {"clustered_ratio": 4.49}},
    ],
    "measurements": {"coverage": 1.0, "mapped_km2": 7.704},
    "gap_hours": -5.12,
    "same_image": False,
    "resolution_m": 40.0,
    "thresholds": {"PARTIAL_EXTENT": 0.1},
}

_ACCORDO = {
    "activation": "EMSR664",
    "product": "AOI01_GRA_PRODUCT",
    "computed": True,
    "reason": None,
    "independent": True,
    "gap_hours": -5.12,
    "resolution_m": 40.0,
    "km2": {"dry": 3142.3, "confirmed": 0.19, "map_only": 7.5, "candidate": 34.6},
    "scores": {"csi": 0.0025, "pod": 0.024, "far": None, "bias": 8.6},
    "quality_verdict": "to check",
    "files": {
        "tif": "AOI01_GRA_PRODUCT_40m_0b223a47_agreement.tif",
        "geojson": "AOI01_GRA_PRODUCT_40m_0b223a47_agreement.geojson",
        "json": "AOI01_GRA_PRODUCT_40m_0b223a47_agreement.json",
    },
}


def _poligono(x: float) -> dict[str, object]:
    return {
        "type": "MultiPolygon",
        "coordinates": [[[[x, 44.0], [x + 0.01, 44.0], [x + 0.01, 44.01], [x, 44.0]]]],
    }


_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"class": "confirmed", "km2": 0.19},
            "geometry": _poligono(12.0),
        },
        {
            "type": "Feature",
            "properties": {"class": "map_only", "km2": 7.5},
            "geometry": _poligono(12.1),
        },
        {
            "type": "Feature",
            "properties": {"class": "candidate", "km2": 34.6},
            "geometry": _poligono(12.2),
        },
    ],
}


def _scrivi(cartella: Path, nome: str, contenuto: object) -> Path:
    cartella.mkdir(parents=True, exist_ok=True)
    path = cartella / nome
    path.write_text(json.dumps(contenuto))
    return path


# ---------------------------------------------------------------------------
# Lettura dei file
# ---------------------------------------------------------------------------
def test_mask_id_matches_the_ingest_ids() -> None:
    assert mask_id("EMSR664", "AOI01_GRA_PRODUCT") == "EMSR664-aoi01-GRA0"
    assert mask_id("emsr664", "AOI01_DEL_MONIT03") == "EMSR664-aoi01-DEL3"
    assert mask_id("EMSR705", "AOI12_FEP_MONIT10") == "EMSR705-aoi12-FEP10"
    assert mask_id("EMSR664", "qualcosa") is None


def test_quality_report_is_parsed_with_its_flags(tmp_path: Path) -> None:
    path = _scrivi(tmp_path, "AOI01_GRA_PRODUCT_40m_0b223a47_quality.json", _QUALITA)
    q = leggi_qualita(path)
    assert q.verdict == "to check"
    assert q.flag_codes == ("possibly_partial", "much_unmapped")
    assert q.stem == "AOI01_GRA_PRODUCT_40m_0b223a47"
    assert q.measurements["mapped_km2"] == 7.704


def test_unknown_verdict_is_rejected(tmp_path: Path) -> None:
    path = _scrivi(tmp_path, "x_quality.json", {**_QUALITA, "verdict": "wrong"})
    with pytest.raises(ValueError):
        leggi_qualita(path)


def test_agreement_with_null_and_non_finite_scores(tmp_path: Path) -> None:
    grezzo = json.dumps(_ACCORDO).replace('"bias": 8.6', '"bias": NaN')
    path = tmp_path / "AOI01_GRA_PRODUCT_40m_0b223a47_agreement.json"
    path.write_text(grezzo)
    a = leggi_accordo(path)
    assert a.computed is True
    assert a.independent is True
    assert a.scores["far"] is None
    assert a.scores["bias"] is None
    assert a.geojson == "AOI01_GRA_PRODUCT_40m_0b223a47_agreement.geojson"


def test_agreement_not_computed_has_no_geojson(tmp_path: Path) -> None:
    non_calcolato = {
        "activation": "EMSR659",
        "product": "AOI04_FEP_PRODUCT",
        "computed": False,
        "reason": "no pre-event image",
        "independent": None,
        "km2": {},
        "scores": {},
        "quality_verdict": None,
        "files": {"json": "AOI04_FEP_PRODUCT_20m_x_agreement.json"},
    }
    path = _scrivi(tmp_path, "AOI04_FEP_PRODUCT_20m_x_agreement.json", non_calcolato)
    a = leggi_accordo(path)
    assert a.computed is False
    assert a.reason == "no pre-event image"
    assert a.geojson is None
    assert a.independent is None


def test_candidate_and_confirmed_stay_separate_and_map_only_is_dropped(tmp_path: Path) -> None:
    path = _scrivi(tmp_path, "a_agreement.geojson", _GEOJSON)
    classi = leggi_classi(path)
    assert set(classi) == {CONFERMATA, POSSIBILE}
    assert classi[POSSIBILE].area_km2 == 34.6


def test_scan_pairs_quality_and_agreement_per_product(tmp_path: Path) -> None:
    s1 = tmp_path / "EMSR664" / "sentinel-1"
    stem = "AOI01_GRA_PRODUCT_40m_0b223a47"
    _scrivi(s1, f"{stem}_quality.json", _QUALITA)
    _scrivi(s1, f"{stem}_agreement.json", _ACCORDO)
    _scrivi(s1, f"{stem}_agreement.geojson", _GEOJSON)
    _scrivi(
        s1,
        "AOI03_GRA_PRODUCT_40m_09687de4_quality.json",
        {**_QUALITA, "product": "AOI03_GRA_PRODUCT", "verdict": "coherent", "flags": []},
    )
    _scrivi(s1, "rotto_quality.json", {"activation": "EMSR664"})

    rapporti = raccogli(tmp_path)

    per_prodotto = {r.product: r for r in rapporti}
    assert set(per_prodotto) == {"AOI01_GRA_PRODUCT", "AOI03_GRA_PRODUCT"}
    r = per_prodotto["AOI01_GRA_PRODUCT"]
    assert r.mask_id == "EMSR664-aoi01-GRA0"
    assert r.verdict == "to check"
    assert r.independent is True
    assert set(r.classi) == {CONFERMATA, POSSIBILE}
    assert per_prodotto["AOI03_GRA_PRODUCT"].accordo is None


def test_scan_on_an_empty_root_finds_nothing(tmp_path: Path) -> None:
    assert raccogli(tmp_path) == []


def test_mapping_lists_reports_without_product_and_products_without_report(
    tmp_path: Path,
) -> None:
    s1 = tmp_path / "EMSR664" / "sentinel-1"
    _scrivi(s1, "AOI01_GRA_PRODUCT_40m_a_quality.json", _QUALITA)
    rapporti = raccogli(tmp_path)

    sconosciuti, senza = confronta(rapporti, {"EMSR664-aoi02-DEL0"})

    assert sconosciuti == ["EMSR664 AOI01_GRA_PRODUCT"]
    assert senza == ["EMSR664-aoi02-DEL0"]
    assert confronta(rapporti, {"EMSR664-aoi01-GRA0"}) == ([], [])


def test_version_is_stable_and_follows_the_content(tmp_path: Path) -> None:
    s1 = tmp_path / "EMSR664" / "sentinel-1"
    _scrivi(s1, "AOI01_GRA_PRODUCT_40m_a_quality.json", _QUALITA)
    prima = versione(raccogli(tmp_path))
    assert versione(raccogli(tmp_path)) == prima
    _scrivi(s1, "AOI01_GRA_PRODUCT_40m_a_quality.json", {**_QUALITA, "verdict": "coherent"})
    assert versione(raccogli(tmp_path)) != prima


# ---------------------------------------------------------------------------
# Backtest: esclusione
# ---------------------------------------------------------------------------
def _v(mask: str, verdict: str | None, flags: tuple[str, ...] = ()) -> VerdettoBacktest:
    return VerdettoBacktest(
        activation_code="EMSR664",
        product=mask,
        mask_id=mask,
        verdict=verdict,
        flag_codes=flags,
        independent=True,
    )


def test_only_to_check_maps_are_excluded() -> None:
    esclusi = prodotti_da_riguardare(
        [
            _v("A", "to check", ("possibly_partial",)),
            _v("B", "coherent"),
            _v("C", "not assessable"),
            _v("D", None),
        ]
    )
    assert set(esclusi) == {"A"}
    assert esclusi["A"].flag_codes == ("possibly_partial",)


def test_truth_without_exclusions_is_the_old_truth() -> None:
    per_prodotto = {
        "c1": {"A": T0, "B": datetime(2023, 5, 18, tzinfo=UTC)},
        "c2": {"A": T0},
    }
    assert verita_senza(per_prodotto, ()) == {"c1": T0, "c2": T0}


def test_excluding_a_map_keeps_cells_another_map_saw() -> None:
    dopo = datetime(2023, 5, 18, tzinfo=UTC)
    per_prodotto = {"c1": {"A": T0, "B": dopo}, "c2": {"A": T0}}
    assert verita_senza(per_prodotto, {"A"}) == {"c1": dopo}


def test_excluding_a_map_removes_its_mask_too() -> None:
    """Senza togliere la maschera, l'acqua di A diventerebbe «osservato asciutto»."""
    per_maschera = {
        "c1": [("A", PASSAGGIO), ("B", PASSAGGIO)],
        "c2": [("A", PASSAGGIO)],
    }
    assert passaggi_senza(per_maschera, ()) == {"c1": [PASSAGGIO, PASSAGGIO], "c2": [PASSAGGIO]}
    assert passaggi_senza(per_maschera, {"A"}) == {"c1": [PASSAGGIO]}


def _thresholds() -> FloodThresholds:
    t = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(t, FloodThresholds)
    return t


def _misura(tally: _Tally, observed: dict[str, list[datetime]]) -> FloodBacktestMetrics:
    return _metrics(
        aoi_id="it-test",
        mode="observed",
        tally=tally,
        observed=observed,
        cells_scored=3,
        window_start=date(2023, 5, 1),
        thresholds=_thresholds(),
    )


def _tally() -> _Tally:
    """c1 allagata per A e B, c2 solo per A; allerta su entrambe il giorno prima."""
    return _Tally(
        alert_days={"c1": [date(2023, 5, 15)], "c2": [date(2023, 5, 15)]},
        truth={"c1": T0, "c2": T0},
        truth_cell_days=20,
        truth_alert_days=2,
        days=10,
        measurable=True,
        truth_days_by_cell={"c1": 10, "c2": 10},
        truth_alert_by_cell={"c1": 1, "c2": 1},
    )


def test_restricting_to_the_same_truth_changes_nothing() -> None:
    tally = _tally()
    observed = {"c1": [PASSAGGIO], "c2": [PASSAGGIO]}
    assert _misura(restringi(tally, tally.truth), observed) == _misura(tally, observed)


def test_excluding_the_map_and_its_mask_does_not_create_false_alarms() -> None:
    tally = _tally()
    per_prodotto = {"c1": {"A": T0, "B": T0}, "c2": {"A": T0}}
    per_maschera = {"c1": [("A", PASSAGGIO), ("B", PASSAGGIO)], "c2": [("A", PASSAGGIO)]}

    senza = _misura(
        restringi(tally, verita_senza(per_prodotto, {"A"})),
        passaggi_senza(per_maschera, {"A"}),
    )

    assert senza.truth_cells == 1
    assert senza.hits == 1
    # c2 non è più verità e nessuno l'ha più osservata: la sua allerta è senza
    # risposta, non un falso allarme.
    assert senza.false_days == 0
    assert senza.unverifiable_days == 1
    assert senza.base_rate == pytest.approx(0.1)


def test_excluding_only_the_polygons_would_have_made_a_false_alarm() -> None:
    """Il motivo per cui si toglie anche la maschera, misurato."""
    tally = _tally()
    solo_poligoni = _misura(
        restringi(tally, {"c1": T0}),
        {"c1": [PASSAGGIO], "c2": [PASSAGGIO]},
    )
    assert solo_poligoni.false_days == 1


def test_confirmed_hit_rate_uses_only_confirmed_cells() -> None:
    tally = _tally()
    solide = verita_confermata(
        tally.truth,
        {"c1": {"A"}, "c2": {"VECCHIA"}, "fuori": {"A"}},
        {"c1": {"A", "B"}, "c2": {"A"}},
    )
    # c2 è confermata, ma da una mappa che non l'ha messa nella verità.
    assert solide == {"c1": T0}
    assert conta_hit(solide, tally.alert_days, lead_max_hours=72.0)[0] == 1


def test_candidate_never_enters_the_backtest() -> None:
    """L'acqua possibile non ha strada verso la verità: il backtest non legge
    la sua tabella, e le sole celle «solide» vengono dall'acqua confermata."""
    sorgente = inspect.getsource(backtest_flood)
    assert "ems_acqua_possibile" not in sorgente
    assert not hasattr(backtest_flood, "POSSIBILE")
    repo = inspect.getsource(
        __import__(
            "limen.data.repos.ems_verdetti_repo", fromlist=["celle_confermate"]
        ).celle_confermate
    )
    assert "ems_acqua_confermata" in repo
    assert "c.independent" in repo


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def _scrivi_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vaglio: Vaglio | None) -> str:
    monkeypatch.setattr(backtest_flood, "REPORTS_DIR", tmp_path)
    tally = _tally()
    run = _misura(tally, {"c1": [PASSAGGIO], "c2": [PASSAGGIO]})
    out = _write_report(
        aoi_id="it-test",
        start=T0,
        end=T0,
        runs=[run],
        provenance={
            "source": "s",
            "licence": "l",
            "credentials": "none",
            "geometry": "g",
            "coverage_note": "c",
            "known_limit": "k",
        },
        activations=[],
        thresholds=_thresholds(),
        nodi_con_portata=(1, 1),
        vaglio=vaglio,
    )
    return out.read_text()


def test_without_verdicts_the_report_has_no_screening_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    testo = _scrivi_report(tmp_path, monkeypatch, None)
    assert "Vaglio radar" not in testo


def test_report_names_every_excluded_map_with_its_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    esclusi = prodotti_da_riguardare([_v("EMSR664-aoi01-GRA0", "to check", ("much_unmapped",))])
    tally = _tally()
    senza = _misura(tally, {"c1": [PASSAGGIO]})
    vaglio = Vaglio(
        esclusi=esclusi,
        esclusi_qui=frozenset({"EMSR664-aoi01-GRA0"}),
        senza=[senza],
        confermate={"observed": (1, 1)},
        verdetti=3,
        senza_rapporto=2,
    )
    testo = _scrivi_report(tmp_path, monkeypatch, vaglio)
    assert "## Vaglio radar delle mappe" in testo
    assert "`EMSR664-aoi01-GRA0`" in testo
    assert "`much_unmapped`" in testo
    assert "senza «to check»" in testo
    assert "acqua confermata" in testo
    assert "sia la sua maschera" in testo.replace(
        "**sia i suoi poligoni allagati sia la ", "sia la "
    )
    assert righe_vaglio([senza], vaglio)[0] == "## Vaglio radar delle mappe"
