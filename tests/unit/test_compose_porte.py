"""Ogni porta pubblicata dai compose sta sul loopback (#496).

Docker scrive le sue catene iptables prima di quelle di ufw: il `default deny
incoming` dell'host non protegge una porta pubblicata da un container. Una
voce `ports:` senza indirizzo esplicito ascolta su 0.0.0.0, cioè su internet.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

RADICE = Path(__file__).resolve().parents[2]
COMPOSE = sorted(
    {
        *RADICE.glob("infra/docker/*.yml"),
        *RADICE.glob("infra/docker/*.yaml"),
        *RADICE.glob("docker-compose*.yml"),
        *RADICE.glob("compose*.yml"),
    }
)

LOOPBACK = re.compile(r"^(\$\{LIMEN_[A-Z0-9_]+_BIND:-127\.0\.0\.1\}|127\.0\.0\.1):")

# (file, servizio) -> host ammesso. Solo ciò che esiste per essere pubblico.
ECCEZIONI: dict[tuple[str, str], str] = {
    # Caddy è l'ingresso pubblico (#306): 80 per ACME e redirect, 443 per la
    # mappa. LIMEN_PROXY_BIND lo restringe dove serve.
    ("docker-compose.demo.yml", "proxy"): "${LIMEN_PROXY_BIND:-0.0.0.0}:",
}


def _voci_porte() -> list[tuple[str, str, Any]]:
    voci: list[tuple[str, str, Any]] = []
    for percorso in COMPOSE:
        documento = yaml.safe_load(percorso.read_text(encoding="utf-8")) or {}
        for servizio, definizione in (documento.get("services") or {}).items():
            for voce in (definizione or {}).get("ports") or []:
                voci.append((percorso.name, servizio, voce))
    return voci


def test_ci_sono_compose_da_controllare() -> None:
    assert len(COMPOSE) >= 5
    assert _voci_porte()


@pytest.mark.parametrize(("file", "servizio", "voce"), _voci_porte())
def test_porta_pubblicata_su_loopback(file: str, servizio: str, voce: Any) -> None:
    if isinstance(voce, dict):
        host = str(voce.get("host_ip", ""))
        assert host == "127.0.0.1" or LOOPBACK.match(f"{host}:"), (
            f"{file}:{servizio} pubblica {voce} senza host_ip su loopback"
        )
        return
    testo = str(voce)
    ammesso = ECCEZIONI.get((file, servizio))
    if ammesso is not None and testo.startswith(ammesso):
        return
    assert LOOPBACK.match(testo), (
        f"{file}:{servizio} pubblica {testo!r} su tutte le interfacce: "
        'usa "${LIMEN_<SERVIZIO>_BIND:-127.0.0.1}:<porta>:<porta>"'
    )


def test_eccezioni_ancora_presenti() -> None:
    presenti = {(file, servizio) for file, servizio, _ in _voci_porte()}
    assert set(ECCEZIONI) <= presenti
