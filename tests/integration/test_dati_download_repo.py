"""La coda dei download (migrazione 086) contro un PostgreSQL vero.

Le regole stanno nelle query: una voce in corso non si riaccoda, si prende la
più vecchia, un worker riavviato riprende le interrotte, e chi accoda sveglia
il worker con un NOTIFY.
"""

from __future__ import annotations

import asyncio

import pytest

from limen.data.db import acquire
from limen.data.repos import dati_download_repo as repo

pytestmark = pytest.mark.integration


@pytest.fixture
async def vuota(pg_pool: object) -> None:
    async with acquire() as conn:
        await conn.execute("TRUNCATE dati_download")


async def test_la_coda_rispetta_l_ordine_e_non_riaccoda_chi_lavora(vuota: None) -> None:
    assert await repo.accoda(["iffi", "dtm"], byte_totali={"dtm": 22_100_000_000}) == [
        "iffi",
        "dtm",
    ]
    assert await repo.prendi_prossima() == "iffi"
    # iffi è in corso: chiederla di nuovo non la rimette in fondo alla coda.
    assert await repo.accoda(["iffi"], byte_totali={}) == []
    await repo.avanza("iffi", 500)
    await repo.chiudi("iffi", errore=None, byte_fatti=800)

    assert await repo.prendi_prossima() == "dtm"
    await repo.chiudi("dtm", errore="Il server di Zenodo ha un problema (errore 503)")
    assert await repo.prendi_prossima() is None

    stati = {r.voce: r for r in await repo.elenco()}
    assert (stati["iffi"].stato, stati["iffi"].byte_fatti) == ("fatto", 800)
    assert stati["dtm"].stato == "errore"
    assert stati["dtm"].byte_totali == 22_100_000_000

    # Una voce finita in errore si riaccoda e perde l'errore vecchio.
    assert await repo.accoda(["dtm"], byte_totali={}) == ["dtm"]
    assert {r.voce: r.errore for r in await repo.elenco()}["dtm"] is None


async def test_un_worker_riavviato_riprende_le_interrotte(vuota: None) -> None:
    await repo.accoda(["dtm"], byte_totali={})
    assert await repo.prendi_prossima() == "dtm"
    assert await repo.riaccoda_interrotte() == ["dtm"]
    assert await repo.prendi_prossima() == "dtm"


async def test_accodare_sveglia_chi_ascolta(vuota: None) -> None:
    sveglia = asyncio.Event()

    def _notifica(*_: object) -> None:
        sveglia.set()

    async with acquire() as conn:
        await conn.add_listener(repo.CANALE, _notifica)
        try:
            await repo.accoda(["litologia"], byte_totali={})
            await asyncio.wait_for(sveglia.wait(), timeout=5)
        finally:
            await conn.remove_listener(repo.CANALE, _notifica)


async def test_una_voce_che_fa_cadere_il_worker_si_ferma_al_tetto(vuota: None) -> None:
    """Un download che uccide il processo tornerebbe in coda a ogni riavvio."""
    await repo.accoda(["corine"], byte_totali={})
    for _ in range(repo.TENTATIVI_MASSIMI - 1):
        assert await repo.prendi_prossima() == "corine"
        assert await repo.riaccoda_interrotte() == ["corine"]
    assert await repo.prendi_prossima() == "corine"
    assert await repo.riaccoda_interrotte() == []
    (riga,) = await repo.elenco()
    assert riga.stato == "errore"
    assert "si è interrotto 3 volte" in (riga.errore or "")
    # Chiederla di nuovo azzera il conto.
    await repo.accoda(["corine"], byte_totali={})
    assert (await repo.elenco())[0].tentativi == 0


async def test_il_lock_tiene_fuori_il_secondo_download(vuota: None) -> None:
    async with repo.blocco_download() as primo, repo.blocco_download() as secondo:
        assert (primo, secondo) == (True, False)
    async with repo.blocco_download() as dopo:
        assert dopo
