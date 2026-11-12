"""Livelli idrometrici dell'Emilia-Romagna dall'archivio Arpae SIMC (#501).

Arpae pubblica un file al mese con tutte le osservazioni della rete
idro-meteorologica (``dati-simc.arpae.it/opendata/osservati/meteo/storico/
AAAA-MM.json.gz``, CC BY 4.0, senza credenziali, ~20 MB), una riga JSON per
stazione e istante, con le coordinate dentro la riga. Il livello è
``B13215`` (metri, rispetto allo zero idrometrico della stazione) con
``timerange`` ``[254, 0, 0]``, cioè istantaneo, ogni 15 minuti.

Qui si tiene, per stazione e giorno UTC, il livello **massimo**: il ramo
fluviale ragiona a passo giornaliero (``backtest-flood``), e di una piena
conta il colmo.

Un livello non è una portata, e lo zero idrometrico cambia da stazione a
stazione: niente di questo modulo confronta stazioni fra loro. Lo fa
:func:`rapporti`, sulla storia di ciascuna.

Sola lettura: un mese che non si scarica è ``None`` e ``integration.degraded``.
"""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

URL = "https://dati-simc.arpae.it/opendata/osservati/meteo/storico/{mese}.json.gz"
LICENZA = "CC BY 4.0, Arpae Emilia-Romagna"
_LIVELLO = "B13215"
_ISTANTANEO = [254, 0, 0]
#: Il «fondo» della stazione: il livello di magra da cui si misura la piena.
#: Lo zero idrometrico è arbitrario, e un rapporto fatto sullo zero direbbe
#: cose diverse per due stazioni identiche con lo zero messo diversamente.
PERCENTILE_FONDO = 0.05


@dataclass(frozen=True, slots=True)
class Stazione:
    chiave: str
    nome: str
    lon: float
    lat: float


@dataclass(slots=True)
class Livelli:
    """Livello massimo giornaliero (m) per stazione."""

    stazioni: dict[str, Stazione]
    massimi: dict[str, dict[date, float]]

    @classmethod
    def vuoti(cls) -> Livelli:
        return cls(stazioni={}, massimi=defaultdict(dict))

    def unisci(self, altro: Livelli) -> None:
        self.stazioni.update(altro.stazioni)
        for chiave, giorni in altro.massimi.items():
            mio = self.massimi.setdefault(chiave, {})
            for giorno, valore in giorni.items():
                mio[giorno] = max(valore, mio.get(giorno, valore))


def mesi(inizio: date, fine: date) -> list[str]:
    """I mesi ``AAAA-MM`` da ``inizio`` a ``fine`` compresi."""
    out: list[str] = []
    anno, mese = inizio.year, inizio.month
    while (anno, mese) <= (fine.year, fine.month):
        out.append(f"{anno:04d}-{mese:02d}")
        anno, mese = (anno + 1, 1) if mese == 12 else (anno, mese + 1)
    return out


def leggi_mese(righe: Iterable[str]) -> Livelli:
    """Le righe JSON di un mese → livelli massimi giornalieri per stazione."""
    out = Livelli.vuoti()
    for riga in righe:
        r = json.loads(riga)
        livello: float | None = None
        nome = ""
        for blocco in r.get("data") or ():
            variabili = blocco.get("vars") or {}
            if "timerange" not in blocco:
                nome = str((variabili.get("B01019") or {}).get("v") or "")
            elif blocco.get("timerange") == _ISTANTANEO and _LIVELLO in variabili:
                v = variabili[_LIVELLO].get("v")
                livello = float(v) if v is not None else None
        if livello is None or r.get("lon") is None or r.get("lat") is None:
            continue
        chiave = f"{r.get('network')}:{r['lon']}:{r['lat']}"
        if chiave not in out.stazioni:
            out.stazioni[chiave] = Stazione(
                chiave=chiave, nome=nome, lon=r["lon"] / 1e5, lat=r["lat"] / 1e5
            )
        giorno = (
            datetime.fromisoformat(str(r["date"]).replace("Z", "+00:00")).astimezone(UTC).date()
        )
        giorni = out.massimi[chiave]
        giorni[giorno] = max(livello, giorni.get(giorno, livello))
    return out


async def _file_del_mese(mese: str, cartella: Path) -> Path | None:
    dest = cartella / f"{mese}.json.gz"
    # Il mese in corso cresce ancora: si riscarica; i mesi chiusi restano su disco.
    chiuso = mese < datetime.now(UTC).strftime("%Y-%m")
    if chiuso and dest.is_file() and dest.stat().st_size > 0:
        return dest
    try:
        resp = await fetch_with_retry(
            "GET", URL.format(mese=mese), client=await SharedHttpClient.get()
        )
    except httpx.HTTPError as exc:
        log.warning("integration.degraded", source="arpae_idrometri", mese=mese, error=str(exc))
        return None
    cartella.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


async def livelli(inizio: date, fine: date, *, cartella: Path) -> tuple[Livelli, list[str]]:
    """I livelli massimi giornalieri fra ``inizio`` e ``fine``, e i mesi mancati."""
    out = Livelli.vuoti()
    mancati: list[str] = []
    for mese in mesi(inizio, fine):
        path = await _file_del_mese(mese, cartella)
        if path is None:
            mancati.append(mese)
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                out.unisci(leggi_mese(fh))
        except (OSError, ValueError) as exc:
            log.warning("integration.degraded", source="arpae_idrometri", mese=mese, error=str(exc))
            mancati.append(mese)
    for giorni in out.massimi.values():
        for giorno in [g for g in giorni if not inizio <= g <= fine]:
            del giorni[giorno]
    return out, mancati


def rapporti(
    giorni: dict[date, float],
    *,
    prima_di: date,
    percentile: float,
    minimo_giorni: int,
) -> dict[date, float]:
    """Livello del giorno sopra il fondo, diviso la piena ordinaria sopra il fondo.

    ``(h - p05) / (p_ref - p05)``, con i due percentili presi dalla storia della
    stazione **prima** di ``prima_di`` (come `_node_reference` per GloFAS: un
    riferimento che vede i giorni giudicati saprebbe già dell'evento). 1 è la
    piena ordinaria della stazione. Vuoto se la storia è corta o piatta.
    """
    storia = sorted(v for g, v in giorni.items() if g < prima_di)
    if len(storia) < minimo_giorni:
        return {}
    fondo = _percentile(storia, PERCENTILE_FONDO)
    piena = _percentile(storia, percentile)
    if piena - fondo <= 0.0:
        return {}
    return {g: (v - fondo) / (piena - fondo) for g, v in giorni.items() if g >= prima_di}


def _percentile(ordinati: list[float], p: float) -> float:
    k = (len(ordinati) - 1) * p
    basso = int(k)
    alto = min(basso + 1, len(ordinati) - 1)
    return ordinati[basso] + (ordinati[alto] - ordinati[basso]) * (k - basso)
