"""Il pacchetto rapido in tre licenze (#406): assegnazione, attribuzioni, verifica."""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest

from limen.config.catalogo_dati import carica_catalogo
from limen.data.backup import BackupError
from limen.data.pacchetto_statico import (
    ESCLUSE,
    PASSI_ESCLUSI,
    RISORSE,
    attribuzioni,
    non_assegnate,
    verifica,
)


def test_ogni_colonna_sta_in_una_sola_risorsa() -> None:
    viste: list[str] = [c for r in RISORSE for c in r.colonne]
    assert len(viste) == len(set(viste))
    assert not set(viste) & set(ESCLUSE)


def test_una_colonna_nuova_senza_licenza_si_vede() -> None:
    assert non_assegnate(["cell_id", "slope_deg", "lithology"]) == []
    assert non_assegnate(["cell_id", "water_wetness_temp"]) == ["water_wetness_temp"]


def test_ispra_e_osm_non_stanno_con_altre_licenze() -> None:
    per_id = {r.id: r for r in RISORSE}
    assert per_id["ispra-by-sa"].licenza == "CC BY-SA 4.0"
    assert {"pai_class_norm", "flood_hazard_norm", "iffi_density_500"} <= set(
        per_id["ispra-by-sa"].colonne
    )
    assert per_id["osm-odbl"].licenza == "ODbL 1.0"
    assert "distance_to_road_m" in per_id["osm-odbl"].colonne
    assert "distance_to_road_m" not in per_id["cc-by"].colonne


def test_le_colonne_miste_e_la_litologia_restano_fuori() -> None:
    for colonna in ("s_static", "exposure_norm", "lithology", "litho_weight", "dist_faults_m"):
        assert colonna in ESCLUSE
    assert "geological" in PASSI_ESCLUSI


@pytest.mark.parametrize("risorsa", RISORSE, ids=lambda r: r.id)
def test_ogni_risorsa_ha_licenza_e_attribuzioni_dal_catalogo(risorsa: object) -> None:
    from limen.data.pacchetto_statico import Risorsa

    assert isinstance(risorsa, Risorsa)
    catalogo = carica_catalogo()
    testo = attribuzioni(risorsa, catalogo, versione="0.1.0")
    assert risorsa.licenza in testo
    assert risorsa.url_licenza in testo
    for id_ in risorsa.voci:
        voce = catalogo.voce(id_)
        assert voce.fonte in testo
        if voce.attribuzione:
            assert voce.attribuzione.strip() in testo
    for colonna in risorsa.colonne:
        assert colonna in testo


def test_le_attribuzioni_citano_osm_e_firms() -> None:
    catalogo = carica_catalogo()
    per_id = {r.id: r for r in RISORSE}
    assert "© OpenStreetMap contributors" in attribuzioni(
        per_id["osm-odbl"], catalogo, versione="x"
    )
    assert "NASA LANCE FIRMS" in attribuzioni(per_id["cc-by"], catalogo, versione="x")


def _scrivi(cartella: Path, nome: str, contenuto: bytes) -> dict[str, object]:
    (cartella / nome).write_bytes(contenuto)
    return {"sha256": hashlib.sha256(contenuto).hexdigest(), "byte": len(contenuto)}


def test_verifica_accetta_un_pacchetto_integro(tmp_path: Path) -> None:
    dati = gzip.compress(b"cell_id,slope_deg\na,1\n")
    manifest = {
        "file": {
            "cc-by.cell_static_factors.csv.gz": _scrivi(
                tmp_path, "cc-by.cell_static_factors.csv.gz", dati
            )
        }
    }
    verifica(tmp_path, manifest)


def test_verifica_rifiuta_un_file_alterato_o_mancante(tmp_path: Path) -> None:
    voce = _scrivi(tmp_path, "a.csv.gz", b"uno")
    (tmp_path / "a.csv.gz").write_bytes(b"due")
    with pytest.raises(BackupError, match="sha256"):
        verifica(tmp_path, {"file": {"a.csv.gz": voce}})
    with pytest.raises(BackupError, match="manca"):
        verifica(tmp_path, {"file": {"b.csv.gz": voce}})
