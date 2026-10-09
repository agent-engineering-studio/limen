"""Il rapporto «Regioni da monitorare» in PDF.

Lo stesso contenuto della pagina, impaginato per la stampa e per essere
inoltrato: numeri, allerta ufficiale, comuni da guardare e il racconto
dell'AI di ogni regione. ReportLab e non un browser senza testa: puro Python,
nessuna libreria di sistema da aggiungere all'immagine.

I caratteri sono quelli standard del PDF (Helvetica, codifica WinAnsi):
un carattere fuori da quella tabella si sostituisce invece di sparire.
"""

from __future__ import annotations

import io
from datetime import datetime
from importlib import resources
from typing import Any
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_ROMA = ZoneInfo("Europe/Rome")

NOME_PERICOLO = {"landslide": "Frane", "flood": "Allagamenti", "wildfire": "Incendi"}
_CLASSE = {
    "None": "nessuno",
    "Low": "basso",
    "Moderate": "moderato",
    "High": "alto",
    "VeryHigh": "molto alto",
}
#: La scala della mappa, con «nessuno» schiarito: sulla carta bianca il quasi
#: nero della sala operativa non si legge come «tranquillo».
_COLORE = {
    "None": "#c9ced6",
    "Low": "#134d47",
    "Moderate": "#f2d45c",
    "High": "#f58a30",
    "VeryHigh": "#e33f5a",
}
_TESTO_SCURO = {"Moderate", "High", "None"}
_ALLERTA = ["nessuna", "gialla", "arancione", "rossa"]
_CAUSA = {
    "static_susceptibility": "la fragilità del terreno",
    "meteo_trigger": "la pioggia",
    "seismic_event": "le scosse recenti",
    "post_fire_destabilization": "gli incendi recenti",
    "human_activity": "l'attività umana",
    "pluvial_rain": "la pioggia prevista",
    "river_discharge": "la portata dei fiumi",
    "hydraulic_susceptibility": "quanto la zona è allagabile",
    "fire_weather": "il tempo secco e ventoso",
    "fuel_load": "la vegetazione che brucia",
    "terrain_slope": "la pendenza",
}
_SOSTITUZIONI = {"≥": ">=", "≤": "<=", "→": "->", "↗": "^", "↘": "v", "²": "2", "\u2212": "-"}


def _t(testo: str) -> str:
    """Testo pronto per un Paragraph: sostituzioni WinAnsi ed escape XML."""
    for a, b in _SOSTITUZIONI.items():
        testo = testo.replace(a, b)
    testo = testo.encode("cp1252", errors="replace").decode("cp1252")
    return escape(testo)


def _stili() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "base", fontName="Helvetica", fontSize=10, leading=14.5, alignment=TA_LEFT
    )
    return {
        "base": base,
        "titolo": ParagraphStyle(
            "titolo", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24
        ),
        "sotto": ParagraphStyle(
            "sotto", parent=base, fontSize=9.5, leading=13.5, textColor=colors.HexColor("#4a5563")
        ),
        "regione": ParagraphStyle(
            "regione",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            spaceBefore=4,
        ),
        "dato": ParagraphStyle(
            "dato", parent=base, fontSize=9.5, leading=13.5, textColor=colors.HexColor("#1f2937")
        ),
        "ai_titolo": ParagraphStyle(
            "ai_titolo",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#6b7280"),
            spaceBefore=6,
        ),
        "ai": ParagraphStyle("ai", parent=base, fontSize=10, leading=14.5, spaceAfter=4),
        "chip": ParagraphStyle(
            "chip", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=11
        ),
    }


