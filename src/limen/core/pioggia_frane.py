"""La pioggia misurata dai pluviometri, letta per zona franosa.

Limen non risponde «quanto piove qui» per una coordinata qualunque: lo dice
per una cella o per le celle franose di un comune, accanto a quello che la
zona è (PAI, IFFI, suscettibilità) e alla soglia d'innesco della sua
macroregione. Le stesse curve di Caine che il motore V1 legge in
``landslide.yaml``; qui servono solo a dire quanto vicino alla soglia è
arrivata la pioggia **misurata**, e non toccano nessun punteggio.

Ogni «non so» resta detto come tale, mai come zero:

* un'ora non misurata è ``None``, e una cumulata con un buco è ``None`` con
  le ore che mancano;
* un evento con ore non misurate dentro, o che confina con ore non misurate
  (l'archivio è notturno: le ultime ore mancano sempre), ha ``almeno: true``:
  la pioggia vera è almeno quella misurata, e l'evento può essere più lungo;
* un pluviometro senza ore misurate nella finestra dice «non misurato», una
  zona senza pluviometri «non coperto», un comune senza PAI né IFFI caricati
  «fattori statici non caricati».

L'archivio si aggiorna di notte (``pluviometri_sync``): per le ultime ore c'è
il radar (``radar_rain_at``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from rainfall_thresholds import RainfallEvent, latest_event, reconstruct_events

from limen.core.istante_frana import istante_frana
from limen.core.scoring.caine import threshold_intensity_mm_h
from limen.core.scoring.regional_thresholds import RegionalThresholds, load_regional_thresholds
from limen.data.repos import pluviometri_repo, zone_franose_repo
from limen.data.repos.pluviometri_repo import Vicino
from limen.data.repos.zone_franose_repo import IFFI_VICINA_M, CellaZona

#: Finestre delle cumulate, in ore.
CUMULATE = (1, 3, 6, 24, 72)
_PLUVIOMETRI_ZONA = 3
#: Le frane datate per cui si ricostruisce la pioggia, al massimo.
_FRANE_MAX = 20

FONTI = {
    "meteotrentino": {
        "licenza": "CC BY 4.0",
        "attribuzione": "Provincia Autonoma di Trento - Meteotrentino",
    },
    "arpa_lombardia": {"licenza": "CC0 1.0", "attribuzione": "ARPA Lombardia"},
}


def cumulate(ore: dict[datetime, float | None], fine: datetime) -> dict[str, dict[str, Any]]:
    """Per ogni finestra di :data:`CUMULATE` che entra nella serie: mm, o ``None``
    con le ore che mancano se anche una sola non è misurata."""
    out: dict[str, dict[str, Any]] = {}
    for h in CUMULATE:
        if fine - timedelta(hours=h - 1) < min(ore, default=fine):
            continue
        finestra = [ore.get(fine - timedelta(hours=k)) for k in range(h)]
        mancanti = sum(v is None for v in finestra)
        out[f"{h}h"] = {
            "mm": None if mancanti else round(sum(v for v in finestra if v is not None), 1),
            "ore_non_misurate": mancanti,
        }
    return out


def evento_contro_soglia(
    ore: dict[datetime, float | None],
    *,
    soglie: RegionalThresholds,
    macroregione: str,
) -> dict[str, Any] | None:
    """L'evento di pioggia della serie, con la soglia d'innesco alla sua durata.

    Lo stesso evento che il motore sceglie (``scelta_evento`` del YAML): il
    più recente, o quello più alto rispetto alla curva.
    """
    caine = soglie.caine
    pausa = caine.event_reconstruction.no_rain_break_hours
    eventi = reconstruct_events(
        sorted(ore.items()),
        no_rain_break_hours=pausa,
        min_event_mm=caine.event_reconstruction.min_event_mm,
        source="pluviometro",
    )

    def rapporto(e: RainfallEvent) -> float:
        soglia = threshold_intensity_mm_h(e.duration_hours, caine=caine, macroregion=macroregione)
        return e.intensity_mm_h / soglia

    if caine.event_reconstruction.scelta_evento == "piu_forte":
        evento = max(eventi, key=rapporto, default=None)
    else:
        evento = latest_event(eventi)
    if evento is None:
        return None
    # Le ore non misurate appena fuori dall'evento, o la serie che finisce prima
    # che la pausa lo chiuda: l'evento può essere cominciato prima o non finito.
    bordi = [evento.start - timedelta(hours=k) for k in range(1, pausa + 1)] + [
        evento.end + timedelta(hours=k) for k in range(1, pausa + 1)
    ]
    aperto = any(ore.get(t) is None for t in bordi)
    soglia_mm_h = threshold_intensity_mm_h(
        evento.duration_hours, caine=caine, macroregion=macroregione
    )
    return {
        "inizio": evento.start,
        "fine": evento.end,
        "durata_h": evento.duration_hours,
        "cumulata_mm": round(evento.total_mm, 1),
        "intensita_mm_h": round(evento.intensity_mm_h, 2),
        "soglia_mm_h": round(soglia_mm_h, 2),
        "soglia_mm": round(soglia_mm_h * evento.duration_hours, 1),
        "rapporto_soglia": round(evento.intensity_mm_h / soglia_mm_h, 2),
        "ore_non_misurate": evento.unmeasured_hours,
        "confina_con_ore_non_misurate": aperto,
        "almeno": evento.unmeasured_hours > 0 or aperto,
    }


def _contesto(c: CellaZona) -> dict[str, Any]:
    return {
        "cell_id": c.cell_id,
        "franosa": None if c.senza_fattori else c.franosa,
        "pai_class_norm": c.pai_class_norm,
        "iffi_density_500": c.iffi_density_500,
        "distance_to_iffi_m": c.distance_to_iffi_m,
        "suscettibilita_statica": c.s_static,
    }


def _stazione(v: Vicino, cell_id: str | None = None) -> dict[str, Any]:
    s = v.stazione
    return {
        "id": s.id,
        "nome": s.nome,
        "fonte": s.fonte,
        "quota_m": s.quota_m,
        "distanza_km": v.distanza_km,
        **({"dalla_cella": cell_id} if cell_id is not None else {}),
        **FONTI.get(s.fonte, {}),
    }


async def _misura(
    v: Vicino, start: datetime, end: datetime, soglie: RegionalThresholds, macroregione: str
) -> dict[str, Any]:
    ore, validata = await pluviometri_repo.serie(v.stazione.id, start, end)
    misurate = [o for o, mm in ore.items() if mm is not None]
    mancanti = len(ore) - len(misurate)
    evento = evento_contro_soglia(ore, soglie=soglie, macroregione=macroregione)
    motivo: str | None
    if not misurate:
        copertura, motivo = "non misurato", "nessuna ora misurata in archivio per questa finestra"
    elif evento is None and mancanti:
        copertura = "parziale"
        motivo = f"nessun evento nelle ore misurate; {mancanti} ore non misurate"
    else:
        copertura = "parziale" if mancanti else "misurato"
        motivo = None if evento is not None else "nessun evento di pioggia nella finestra"
    return {
        "copertura": copertura,
        "ore": len(ore),
        "ore_misurate": len(misurate),
        "ultima_ora_misurata": max(misurate, default=None),
        "validata": validata,
        "cumulate": cumulate(ore, end),
        "evento": evento,
        **({"motivo_evento": motivo} if motivo else {}),
    }


async def _vicini_della_zona(
    celle: list[CellaZona], raggio_km: float, inizio: datetime, fine: datetime
) -> list[tuple[Vicino, str]]:
    """I pluviometri attivi più vicini a una qualunque cella della zona, con la cella."""
    migliori: dict[str, tuple[Vicino, str]] = {}
    for c in celle:
        for v in await pluviometri_repo.vicini(
            c.lon, c.lat, raggio_km=raggio_km, dal=inizio.date(), al=fine.date()
        ):
            noto = migliori.get(v.stazione.id)
            if noto is None or v.distanza_km < noto[0].distanza_km:
                migliori[v.stazione.id] = (v, c.cell_id)
    return sorted(migliori.values(), key=lambda x: x[0].distanza_km)[:_PLUVIOMETRI_ZONA]


def _chiave_zona(cell_id: str | None, istat_code: str | None) -> dict[str, Any]:
    return {"cell_id": cell_id} if cell_id is not None else {"istat_code": istat_code}


def _copertura_zona(pluviometri: list[dict[str, Any]]) -> str:
    if not pluviometri:
        return "non coperto"
    if all(p["copertura"] == "non misurato" for p in pluviometri):
        return "non misurato"
    return "coperto"


_NON_COPERTO = (
    "Nessun pluviometro archiviato entro {raggio:g} km dalla zona: la pioggia non è misurata "
    "qui, il che non vuol dire che non piova. Oggi l'archivio copre Lombardia e Trentino; "
    "altrove c'è il radar (radar_rain_at)."
)
_NON_MISURATO = (
    "I pluviometri vicini non hanno ore in archivio per questa finestra (archivio non ancora "
    "riempito, o mese non scaricato): la pioggia non è misurata, non è zero."
)


async def pioggia_zona_franosa(
    *,
    cell_id: str | None = None,
    istat_code: str | None = None,
    ore: int = 72,
    fino_a: datetime | None = None,
    raggio_km: float,
) -> dict[str, Any]:
    """La pioggia dei pluviometri vicini a una zona franosa, contro la soglia d'innesco."""
    if (cell_id is None) == (istat_code is None):
        return {"errore": "indica una cella (cell_id) oppure un comune (istat_code)"}
    chiave = _chiave_zona(cell_id, istat_code)
    zona = await zone_franose_repo.zona(cell_id, istat_code)
    if zona is None:
        return {"zona": chiave, "errore": "cella o comune non trovati"}
    if not zona.celle:
        senza = zona.celle_totali > 0 and zona.celle_senza_fattori == zona.celle_totali
        return {
            "zona": chiave,
            "celle_franose": None if senza else 0,
            "nota": (
                "Fattori statici (PAI, IFFI) non caricati per questo comune: non si sa dove "
                "sono le aree franose. Vedi `limen data-status`."
            )
            if senza
            else (
                f"Nessuna cella del comune è in un'area PAI o a meno di {IFFI_VICINA_M:g} m da "
                "una frana IFFI. Non vuol dire terreno sicuro dove l'inventario è poco "
                "rilevato: vedi affidabilita_iffi in comune_risk."
            ),
        }
    soglie = load_regional_thresholds()
    macroregione = soglie.macroregion_for(zona.aoi_id) if zona.aoi_id else "italy_default"
    fine = (fino_a or datetime.now(UTC)).astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    inizio = fine - timedelta(hours=ore)
    pluviometri = [
        {**_stazione(v, cella), **await _misura(v, inizio, fine, soglie, macroregione)}
        for v, cella in await _vicini_della_zona(zona.celle, raggio_km, inizio, fine)
    ]
    copertura = _copertura_zona(pluviometri)
    risposta: dict[str, Any] = {
        "zona": chiave,
        "celle_franose": sum(c.franosa for c in zona.celle),
        "contesto": _contesto(zona.celle[0]) if cell_id is not None else None,
        "macroregione": macroregione,
        "finestra": {"inizio": inizio, "fine": fine},
        "copertura": copertura,
        "pluviometri": pluviometri,
    }
    if copertura == "non coperto":
        risposta["nota"] = _NON_COPERTO.format(raggio=raggio_km)
    elif copertura == "non misurato":
        risposta["nota"] = _NON_MISURATO
    return risposta


