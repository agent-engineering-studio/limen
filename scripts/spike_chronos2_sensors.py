"""Spike #80 — Chronos-2 sulle serie dei sensori in situ, go/no-go.

**Non è codice di produzione.** Sta in `scripts/` e non nel pacchetto, non ha
test, e le sue dipendenze non entrano in `pyproject.toml`:

    uv run --no-project --with "chronos-forecasting>=2.0" --with pandas \\
        --with scikit-learn python scripts/spike_chronos2_sensors.py

Domanda: un modello fondazionale per serie temporali, con la **pioggia prevista
come covariata futura nota**, anticipa i precursori misurati da un sensore
meglio delle due baseline che Limen già saprebbe scrivere?

Dati: USGS, "Landslide monitoring site installation details, geotechnical
parameters, hydrologic time series data, and landslide locations from storms
occurring between 25 December 2022 and 19 January 2023 in the San Francisco Bay
area, California", ScienceBase 66ccb50cd34e98e8a92435bf, **CC0 1.0**. Tre siti
(BALT1/2/3), 5 minuti, 26 giorni di fiumi atmosferici: 176-502 mm di pioggia.
Piezometri, umidità del suolo, pluviometro.

Perché dati pubblici e non i nostri: `sensor_devices`, `sensor_observations` e
`sensor_features_hourly` sono **vuote** su questo deployment, e `enable_insitu`
è false. La issue prevedeva il caso.

Il limite che questo dataset impone, e che nessuna scelta di modello può
aggirare: **non contiene spostamento**. Niente inclinometro, niente
estensimetro, quindi niente `displacement_mm`, `velocity_mmd`,
`inverse_velocity`. Il criterio di go scritto nella issue — lead time sulla
velocità inversa rispetto alla soglia `kinematic` — non è misurabile su dati
reali, e misurarlo su dati sintetici significherebbe generare una serie con un
modello e poi verificare che un forecaster la ricostruisce: si misurerebbe il
generatore, non Chronos-2. Qui si misura ciò che i dati reggono — la pressione
interstiziale, che in `scoring/engine.py:209` sostituisce direttamente il
fattore API della componente M — e il resto si dichiara non misurato.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Dati ────────────────────────────────────────────────────────────────────

SCIENCEBASE_ITEM = "66ccb50cd34e98e8a92435bf"
_BASE = f"https://www.sciencebase.gov/catalog/file/get/{SCIENCEBASE_ITEM}?f=__disk__"
SITES: dict[str, str] = {
    "BALT1": _BASE + "b9%2F9b%2F4c%2Fb99b4cfd91998e5abd6c4743f407cb0375112136",
    "BALT2": _BASE + "e7%2F2f%2Fd7%2Fe72fd74509f64f1657701918708db40042173b82",
    "BALT3": _BASE + "23%2F98%2F06%2F239806da157cfb2d1c256079ae92be2e1f9b156c",
}
#: Le prime nove righe sono intestazione descrittiva, la decima è l'header.
_HEADER_ROWS = 9
#: 1 cm di colonna d'acqua = 0,0980665 kPa. `SensorFeatures.pore_pressure_kpa`
#: vive in kPa, quindi il confronto con le soglie va fatto qui.
CM_H2O_TO_KPA = 0.0980665

#: Oltre questa quota di ore mancanti la colonna non e' una serie con lacune,
#: e' un sensore rotto: interpolarla vorrebbe dire inventare meta' dei dati.
_MAX_GAP_FRACTION = 0.10

CONTEXT_HOURS = 168
HORIZONS = (24, 48, 72)
ORIGIN_STEP_HOURS = 6
QUANTILES = (0.1, 0.5, 0.9)


def fetch(cache: Path) -> dict[str, pd.DataFrame]:
    """Scarica (una volta) e porta a passo orario le tre serie."""
    cache.mkdir(parents=True, exist_ok=True)
    out: dict[str, pd.DataFrame] = {}
    for site, url in SITES.items():
        raw = cache / f"{site.lower()}.csv"
        if not raw.exists():
            print(f"  scarico {site}…")
            with urllib.request.urlopen(url, timeout=180) as r:
                raw.write_bytes(r.read())
        df = pd.read_csv(raw, skiprows=_HEADER_ROWS)
        df.columns = [c.strip() for c in df.columns]
        stamp = pd.to_datetime(df[df.columns[0]], format="%m/%d/%Y %H:%M")
        df = df.drop(columns=[df.columns[0]]).set_index(stamp)
        df = df.apply(pd.to_numeric, errors="coerce")
        hourly = pd.DataFrame(index=df.resample("1h").mean().index)
        for col in df.columns:
            # La pioggia si somma sull'ora, tutto il resto si media: è la
            # stessa regola di `iot_rollup`, e sbagliarla qui darebbe un
            # accumulo dodici volte troppo grande.
            hourly[col] = (
                df[col].resample("1h").sum()
                if col.startswith("Rain")
                else df[col].resample("1h").mean()
            )
        # `dropna()` sull'intero frame era un errore silenzioso: a BALT2 un
        # sensore e' giu' per 368 ore su 624, e buttare le righe con un NaN
        # qualsiasi eliminava 365 ore **per ogni colonna** di quel sito,
        # pioggia compresa. Poi il troncamento si propagava agli altri due
        # siti, perche' le origini si tagliano sulla serie piu' corta: 73
        # origini per orizzonte diventavano 12, e gli episodi da 62 a 5.
        # Si scarta la **colonna** troppo bucata, non l'ora.
        gappy = [c for c in hourly.columns if hourly[c].isna().mean() > _MAX_GAP_FRACTION]
        if gappy:
            print(f"  {site}: sensori scartati per lacune > {_MAX_GAP_FRACTION:.0%}: {gappy}")
        kept = hourly.drop(columns=gappy).interpolate(limit=6, limit_direction="both")
        out[site] = kept.dropna()
    return out


#: Escursione minima perché una serie conti come "il sensore ha risposto",
#: nell'unità della grandezza: 0,5 kPa ≈ 5 cm di colonna d'acqua, 0,02 m3/m3 è
#: circa il rumore dichiarato di una sonda capacitiva EC-5.
_FLAT_RANGE = {"pore_pressure_kpa": 0.5, "soil_moisture": 0.02}


@dataclass(frozen=True, slots=True)
class Series:
    """Una serie bersaglio con la sua covariata di pioggia."""

    site: str
    name: str
    kind: str
    y: np.ndarray
    rain: np.ndarray

    @property
    def label(self) -> str:
        return f"{self.site}/{self.name}"

    @property
    def responsive(self) -> bool:
        """Il sensore ha reagito alla stagione, o è piatto.

        Un piezometro che in 500 mm di pioggia si muove di 0,3 cH2O non è una
        serie difficile: è un sensore che non misura. Tenerlo fra i bersagli
        gonfierebbe ogni MAE verso lo zero e farebbe sembrare bravi tutti.

        La soglia è **per grandezza**: kPa e m3/m3 non si confrontano con lo
        stesso numero, e un unico valore scarterebbe in blocco tutta l'umidità
        del suolo, che si muove fra 0,15 e 0,45.
        """
        return float(np.nanmax(self.y) - np.nanmin(self.y)) > _FLAT_RANGE[self.kind]


def build_series(frames: dict[str, pd.DataFrame]) -> list[Series]:
    out: list[Series] = []
    for site, df in frames.items():
        rain = df["Rain (mm)"].to_numpy(dtype=float)
        for col in df.columns:
            if col.startswith("PP"):
                kind, y = "pore_pressure_kpa", df[col].to_numpy(dtype=float) * CM_H2O_TO_KPA
            elif col.startswith("SM"):
                kind, y = "soil_moisture", df[col].to_numpy(dtype=float)
            else:
                continue
            out.append(Series(site=site, name=col.split(" ")[0], kind=kind, y=y, rain=rain))
    return out


# ── Baseline ────────────────────────────────────────────────────────────────


def baseline_persistence(hist: np.ndarray, horizon: int) -> np.ndarray:
    """L'ultimo valore, ripetuto. La baseline che ogni forecast deve battere."""
    return np.full(horizon, hist[-1], dtype=float)


