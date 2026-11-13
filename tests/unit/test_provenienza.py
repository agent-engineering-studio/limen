"""Provenienza dei report di misura e loro archivio (#481)."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from limen.cli import archivia_report
from limen.cli.provenienza import ambiente, gemello, provenienza, scrivi_report
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import load_hazard_thresholds

ORA = datetime(2026, 11, 10, 9, 30, tzinfo=UTC)


def test_ambiente_tiene_le_manopole_senza_segreti_ne_percorsi() -> None:
    env = {
        "LIMEN_BACKTEST_AOI": "it-sicilia",
        "LIMEN_REPORTS_DIR": "/Users/qualcuno/reports",
        "SCORING__ENGINE": "deterministic",
        "INSTALLAZIONE__TOKEN": "x",
        "LIMEN_API_KEY": "x",
        "LIMEN_MINIO_ROOT_USER": "x",
        "LIMEN_COMMIT": "abc",
        "HOME": "/Users/qualcuno",
    }
    assert ambiente(env) == {
        "LIMEN_BACKTEST_AOI": "it-sicilia",
        "LIMEN_REPORTS_DIR": "<percorso locale>",
        "SCORING__ENGINE": "deterministic",
    }


def test_ambiente_toglie_utente_e_password_dagli_url() -> None:
    env = {
        "SCORING__MLFLOW_TRACKING_URI": "postgresql://limen:segreta@postgres:5432/mlflow",
        "SCORING__MLFLOW_ARTIFACT_ROOT": "file:///var/lib/limen/mlruns",
    }
    assert ambiente(env) == {
        "SCORING__MLFLOW_ARTIFACT_ROOT": "file:///var/lib/limen/mlruns",
        "SCORING__MLFLOW_TRACKING_URI": "postgresql://<credenziali>@postgres:5432/mlflow",
    }


def test_provenienza_dichiara_commit_versioni_e_comando(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIMEN_COMMIT", "0ec0570")
    p = provenienza(ora=ORA, argv=["/app/.venv/bin/limen", "backtest-wildfire"], env={})
    assert p["commit"] == "0ec0570"
    assert p["comando"] == "limen backtest-wildfire"
    assert p["generato"] == "2026-11-10T09:30:00+00:00"
    assert p["versioni"] == {h.value: load_hazard_thresholds(h).model_version for h in HazardType}


def _report(cartella: Path, nome: str, ora: datetime) -> Path:
    out = cartella / nome
    scrivi_report(out, "# Backtest\n\nHit rate 79 %\n", ora=ora, argv=["limen", "x"], env={})
    return out


def test_scrivi_report_aggiunge_provenienza_e_gemello(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIMEN_COMMIT", "0ec0570")
    out = _report(tmp_path, "backtest.md", ORA)
    testo = out.read_text(encoding="utf-8")
    assert testo.startswith("# Backtest\n\nHit rate 79 %\n\n## Provenienza")
    assert "| commit | `0ec0570` |" in testo
    dati = json.loads(gemello(out).read_text(encoding="utf-8"))
    assert dati["report"] == "backtest.md"
    assert dati["commit"] == "0ec0570"


def test_archivia_copia_e_indicizza_dal_piu_recente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIMEN_COMMIT", "0ec0570")
    sorgente = tmp_path / "reports"
    sorgente.mkdir()
    vecchio = _report(sorgente, "a.md", datetime(2026, 1, 1, tzinfo=UTC))
    nuovo = _report(sorgente, "b.md", ORA)
    misure = tmp_path / "misure"
    args = argparse.Namespace(report=[str(vecchio), str(nuovo)], cartella=str(misure))
    assert archivia_report.run(args) == 0
    assert (misure / "a.md").is_file()
    assert gemello(misure / "b.md").is_file()
    righe = (misure / archivia_report.INDICE).read_text(encoding="utf-8").splitlines()
    voci = [r for r in righe if r.startswith("| 20")]
    assert [v.split(" | ")[1] for v in voci] == ["[b.md](b.md)", "[a.md](a.md)"]


def test_archivia_rifiuta_un_report_senza_provenienza(tmp_path: Path) -> None:
    vecchio = tmp_path / "vecchio.md"
    vecchio.write_text("# senza provenienza\n", encoding="utf-8")
    args = argparse.Namespace(report=[str(vecchio)], cartella=str(tmp_path / "misure"))
    assert archivia_report.run(args) == 2
    assert not (tmp_path / "misure").exists()