async def pioggia_prima_delle_frane(
    *,
    cell_id: str | None = None,
    istat_code: str | None = None,
    dal: datetime,
    al: datetime | None = None,
    ore_prima: int = 72,
    raggio_km: float,
) -> dict[str, Any]:
    """Le frane datate della zona e la pioggia misurata nelle ore prima di ognuna."""
    if (cell_id is None) == (istat_code is None):
        return {"errore": "indica una cella (cell_id) oppure un comune (istat_code)"}
    zona = await zone_franose_repo.zona(cell_id, istat_code)
    if zona is None:
        return {"zona": _chiave_zona(cell_id, istat_code), "errore": "cella o comune non trovati"}
    soglie = load_regional_thresholds()
    macroregione = soglie.macroregion_for(zona.aoi_id) if zona.aoi_id else "italy_default"
    fine = (al or datetime.now(UTC)).astimezone(UTC)
    out = []
    for f in await zone_franose_repo.frane(
        cell_id, istat_code, dal.astimezone(UTC), fine, _FRANE_MAX
    ):
        quando: datetime = f["event_time"].astimezone(UTC)
        # Una frana datata al giorno può essere di qualunque ora di quel giorno:
        # la finestra arriva alla fine del giorno, ora di Roma (``istante_frana``).
        oraria = f["temporal_accuracy"] == "T1"
        fine_finestra = istante_frana(quando, oraria).replace(minute=0, second=0, microsecond=0)
        inizio_finestra = fine_finestra - timedelta(hours=ore_prima)
        voce: dict[str, Any] = {
            "quando": quando,
            "fonte": f["source"],
            "precisione_data": f["temporal_accuracy"],
            "finestra": {"inizio": inizio_finestra, "fine": fine_finestra},
        }
        scelto: tuple[Vicino, dict[str, Any]] | None = None
        # Il più vicino che ha misurato: uno senza ore in archivio non deve
        # nascondere quello a due chilometri che le ha.
        for v in await pluviometri_repo.vicini(
            f["lon"],
            f["lat"],
            raggio_km=raggio_km,
            dal=inizio_finestra.date(),
            al=fine_finestra.date(),
        ):
            misura = await _misura(v, inizio_finestra, fine_finestra, soglie, macroregione)
            if scelto is None or (
                scelto[1]["copertura"] == "non misurato" and misura["copertura"] != "non misurato"
            ):
                scelto = (v, misura)
        if scelto is None:
            voce["copertura"] = "non coperto"
        else:
            voce["pluviometro"] = _stazione(scelto[0])
            voce.update(scelto[1])
        out.append(voce)
    return {
        "zona": _chiave_zona(cell_id, istat_code),
        "macroregione": macroregione,
        "frane": out,
        "nota": "Frane datate di e-ITALICA, FraneItalia e del fact check di Limen, le più "
        f"recenti per prime (al massimo {_FRANE_MAX}). «non coperto»: nessun pluviometro "
        f"entro {raggio_km:g} km; «non misurato»: pluviometri senza ore in archivio. "
        "Nessuno dei due vuol dire che non piovesse.",
    }