def baseline_rain_linear(
    hist: np.ndarray, rain_hist: np.ndarray, rain_future: np.ndarray, horizon: int
) -> np.ndarray:
    """Regressione lineare su pioggia cumulata 24/72 h — quello che fa oggi l'A_PI.

    Addestrata sulla sola finestra di contesto, come farebbe un job che non
    tiene stato: due regressori (accumulo a 24 e a 72 ore) più intercetta,
    minimi quadrati. È la baseline onesta da battere, perché è ciò che Limen
    saprebbe già scrivere senza nessun modello fondazionale.
    """
    acc24 = pd.Series(rain_hist).rolling(24, min_periods=1).sum().to_numpy()
    acc72 = pd.Series(rain_hist).rolling(72, min_periods=1).sum().to_numpy()
    design = np.column_stack([acc24, acc72, np.ones_like(acc24)])
    coef, *_ = np.linalg.lstsq(design, hist, rcond=None)

    full = np.concatenate([rain_hist, rain_future])
    f24 = pd.Series(full).rolling(24, min_periods=1).sum().to_numpy()[-horizon:]
    f72 = pd.Series(full).rolling(72, min_periods=1).sum().to_numpy()[-horizon:]
    return np.column_stack([f24, f72, np.ones(horizon)]) @ coef


