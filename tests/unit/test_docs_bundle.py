"""Il bundle della SPA deve restare allineato alle pagine di `docs/guida/`.

I generati (`frontend/src/content/guida.ts`, `integrazioni.ts`) esistono perché il contesto
Docker del frontend non contiene `docs/`: senza di esso la build
dell'immagine fallirebbe su un import fuori contesto. Il prezzo è che il
Markdown può cambiare senza che il bundle se ne accorga, e la SPA
pubblicherebbe in silenzio un testo diverso da quello del repository.

Il test vive qui e non fra quelli del frontend perché `tsconfig.json`
dichiara esplicitamente i `types` e non include quelli di Node: un test
Vitest che legge dal disco non compila.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "build_docs_bundle.py"
GUIDA = ROOT / "docs" / "guida"
CONTENT = ROOT / "frontend" / "src" / "content"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_docs_bundle", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PAGES = _load_generator().PAGES


@pytest.mark.parametrize(("source", "target", "prefix"), _PAGES)
def test_bundle_matches_markdown_source(source: str, target: str, prefix: str) -> None:
    generated = _load_generator().build(source, prefix)
    assert (CONTENT / target).read_text(encoding="utf-8") == generated, (
        f"frontend/src/content/{target} è disallineato da docs/guida/{source}: "
        "esegui `make docs-bundle`"
    )


def _struttura(text: str) -> list[str]:
    """Lo scheletro di una pagina: titoli per livello, marcatori, blocchi di
    codice e colonne delle tabelle — tutto tranne le parole."""
    out: list[str] = []
    in_code = False
    prev = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            if not in_code:
                out.append("code")
            in_code = not in_code
        elif in_code:
            pass
        elif m := re.match(r"^(#{1,4})\s", line):
            out.append(f"h{len(m.group(1))}")
        elif m := re.match(r"^<!--\s*(\S+:\s*[a-z-]+)\s*-->$", line):
            out.append(m.group(1))
        elif re.match(r"^\|(\s*:?-+:?\s*\|)+$", line):
            out.append(f"table{prev.count('|') - 1}")
        prev = line
    return out


@pytest.mark.parametrize(("source", "target", "prefix"), _PAGES)
def test_english_has_the_same_structure(source: str, target: str, prefix: str) -> None:
    """Le ancore delle sezioni inglesi sono quelle italiane prese per posizione
    (`DocPage.tsx`): un titolo in più o in meno sposterebbe ogni link
    condiviso dopo di lui, e un marcatore perso toglierebbe una figura."""
    english = _load_generator().english(source)
    it = _struttura((GUIDA / source).read_text(encoding="utf-8"))
    en = _struttura((GUIDA / english).read_text(encoding="utf-8"))
    assert en == it, f"docs/guida/{english} non ha la struttura di {source}"
