"""L'esposizione ISPRA per comune nel database (migrazione 085)."""

from __future__ import annotations

import pytest

from limen.data.db import acquire
from limen.data.repos import dataset_versions_repo, esposizione_comuni_repo
from limen.integrations.idrogeo.esposizione import EsposizioneComune, da_indicatori

pytestmark = pytest.mark.integration


def _riga(uid: int, nome: str, frana: int) -> EsposizioneComune:
    riga = da_indicatori({"uid": uid, "nome": nome, "popfr_p3p4": frana, "pop_res021": 1000})
    assert riga is not None
    return riga


async def test_la_fotografia_nuova_sostituisce_la_vecchia(reset_db: None, pg_pool: object) -> None:
    v1 = await dataset_versions_repo.record(source="ispra", dataset="pir_comuni", version="v1")
    await esposizione_comuni_repo.sostituisci(
        [_riga(72006, "Bari", 484), _riga(1001, "Agliè", 12)],
        version_id=v1,
    )
    async with acquire() as conn:
        letti = await esposizione_comuni_repo.per_comuni(conn, ["072006", "001001", "999999"])
    assert set(letti) == {"072006", "001001"}
    assert letti["072006"]["pop_frana_p3p4"] == 484
    assert letti["072006"]["pop_residenti"] == 1000
    assert "aggiornato" in letti["072006"]

    # ISPRA non elenca più Agliè (una fusione): non deve restare con i numeri di prima.
    v2 = await dataset_versions_repo.record(source="ispra", dataset="pir_comuni", version="v2")
    await esposizione_comuni_repo.sostituisci(
        [_riga(72006, "Bari", 500)],
        version_id=v2,
    )
    async with acquire() as conn:
        letti = await esposizione_comuni_repo.per_comuni(conn, ["072006", "001001"])
        versione = await conn.fetchval(
            "SELECT dataset_version_id FROM esposizione_comuni WHERE istat_code = '072006'"
        )
    assert list(letti) == ["072006"]
    assert letti["072006"]["pop_frana_p3p4"] == 500
    assert versione == v2
    assert await esposizione_comuni_repo.per_comuni(conn, []) == {}
