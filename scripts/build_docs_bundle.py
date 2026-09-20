#!/usr/bin/env python3
"""Porta le pagine di `docs/divulgazione/` dentro il bundle del frontend.

Perché un file generato invece di importare i Markdown direttamente. La SPA
si costruisce con il contesto Docker limitato a `frontend/`: `docs/` non
esiste dentro l'immagine, quindi un `import "../../docs/..."` funzionerebbe
in sviluppo e fallirebbe nella build di produzione — il caso peggiore, un
guasto che si vede solo in fondo. Il generato vive dentro `frontend/src`,
quindi la build funziona ovunque, e un test verifica che sia allineato ai
Markdown: la fonte di verità resta `docs/divulgazione/`.

Uso: `make docs-bundle` (oppure `python scripts/build_docs_bundle.py`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "divulgazione"
TARGET = ROOT / "frontend" / "src" / "content" / "divulgazione.ts"

#: L'indice della cartella diventa la pagina di apertura della sezione.
SLUGS = {"README": "indice"}

HEADING = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def slug_for(stem: str) -> str:
    return SLUGS.get(stem, stem)


def build() -> str:
    pages = []
    for md in sorted(SOURCE.glob("*.md"), key=lambda p: (p.stem != "README", p.stem)):
        text = md.read_text(encoding="utf-8")
        match = HEADING.search(text)
        if match is None:
            raise SystemExit(f"{md.name}: manca il titolo di primo livello")
        pages.append(
            {
                "slug": slug_for(md.stem),
                "file": md.name,
                "title": match.group(1).strip(),
                "markdown": text,
            }
        )
    body = ",\n".join(
        "  {\n"
        + "".join(
            f"    {key}: {json.dumps(value, ensure_ascii=False)},\n" for key, value in page.items()
        )
        + "  }"
        for page in pages
    )
    return (
        "// GENERATO DA scripts/build_docs_bundle.py — non modificare a mano.\n"
        "// La fonte è docs/divulgazione/*.md; rigenera con `make docs-bundle`.\n"
        "\n"
        "export interface DocPage {\n"
        "  slug: string;\n"
        "  file: string;\n"
        "  title: string;\n"
        "  markdown: string;\n"
        "}\n"
        "\n"
        "export const DOC_PAGES: [DocPage, ...DocPage[]] = [\n" + body + ",\n];\n"
    )


if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(build(), encoding="utf-8")
    print(f"scritto {TARGET.relative_to(ROOT)}")
