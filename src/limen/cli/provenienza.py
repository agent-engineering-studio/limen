"""Da dove viene un report di misura (#481).

Un numero di backtest citato in una PR o nel libro va rifatto, e per rifarlo
servono il commit, la ``model_version`` di ogni pericolo, il comando e le
manopole d'ambiente con cui è uscito. Ogni comando di misura scrive il suo
report con :func:`scrivi_report`, che aggiunge in coda la sezione
«Provenienza» e accanto un ``.json`` con gli stessi campi: il secondo è quello
che ``limen archivia-report`` legge per costruire l'indice di ``docs/misure``.

Dell'ambiente entrano solo le manopole di Limen, mai i segreti (token, chiavi,
password, stringhe di connessione) e mai il valore di un percorso locale, che
in un file versionato direbbe solo com'è fatto il disco di chi ha misurato.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen import __version__
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import load_hazard_thresholds

#: Lo sha del commit, scritto nell'immagine dalla CI (``--build-arg``).
COMMIT_ENV = "LIMEN_COMMIT"
_PREFISSI = ("LIMEN_", "SCORING__", "FORECAST__", "BACKTEST__")
_SEGRETI = ("TOKEN", "KEY", "SECRET", "PASSWORD", "CONNECTION", "CREDENZIAL")
_PERCORSO = "<percorso locale>"


def commit() -> str | None:
    """Lo sha dell'immagine, oppure quello del checkout (``+modifiche`` se sporco)."""
    dichiarato = os.getenv(COMMIT_ENV)
    if dichiarato:
        return dichiarato
    radice = Path(__file__).resolve().parents[3]
    try:
        sha = subprocess.run(
            ["git", "-C", str(radice), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        sporco = subprocess.run(
            ["git", "-C", str(radice), "diff", "--quiet", "HEAD", "--", "src"],
            capture_output=True,
            timeout=5,
        ).returncode
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{sha}+modifiche" if sporco else sha


def ambiente(env: Mapping[str, str]) -> dict[str, str]:
    """Le manopole di Limen impostate, senza segreti e senza percorsi."""
    out: dict[str, str] = {}
    for nome in sorted(env):
        if not nome.startswith(_PREFISSI) or nome == COMMIT_ENV:
            continue
        if any(s in nome.upper() for s in _SEGRETI):
            continue
        valore = env[nome]
        out[nome] = _PERCORSO if valore.startswith(("/", "~", "./")) else valore
    return out


def provenienza(
    *,
    ora: datetime | None = None,
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    comando = list(sys.argv if argv is None else argv)
    if comando:
        comando[0] = Path(comando[0]).name
    return {
        "generato": (ora or datetime.now(UTC)).isoformat(timespec="seconds"),
        "limen": __version__,
        "commit": commit(),
        "versioni": {h.value: load_hazard_thresholds(h).model_version for h in HazardType},
        "comando": " ".join(comando),
        "ambiente": ambiente(os.environ if env is None else env),
    }


def sezione(p: Mapping[str, Any]) -> list[str]:
    righe = [
        "## Provenienza",
        "",
        "| | |",
        "|---|---|",
        f"| generato | {p['generato']} |",
        f"| commit | `{p['commit'] or 'ignoto'}` |",
        f"| limen | {p['limen']} |",
        *(f"| {h} | `{v}` |" for h, v in p["versioni"].items()),
        f"| comando | `{p['comando']}` |",
    ]
    righe += [f"| `{k}` | `{v}` |" for k, v in p["ambiente"].items()]
    return righe


def scrivi_report(percorso: Path, testo: str, **kwargs: Any) -> Path:
    """Il report con la sua provenienza in coda, e il ``.json`` gemello."""
    p = provenienza(**kwargs)
    corpo = testo.rstrip("\n") + "\n\n" + "\n".join(sezione(p)) + "\n"
    percorso.write_text(corpo, encoding="utf-8")
    gemello(percorso).write_text(
        json.dumps({"report": percorso.name, **p}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return percorso


def gemello(percorso: Path) -> Path:
    return percorso.with_suffix(".provenienza.json")
