"""L'impronta che decide se un passo del bootstrap va rifatto (#101).

Il valore di questo meccanismo non è che salta dei passi: è che salta quelli
giusti. Un'impronta troppo grossolana ricalcola un'ora e mezza per niente;
una troppo fine risponde "invariato" a una domanda diversa, e quella è la
modalità di guasto peggiore perché è silenziosa.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from limen.integrations.static_bootstrap import fingerprint


def test_a_missing_env_var_is_a_clean_skip() -> None:
    """Una sorgente non configurata non è un errore: è un layer che questo
    deployment non ha, e il bootstrap deve proseguire."""
    fp = fingerprint.of_env_file("LIMEN_TEST_NON_ESISTE")
    assert fp.available is False
    assert "LIMEN_TEST_NON_ESISTE" in fp.reason


def test_a_configured_but_absent_file_is_also_a_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Variabile impostata su un percorso che non esiste: skip, non crash.

    È il caso di chi copia un `.env` da un'altra macchina."""
    monkeypatch.setenv("LIMEN_TEST_RASTER", "/tmp/non-esiste-davvero.tif")
    fp = fingerprint.of_env_file("LIMEN_TEST_RASTER")
    assert fp.available is False
    assert "file assente" in fp.reason


def test_the_same_file_gives_the_same_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raster = tmp_path / "dtm.tif"
    raster.write_bytes(b"x" * 128)
    monkeypatch.setenv("LIMEN_TEST_RASTER", str(raster))
    assert fingerprint.of_env_file("LIMEN_TEST_RASTER") == fingerprint.of_env_file(
        "LIMEN_TEST_RASTER"
    )


def test_touching_the_file_changes_the_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Il criterio di accettazione della issue: toccare un raster fa
    rieseguire il passo che lo usa."""
    raster = tmp_path / "dtm.tif"
    raster.write_bytes(b"x" * 128)
    monkeypatch.setenv("LIMEN_TEST_RASTER", str(raster))
    before = fingerprint.of_env_file("LIMEN_TEST_RASTER")

    os.utime(raster, (1_700_000_000, 1_700_000_000))
    after = fingerprint.of_env_file("LIMEN_TEST_RASTER")

    assert before.parts != after.parts


def test_same_mtime_but_different_size_still_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'mtime da solo non basta.

    Sostituire un file conservando il timestamp è raro ma non impossibile —
    `cp -p`, un restore da backup, un rsync con `--times`. La dimensione
    chiude il caso pratico senza pagare l'hash di un mosaico da gigabyte.
    """
    raster = tmp_path / "dtm.tif"
    raster.write_bytes(b"x" * 128)
    monkeypatch.setenv("LIMEN_TEST_RASTER", str(raster))
    os.utime(raster, (1_700_000_000, 1_700_000_000))
    before = fingerprint.of_env_file("LIMEN_TEST_RASTER")

    raster.write_bytes(b"x" * 256)
    os.utime(raster, (1_700_000_000, 1_700_000_000))
    after = fingerprint.of_env_file("LIMEN_TEST_RASTER")

    assert before.parts != after.parts


def test_merge_propagates_unavailability() -> None:
    """Un passo che dipende da due sorgenti e ne ha una sola non può girare."""
    ok = fingerprint.Fingerprint(parts=("a:1",))
    ko = fingerprint.missing("manca la seconda")
    assert ok.merge(ko).available is False
    assert ko.merge(ok).available is False
    assert ok.merge(ok).available is True


def _gate(aoi: str = "it-test", cells: int = 100, *, force: bool = False) -> fingerprint.StepGate:
    """Un gate senza database: `create()` legge il conteggio celle, qui lo si
    passa a mano per tenere il test unitario."""
    return fingerprint.StepGate(aoi, cells, force=force)


def test_the_version_changes_with_the_grid() -> None:
    """Un re-seed che cambia la griglia deve invalidare tutto: i fattori sono
    per cella, e le celle non sono più quelle."""
    fp = fingerprint.Fingerprint(parts=("dtm:1:2",))
    assert _gate(cells=100)._version("dem", fp) != _gate(cells=101)._version("dem", fp)


def test_the_version_changes_with_the_step_code_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quando cambia la formula e non la sorgente, il risultato va rifatto.

    È il caso reale della formula WUI (#62) e di `imperviousness_norm` (#63):
    senza questa riga il bootstrap avrebbe risposto "invariato" a una domanda
    diversa da quella di prima.
    """
    fp = fingerprint.Fingerprint(parts=("corine:1:2",))
    gate = _gate()
    before = gate._version("wui", fp)
    monkeypatch.setitem(fingerprint.STEP_VERSION, "wui", fingerprint.STEP_VERSION["wui"] + 1)
    assert gate._version("wui", fp) != before


def test_the_version_is_per_step() -> None:
    """Due passi con la stessa sorgente non devono condividere la versione,
    o bumparne uno salterebbe l'altro."""
    fp = fingerprint.Fingerprint(parts=("corine:1:2",))
    gate = _gate()
    assert gate._version("corine", fp) != gate._version("wui", fp)


def test_an_unavailable_source_never_runs_and_is_counted() -> None:
    gate = _gate()
    assert gate.outcomes == []
    # `needs` è async, ma sul ramo "sorgente assente" non tocca il database:
    # si può esercitare senza, ed è il ramo che deve restare gratuito.
    import asyncio

    ran = asyncio.run(gate.needs("dem", fingerprint.missing("niente DTM")))
    assert ran is False
    assert gate.outcomes == [fingerprint.StepOutcome("dem", ran=False, reason="niente DTM")]


def test_the_summary_says_nothing_was_recomputed() -> None:
    """`make up` deve dire cosa ha saltato, non tacere: un passo idempotente
    che tace è indistinguibile da un passo che non è stato eseguito."""
    gate = _gate("it-molise")
    gate.outcomes = [
        fingerprint.StepOutcome("dem", ran=False, reason="sorgente invariata"),
        fingerprint.StepOutcome("corine", ran=False, reason="sorgente invariata"),
    ]
    assert gate.summary() == "it-molise: 2 passi saltati (sorgente invariata), 0 ricalcolati"


def test_the_summary_names_what_it_recomputed_and_why() -> None:
    gate = _gate("it-puglia")
    gate.outcomes = [
        fingerprint.StepOutcome("dem", ran=True, reason="sorgente cambiata"),
        fingerprint.StepOutcome("corine", ran=False, reason="sorgente invariata"),
    ]
    summary = gate.summary()
    assert "1 ricalcolati" in summary
    assert "dem: sorgente cambiata" in summary
    assert "1 saltati" in summary
