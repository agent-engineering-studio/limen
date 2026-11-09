"""``limen importa-eventi`` contro un Postgres vero (#509)."""

from __future__ import annotations

from pathlib import Path

import pytest

from limen.cli.importa_eventi import run
from limen.data.db import acquire

pytestmark = pytest.mark.integration

AOI = "ie-aoi"
_INTESTAZIONE = "id;pericolo;data;ora;comuni;luogo;fonte"


async def _seed_comune() -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1,'IE','region',"
            "ST_Multi(ST_MakeEnvelope(15.0, 37.0, 16.0, 38.0, 4326)))",
            AOI,
        )
        await conn.execute(
            "INSERT INTO comuni (istat_code, name, aoi_id, geom) VALUES ('999001','IE',$1,"
            "ST_Multi(ST_MakeEnvelope(15.0, 37.0, 15.2, 37.2, 4326)))",
            AOI,
        )


def _file(tmp_path: Path, *righe: str) -> Path:
    p = tmp_path / "eventi.csv"
    p.write_text("\n".join((_INTESTAZIONE, *righe)) + "\n", encoding="utf-8")
    return p


async def test_import_registra_frane_e_non_rilegge(
    reset_db: None, pg_pool: object, tmp_path: Path
) -> None:
    await _seed_comune()
    p = _file(
        tmp_path,
        "1;frana;2025-11-14;;999001;SP 22;verbale 112",
        "2;alluvione;2025-11-15;08:00;999001;Sottopasso;verbale 113",
    )
    assert await run(str(p), ente="Comune IE", licenza="CC BY 4.0") == 0
    async with acquire() as conn:
        righe = await conn.fetch(
            "SELECT slug, esito, precisione_ora, fonti->0->>'licenza' AS licenza "
            "FROM verifiche_eventi ORDER BY slug"
        )
        frane = await conn.fetch("SELECT id, source FROM landslide_events WHERE source = 'ente'")
        versioni = await conn.fetchval(
            "SELECT count(*) FROM dataset_versions WHERE source = 'ente' AND dataset = 'comune-ie'"
        )
    assert [(r["slug"], r["esito"], r["precisione_ora"], r["licenza"]) for r in righe] == [
        ("2025-11-14-frana-ente-comune-ie-1", "non_verificabile", "T3", "CC BY 4.0"),
        ("2025-11-15-alluvione-ente-comune-ie-2", "non_verificabile", "T1", "CC BY 4.0"),
    ]
    assert [(f["id"], f["source"]) for f in frane] == [
        ("ente:2025-11-14-frana-ente-comune-ie-1", "ente")
    ]
    assert versioni == 1

    # Lo stesso file non si rilegge; uno che cresce misura solo la riga nuova.
    assert await run(str(p), ente="Comune IE", licenza="CC BY 4.0") == 0
    p = _file(
        tmp_path,
        "1;frana;2025-11-14;;999001;SP 22;verbale 112",
        "2;alluvione;2025-11-15;08:00;999001;Sottopasso;verbale 113",
        "3;incendio;2025-08-02;;999001;Pineta;verbale 90",
    )
    assert await run(str(p), ente="Comune IE", licenza="CC BY 4.0") == 0
    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM verifiche_eventi") == 3
        assert await conn.fetchval("SELECT count(*) FROM dataset_versions WHERE source='ente'") == 2


async def test_un_comune_sconosciuto_ferma_tutto(
    reset_db: None, pg_pool: object, tmp_path: Path
) -> None:
    await _seed_comune()
    p = _file(
        tmp_path,
        "1;frana;2025-11-14;;999001;SP 22;verbale 112",
        "2;frana;2025-11-14;;999999;Altrove;verbale 113",
    )
    assert await run(str(p), ente="Comune IE", licenza="CC BY 4.0") == 2
    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM verifiche_eventi") == 0
