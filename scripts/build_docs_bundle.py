#!/usr/bin/env python3
"""Porta la guida `docs/guida/limen.md` dentro il bundle del frontend.

Perché un file generato invece di importare il Markdown direttamente. La SPA
si costruisce con il contesto Docker limitato a `frontend/`: `docs/` non
esiste dentro l'immagine, quindi un `import "../../docs/..."` funzionerebbe
in sviluppo e fallirebbe nella build di produzione — il caso peggiore, un
guasto che si vede solo in fondo. Il generato vive dentro `frontend/src`,
quindi la build funziona ovunque, e un test verifica che sia allineato al
Markdown: la fonte di verità resta `docs/guida/limen.md`.

Uso: `make docs-bundle` (oppure `python scripts/build_docs_bundle.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "guida" / "limen.md"
TARGET = ROOT / "frontend" / "src" / "content" / "guida.ts"


def build() -> str:
    text = SOURCE.read_text(encoding="utf-8")
    if not text.startswith("# "):
        raise SystemExit(f"{SOURCE.name}: manca il titolo di primo livello")
    return (
        "// GENERATO DA scripts/build_docs_bundle.py — non modificare a mano.\n"
        "// La fonte è docs/guida/limen.md; rigenera con `make docs-bundle`.\n"
        "\n"
        f"export const GUIDA_FILE = {json.dumps('docs/guida/' + SOURCE.name)};\n"
        "\n"
        f"export const GUIDA_MARKDOWN = {json.dumps(text, ensure_ascii=False)};\n"
    )


if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(build(), encoding="utf-8")
    print(f"scritto {TARGET.relative_to(ROOT)}")
