"""La SPA dichiara le licenze del catalogo dei dati (#491).

``config/dati.yaml`` è la fonte unica di licenza e titolare; la pagina
``#/fonti`` (``frontend/src/lib/fonti.ts``) e le righe di attribuzione degli
strati della mappa li ripetono a mano. È successo che divergessero: IFFI e i
mosaici ISPRA dati per CC BY 4.0 invece di CC BY-SA 4.0, la litologia
attribuita a ISPRA invece che al Ministero dell'Ambiente. Un errore di licenza
si propaga a chi riusa i dati, e lo share-alike è proprio la clausola che
sparisce.

Il controllo legge i file TypeScript come testo invece di far importare alla
SPA un JSON generato dal YAML: niente dipendenza YAML nel frontend, niente
passo di generazione da dimenticare, e gira nel gate veloce di ogni PR.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from limen.config.catalogo_dati import VoceDato, carica_catalogo

_RADICE = Path(__file__).resolve().parents[2]
_SPA = _RADICE / "frontend" / "src"

# voce del catalogo → (voce di fonti.ts, titolare che entrambe devono nominare)
_CORRISPONDENZE: dict[str, tuple[str, str]] = {
    "iffi": ("ispra-iffi", "ISPRA"),
    "pai_frana": ("ispra-pai", "ISPRA"),
    "idraulica": ("ispra-idraulica", "ISPRA"),
    "dtm": ("cnr-irpi-dtm", "CNR-IRPI"),
    "corine": ("corine", "Copernicus Land Monitoring Service"),
    "impermeabilizzazione": ("imperviousness", "Copernicus Land Monitoring Service"),
    "comuni": ("istat", "ISTAT"),
    "strade": ("osm-reti", "OpenStreetMap"),
    "litologia": ("mase-geologia", "Ministero dell'Ambiente e della Sicurezza Energetica"),
    "perimetri_effis": ("effis", "EFFIS"),
    "firms_storico": ("firms", "NASA"),
}

_FRASE_ECMWF = (
    "ECMWF does not accept any liability whatsoever for any error or omission in the data"
)


def _normalizza(licenza: str) -> str:
    """«CC-BY 4.0», «CC-BY-4.0» e «CC BY 4.0» sono la stessa licenza."""
    return re.sub(r"[\s\-]+", " ", licenza.strip().upper())


def _voci_fonti() -> dict[str, str]:
    """Il testo di ogni voce di ``FONTI``, per id."""
    testo = (_SPA / "lib" / "fonti.ts").read_text(encoding="utf-8")
    elenco = testo.split("export const FONTI", 1)[1]
    blocchi = re.split(r'\n  \{\n    id: "', elenco)[1:]
    return {b.split('"', 1)[0]: b for b in blocchi}


def _campo(blocco: str, nome: str) -> str:
    trovato = re.search(rf'^    {nome}: "((?:[^"\\]|\\.)*)",$', blocco, re.MULTILINE)
    assert trovato, f"campo {nome} mancante"
    return trovato.group(1)


def _catalogo() -> dict[str, VoceDato]:
    return {v.id: v for v in carica_catalogo().voci}


def test_ogni_voce_del_catalogo_con_licenza_propria_ha_la_sua_fonte() -> None:
    # Una voce nuova nel catalogo obbliga a dire dove la SPA la dichiara.
    proprie = {v.id for v in _catalogo().values() if v.deriva_da is None}
    assert proprie <= _CORRISPONDENZE.keys(), proprie - _CORRISPONDENZE.keys()


@pytest.mark.parametrize("voce_catalogo", sorted(_CORRISPONDENZE))
def test_fonti_ts_ripete_licenza_e_titolare_del_catalogo(voce_catalogo: str) -> None:
    voce = _catalogo()[voce_catalogo]
    id_fonte, titolare = _CORRISPONDENZE[voce_catalogo]
    blocco = _voci_fonti()[id_fonte]

    assert _normalizza(_campo(blocco, "licenza")) == _normalizza(voce.licenza)
    assert titolare in _campo(blocco, "ente").replace("\\'", "'")
    assert voce.attribuzione is not None
    assert titolare in voce.attribuzione


def test_gli_strati_ispra_della_mappa_dichiarano_la_licenza_del_catalogo() -> None:
    catalogo = _catalogo()
    attesa = {_normalizza(catalogo[i].licenza) for i in ("iffi", "pai_frana", "idraulica")}
    assert len(attesa) == 1

    trovate: list[tuple[str, str]] = []
    for file in _SPA.rglob("*.ts*"):
        if "__tests__" in file.parts or "content" in file.parts:
            continue
        testo = file.read_text(encoding="utf-8")
        trovate += [(file.name, m) for m in re.findall(r"ISPRA[^\"\n(]*\((CC[^)]*)\)", testo)]

    assert trovate, "nessuna attribuzione ISPRA trovata: il controllo non vede più la SPA"
    sbagliate = [(f, lic) for f, lic in trovate if {_normalizza(lic)} != attesa]
    assert not sbagliate, sbagliate


def test_la_frase_ecmwf_accompagna_il_meteo() -> None:
    attribuzioni = (_SPA / "lib" / "attribuzioni.ts").read_text(encoding="utf-8")
    assert _FRASE_ECMWF in attribuzioni
    for dove in ("components/RiskMap.tsx", "components/HomePage.tsx", "lib/fonti.ts"):
        assert "meteoEcmwf(" in (_SPA / dove).read_text(encoding="utf-8"), dove
