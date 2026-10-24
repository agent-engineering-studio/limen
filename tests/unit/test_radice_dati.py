"""Una sola radice per i dati del deployment (#302)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from limen.integrations.imperviousness.fetch import DEFAULT_DEST, _resolve_dest


def test_imperviousness_sotto_la_radice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIMEN_IMPERVIOUSNESS_DEST", raising=False)
    monkeypatch.delenv("LIMEN_DATA_ROOT", raising=False)
    assert _resolve_dest(None) == DEFAULT_DEST  # data/ del repo, come prima
    monkeypatch.setenv("LIMEN_DATA_ROOT", "/opt/limen")
    assert _resolve_dest(None) == Path("/opt/limen/sealing/clms_imd_2018/imd_2018_100m.tif")
    # La variabile specifica vince sempre sulla radice.
    monkeypatch.setenv("LIMEN_IMPERVIOUSNESS_DEST", "/altrove/imd.tif")
    assert _resolve_dest(None) == Path("/altrove/imd.tif")


@pytest.mark.parametrize(
    ("radice", "esistente", "creato"),
    [
        ("file:///var/lib/limen/mlruns", False, True),
        ("file:///var/lib/limen/mlruns", True, False),
        ("", False, False),
    ],
    ids=["nuovo_con_radice", "esistente_resta_dov_e", "senza_radice"],
)
def test_esperimento_mlflow_con_radice_artefatti(
    monkeypatch: pytest.MonkeyPatch, radice: str, esistente: bool, creato: bool
) -> None:
    """Un esperimento nuovo nasce con gli artefatti nel volume montato, non
    in ./mlruns della cartella di lavoro (nel container /app, non montato)."""
    import mlflow

    from limen.ml import train

    chiamate: list[tuple[str, Any]] = []
    monkeypatch.setattr(
        mlflow, "get_experiment_by_name", lambda nome: object() if esistente else None
    )
    monkeypatch.setattr(
        mlflow,
        "create_experiment",
        lambda nome, artifact_location=None: chiamate.append((nome, artifact_location)),
    )
    train.prepara_esperimento("limen-landslide", radice)
    assert chiamate == ([("limen-landslide", radice)] if creato else [])
