"""Il bundle della SPA deve restare allineato a `docs/divulgazione/`.

Il generato (`frontend/src/content/divulgazione.ts`) esiste perché il
contesto Docker del frontend non contiene `docs/`: senza di esso la build
dell'immagine fallirebbe su un import fuori contesto. Il prezzo è che i
Markdown possono cambiare senza che il bundle se ne accorga, e la SPA
pubblicherebbe in silenzio un testo diverso da quello del repository.

Il test vive qui e non fra quelli del frontend perché `tsconfig.json`
dichiara esplicitamente i `types` e non include quelli di Node: un test
Vitest che legge dal disco non compila.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "build_docs_bundle.py"
BUNDLE = ROOT / "frontend" / "src" / "content" / "divulgazione.ts"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_docs_bundle", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_matches_markdown_sources() -> None:
    generated = _load_generator().build()
    assert BUNDLE.read_text(encoding="utf-8") == generated, (
        "frontend/src/content/divulgazione.ts è disallineato dai Markdown: "
        "esegui `make docs-bundle`"
    )


def test_every_page_is_in_the_bundle() -> None:
    module = _load_generator()
    names = {path.name for path in module.SOURCE.glob("*.md")}
    generated = module.build()
    for name in names:
        assert f'"{name}"' in generated, f"{name} manca dal bundle"
