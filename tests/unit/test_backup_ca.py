"""La CA dei sensori esce dal server solo cifrata (#304)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from limen.cli import sensore
from limen.config.settings import BackupSettings, ObjectStoreBackend, Settings
from limen.data.backup import BackupError, cifra, decifra
from limen.data.object_store.filesystem import FilesystemObjectStore

PASSPHRASE = "una frase lunga che sta anche fuori dal server"


def test_andata_e_ritorno() -> None:
    blob = cifra(b"chiave della CA", PASSPHRASE)
    assert b"chiave della CA" not in blob
    assert decifra(blob, PASSPHRASE) == b"chiave della CA"
    # Sale e nonce nuovi a ogni backup: due cifrature non si somigliano.
    assert cifra(b"chiave della CA", PASSPHRASE) != blob


def test_passphrase_sbagliata_o_file_alterato() -> None:
    blob = cifra(b"chiave della CA", PASSPHRASE)
    with pytest.raises(BackupError, match="passphrase"):
        decifra(blob, "un'altra frase")
    alterato = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(BackupError, match="alterato"):
        decifra(alterato, PASSPHRASE)
    with pytest.raises(BackupError, match="non è un backup"):
        decifra(b"qualcos'altro", PASSPHRASE)


def _settings(tmp_path: Path, *, passphrase: str | None = PASSPHRASE) -> Settings:
    ca = tmp_path / "sensori" / "ca"
    ca.mkdir(parents=True, exist_ok=True)
    (ca / "ca.key").write_text("-----BEGIN PRIVATE KEY-----\nsegreta\n")
    (ca / "index.txt").write_text("V\t...\t\t01\tunknown\t/CN=pluvio-01\n")
    return Settings(
        backup=BackupSettings(
            backend=ObjectStoreBackend.FILESYSTEM,
            root=tmp_path / "store",
            cartella_ca=ca,
            passphrase_ca=None if passphrase is None else SecretStr(passphrase),
        )
    )


async def test_backup_e_ripristino_della_ca(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert await sensore.backup_ca(settings) == 0
    store = FilesystemObjectStore(tmp_path / "store")
    [chiave] = await store.list("ca-sensori/")
    assert b"segreta" not in await store.get(chiave)

    dove = tmp_path / "nuovo-server"
    assert await sensore.ripristina_ca(settings, dove=dove, chiave=None) == 0
    assert (dove / "ca" / "ca.key").read_text().endswith("segreta\n")
    assert (dove / "ca" / "index.txt").exists()
    # Una CA che c'è già non si sovrascrive.
    assert await sensore.ripristina_ca(settings, dove=dove, chiave=None) == 1


async def test_senza_passphrase_non_esce_niente(tmp_path: Path) -> None:
    settings = _settings(tmp_path, passphrase=None)
    assert await sensore.backup_ca(settings) == 1
    assert await FilesystemObjectStore(tmp_path / "store").list() == []
