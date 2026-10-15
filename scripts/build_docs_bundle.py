#!/usr/bin/env python3
"""Porta le pagine di `docs/guida/` dentro il bundle del frontend.

Perché un file generato invece di importare il Markdown direttamente. La SPA
si costruisce con il contesto Docker limitato a `frontend/`: `docs/` non
esiste dentro l'immagine, quindi un `import "../../docs/..."` funzionerebbe
in sviluppo e fallirebbe nella build di produzione — il caso peggiore, un
guasto che si vede solo in fondo. Il generato vive dentro `frontend/src`,
quindi la build funziona ovunque, e un test verifica che sia allineato al
Markdown: la fonte di verità resta `docs/guida/`.

Uso: `make docs-bundle` (oppure `python scripts/build_docs_bundle.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDA = ROOT / "docs" / "guida"
CONTENT = ROOT / "frontend" / "src" / "content"

# (sorgente italiana in docs/guida, generato in frontend/src/content, prefisso
# delle costanti). La traduzione inglese è la stessa sorgente con `.en.md`.
PAGES: tuple[tuple[str, str, str], ...] = (
    ("limen.md", "guida.ts", "GUIDA"),
    ("integrazioni.md", "integrazioni.ts", "INTEGRAZIONI"),
    ("sensori.md", "sensori.ts", "SENSORI"),
)


def english(source: str) -> str:
    return source.removesuffix(".md") + ".en.md"


def _read(source: str) -> str:
    text = (GUIDA / source).read_text(encoding="utf-8")
    if not text.startswith("# "):
        raise SystemExit(f"{source}: manca il titolo di primo livello")
    return text


def build(source: str = "limen.md", prefix: str = "GUIDA") -> str:
    en = english(source)
    return (
        "// GENERATO DA scripts/build_docs_bundle.py — non modificare a mano.\n"
        f"// Le fonti sono docs/guida/{source} e {en}; rigenera con `make docs-bundle`.\n"
        "\n"
        f"export const {prefix}_FILE = {json.dumps('docs/guida/' + source)};\n"
        f"export const {prefix}_FILE_EN = {json.dumps('docs/guida/' + en)};\n"
        "\n"
        f"export const {prefix}_MARKDOWN = {json.dumps(_read(source), ensure_ascii=False)};\n"
        "\n"
        f"export const {prefix}_MARKDOWN_EN = {json.dumps(_read(en), ensure_ascii=False)};\n"
    )


if __name__ == "__main__":
    CONTENT.mkdir(parents=True, exist_ok=True)
    for source, target, prefix in PAGES:
        out = CONTENT / target
        out.write_text(build(source, prefix), encoding="utf-8")
        print(f"scritto {out.relative_to(ROOT)}")
