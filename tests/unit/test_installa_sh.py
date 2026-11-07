"""``scripts/installa.sh`` (#405): il .env si controlla prima di partire.

Docker e make sono finti: qui conta che un .env incompleto fermi lo script
prima di ``nuovo_host.sh``, cioè prima di ogni avvio e di ogni download.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_RADICE = Path(__file__).resolve().parents[2]
_COMPLETO = "LIMEN_DATA_ROOT=/dati\nLIMEN_DOMINIO=localhost\nLIMEN_PROXY_BIND=127.0.0.1\n"
_SEGRETO = "sk-non-si-stampa"


def _eseguibile(percorso: Path, testo: str) -> None:
    percorso.write_text(f"#!/bin/sh\n{testo}\n")
    percorso.chmod(percorso.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    dove = tmp_path / "clone"
    (dove / "scripts").mkdir(parents=True)
    shutil.copy(_RADICE / "scripts" / "installa.sh", dove / "scripts")
    shutil.copy(_RADICE / ".env.example", dove)
    _eseguibile(dove / "scripts" / "nuovo_host.sh", 'echo PARTITO "$@"')
    subprocess.run(["git", "init", "-q"], cwd=dove, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        ],
        cwd=dove,
        check=True,
    )
    finti = tmp_path / "finti"
    finti.mkdir()
    _eseguibile(finti / "docker", 'case "$1" in info) echo 17179869184;; esac')
    _eseguibile(finti / "make", "echo 'GNU Make 4.4.1'")
    return dove


def _lancia(clone: Path) -> subprocess.CompletedProcess[str]:
    ambiente = os.environ | {
        "PATH": f"{clone.parent / 'finti'}:{os.environ['PATH']}",
        "HOME": str(clone.parent),
    }
    return subprocess.run(
        ["bash", "scripts/installa.sh"],
        cwd=clone,
        env=ambiente,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )


def test_senza_env_lo_crea_e_parte(clone: Path) -> None:
    esito = _lancia(clone)
    assert esito.returncode == 0, esito.stderr
    assert "PARTITO --solo-stack" in esito.stdout
    assert (clone / ".env").stat().st_mode & 0o077 == 0


def test_una_variabile_vuota_ferma_tutto_e_ne_dice_il_nome(clone: Path) -> None:
    (clone / ".env").write_text(f"{_COMPLETO}ANTHROPIC_API_KEY=\nEMAIL_HOST=  \n")
    esito = _lancia(clone)
    assert esito.returncode != 0
    assert "PARTITO" not in esito.stdout
    assert "ANTHROPIC_API_KEY" in esito.stderr
    assert "EMAIL_HOST" in esito.stderr


def test_i_segreti_generati_dopo_possono_essere_vuoti(clone: Path) -> None:
    (clone / ".env").write_text(f"{_COMPLETO}DB__TILES_PASSWORD=\nINSTALLAZIONE__TOKEN=\n")
    assert "PARTITO" in _lancia(clone).stdout


def test_una_radice_relativa_non_passa(clone: Path) -> None:
    (clone / ".env").write_text("LIMEN_DATA_ROOT=dati\nLIMEN_DOMINIO=localhost\n")
    esito = _lancia(clone)
    assert "PARTITO" not in esito.stdout
    assert "assoluto" in esito.stderr


def test_i_valori_del_env_non_si_stampano(clone: Path) -> None:
    (clone / ".env").write_text(f"{_COMPLETO}ANTHROPIC_API_KEY={_SEGRETO}\nVUOTA=\n")
    esito = _lancia(clone)
    assert _SEGRETO not in esito.stdout + esito.stderr


def test_il_tag_vecchio_segue_il_commit(clone: Path) -> None:
    prefisso = "LIMEN_IMAGE_PREFIX=ghcr.io/x/limen-\n"
    (clone / ".env").write_text(f"{_COMPLETO}{prefisso}LIMEN_IMAGE_TAG=sha-vecchio\n")
    esito = _lancia(clone)
    testo = (clone / ".env").read_text()
    if os.uname().machine == "x86_64":
        assert "sha-vecchio" not in testo
    else:
        assert "sha-vecchio" in testo
        assert "resto su sha-vecchio" in esito.stdout
    assert prefisso in testo


def _env(clone: Path) -> dict[str, str]:
    righe = (clone / ".env").read_text().splitlines()
    return dict(r.split("=", 1) for r in righe if "=" in r and not r.startswith("#"))


def test_senza_bucket_il_backup_va_su_minio_locale(clone: Path) -> None:
    (clone / ".env").write_text(_COMPLETO)
    esito = _lancia(clone)
    assert "PARTITO" in esito.stdout, esito.stderr
    env = _env(clone)
    assert env["BACKUP__BUCKET"] == "limen-backup"
    assert env["BACKUP__ENDPOINT_URL"] == "http://minio:9000"
    assert env["LIMEN_BACKUP_DIR"] == str(clone.parent / "limen-backup")
    assert (clone.parent / "limen-backup").is_dir()
    segreti = [env["BACKUP__SECRET_ACCESS_KEY"], env["LIMEN_MINIO_ROOT_PASSWORD"]]
    assert all(len(s) == 48 for s in segreti)
    assert not any(s in esito.stdout + esito.stderr for s in segreti)


def test_i_segreti_di_minio_non_si_rigenerano(clone: Path) -> None:
    (clone / ".env").write_text(_COMPLETO)
    _lancia(clone)
    prima = _env(clone)
    _lancia(clone)
    dopo = _env(clone)
    for chiave in ("BACKUP__SECRET_ACCESS_KEY", "LIMEN_MINIO_ROOT_PASSWORD"):
        assert dopo[chiave] == prima[chiave]


def test_un_bucket_esterno_non_si_tocca(clone: Path) -> None:
    esterno = "BACKUP__BUCKET=fuori\nBACKUP__ENDPOINT_URL=https://s3.esempio.it\n"
    (clone / ".env").write_text(f"{_COMPLETO}{esterno}")
    _lancia(clone)
    env = _env(clone)
    assert env["BACKUP__ENDPOINT_URL"] == "https://s3.esempio.it"
    assert "LIMEN_MINIO_ROOT_PASSWORD" not in env
