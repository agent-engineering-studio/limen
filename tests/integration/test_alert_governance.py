"""Coda del digest, dedup comunale e contatori per canale (issue #59).

Sono le parti che vivono nel database, quindi si provano contro un Postgres
vero: che una voce accodata torni fuori identica, che il digest la marchi e
non la rispedisca, che un comune già allertato non riceva due volte lo stesso
avviso, e che il contatore orario ignori gli invii falliti.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.core.models.hazard import HazardType
from limen.core.models.risk import RiskLevel
from limen.data.db import acquire
from limen.data.repos.alert_aggregates_repo import (
    comuni_alerted_within,
    comuni_queued,
    expire_stale,
    fetch_queued,
    insert_aggregates,
    mark_sent,
    record_sends,
    sample_recent,
    sends_last_hour,
)
from limen.notifications.governance import ComuneAggregate, summarise_digest_it

pytestmark = pytest.mark.integration

_AOI_ID = "gov-test-aoi"


def _agg(
    comune: str,
    hazard: HazardType,
    level: RiskLevel = RiskLevel.High,
    *,
    cells: int = 4,
    score: float = 0.72,
) -> ComuneAggregate:
    return ComuneAggregate(
        istat_code=f"9{abs(hash(comune)) % 100000:05d}",
        comune=comune,
        aoi_id=_AOI_ID,
        hazard=hazard,
        max_level=level,
        max_score=score,
        cells_count=cells,
        top_cells=(("cell-a", score, level), ("cell-b", score - 0.05, level)),
    )


@pytest.fixture(autouse=True)
async def _clean(reset_db: None) -> None:
    # `alert_aggregates` e `notification_sends` non sono in reset_db: senza
    # questo, i conteggi dipenderebbero dall'ordine dei moduli di test.
    async with acquire() as conn:
        await conn.execute("TRUNCATE alert_aggregates, notification_sends")


async def test_a_queued_aggregate_round_trips_unchanged() -> None:
    """Quel che entra in coda deve tornare fuori identico, o il digest mente."""
    originale = _agg("Matera", HazardType.FLOOD, RiskLevel.High, cells=7, score=0.81)
    ids = await insert_aggregates([originale], state="queued")
    assert len(ids) == 1

    letti_ids, letti = await fetch_queued(max_age=timedelta(hours=6))
    assert letti_ids == ids
    assert len(letti) == 1
    tornato = letti[0]
    assert tornato.comune == "Matera"
    assert tornato.hazard is HazardType.FLOOD
    assert tornato.max_level is RiskLevel.High
    assert tornato.max_score == pytest.approx(0.81)
    assert tornato.cells_count == 7
    assert [c[0] for c in tornato.top_cells] == ["cell-a", "cell-b"]


async def test_the_digest_marks_what_it_sent_and_does_not_send_it_twice() -> None:
    ids = await insert_aggregates(
        [_agg("Altamura", HazardType.LANDSLIDE), _agg("Gravina", HazardType.WILDFIRE)],
        state="queued",
    )
    _, coda = await fetch_queued(max_age=timedelta(hours=6))
    assert len(coda) == 2

    await mark_sent(ids, digest_id="digest-test", channels={"telegram": True})

    residuo_ids, residuo = await fetch_queued(max_age=timedelta(hours=6))
    assert residuo_ids == []
    assert residuo == []

    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT state, digest_id, sent_at FROM alert_aggregates WHERE id = $1", ids[0]
        )
    assert row is not None
    assert row["state"] == "sent"
    assert row["digest_id"] == "digest-test"
    assert row["sent_at"] is not None


async def test_the_digest_text_joins_hazards_of_the_same_comune() -> None:
    """L'alert congiunto della #58, attraverso la coda.

    Due pericoli sullo stesso comune arrivano da due esecuzioni separate del
    workflow, che non si conoscono; la coda li ritrova insieme.
    """
    await insert_aggregates(
        [
            _agg("Matera", HazardType.LANDSLIDE, RiskLevel.High, cells=4),
            _agg("Matera", HazardType.FLOOD, RiskLevel.High, cells=2),
        ],
        state="queued",
    )
    _, coda = await fetch_queued(max_age=timedelta(hours=6))
    testo = summarise_digest_it(coda)
    assert "Matera" in testo
    assert "frana" in testo and "alluvione" in testo
    assert "più pericoli insieme" in testo


async def test_stale_queue_entries_expire_instead_of_being_sent() -> None:
    """Un riepilogo di allerte di ieri è disinformazione, non ritardo."""
    ids = await insert_aggregates([_agg("Vecchio", HazardType.FLOOD)], state="queued")
    async with acquire() as conn:
        await conn.execute(
            "UPDATE alert_aggregates SET created_at = now() - interval '10 hours' WHERE id = $1",
            ids[0],
        )

    _, spedibili = await fetch_queued(max_age=timedelta(hours=6))
    assert spedibili == []

    scadute = await expire_stale(max_age=timedelta(hours=6))
    assert scadute == 1
    async with acquire() as conn:
        stato = await conn.fetchval("SELECT state FROM alert_aggregates WHERE id = $1", ids[0])
    assert stato == "expired"


async def test_comune_dedup_is_per_hazard_and_only_counts_what_was_sent() -> None:
    frana = _agg("Potenza", HazardType.LANDSLIDE)
    await insert_aggregates([frana], state="sent")
    # Accodato, non spedito: nessuno l'ha ricevuto, quindi non deve sopprimere.
    alluvione = _agg("Potenza", HazardType.FLOOD)
    await insert_aggregates([alluvione], state="queued")

    soppressi_frana = await comuni_alerted_within(
        [frana.istat_code or ""], window=timedelta(hours=3), hazard=HazardType.LANDSLIDE
    )
    assert soppressi_frana == {frana.istat_code}

    # Altro pericolo sullo stesso comune: non soppresso.
    soppressi_incendio = await comuni_alerted_within(
        [frana.istat_code or ""], window=timedelta(hours=3), hazard=HazardType.WILDFIRE
    )
    assert soppressi_incendio == set()

    # Lo stesso comune con una voce solo accodata non conta come allertato.
    soppressi_alluvione = await comuni_alerted_within(
        [alluvione.istat_code or ""], window=timedelta(hours=3), hazard=HazardType.FLOOD
    )
    assert soppressi_alluvione == set()


async def test_comune_dedup_window_expires() -> None:
    agg = _agg("Melfi", HazardType.FLOOD)
    await insert_aggregates([agg], state="sent")
    async with acquire() as conn:
        await conn.execute("UPDATE alert_aggregates SET created_at = now() - interval '5 hours'")
    dentro = await comuni_alerted_within(
        [agg.istat_code or ""], window=timedelta(hours=6), hazard=HazardType.FLOOD
    )
    fuori = await comuni_alerted_within(
        [agg.istat_code or ""], window=timedelta(hours=1), hazard=HazardType.FLOOD
    )
    assert dentro == {agg.istat_code}
    assert fuori == set()


async def test_the_hourly_counter_ignores_failed_sends() -> None:
    """Un invio fallito non ha consumato l'attenzione di nessuno.

    Contarlo nel limite farebbe tacere il sistema proprio quando un canale è
    rotto — il momento in cui serve di più che gli altri parlino.
    """
    await record_sends({"telegram": True, "email": False}, kind="alert", aggregates=3)
    await record_sends({"telegram": True, "email": False}, kind="digest", aggregates=9)

    assert await sends_last_hour("telegram") == 2
    assert await sends_last_hour("email") == 0
    assert await sends_last_hour("mqtt") == 0


async def test_the_hourly_counter_forgets_older_sends() -> None:
    await record_sends({"telegram": True}, kind="alert", aggregates=1)
    async with acquire() as conn:
        await conn.execute("UPDATE notification_sends SET sent_at = now() - interval '90 minutes'")
    assert await sends_last_hour("telegram") == 0


async def test_the_far_sample_reads_back_what_it_needs() -> None:
    await insert_aggregates(
        [_agg(f"Comune {i}", HazardType.LANDSLIDE) for i in range(12)],
        state="sent",
        channels={"telegram": True},
    )
    campione = await sample_recent(limit=5, since=timedelta(days=30))
    assert len(campione) == 5
    for riga in campione:
        assert riga["comune"]
        assert riga["hazard_type"] == "landslide"
        assert isinstance(riga["created_at"], datetime)
        assert riga["top_cells"]

    # Fuori finestra: niente.
    async with acquire() as conn:
        await conn.execute("UPDATE alert_aggregates SET created_at = now() - interval '60 days'")
    assert await sample_recent(limit=5, since=timedelta(days=30)) == []


async def test_sent_aggregates_stamp_the_channels_they_reached() -> None:
    await insert_aggregates(
        [_agg("Venosa", HazardType.WILDFIRE)],
        state="sent",
        channels={"telegram": True, "webhook": False},
    )
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT channels, sent_at, created_at FROM alert_aggregates LIMIT 1"
        )
    assert row is not None
    canali = row["channels"]
    if isinstance(canali, str):
        import json

        canali = json.loads(canali)
    assert canali == {"telegram": True, "webhook": False}
    # `sent_at` viene messo dall'INSERT quando lo stato è 'sent': senza,
    # non si potrebbe distinguere una riga spedita da una in coda per data.
    assert row["sent_at"] is not None
    assert row["created_at"] <= datetime.now(UTC)


async def test_a_comune_already_queued_is_not_queued_twice() -> None:
    """Un ciclo trattenuto non scrive in `alert_dispatches`, quindi il ciclo
    dopo ritrova le stesse celle: senza questo controllo il riepilogo
    nominerebbe lo stesso comune N volte con lo stesso numero."""
    primo = _agg("Tricarico", HazardType.LANDSLIDE)
    await insert_aggregates([primo], state="queued")

    in_coda = await comuni_queued([primo.istat_code or ""], hazard=HazardType.LANDSLIDE)
    assert in_coda == {primo.istat_code}

    # Altro pericolo: non è in coda, e va accodato.
    assert await comuni_queued([primo.istat_code or ""], hazard=HazardType.FLOOD) == set()

    # Spedito dal digest: esce dalla coda, e un ciclo nuovo può riaccodarlo.
    await mark_sent([1_000_000], digest_id="nessuno", channels={})  # id inesistente
    async with acquire() as conn:
        await conn.execute("UPDATE alert_aggregates SET state = 'sent'")
    assert await comuni_queued([primo.istat_code or ""], hazard=HazardType.LANDSLIDE) == set()
