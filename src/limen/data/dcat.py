"""I metadati DCAT-AP_IT del pacchetto rapido (#504).

Chi cerca dati sul dissesto in un catalogo — dati.gov.it, data.europa.eu, un
portale regionale — non trova un asset di release. DCAT-AP_IT è il profilo
italiano dei metadati dei cataloghi pubblici: un ``dcatapit:Dataset`` per
risorsa del pacchetto (una per licenza, perché le licenze non si mescolano),
con licenza, titolare, copertura, fonti e una ``dcatapit:Distribution`` per
file, con dimensione e SHA-256 presi dal manifest.

Validato con le shape SHACL di DCAT-AP 3.0.1 (SEMIC): la dimensione è un
``xsd:nonNegativeInteger`` e lo SHA-256 è ammesso, mentre DCAT-AP 2.1.1
accettava solo SHA-1 — il manifest porta SHA-256, e un secondo hash solo per
un profilo superato non vale una lettura in più di ogni file.

Turtle e non JSON-LD: è il formato che accetta il validatore semantico di AgID.
Si scrive a mano perché il grafo è piccolo e fisso, e una libreria RDF in più
nell'immagine per venti triple non vale la dipendenza; i letterali passano
tutti da :func:`_testo`.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from limen.config.catalogo_dati import CatalogoDati

if TYPE_CHECKING:
    from limen.data.pacchetto_statico import Risorsa

REPOSITORY = "https://github.com/agent-engineering-studio/limen"
TITOLARE = "Agent Engineering Studio — progetto Limen"
TITOLARE_ID = "agent-engineering-studio"
EMAIL = "gzileni@agentengineering.it"

_TEMA = "http://publications.europa.eu/resource/authority/data-theme/ENVI"
_ITALIA = "http://publications.europa.eu/resource/authority/country/ITA"
_ITALIANO = "http://publications.europa.eu/resource/authority/language/ITA"
_IRREGOLARE = "http://publications.europa.eu/resource/authority/frequency/IRREG"
_CSV = "http://publications.europa.eu/resource/authority/file-type/CSV"
#: La licenza dei metadati, non dei dati: chi li raccoglie li ripubblica senza vincoli.
_CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"
_TIPO_LICENZA = {
    "CC BY 4.0": "http://purl.org/adms/licencetype/Attribution",
    "CC BY-SA 4.0": "http://purl.org/adms/licencetype/ShareAlike",
    "ODbL 1.0": "http://purl.org/adms/licencetype/ShareAlike",
    "CC0 1.0": "http://purl.org/adms/licencetype/PublicDomain",
}
_PAROLE = ("frane", "alluvioni", "incendi boschivi", "dissesto idrogeologico", "griglia 1 km")

_PREFISSI = """\
@prefix dcat: <http://www.w3.org/ns/dcat#> .
@prefix dcatap: <http://data.europa.eu/r5r/> .
@prefix dcatapit: <http://dati.gov.it/onto/dcatapit#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix spdx: <http://spdx.org/rdf/terms#> .
@prefix vcard: <http://www.w3.org/2006/vcard/ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def _testo(s: str, lingua: str = "it") -> str:
    esc = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
    return f'"{esc}"@{lingua}' if lingua else f'"{esc}"'


def _iri(u: str) -> str:
    return f"<{u}>"


def _blocco(soggetto: str, proprieta: list[tuple[str, str]]) -> str:
    righe = [soggetto]
    for i, (p, o) in enumerate(proprieta):
        fine = " ." if i == len(proprieta) - 1 else " ;"
        righe.append(f"    {p} {o}{fine}")
    return "\n".join(righe) + "\n"