# ── Metriche ────────────────────────────────────────────────────────────────


@dataclass
class Tally:
    """Accumulatore per (metodo, orizzonte)."""

    abs_err: list[float] = field(default_factory=list)
    covered: list[float] = field(default_factory=list)
    lead_gain_h: list[float] = field(default_factory=list)
    episodes: int = 0
    detected: int = 0
    false_alarms: int = 0
    quiet_windows: int = 0
    seconds: list[float] = field(default_factory=list)

    def summary(self) -> dict[str, float | None | int]:
        def med(xs: list[float]) -> float | None:
            return float(np.median(xs)) if xs else None

        return {
            "mae": med(self.abs_err),
            "coverage": (float(np.mean(self.covered)) if self.covered else None),
            # Il lead time **solo sugli episodi visti**, con accanto quanti ne
            # ha visti: un metodo che ne coglie uno solo, con dieci ore di
            # anticipo, non è migliore di uno che li coglie tutti puntuale.
            "lead_gain_h_median": med(self.lead_gain_h),
            "episodes": self.episodes,
            "detected": self.detected,
            "detection_rate": (self.detected / self.episodes if self.episodes else None),
            # Il metro accanto alla metrica: quante volte ha gridato al lupo
            # in una finestra dove non succedeva niente.
            "false_alarm_rate": (
                self.false_alarms / self.quiet_windows if self.quiet_windows else None
            ),
            "seconds_per_series": med(self.seconds),
            "n": len(self.abs_err),
        }


def crossing_hour(values: np.ndarray, threshold: float) -> int | None:
    """Prima ora in cui la serie supera la soglia, o ``None``."""
    hits = np.flatnonzero(values >= threshold)
    return int(hits[0]) if hits.size else None


