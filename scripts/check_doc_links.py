#!/usr/bin/env python3
"""Verifica che i link relativi dentro `docs/` puntino a qualcosa che esiste.

Un link rotto in una pagina divulgativa non rompe nessun test e nessun
deploy: si scopre quando un lettore ci clicca sopra. Questo script lo
trasforma in un errore di build.

Controlla solo i target locali (percorsi relativi, con eventuale ancora):
gli URL esterni richiederebbero rete e diventerebbero rossi per colpa di un
sito altrui.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _broken(md: Path) -> list[str]:
    out: list[str] = []
    for target in LINK.findall(md.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = (md.parent / target.split("#", 1)[0]).resolve()
        if not path.exists():
            out.append(f"{md.relative_to(ROOT)} → {target}")
    return out


def main() -> int:
    docs = [*sorted((ROOT / "docs").rglob("*.md")), ROOT / "README.md"]
    broken = [problem for md in docs for problem in _broken(md)]
    for problem in broken:
        print(f"link rotto: {problem}", file=sys.stderr)
    print(f"{len(docs)} file controllati, {len(broken)} link rotti")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
