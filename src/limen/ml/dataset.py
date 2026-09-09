"""Convert ``training_samples`` rows into the (X, y, group) arrays.

Heavy deps (numpy + pandas) are imported lazily so plain code paths
can ``import limen.ml.dataset`` without the `ml` group installed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.repos.training_samples_repo import TrainingSample

# Order matters — the booster's feature_names list is persisted to MLflow
# so the live engine projects bundles onto the same vector.
#
# Il nome resta `CANONICAL_FEATURES` ed è la lista **delle frane**: i run già
# registrati in MLflow portano questo schema, e rinominarla non comprerebbe
# niente. Le liste per pericolo stanno in `FEATURES_BY_HAZARD`.
CANONICAL_FEATURES: tuple[str, ...] = (
    "static.susc_ispra",
    "static.iffi_density_500",
    "static.distance_to_iffi_m",
    "static.slope_deg",
    "static.twi",
    "static.curvature",
    "static.litho_weight",
    "static.pai_class_norm",
    "insar.velocity_mmy",
    "insar.accel_mmy2",
    "insar.scatterer_count",
    # Antecedent rainfall at the sample's (cell, time) — CERRA replay
    # (ml/rain_features.py). Absent (pre-enrichment rows) degrades to 0.
    "rain.rain_24h_mm",
    "rain.rain_72h_mm",
    "rain.rain_30d_mm",
    "rain.max_i_24h_mmh",
)

#: Feature dell'incendio (#68). **Lista separata, non in coda alla comune.**
#:
#: L'issue lasciava la scelta: accodare `fire.*` a `CANONICAL_FEATURES` o
#: tenere liste per pericolo. Accodare darebbe a un modello frane sei colonne
#: sempre a zero e a un modello incendio sedici — densità IFFI, velocità
#: InSAR, litologia descrivono un versante che si muove, non un bosco che
#: brucia. Colonne costanti non fanno danno all'albero, ma fanno danno a chi
#: legge lo SHAP: sedici feature a importanza zero nascondono le tre che
#: contano.
#:
#: `rain.rain_30d_mm` è l'unica riusata, e non per comodità: trenta giorni di
#: pioggia sono la stessa grandezza per un versante saturo e per un bosco
#: secco, letta con il segno opposto.
WILDFIRE_FEATURES: tuple[str, ...] = (
    # Meteo del giorno, dalla catena FWI ricostruita (ml/fire_features.py).
    "fire.fwi",
    "fire.isi",
    "fire.dc",
    # Statiche: combustibile, morfologia, interfaccia urbano-foresta.
    "fire.fuel_class_norm",
    "fire.wui_proximity_norm",
    "fire.density_hist",
    "static.slope_deg",
    # Pioggia antecedente: qui è un *inibitore*, non un innesco.
    "rain.rain_30d_mm",
)

#: Quale schema per quale pericolo. Un pericolo senza voce usa quello delle
#: frane, che è il comportamento di prima della #68.
FEATURES_BY_HAZARD: dict[HazardType, tuple[str, ...]] = {
    HazardType.LANDSLIDE: CANONICAL_FEATURES,
    HazardType.WILDFIRE: WILDFIRE_FEATURES,
}


def features_for(hazard: HazardType) -> tuple[str, ...]:
    """Lo schema ordinato di un pericolo."""
    return FEATURES_BY_HAZARD.get(hazard, CANONICAL_FEATURES)


@dataclass(frozen=True, slots=True)
class TrainingMatrix:
    """X, y, groups (spatial block) + the ordered feature schema."""

    feature_names: tuple[str, ...]
    X: Any  # np.ndarray
    y: Any  # np.ndarray
    groups: tuple[str, ...]


def _flatten(features: dict[str, Any]) -> dict[str, float]:
    """Appiattisce il vettore, ignorando ciò che non è un numero.

    Il dizionario delle feature porta anche gli **input grezzi** che servono a
    rigiocare il motore V1 sullo stesso campione — `landuse_code` è una
    stringa CLC. Sono provenienza, non colonne: senza questo filtro un
    `float("312")` andrebbe a buon fine e infilerebbe un codice di uso del
    suolo nella matrice come se fosse una grandezza continua.
    """
    flat: dict[str, float] = {}
    for top, child in features.items():
        if not isinstance(child, dict):
            continue
        for k, v in child.items():
            if v is None:
                flat[f"{top}.{k}"] = 0.0
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            flat[f"{top}.{k}"] = float(v)
    return flat


def to_matrix(
    samples: list[TrainingSample], *, hazard: HazardType = DEFAULT_HAZARD
) -> TrainingMatrix:
    """Stack samples into the ordered matrix of the hazard's schema."""
    import numpy as np

    names = features_for(hazard)
    rows: list[list[float]] = []
    labels: list[int] = []
    groups: list[str] = []
    for s in samples:
        flat = _flatten(s.features)
        rows.append([flat.get(name, 0.0) for name in names])
        labels.append(int(s.label))
        groups.append(s.split_block)
    matrix_x = np.array(rows, dtype=float)
    labels_y = np.array(labels, dtype=int)
    return TrainingMatrix(
        feature_names=names,
        X=matrix_x,
        y=labels_y,
        groups=tuple(groups),
    )


