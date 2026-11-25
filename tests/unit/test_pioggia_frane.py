"""Pioggia dei pluviometri per zona franosa: le parti pure (migrazione 099)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from limen.core.pioggia_frane import cumulate, evento_contro_soglia
from limen.core.scoring.caine import threshold_intensity_mm_h
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.repos.pluviometri_repo import GiornoPioggia, per_giorno
from limen.integrations.pluviometri_sync import _vuoto_sospetto, mesi

FINE = datetime(2014, 11, 5, 12, tzinfo=UTC)


def _ore(valori: list[float | None]) -> dict[datetime, float | None]:
    """Le ore che finiscono a FINE, in ordine: l'ultima della lista è FINE."""
    n = len(valori)
    return {FINE - timedelta(hours=n - 1 - k): v for k, v in enumerate(valori)}


def test_mesi_dal_piu_recente_fino_a_gennaio() -> None:
    assert mesi(2025, date(2026, 2, 14)) == [
        (2026, 2),
        (2026, 1),
        *[(2025, m) for m in range(12, 0, -1)],
    ]


def test_per_giorno_mette_ogni_ora_al_suo_posto_e_salta_i_giorni_vuoti() -> None:
    ore = {
        datetime(2025, 10, 1, 1, tzinfo=UTC): [0.4, None],  # finisce alle 01: posizione 1
        datetime(2025, 10, 2, 0, tzinfo=UTC): [1.0, None],  # finisce a mezzanotte: la 24ª del 1°
        datetime(2025, 10, 2, 1, tzinfo=UTC): [None, None],
    }
    righe = per_giorno(ore, ["a", "b"], {("a", date(2025, 10, 1)): True})
    assert len(righe) == 1
    riga = righe[0]
    assert (riga.pluviometro_id, riga.giorno, riga.validata) == ("a", date(2025, 10, 1), True)
    assert riga.mm[0] == 0.4 and riga.mm[23] == 1.0
    assert sum(v is not None for v in riga.mm) == 2


def test_cumulate_con_un_buco_non_sono_zero() -> None:
    ore = _ore([None] + [2.0] * 5)
    c = cumulate(ore, FINE)
    assert c["1h"] == {"mm": 2.0, "ore_non_misurate": 0}
    assert c["3h"] == {"mm": 6.0, "ore_non_misurate": 0}
    assert c["6h"] == {"mm": None, "ore_non_misurate": 1}
    assert "24h" not in c


def test_evento_contro_la_soglia_della_macroregione() -> None:
    soglie = load_regional_thresholds()
    ore = _ore([0.0] * 6 + [10.0] * 6 + [0.0] * 30)
    e = evento_contro_soglia(ore, soglie=soglie, macroregione="northern_italy")
    assert e is not None
    soglia = threshold_intensity_mm_h(6.0, caine=soglie.caine, macroregion="northern_italy")
    assert e["durata_h"] == 6.0 and e["cumulata_mm"] == 60.0
    assert e["rapporto_soglia"] == round(10.0 / soglia, 2)
    assert e["almeno"] is False and e["confina_con_ore_non_misurate"] is False


def test_evento_con_ore_non_misurate_e_un_limite_inferiore() -> None:
    soglie = load_regional_thresholds()
    ore = _ore([5.0, None, 5.0] + [0.0] * 30)
    e = evento_contro_soglia(ore, soglie=soglie, macroregione="northern_italy")
    assert e is not None
    assert e["ore_non_misurate"] == 1 and e["almeno"] is True


def test_nessun_evento_senza_pioggia() -> None:
    soglie = load_regional_thresholds()
    assert evento_contro_soglia(_ore([0.0] * 24), soglie=soglie, macroregione="x") is None


def test_evento_che_finisce_dove_l_archivio_si_ferma_e_un_limite_inferiore() -> None:
    """L'archivio è notturno: la pioggia può continuare nelle ore che non ci sono ancora."""
    soglie = load_regional_thresholds()
    ore = _ore([0.0] * 10 + [8.0] * 4 + [None] * 10)
    e = evento_contro_soglia(ore, soglie=soglie, macroregione="northern_italy")
    assert e is not None
    assert e["ore_non_misurate"] == 0
    assert e["confina_con_ore_non_misurate"] is True and e["almeno"] is True


def test_evento_all_inizio_della_serie_puo_essere_cominciato_prima() -> None:
    soglie = load_regional_thresholds()
    ore = _ore([8.0] * 3 + [0.0] * 20)
    e = evento_contro_soglia(ore, soglie=soglie, macroregione="northern_italy")
    assert e is not None and e["almeno"] is True


def test_una_risposta_vuota_con_sensori_attivi_non_cancella_il_mese() -> None:
    giorno = GiornoPioggia("x:1", date(2026, 10, 1), (0.0,) * 24, None)
    assert _vuoto_sospetto("x", "pluviometri/2026-10", ["1"], []) is True
    assert _vuoto_sospetto("x", "pluviometri/2026-10", [], []) is False
    assert _vuoto_sospetto("x", "pluviometri/2026-10", ["1"], [giorno]) is False


async def test_un_mese_vuoto_non_ferma_lo_storico(monkeypatch: pytest.MonkeyPatch) -> None:
    """La Lombardia non pubblica marzo 2026: i mesi prima vanno letti lo stesso."""
    from limen.integrations import pluviometri_sync as sync
    from limen.integrations.arpa_lombardia.pluviometri import Pluviometro

    vuoto = datetime(2026, 3, 1, tzinfo=UTC)
    scritti: list[str] = []

    async def stazioni(_bbox: object) -> list[Pluviometro]:
        return [Pluviometro("1", "A", 9.0, 45.5, date(2000, 1, 1), None)]

    async def orarie(
        _s: list[str], start: datetime, _end: datetime
    ) -> dict[datetime, list[float | None]]:
        return {} if start == vuoto else {start + timedelta(hours=1): [0.5]}

    async def niente(*_a: object, **_k: object) -> None:
        return None

    async def scrivi(_f: str, anno: int, mese: int, giorni: list[GiornoPioggia]) -> int:
        scritti.append(f"{anno}-{mese:02d}")
        return len(giorni)

    monkeypatch.setattr(sync.lombardia, "pluviometri", stazioni)
    monkeypatch.setattr(sync.lombardia, "orarie", orarie)
    monkeypatch.setattr(sync.pluviometri_repo, "salva_stazioni", niente)
    monkeypatch.setattr(sync.dataset_versions_repo, "latest", niente)
    monkeypatch.setattr(sync.dataset_versions_repo, "find", niente)
    monkeypatch.setattr(sync.dataset_versions_repo, "record", niente)
    monkeypatch.setattr(sync, "_scrivi", scrivi)
    monkeypatch.setattr(sync, "mesi", lambda _a, _o: [(2026, 4), (2026, 3), (2026, 2), (2026, 1)])

    conti = await sync.sincronizza_lombardia(dal_anno=2026, limite=None)
    assert scritti == ["2026-04", "2026-02", "2026-01"]
    assert conti["vuoti"] == 1 and "stato" not in conti