def score_episode(
    t: Tally, pred: np.ndarray, truth: np.ndarray, threshold: float, last_observed: float
) -> None:
    """Registra l'esito di una finestra rispetto alla soglia di episodio.

    Tre esiti distinti, e tenerli distinti è il punto: un episodio **visto in
    anticipo**, un episodio **mancato**, e un allarme in una finestra quieta.
    Mediare i tre in un solo numero — come faceva la prima versione, che dava
    a un episodio mancato una penalità di -72 h — produce una mediana che dice
    solo quanti ne ha mancati, mascherata da lead time.

    **L'episodio è un'ascesa, non uno stato.** Se all'origine il sensore è già
    sopra soglia non c'è niente da anticipare: la persistenza "indovina" al
    primo passo e ogni metodo segna lead time zero, che è esattamente il
    risultato inutile che la prima versione produceva su tutte le righe.
    Quelle finestre si scartano.
    """
    if last_observed >= threshold:
        return
    t_true = crossing_hour(truth, threshold)
    t_pred = crossing_hour(pred, threshold)
    if t_true is None:
        t.quiet_windows += 1
        if t_pred is not None:
            t.false_alarms += 1
        return
    t.episodes += 1
    if t_pred is None:
        return
    t.detected += 1
    t.lead_gain_h.append(float(t_true - t_pred))


# ── Esperimento ─────────────────────────────────────────────────────────────


def rolling_origins(n: int, horizon: int) -> list[int]:
    first = CONTEXT_HOURS
    last = n - horizon
    return list(range(first, last + 1, ORIGIN_STEP_HOURS))


def run(limit_series: int | None, skip_chronos: bool) -> dict[str, Any]:
    print("Dati USGS (CC0)…")
    frames = fetch(Path(__file__).resolve().parent.parent / ".cache" / "spike80")
    series = build_series(frames)
    targets = [s for s in series if s.responsive]
    flat = [s.label for s in series if not s.responsive]
    if limit_series:
        targets = targets[:limit_series]
    print(f"  {len(series)} serie, {len(targets)} reattive; piatte scartate: {flat}")

    pipeline = None
    if not skip_chronos:
        from chronos import Chronos2Pipeline

        t0 = time.perf_counter()
        pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
        load_seconds = time.perf_counter() - t0
        print(f"  modello caricato in {load_seconds:.1f}s")
    else:
        load_seconds = None

    # Chiave a tre: mediare un errore in kPa con uno in m3/m3 darebbe un
    # numero che non è nessuna delle due grandezze, e la MAE dell'umidità
    # (~0,03) schiaccerebbe quella del piezometro (~1,0) fino a farla sparire.
    tallies: dict[tuple[str, int, str], Tally] = {}

    def tally(method: str, horizon: int, kind: str) -> Tally:
        return tallies.setdefault((method, horizon, kind), Tally())

    # La soglia dell'episodio è il 90mo percentile della serie stessa: una
    # soglia assoluta non ha senso su piezometri a profondità diverse, e
    # `kinematic.inverse_velocity_alarm` riguarda una grandezza che questo
    # dataset non contiene.
    thresholds = {s.label: float(np.nanpercentile(s.y, 90)) for s in targets}
    n_hours = min(len(s.y) for s in targets)

    for horizon in HORIZONS:
        origins = rolling_origins(n_hours, horizon)
        print(f"  orizzonte {horizon}h: {len(origins)} origini x {len(targets)} serie")
        for o in origins:
            # Le baseline, una serie alla volta: sono aritmetica.
            for sr in targets:
                hist, truth = sr.y[o - CONTEXT_HOURS : o], sr.y[o : o + horizon]
                rain_hist, rain_future = sr.rain[o - CONTEXT_HOURS : o], sr.rain[o : o + horizon]
                thr = thresholds[sr.label]
                for name, pred in (
                    ("persistence", baseline_persistence(hist, horizon)),
                    ("rain_linear", baseline_rain_linear(hist, rain_hist, rain_future, horizon)),
                ):
                    t = tally(name, horizon, sr.kind)
                    t.abs_err.append(float(np.mean(np.abs(pred - truth))))
                    score_episode(t, pred, truth, thr, hist[-1])

            if pipeline is None:
                continue

            # Chronos-2 in **un colpo per origine**, tutte le serie insieme:
            # è così che lo chiamerebbe il job (un batch per tick), ed è
            # l'unico modo per cui il costo misurato somigli a quello vero.
            # Una chiamata per serie sarebbe anche ~17 volte piu' lenta a parità di
            # lavoro, perché il modello fa cross-learning fra gli item.
            for name, with_cov in (("chronos2", False), ("chronos2_rain", True)):
                started = time.perf_counter()
                preds = _forecast_batch(pipeline, targets, o, horizon, with_cov)
                elapsed = time.perf_counter() - started
                for sr in targets:
                    truth = sr.y[o : o + horizon]
                    hist_last = sr.y[o - 1]
                    lo, mid, hi = preds[sr.label]
                    t = tally(name, horizon, sr.kind)
                    t.seconds.append(elapsed / len(targets))
                    t.abs_err.append(float(np.mean(np.abs(mid - truth))))
                    t.covered.append(float(np.mean((truth >= lo) & (truth <= hi))))
                    score_episode(t, mid, truth, thresholds[sr.label], hist_last)

    return {
        "series_total": len(series),
        "series_used": [s.label for s in targets],
        "series_flat_excluded": flat,
        "context_hours": CONTEXT_HOURS,
        "origin_step_hours": ORIGIN_STEP_HOURS,
        "model_load_seconds": load_seconds,
        "results": {
            f"{kind}|{m}@{h}h": t.summary()
            for (m, h, kind), t in sorted(
                tallies.items(), key=lambda kv: (kv[0][2], kv[0][1], kv[0][0])
            )
        },
    }