def dcat_ap_it(
    manifest: dict[str, Any],
    catalogo: CatalogoDati,
    *,
    risorse: Iterable[Risorsa],
    url_base: str | None,
) -> str:
    """Il catalogo DCAT-AP_IT del pacchetto descritto da ``manifest``.

    ``url_base``, se dato, è da dove si scaricano i file: senza, le
    distribuzioni portano solo la pagina delle release.
    """
    versione = str(manifest["limen"])
    modificato = datetime.fromisoformat(str(manifest["creato"])).date().isoformat()
    base = f"{REPOSITORY}/releases/tag/v{versione}"
    accesso = f"{REPOSITORY}/releases"
    data = f'"{modificato}"^^xsd:date'
    titolare = _iri(f"{REPOSITORY}#titolare")
    contatto = _iri(f"{REPOSITORY}#contatto")

    blocchi = [_PREFISSI]
    dataset_iri: list[str] = []
    licenze: dict[str, tuple[str, str]] = {_CC0: ("CC0 1.0", _TIPO_LICENZA["CC0 1.0"])}
    for r in risorse:
        ds = _iri(f"{base}#{r.id}")
        dataset_iri.append(ds)
        licenza = _iri(r.url_licenza)
        licenze[r.url_licenza] = (r.licenza, _TIPO_LICENZA[r.licenza])
        voci = [catalogo.voce(v) for v in r.voci]
        fonti = "; ".join(f"{v.nome} ({v.fonte})" for v in voci)
        descrizione = (
            f"Valori per cella della griglia di 1 km sull'Italia, calcolati da Limen: "
            f"dati modificati, non i dati originali. Fonti: {fonti}. "
            f"Colonne: {', '.join(r.colonne)}. Licenza {r.licenza}: "
            f"le attribuzioni complete sono nel file ATTRIBUZIONI-{r.id}.txt."
        )
        distribuzioni: list[str] = []
        for nome, f in manifest["file"].items():
            if f.get("risorsa") != r.id or "tabella" not in f:
                continue
            dist = _iri(f"{base}#{nome}")
            distribuzioni.append(dist)
            prop = [
                ("a", "dcatapit:Distribution, dcat:Distribution"),
                ("dct:title", _testo(f"{f['tabella']} — {r.licenza}")),
                ("dct:description", _testo(f"CSV compresso con gzip: {f['righe']} righe.")),
                ("dct:format", _iri(_CSV)),
                ("dcat:mediaType", _iri("http://www.iana.org/assignments/media-types/text/csv")),
                (
                    "dcat:compressFormat",
                    _iri("http://www.iana.org/assignments/media-types/application/gzip"),
                ),
                ("dct:license", licenza),
                ("dcat:accessURL", _iri(accesso)),
                # Gli asset di una release non cambiano: un pacchetto nuovo è una release nuova.
                ("dcatap:availability", _iri("http://data.europa.eu/r5r/availability/stable")),
            ]
            if url_base:
                prop.append(("dcat:downloadURL", _iri(f"{url_base.rstrip('/')}/{nome}")))
            prop += [
                ("dcat:byteSize", f'"{f["byte"]}"^^xsd:nonNegativeInteger'),
                (
                    "spdx:checksum",
                    "[ a spdx:Checksum ; spdx:algorithm spdx:checksumAlgorithm_sha256 ; "
                    f'spdx:checksumValue "{f["sha256"]}"^^xsd:hexBinary ]',
                ),
            ]
            blocchi.append(_blocco(dist, prop))
        prop_ds = [
            ("a", "dcatapit:Dataset, dcat:Dataset"),
            ("dct:identifier", _testo(f"limen:{versione}:{r.id}", "")),
            ("dct:title", _testo(f"Limen {versione} — fattori statici per cella ({r.licenza})")),
            ("dct:description", _testo(descrizione)),
            ("dct:modified", data),
            ("dct:issued", data),
            ("dcat:theme", _iri(_TEMA)),
            ("dct:spatial", _iri(_ITALIA)),
            ("dct:language", _iri(_ITALIANO)),
            ("dct:accrualPeriodicity", _iri(_IRREGOLARE)),
            ("dcat:keyword", ", ".join(_testo(k) for k in _PAROLE)),
            ("dct:publisher", titolare),
            ("dct:rightsHolder", titolare),
            ("dcat:contactPoint", contatto),
            ("dcat:landingPage", _iri(base)),
        ]
        prop_ds.append(("dcat:distribution", ", ".join(distribuzioni)))
        blocchi.append(_blocco(ds, prop_ds))

    for url, (nome, tipo) in licenze.items():
        blocchi.append(
            _blocco(
                _iri(url),
                [
                    ("a", "dct:LicenseDocument"),
                    ("dct:type", _iri(tipo)),
                    ("foaf:name", _testo(nome, "")),
                ],
            )
        )
    blocchi += [_blocco(_iri(pagina), [("a", "foaf:Document")]) for pagina in (base, REPOSITORY)]
    blocchi.append(_blocco("spdx:checksumAlgorithm_sha256", [("a", "spdx:ChecksumAlgorithm")]))
    blocchi.append(
        _blocco(
            titolare,
            [
                ("a", "dcatapit:Agent, foaf:Agent"),
                ("dct:identifier", _testo(TITOLARE_ID, "")),
                ("foaf:name", _testo(TITOLARE)),
            ],
        )
    )
    blocchi.append(
        _blocco(
            contatto,
            [
                ("a", "dcatapit:Organization, vcard:Organization, vcard:Kind"),
                ("vcard:fn", _testo(TITOLARE)),
                ("vcard:hasEmail", _iri(f"mailto:{EMAIL}")),
            ],
        )
    )
    blocchi.append(
        _blocco(
            _iri(f"{base}#catalogo"),
            [
                ("a", "dcatapit:Catalog, dcat:Catalog"),
                ("dct:title", _testo(f"Limen {versione} — pacchetto di dati statici")),
                (
                    "dct:description",
                    _testo(
                        "I fattori statici per cella con cui Limen calcola il pericolo di "
                        "frane, alluvioni e incendi boschivi, in tre file, uno per licenza."
                    ),
                ),
                ("dct:publisher", titolare),
                ("dct:modified", data),
                ("dct:issued", data),
                ("dct:language", _iri(_ITALIANO)),
                ("dct:spatial", _iri(_ITALIA)),
                ("dct:license", _iri(_CC0)),
                ("foaf:homepage", _iri(REPOSITORY)),
                (
                    "dcat:themeTaxonomy",
                    _iri("http://publications.europa.eu/resource/authority/data-theme"),
                ),
                ("dcat:dataset", ", ".join(dataset_iri)),
            ],
        )
    )
    return "\n".join(blocchi)