def matrix_sha(matrix: TrainingMatrix) -> str:
    """SHA-256 della matrice, per la riproducibilità richiesta dalla #68.

    Sui valori **arrotondati a nove decimali** e non sui byte grezzi: BLAS
    somma in ordine dipendente dal numero di thread, e una differenza
    nell'ultimo bit di mantissa cambierebbe l'hash senza che il dataset sia
    cambiato — un controllo che dà falsi allarmi non lo guarda più nessuno.
    Nove decimali stanno molto sotto la precisione di qualunque feature qui e
    molto sopra il rumore di somma.

    Include nomi, etichette e blocchi: due matrici con gli stessi numeri ma
    colonne diverse, o la stessa X con uno split diverso, non sono lo stesso
    dataset.
    """
    import numpy as np

    digest = hashlib.sha256()
    digest.update("|".join(matrix.feature_names).encode("utf-8"))
    digest.update(b"\x00")
    rounded = np.round(np.asarray(matrix.X, dtype=float), 9)
    digest.update(np.ascontiguousarray(rounded).tobytes())
    digest.update(np.ascontiguousarray(np.asarray(matrix.y, dtype=np.int64)).tobytes())
    digest.update("|".join(matrix.groups).encode("utf-8"))
    return digest.hexdigest()


def prune_collinear(
    matrix: TrainingMatrix, *, threshold: float
) -> tuple[TrainingMatrix, list[tuple[str, str, float]]]:
    """Drop features whose |Pearson r| with an earlier feature exceeds
    ``threshold``. Canonical order is the priority: the first feature of
    a collinear pair survives. GBMs tolerate collinearity numerically,
    but it splits SHAP credit across twins and muddies the breakdown.

    Returns the pruned matrix + the dropped pairs ``(kept, dropped, r)``.
    """
    import numpy as np

    x = np.asarray(matrix.X, dtype=float)
    names = list(matrix.feature_names)
    # Zero-variance columns produce NaN correlations — treat as 0.
    with np.errstate(invalid="ignore"):
        corr = np.corrcoef(x, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0)

    dropped: list[tuple[str, str, float]] = []
    keep: list[int] = []
    for j in range(len(names)):
        twin = next(
            (i for i in keep if abs(corr[i, j]) > threshold),
            None,
        )
        if twin is None:
            keep.append(j)
        else:
            dropped.append((names[twin], names[j], float(corr[twin, j])))
    if not dropped:
        return matrix, []
    return (
        TrainingMatrix(
            feature_names=tuple(names[j] for j in keep),
            X=x[:, keep],
            y=matrix.y,
            groups=matrix.groups,
        ),
        dropped,
    )


__all__ = ["CANONICAL_FEATURES", "TrainingMatrix", "prune_collinear", "to_matrix"]