#: Istante fittizio di partenza: a Chronos-2 serve un asse dei tempi regolare,
#: non la data vera, e il dataset USGS è già a passo orario esatto.
_EPOCH = pd.Timestamp("2022-12-25 00:00:00")


def _forecast_batch(
    pipeline: Any,
    targets: list[Series],
    origin: int,
    horizon: int,
    with_covariates: bool,
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Un `predict_df` per tutte le serie a una data origine.

    Formato lungo: una riga per (id, istante). Con le covariate, `future_df`
    porta la pioggia delle ore da prevedere — che nel worker verrebbe da
    Open-Meteo, l'unica ragione per cui un modello con covariate può battere
    la persistenza su un precursore guidato dalla pioggia.
    """
    ctx_idx = pd.date_range(
        _EPOCH + pd.Timedelta(hours=origin - CONTEXT_HOURS), periods=CONTEXT_HOURS, freq="h"
    )
    fut_idx = pd.date_range(_EPOCH + pd.Timedelta(hours=origin), periods=horizon, freq="h")

    ctx_rows, fut_rows = [], []
    for sr in targets:
        block = {
            "id": sr.label,
            "timestamp": ctx_idx,
            "target": sr.y[origin - CONTEXT_HOURS : origin],
        }
        if with_covariates:
            block["rain"] = sr.rain[origin - CONTEXT_HOURS : origin]
            fut_rows.append(
                pd.DataFrame(
                    {
                        "id": sr.label,
                        "timestamp": fut_idx,
                        "rain": sr.rain[origin : origin + horizon],
                    }
                )
            )
        ctx_rows.append(pd.DataFrame(block))

    context_df = pd.concat(ctx_rows, ignore_index=True)
    kwargs: dict[str, Any] = {}
    if with_covariates:
        kwargs["future_df"] = pd.concat(fut_rows, ignore_index=True)

    pred = pipeline.predict_df(
        context_df,
        prediction_length=horizon,
        quantile_levels=list(QUANTILES),
        id_column="id",
        timestamp_column="timestamp",
        target="target",
        **kwargs,
    )
    out: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    cols = [str(q) for q in QUANTILES]
    for label, g in pred.groupby("id", sort=False):
        arr = g[cols].to_numpy(dtype=float)
        out[str(label)] = (arr[:, 0], arr[:, 1], arr[:, 2])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit-series", type=int, default=None)
    ap.add_argument("--skip-chronos", action="store_true", help="solo baseline")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    report = run(args.limit_series, args.skip_chronos)
    text = json.dumps(report, indent=2, default=str)
    print(text)
    if args.out:
        args.out.write_text(text)


if __name__ == "__main__":
    main()