def _ora(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(_ROMA).strftime("%d/%m %H:%M")


def _giorno(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(_ROMA).strftime("%d/%m")


def _righe_numeri(r: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for h in ("flood", "landslide", "wildfire"):
        adesso = r["pericoli"].get(h)
        poi = r["previsto"].get(h)
        parti: list[str] = []
        if adesso and adesso["alte"] > 0:
            parti.append(f"{adesso['alte']:,} aree in classe alta adesso".replace(",", "."))
        elif adesso and adesso["moderate"] > 0:
            parti.append(f"{adesso['moderate']:,} aree moderate adesso".replace(",", "."))
        if poi:
            parti.append(f"picco previsto {_CLASSE[poi['classe']]} il {_giorno(poi['target_at'])}")
        if parti:
            out.append(f"<b>{NOME_PERICOLO[h]}</b>: {_t(' · '.join(parti))}")
    return out


def _chip(r: dict[str, Any], stili: dict[str, ParagraphStyle]) -> Table | None:
    p = r["peggiore"]
    if not p:
        return None
    previsto = " previsto" if p["previsto"] else ""
    testo = f"{NOME_PERICOLO[p['hazard']]} · {_CLASSE[p['classe']]}{previsto}"
    colore_testo = "#111827" if p["classe"] in _TESTO_SCURO else "#ffffff"
    cella = Paragraph(f'<font color="{colore_testo}">{_t(testo)}</font>', stili["chip"])
    from reportlab.pdfbase.pdfmetrics import stringWidth

    larghezza = stringWidth(_t(testo), "Helvetica-Bold", 8.5) + 14
    chip = Table([[cella]], colWidths=[larghezza], hAlign="LEFT")
    chip.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_COLORE[p["classe"]])),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return chip


def _sezione(r: dict[str, Any], posizione: int, stili: dict[str, ParagraphStyle]) -> list[Any]:
    testa: list[Any] = [Paragraph(f"{posizione}. {_t(r['nome'])}", stili["regione"])]
    chip = _chip(r, stili)
    testa.append(chip if chip is not None else Paragraph("nessun segnale", stili["sotto"]))
    testa.append(Spacer(1, 4))
    for riga in _righe_numeri(r):
        testa.append(Paragraph(riga, stili["dato"]))
    allerta = r.get("allerta") or {}
    oggi = allerta.get("oggi")
    domani = allerta.get("domani")
    testa.append(
        Paragraph(
            "<b>Allerta ufficiale</b>: oggi "
            + _t(_ALLERTA[oggi] if oggi is not None else "n.d.")
            + " · domani "
            + _t(_ALLERTA[domani] if domani is not None else "non ancora emessa"),
            stili["dato"],
        )
    )
    if r["comuni"]:
        nomi = ", ".join(f"{c['nome']} ({NOME_PERICOLO[c['hazard']].lower()})" for c in r["comuni"])
        testa.append(Paragraph(f"<b>Comuni da guardare</b>: {_t(nomi)}", stili["dato"]))
    blocchi: list[Any] = [KeepTogether(testa)]

    ordine = sorted(r["spiegazioni"], key=lambda h: (h != (r["peggiore"] or {}).get("hazard"), h))
    for h in ordine:
        s = r["spiegazioni"][h]
        racconto: list[Any] = [
            Paragraph(
                _t(f"{NOME_PERICOLO[h].upper()} · IL RACCONTO DELL'AI · {_ora(s['scritta'])}"),
                stili["ai_titolo"],
            )
        ]
        analisi = s.get("analisi") or {}
        if analisi.get("driver"):
            racconto.append(
                Paragraph(
                    "<i>Causa principale: "
                    + _t(_CAUSA.get(analisi["driver"], analisi["driver"]))
                    + f" · da tenere d'occhio per {analisi.get('attention_window_hours', '-')}"
                    + " ore</i>",
                    stili["dato"],
                )
            )
        for paragrafo in [p for p in s["testo"].split("\n\n") if p.strip()]:
            racconto.append(Paragraph(_t(paragrafo.strip()), stili["ai"]))
        blocchi.append(KeepTogether(racconto[:3]))
        blocchi.extend(racconto[3:])
    blocchi.append(Spacer(1, 10))
    return blocchi


def rapporto_pdf(regioni: list[dict[str, Any]], *, generato: datetime) -> bytes:
    """Il PDF delle regioni passate, nell'ordine dato."""
    stili = _stili()
    buffer = io.BytesIO()
    quando = generato.astimezone(_ROMA).strftime("%d/%m/%Y alle %H:%M")
    limen = resources.files("limen.report").joinpath("assets/limen-logo.png").read_bytes()

    def pagina(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        larghezza, _ = A4
        canvas.setStrokeColor(colors.HexColor("#d1d5db"))
        canvas.line(18 * mm, 16 * mm, larghezza - 18 * mm, 16 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(
            18 * mm,
            11 * mm,
            _t(f"Limen · Regioni da monitorare · {quando} · pagina {doc.page}").replace(
                "&amp;", "&"
            ),
        )
        canvas.drawRightString(
            larghezza - 18 * mm, 11 * mm, "Racconti scritti con Claude, il modello di Anthropic"
        )
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=22 * mm,
        title="Limen · Regioni da monitorare",
        author="Limen",
    )
    intestazione = Table(
        [
            [
                _immagine(limen, 14 * mm),
                [
                    Paragraph("Regioni da monitorare", stili["titolo"]),
                    Paragraph(_t(f"Rapporto Limen del {quando}"), stili["sotto"]),
                ],
            ]
        ],
        colWidths=[18 * mm, None],
        hAlign="LEFT",
    )
    intestazione.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    storia: list[Any] = [
        intestazione,
        Spacer(1, 6),
        Paragraph(
            _t(
                "Le regioni in ordine di pericolo stimato, adesso e nelle prossime 72 ore. "
                "L'ordine lo decidono i numeri; il racconto di ogni regione è scritto "
                "dall'AI e non cambia nessun numero. I colori sono il pericolo stimato da "
                "Limen, non un livello di allerta: l'allerta che vale è quella del "
                "bollettino della Protezione Civile, riportata per ogni regione."
            ),
            stili["sotto"],
        ),
        Spacer(1, 10),
    ]
    for i, r in enumerate(regioni, start=1):
        storia.extend(_sezione(r, i, stili))
    doc.build(storia, onFirstPage=pagina, onLaterPages=pagina)
    return buffer.getvalue()


def _immagine(dati: bytes, lato: float) -> Any:
    from reportlab.platypus import Image

    larghezza, altezza = ImageReader(io.BytesIO(dati)).getSize()
    return Image(io.BytesIO(dati), width=lato, height=lato * altezza / larghezza)


__all__ = ["NOME_PERICOLO", "rapporto_pdf"]
