"""I metadati DCAT-AP_IT del pacchetto rapido (#504)."""

from __future__ import annotations

from typing import Any

from limen.config.catalogo_dati import carica_catalogo
from limen.data.dcat import _testo, dcat_ap_it
from limen.data.pacchetto_statico import RISORSE, _nome_attribuzioni, _nome_dati


def _manifest() -> dict[str, Any]:
    file: dict[str, dict[str, Any]] = {}
    for r in RISORSE:
        file[_nome_dati(r)] = {
            "risorsa": r.id,
            "tabella": "public.cell_static_factors",
            "righe": 312550,
            "byte": 1000,
            "sha256": "ab" * 32,
        }
        for t in r.tabelle:
            file[_nome_dati(r, t)] = {
                "risorsa": r.id,
                "tabella": t,
                "righe": 10,
                "byte": 10,
                "sha256": "cd" * 32,
            }
        file[_nome_attribuzioni(r)] = {"risorsa": r.id, "byte": 1, "sha256": "ef" * 32}
    return {"limen": "0.9.0", "creato": "2026-11-09T10:00:00+00:00", "file": file}


def _ttl(url_base: str | None = None) -> str:
    return dcat_ap_it(_manifest(), carica_catalogo(), risorse=RISORSE, url_base=url_base)


def test_un_dataset_per_licenza_con_le_sue_distribuzioni() -> None:
    ttl = _ttl()
    assert ttl.count("a dcatapit:Dataset, dcat:Dataset") == len(RISORSE)
    # Una distribuzione per file di dati: le attribuzioni non sono una distribuzione.
    dati = sum(1 + len(r.tabelle) for r in RISORSE)
    assert ttl.count("a dcatapit:Distribution") == dati
    assert ttl.count('spdx:checksumValue "' + "ab" * 32) == len(RISORSE)
    assert "<https://creativecommons.org/licenses/by-sa/4.0/>" in ttl
    assert "<http://purl.org/adms/licencetype/ShareAlike>" in ttl
    assert '"2026-11-09"^^xsd:date' in ttl
    assert "releases/tag/v0.9.0#catalogo" in ttl


def test_senza_url_base_niente_download_url() -> None:
    assert "dcat:downloadURL" not in _ttl()
    con = _ttl("https://example.org/v0.9.0/")
    assert "<https://example.org/v0.9.0/ispra-by-sa.cell_static_factors.csv.gz>" in con


def test_i_letterali_sono_protetti() -> None:
    assert _testo('a "b"\nc\\') == '"a \\"b\\"\\nc\\\\"@it'
    assert _testo("x", "") == '"x"'
