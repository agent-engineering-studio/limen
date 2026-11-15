"""Il metro per comune: anticipate, apparenti e tasso di base."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from limen.cli import verifiche_report
from limen.cli.verifiche_report import riepiloga, scrivi_report
from limen.core.models.hazard import HazardType
from limen.data.repos.carico_repo import Carico
from limen.data.repos.verifiche_eventi_repo import RigaVerifica

_T = datetime(2026, 10, 10, 10, tzinfo=UTC)


def _riga(
    slug: str,
    *,
    hazard: HazardType = HazardType.LANDSLIDE,
    esito: str = "mancata",
    moderato: int | None = None,
    alto: int | None = None,
    fondo: str | None = "None",
    sopra: int | None = None,
) -> RigaVerifica:
    return RigaVerifica(
        slug=slug,
        hazard=hazard,
        esito=esito,
        evento_at=_T,
        luogo=slug,
        anticipo_ore_moderato=moderato,
        anticipo_ore_alto=alto,
        classe_prevista_max="Moderate" if moderato is not None else None,
        fondo_classe_max=fondo,
        fondo_giorni_moderato=None,
        anticipo_sopra_fondo_ore=sopra if sopra is not None else moderato,
    )


def test_l_anticipo_sullo_sfondo_e_apparente_non_previsto() -> None:
    """Melito, San Lorenzo, Roccaforte: «anticipo» di 74-80 ore, ma il comune
    era già in Moderato. Apparenti 100 %, tasso di base 100 %, anticipate 0."""
    righe = [_riga(s, moderato=80, fondo="Moderate") for s in ("melito", "san-lorenzo", "rocca")]
    (s,) = riepiloga(righe)
    assert (s.verificati, s.anticipate, s.mancate) == (3, 0, 3)
    assert s.quota_apparenti == 1.0
    assert s.tasso_di_base == 1.0
    assert s.anticipo_mediano_ore is None


def test_non_verificabile_resta_fuori_dal_conto() -> None:
    righe = [
        _riga("a", esito="anticipata", moderato=40, alto=20),
        _riga("b", esito="anticipata", moderato=60),
        _riga("c"),
        _riga("d", esito="non_verificabile"),
    ]
    (s,) = riepiloga(righe)
    assert (s.verificati, s.non_verificabili) == (3, 1)
    assert s.quota_anticipate == pytest.approx(2 / 3)
    assert s.con_alto == 1
    assert s.anticipo_mediano_ore == 50
    assert s.tasso_di_base == 0.0


def test_un_riepilogo_per_pericolo_presente() -> None:
    righe = [_riga("frana"), _riga("foggia", hazard=HazardType.FLOOD)]
    assert [s.hazard for s in riepiloga(righe)] == [HazardType.LANDSLIDE, HazardType.FLOOD]
    assert riepiloga([]) == []


def test_il_report_mette_il_tasso_di_base_accanto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(verifiche_report, "REPORTS_DIR", tmp_path)
    righe = [_riga("melito", moderato=74, fondo="Moderate")]
    testo = scrivi_report(riepiloga(righe), righe, dal=None, al=None).read_text(encoding="utf-8")
    assert "contro un tasso di base di 100%" in testo
    assert "| 2026-10-10 melito | mancata | 74 h | — | Moderate | Moderate |" in testo


def test_l_anticipo_mediano_si_conta_sopra_il_fondo() -> None:
    """Fondo Alto, Alto 72 h prima, Molto alto 20 h prima: 20 ore, non 72."""
    riga = _riga("a", esito="anticipata", moderato=72, alto=72, fondo="High", sopra=20)
    (s,) = riepiloga([riga])
    assert s.anticipo_mediano_ore == 20


def _carico(sopra: int, *, comuni: int = 100, giorni: int = 10) -> Carico:
    return Carico(
        hazard=HazardType.LANDSLIDE,
        comuni_giorno_sopra=sopra,
        comuni=comuni,
        giorni=giorni,
        dal_giorno=date(2026, 10, 1),
        al_giorno=date(2026, 10, 10),
    )


def test_il_carico_sta_accanto_agli_eventi_colti(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Il metro della #345: colti e carico nella stessa sezione, per pericolo."""
    monkeypatch.setattr(verifiche_report, "REPORTS_DIR", tmp_path)
    righe = [_riga("a", esito="anticipata", moderato=40), _riga("b", hazard=HazardType.FLOOD)]
    frana, alluvione = riepiloga(righe, {HazardType.LANDSLIDE: _carico(125)})
    assert frana.carico is not None
    assert frana.carico.quota == pytest.approx(0.125)
    assert alluvione.carico is None
    testo = scrivi_report([frana, alluvione], righe, dal=None, al=None).read_text(encoding="utf-8")
    assert "- Carico: **12.5%** dei comuni-giorno" in testo
    assert "(125 su 1000: 100 comuni per 10 giorni, 2026-10-01 → 2026-10-10)" in testo
    assert "- Carico: — (nessun giorno di previsioni valutato nella finestra)" in testo


def test_un_carico_senza_giorni_valutati_non_e_zero() -> None:
    assert _carico(0, giorni=0).quota is None
    assert _carico(0).quota == 0.0
