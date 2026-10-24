"""Backup notturno (#304): retention, store su file, allarme e stato `warn`."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import structlog

from limen.api.jobs import _tracking, hourly_monitoring
from limen.config.settings import BackupSettings, ObjectStoreBackend
from limen.data.backup import (
    _crollato,
    _errori_non_ammessi,
    _pg,
    archivio_cartella,
    backup_completi,
    estrai_archivio,
    istante,
    mlflow_database,
    pulisci,
)
from limen.data.object_store import build_backup_store
from limen.data.object_store.filesystem import FilesystemObjectStore

ADESSO = datetime(2026, 10, 24, 2, 0, tzinfo=UTC)


async def _backup(store: FilesystemObjectStore, giorni_fa: float, *, completo: bool = True) -> str:
    quando = ADESSO - timedelta(days=giorni_fa)
    base = f"backup/{quando.strftime('%Y-%m-%dT%H-%M-%SZ')}/"
    await store.put(base + "limen.dump", b"dump")
    if completo:
        await store.put(base + "manifest.json", b"{}")
    return base


async def test_store_su_file_copia_ed_elenca(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path / "store")
    sorgente = tmp_path / "grande.bin"
    sorgente.write_bytes(b"x" * 3_000_000)
    await store.put_file("backup/a/limen.dump", sorgente)
    await store.put("backup/a/manifest.json", b"{}")
    await store.put("altro/file", b"y")
    assert await store.list("backup/") == ["backup/a/limen.dump", "backup/a/manifest.json"]
    copia = tmp_path / "copia.bin"
    await store.get_file("backup/a/limen.dump", copia)
    assert copia.read_bytes() == sorgente.read_bytes()
    with pytest.raises(FileNotFoundError):
        await store.get_file("backup/manca", copia)


async def test_retention_tiene_sempre_gli_ultimi(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    cfg = BackupSettings(retention_giorni=30, tieni_almeno=3)
    vecchi = [await _backup(store, g) for g in (90, 60, 45)]
    recenti = [await _backup(store, g) for g in (10, 1)]
    interrotto_vecchio = await _backup(store, 2, completo=False)
    interrotto_di_stanotte = await _backup(store, 0.1, completo=False)

    via = await pulisci(store, cfg, ADESSO)
    # Fuori retention, ma il più recente dei tre vecchi resta: con gli ultimi
    # due fa i tre da tenere comunque.
    assert sorted(via) == sorted([vecchi[0], vecchi[1], interrotto_vecchio])
    assert await backup_completi(store) == [vecchi[2], *recenti]
    # Un backup interrotto di stanotte può essere ancora in corso.
    assert await store.exists(interrotto_di_stanotte + "limen.dump")


async def test_un_notturno_fermo_non_svuota_il_bucket(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    cfg = BackupSettings(retention_giorni=7, tieni_almeno=2)
    tutti = [await _backup(store, g) for g in (100, 90, 80)]
    await pulisci(store, cfg, ADESSO)
    assert await backup_completi(store) == tutti[1:]


def test_istante_dalla_chiave() -> None:
    assert istante("backup/2026-10-24T02-05-00Z/limen.dump") == datetime(
        2026, 10, 24, 2, 5, tzinfo=UTC
    )
    assert istante("backup/non-una-data/x") is None


def test_store_del_backup_solo_se_configurato(tmp_path: Path) -> None:
    assert build_backup_store(BackupSettings()) is None
    assert build_backup_store(BackupSettings(backend=ObjectStoreBackend.FILESYSTEM)) is None
    store = build_backup_store(BackupSettings(backend=ObjectStoreBackend.FILESYSTEM, root=tmp_path))
    assert isinstance(store, FilesystemObjectStore)


async def test_un_warn_si_registra_come_ok_con_avviso(monkeypatch: pytest.MonkeyPatch) -> None:
    """Il CHECK di `job_runs` non ha `warn`: la riga restava `running` (#304)."""
    chiusi: list[dict[str, Any]] = []

    async def start(job_id: str, *, scope: str | None = None) -> int:
        return 1

    async def finish(run_id: int, **kw: Any) -> None:
        chiusi.append(kw)

    monkeypatch.setattr(_tracking.job_runs_repo, "start", start)
    monkeypatch.setattr(_tracking.job_runs_repo, "finish", finish)
    async with _tracking.tracked("limen-nightly", scope="storage") as metrics:
        metrics["status"] = "warn"
    [chiuso] = chiusi
    assert chiuso["status"] == "ok"
    assert chiuso["metrics"]["avviso"] is True


@pytest.mark.parametrize(
    ("cfg", "ultimo", "avvisa"),
    [
        (BackupSettings(bucket="b"), None, True),
        (BackupSettings(bucket="b"), timedelta(hours=40), True),
        (BackupSettings(bucket="b"), timedelta(hours=20), False),
        (BackupSettings(), None, False),
    ],
    ids=["mai", "vecchio", "recente", "spento"],
)
async def test_allarme_backup_vecchio(
    monkeypatch: pytest.MonkeyPatch, cfg: BackupSettings, ultimo: timedelta | None, avvisa: bool
) -> None:
    from limen.data.repos import job_runs_repo

    async def ultimo_riuscito(job_id: str, *, scope: str | None = None) -> datetime | None:
        assert (job_id, scope) == ("limen-nightly", "backup")
        return None if ultimo is None else datetime.now(UTC) - ultimo

    monkeypatch.setattr(job_runs_repo, "ultimo_riuscito", ultimo_riuscito)
    with structlog.testing.capture_logs() as logs:
        await hourly_monitoring.avvisa_backup_vecchio(cfg)
    assert any(e.get("label") == "backup.stale" for e in logs) is avvisa


# --- Revisione #304: errori, password, passphrase ---------------------------

STDERR_POSTGIS = "\n".join(
    [
        "pg_restore: error: could not execute query: ERROR:  cannot drop extension "
        "postgis because other objects depend on it",
        "DETAIL:  extension postgis_topology depends on extension postgis",
        "Command was: DROP EXTENSION IF EXISTS postgis;",
        "pg_restore: error: could not execute query: ERROR:  cannot drop inherited "
        'constraint "model_runs_20261024_pkey" of relation "model_runs_20261024"',
        "Command was: ALTER TABLE IF EXISTS ONLY public.model_runs_20261024 ...",
        "pg_restore: warning: errors ignored on restore: 2",
    ]
)


def test_gli_errori_noti_di_clean_si_ammettono() -> None:
    assert _errori_non_ammessi(STDERR_POSTGIS) == []
    assert _errori_non_ammessi('psql:ruoli.sql:5: ERROR:  role "limen" already exists') == []


def test_ogni_altro_errore_ferma_il_ripristino() -> None:
    cattivo = STDERR_POSTGIS + (
        'pg_restore: error: could not execute query: ERROR:  type "geometry" does not exist\n'
        "Command was: CREATE TABLE public.verifiche_eventi (...);\n"
    )
    assert _errori_non_ammessi(cattivo) == ['type "geometry" does not exist']


def test_la_password_non_va_negli_argomenti() -> None:
    cfg = BackupSettings(comando_pg="docker exec -i limen-postgres")
    pg = _pg(cfg, "postgresql://limen:segreta@localhost:5432/limen")
    argv = pg("pg_dump", f"--dbname={pg.dsn}")
    assert "segreta" not in " ".join(argv)
    assert argv[:5] == ["docker", "exec", "-e", "PGPASSWORD", "-i"]
    assert pg.env["PGPASSWORD"] == "segreta"
    assert pg.dsn == "postgresql://limen@localhost:5432/limen"
    # Senza password la DSN resta com'è, e senza docker niente `-e`.
    nuda = _pg(BackupSettings(), "postgresql://limen@db/limen")
    assert nuda.argv0 == () and nuda.dsn == "postgresql://limen@db/limen"


@pytest.mark.parametrize("valore", ["", None])
def test_passphrase_vuota_e_come_assente(valore: str | None) -> None:
    assert BackupSettings(passphrase_ca=valore).passphrase_ca is None


def test_passphrase_corta_rifiutata() -> None:
    with pytest.raises(ValueError, match="20 caratteri"):
        BackupSettings(passphrase_ca="corta")


def test_la_ca_si_archivia_sempre_come_ca(tmp_path: Path) -> None:
    cartella = tmp_path / "mia-ca"
    cartella.mkdir()
    (cartella / "ca.key").write_text("k")
    estrai_archivio(archivio_cartella(cartella), tmp_path / "dove")
    assert (tmp_path / "dove" / "ca" / "ca.key").read_text() == "k"


def test_mlflow_solo_se_su_postgresql_nello_stesso_server() -> None:
    app = "postgresql://limen:limen@postgres:5432/limen"
    assert mlflow_database("postgresql://limen:x@postgres:5432/mlflow", app) == "mlflow"
    assert mlflow_database("postgresql://limen:x@Postgres/mlflow", app) == "mlflow"
    assert mlflow_database("sqlite:///mlflow.db", app) is None
    assert mlflow_database("http://mlflow:5000", app) is None
    # Codex su #311: un registry su un altro server non si confonde con un
    # omonimo locale.
    assert mlflow_database("postgresql://u:x@registry.example.org/mlflow", app) is None
    assert mlflow_database("postgresql://u:x@postgres:6543/mlflow", app) is None


async def _manifest(
    store: FilesystemObjectStore, giorni_fa: float, righe: int, *, crollato: bool
) -> None:
    base = await _backup(store, giorni_fa)
    await store.put(
        base + "manifest.json",
        json.dumps({"righe": {"public.t": righe}, "crollato": crollato}).encode(),
    )


async def test_il_metro_del_crollo_e_l_ultimo_backup_sano(tmp_path: Path) -> None:
    """Codex su #311: un secondo backup crollato non deve diventare il metro."""
    store = FilesystemObjectStore(tmp_path)
    cfg = BackupSettings()
    await _manifest(store, 10, 1000, crollato=False)
    await _manifest(store, 9, 10, crollato=True)
    await _manifest(store, 8, 10, crollato=True)
    assert await _crollato(store, cfg, {"public.t": 10}) is True
    # Il database si riprende: si torna a confrontare normalmente.
    assert await _crollato(store, cfg, {"public.t": 990}) is False
    assert await _crollato(FilesystemObjectStore(tmp_path / "vuoto"), cfg, {"public.t": 1}) is False


def test_password_codificata_e_ipv6() -> None:
    """Codex su #311: `p%40ss` in una DSN è `p@ss` per PostgreSQL."""
    pg = _pg(BackupSettings(), "postgresql://limen:p%40ss%3Aword@[::1]:5432/limen")
    assert pg.env["PGPASSWORD"] == "p@ss:word"
    assert pg.dsn == "postgresql://limen@[::1]:5432/limen"
