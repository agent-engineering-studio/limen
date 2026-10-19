"""Il DSN di un ruolo ristretto è lo stesso database con un altro utente (#267)."""

from __future__ import annotations

import pytest

from limen.data.db import dsn_con_ruolo

PW = "0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize(
    ("dsn", "atteso"),
    [
        (
            "postgresql://limen:limen@postgres:5432/limen",
            f"postgresql://limen_ingestore:{PW}@postgres:5432/limen",
        ),
        (
            "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/limen?sslmode=require",
            f"postgresql://limen_ingestore:{PW}@ep-x.eu-central-1.aws.neon.tech/limen?sslmode=require",
        ),
        (
            "postgresql://u:p@[::1]:5432/limen",
            f"postgresql://limen_ingestore:{PW}@[::1]:5432/limen",
        ),
        (
            "postgresql://u:p@db1:5432,db2:5432/limen?target_session_attrs=read-write",
            f"postgresql://limen_ingestore:{PW}@db1:5432,db2:5432/limen?target_session_attrs=read-write",
        ),
        (
            "postgresql:///limen?host=/run/postgresql",
            f"postgresql://limen_ingestore:{PW}@/limen?host=/run/postgresql",
        ),
    ],
)
def test_cambia_solo_l_utente(dsn: str, atteso: str) -> None:
    assert dsn_con_ruolo(dsn, "limen_ingestore", PW) == atteso
