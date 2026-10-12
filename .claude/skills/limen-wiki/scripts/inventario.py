#!/usr/bin/env python3
"""Inventario per limen-wiki: cosa è cambiato e cosa manca nelle due pagine.

Tre sezioni, tutte lette dal repository (nessun DB, nessuna rete):

1. FONTI — ogni documento sotto docs/ e il README con la data dell'ultimo
   commit, marcato «NUOVO» se è più recente dell'ultimo commit della pagina
   che lo racconta.
2. SUPERFICI — rotte REST, strumenti MCP e skill A2A dichiarati nel codice,
   e quali di questi `docs/guida/integrazioni.md` non nomina mai.
3. FIGURE — i marcatori `<!-- componente: nome -->` nelle due pagine contro
   i componenti registrati in `COMPONENTI` di `DocPage.tsx`.

Uso: `python3 .claude/skills/limen-wiki/scripts/inventario.py`
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GUIDA = ROOT / "docs" / "guida" / "limen.md"
INTEGRAZIONI = ROOT / "docs" / "guida" / "integrazioni.md"
DOCPAGE = ROOT / "frontend" / "src" / "components" / "DocPage.tsx"

# Quale pagina racconta quale fonte: le integrazioni vengono da questi tre,
# tutto il resto confluisce nella guida.
INTEGRAZIONI_FONTI = {"docs/api.md", "docs/openclaw.md", "docs/geodata.md"}


def ultimo_commit(path: Path) -> str:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%cs", "--", str(path.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return out or "non committato"


def fonti() -> None:
    print("== FONTI (data ultimo commit; NUOVO = più recente della pagina)")
    pagine = {"guida": ultimo_commit(GUIDA), "integrazioni": ultimo_commit(INTEGRAZIONI)}
    print(f"   pagina guida: {pagine['guida']} · pagina integrazioni: {pagine['integrazioni']}")
    for it in (GUIDA, INTEGRAZIONI):
        en = it.with_suffix(".en.md")
        if not en.exists():
            print(f"   MANCA LA TRADUZIONE: {en.relative_to(ROOT)}")
        elif ultimo_commit(en) < ultimo_commit(it):
            print(f"   TRADUZIONE INDIETRO: {en.name} ({ultimo_commit(en)}) < {it.name}")
    files = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    for f in files:
        rel = str(f.relative_to(ROOT))
        if rel.startswith("docs/guida/") or rel.startswith("docs/superpowers/"):
            continue
        quando = ultimo_commit(f)
        pagina = "integrazioni" if rel in INTEGRAZIONI_FONTI else "guida"
        nuovo = "NUOVO" if quando > pagine[pagina] else ""
        print(f"   {quando}  {nuovo:5}  {pagina:12}  {rel}")


def superfici() -> None:
    testo = INTEGRAZIONI.read_text(encoding="utf-8") if INTEGRAZIONI.exists() else ""
    print("\n== SUPERFICI (✗ = non nominata in docs/guida/integrazioni.md)")

    rotte: list[str] = []
    for f in sorted((ROOT / "src" / "limen" / "api" / "endpoints").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        prefix_m = re.search(r'APIRouter\(\s*prefix="([^"]*)"', src)
        prefix = prefix_m.group(1) if prefix_m else ""
        for verb, path in re.findall(r'@router\.(get|post|put|delete)\(\s*"([^"]*)"', src):
            rotte.append(f"{verb.upper()} {prefix}{path}")
    print("   REST:")
    for r in rotte:
        path = r.split(" ", 1)[1]
        print(f"     {'✓' if path in testo else '✗'} {r}")

    mcp = re.findall(
        r"async def (tool_\w+)",
        (ROOT / "src" / "limen" / "mcp" / "server.py").read_text(encoding="utf-8"),
    )
    geo_server = ROOT / "geodata"
    geo: list[str] = []
    for f in geo_server.rglob("*.py"):
        if "mcp" in f.parts:
            geo += re.findall(r"def (tool_\w+)", f.read_text(encoding="utf-8"))
    print("   MCP limen-ops:")
    for t in mcp:
        print(f"     {'✓' if t in testo else '✗'} {t}")
    print("   MCP ispra-geo:")
    for t in sorted(set(geo)):
        print(f"     {'✓' if t in testo else '✗'} {t}")

    skills = re.findall(
        r'id="(\w+)"', (ROOT / "src" / "limen" / "a2a" / "skills.py").read_text(encoding="utf-8")
    )
    print("   A2A skill:")
    for s in skills:
        print(f"     {'✓' if s in testo else '✗'} {s}")


def figure() -> None:
    print("\n== FIGURE (marcatori nel Markdown contro COMPONENTI registrati)")
    reg_src = DOCPAGE.read_text(encoding="utf-8") if DOCPAGE.exists() else ""
    blocco = re.search(r"const COMPONENTI[^{]*\{(.*?)\n\};", reg_src, re.S)
    registrati = (
        set(re.findall(r'^\s*"?([a-z-]+)"?\s*:', blocco.group(1), re.M)) if blocco else set()
    )
    usati: dict[str, list[str]] = {}
    for pagina in (GUIDA, INTEGRAZIONI):
        if not pagina.exists():
            continue
        for nome in re.findall(r"<!--\s*componente:\s*([a-z-]+)\s*-->", pagina.read_text()):
            usati.setdefault(nome, []).append(pagina.name)
    for nome in sorted(registrati | set(usati)):
        dove = ", ".join(usati.get(nome, [])) or "—"
        stato = (
            "ok"
            if nome in registrati and nome in usati
            else ("MANCA IL COMPONENTE" if nome in usati else "registrato, non usato")
        )
        print(f"   {nome:28} {stato:22} {dove}")


if __name__ == "__main__":
    fonti()
    superfici()
    figure()
