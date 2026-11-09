"""Misure offline di un segnale per cella: AUC e osservate/attese stratificate (#480).

Il metodo che ha deciso #295, #419, #420 e #469, prima vissuto in script di
sessione: una feature statica per cella contro una verità (celle bruciate da
EFFIS, celle allagate da Copernicus EMS), **dentro strati** di nodo meteo
(0,25°) e fascia di quota. Lo strato toglie il confondente più grosso: dove
piove o fa caldo di più succede di più, qualunque cosa dica la feature, e una
AUC sull'Italia intera premierebbe chi distingue il Nord dal Sud.

* **AUC stratificata**: la media delle AUC dentro ogni strato che ha sia
  positive sia negative, pesata con il numero di coppie positiva-negativa
  che lo strato confronta. 0,5 = la feature non distingue.
* **Osservate/attese** per classe della feature: le attese sono, cella per
  cella, il tasso di base del suo strato. Un rapporto sopra 1 in una classe
  vuol dire più eventi di quanti ne darebbe la sola posizione.

Le classi si fissano sul periodo di **stima** e si applicano invariate a quello
di **verifica**: una soglia scelta sugli stessi dati su cui la si misura
misurerebbe sé stessa.

Solo numpy, niente database: le righe le prepara ``data.repos.misure_repo``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

Vettore = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Campione:
    """Una riga per cella: valore della feature, verità, strato."""

    valori: Vettore
    positive: npt.NDArray[np.bool_]
    strati: npt.NDArray[np.str_]

    def __post_init__(self) -> None:
        n = len(self.valori)
        if len(self.positive) != n or len(self.strati) != n:
            raise ValueError("valori, positive e strati devono avere la stessa lunghezza")


@dataclass(frozen=True, slots=True)
class RigaOA:
    classe: str
    celle: int
    osservate: int
    attese: float

    @property
    def rapporto(self) -> float | None:
        return None if self.attese == 0 else self.osservate / self.attese


def strato(
    lon: float, lat: float, quota: float | None, *, passo: float, fasce: Sequence[float]
) -> str:
    """``nodo_x:nodo_y:fascia``; una quota ignota è una fascia sua."""
    nodo = f"{math.floor(lon / passo)}:{math.floor(lat / passo)}"
    if quota is None:
        return f"{nodo}:?"
    fascia = int(np.searchsorted(np.asarray(fasce, dtype=float), quota, side="right"))
    return f"{nodo}:{fascia}"


def auc(valori: Vettore, positive: npt.NDArray[np.bool_]) -> float | None:
    """AUC di Mann-Whitney, con i pari a metà; ``None`` senza una delle due classi."""
    n_pos = int(positive.sum())
    n_neg = len(positive) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    ordine = np.argsort(valori, kind="mergesort")
    ordinati = valori[ordine]
    ranghi = np.empty(len(valori), dtype=float)
    i = 0
    while i < len(ordinati):
        j = i
        while j + 1 < len(ordinati) and ordinati[j + 1] == ordinati[i]:
            j += 1
        ranghi[ordine[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    somma = float(ranghi[positive].sum())
    return (somma - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def auc_stratificata(c: Campione) -> tuple[float | None, int]:
    """La media pesata delle AUC per strato, e quanti strati vi entrano."""
    somma = 0.0
    pesi = 0.0
    usati = 0
    for s in np.unique(c.strati):
        dentro = c.strati == s
        p = c.positive[dentro]
        n_pos = int(p.sum())
        n_neg = len(p) - n_pos
        a = auc(c.valori[dentro], p)
        if a is None:
            continue
        peso = float(n_pos * n_neg)
        somma += a * peso
        pesi += peso
        usati += 1
    return (somma / pesi if pesi else None), usati


def soglie_quantili(valori: Vettore, classi: int = 5) -> Vettore:
    """I confini interni delle classi, dai quantili; i doppi si fondono
    (una feature con molti zeri fa meno classi, non classi vuote)."""
    q = np.quantile(valori, np.linspace(0, 1, classi + 1)[1:-1])
    return np.unique(q)


def osservate_attese(c: Campione, soglie: Vettore) -> list[RigaOA]:
    """O/A per classe della feature, con le attese dal tasso di base di ogni strato."""
    tasso = np.zeros(len(c.valori))
    for s in np.unique(c.strati):
        dentro = c.strati == s
        tasso[dentro] = c.positive[dentro].mean()
    classe = np.searchsorted(soglie, c.valori, side="right")
    righe: list[RigaOA] = []
    for k in range(len(soglie) + 1):
        dentro = classe == k
        sotto = "-inf" if k == 0 else f"{soglie[k - 1]:.4g}"
        sopra = "+inf" if k == len(soglie) else f"{soglie[k]:.4g}"
        righe.append(
            RigaOA(
                classe=f"[{sotto}, {sopra})",
                celle=int(dentro.sum()),
                osservate=int(c.positive[dentro].sum()),
                attese=float(tasso[dentro].sum()),
            )
        )
    return righe
