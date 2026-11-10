"""Il paragrafo dell'AI sul riepilogo della qualità dei dati: parole, mai numeri (#421)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from limen.agents.chat_agents.qualita_dati import riformula
from limen.agents.chat_agents.traduttore import numeri_dentro
from limen.agents.llm_factory.base import ChatMessage
from limen.agents.llm_factory.stub import StubChatClient
from limen.core.qualita_dati import Cadenza, Fatti
from limen.core.qualita_dati import testo as riepilogo

RIGHE = [
    "**limen-hourly-monitoring** è fermo in 20 ambiti (it-puglia, …): ultimo successo 15 h fa, "
    "di solito gira ogni 1 h.",
    "**limen-nowcast** è fallito 3 volte nelle ultime 24 ore, l'ultima alle 02:40 UTC: "
    "«column c.land_cover does not exist».",
]


async def test_il_paragrafo_che_ripete_le_cifre_passa() -> None:
    testo = (
        "Lo sweep orario limen-hourly-monitoring è fermo da 15 h su 20 ambiti; "
        "il nowcast fallisce perché manca la colonna land_cover: è lo schema da controllare."
    )
    client = StubChatClient(canned_responses=[f"  {testo}\n"])
    assert await riformula(client, RIGHE) == testo
    (chiamata,) = client.calls
    assert "Nessun numero nuovo" in chiamata[0].content
    assert RIGHE[1] in chiamata[1].content


async def test_un_numero_inventato_scarta_il_paragrafo() -> None:
    client = StubChatClient(canned_responses=["Lo sweep è fermo da 16 h su tutte le regioni."])
    assert await riformula(client, RIGHE) is None


async def test_un_modello_che_non_risponde_lascia_le_righe() -> None:
    class Guasto(StubChatClient):
        async def chat(self, messages: Sequence[ChatMessage], **_: object) -> str:
            raise RuntimeError("tetto mensile di 10 $ raggiunto")

    assert await riformula(Guasto(), RIGHE) is None
    assert await riformula(StubChatClient(canned_responses=["  "]), RIGHE) is None


def test_tacere_una_cifra_e_lecito_cambiarla_no() -> None:
    assert numeri_dentro("fermo da ore", "fermo da 15 h")
    assert numeri_dentro("ultimo alle 02:40", "l'ultima alle 02:40 UTC")
    assert not numeri_dentro("fermo da 1,5 giorni", "fermo da 15 h")


def test_il_paragrafo_sta_sopra_le_righe_che_fanno_fede() -> None:
    ora = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)
    fermo = Cadenza("limen-x", None, ora - timedelta(hours=5), timedelta(hours=1), 50)
    testo = riepilogo(Fatti(ora, [], [fermo], {}), None, "Il job limen-x è fermo.")
    assert testo.index("Il job limen-x è fermo.") < testo.index("**limen-x** è fermo")
    assert "fanno fede" in testo
