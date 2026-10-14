#!/usr/bin/env python3
"""Copia locale dell'archivio radar DPC 2010-2025 (IT-DPC-SRI), per il backtest.

IT-DPC-SRI (Fondazione Bruno Kessler su dati DPC, CC BY-SA 4.0, attribuzione
«© Dipartimento della Protezione Civile») è uno Zarr v2 da ~51 GB con un chunk
per istante. Zenodo lo dà come un unico .tar.zst, e lo serve a ~0,1 MB/s:
giorni. La stessa copia sta sull'object store di ECMWF (catalogo
mlcast-datasets), anonima, un fotogramma in ~0,14 s: con trenta richieste in
parallelo l'archivio intero arriva in qualche ora.

Riprendibile: salta i fotogrammi già su disco. Uno che il server non ha
(403/404) è un buco dell'archivio, si annota in ``missing.txt`` e non si
ritenta. ``PRIMO``/``ULTIMO`` limitano l'intervallo di indici: il backtest
vuole prima gli anni buoni (2015 in poi, indice 179087).

Uso: ``make radar-data`` oppure
``python scripts/mirror_it_dpc_sri.py DEST [CONCORRENZA] [PRIMO] [ULTIMO]``.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

BASE = (
    "https://object-store.os-api.cci2.ecmwf.int/mlcast-source-datasets/"
    "IT-DPC-SRI/v0.1.0/italian-radar-dpc-sri.zarr"
)
COORDINATE = ("crs", "lat", "lon", "x", "y", "time", "missing_times")


async def _get(cl: httpx.AsyncClient, key: str) -> bytes | None:
    for tentativo in range(6):
        try:
            r = await cl.get(f"{BASE}/{key}")
            if r.status_code == 200:
                return r.content
            if r.status_code in (403, 404):
                return None
        except httpx.HTTPError:
            pass
        await asyncio.sleep(2 * (tentativo + 1))
    raise RuntimeError(f"{key}: sei tentativi falliti")


async def _metadati(cl: httpx.AsyncClient, dest: Path) -> dict[str, dict[str, object]]:
    for k in (".zmetadata", ".zgroup", ".zattrs"):
        (dest / k).write_bytes(await _get(cl, k) or b"")
    meta: dict[str, dict[str, object]] = json.loads((dest / ".zmetadata").read_text())["metadata"]
    for k, v in meta.items():
        if k.endswith((".zarray", ".zattrs")):
            p = dest / k
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(v))
    for arr in COORDINATE:
        shape = meta[f"{arr}/.zarray"]["shape"]
        assert isinstance(shape, list)
        key = f"{arr}/" + (".".join("0" for _ in shape) if shape else "0")
        if not (dest / key).exists():
            data = await _get(cl, key)
            if data is not None:
                (dest / key).write_bytes(data)
    return meta


async def main(dest: Path, conc: int, primo: int, ultimo: int | None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=conc)) as cl:
        meta = await _metadati(cl, dest)
        shape = meta["RR/.zarray"]["shape"]
        assert isinstance(shape, list)
        rr = dest / "RR"
        rr.mkdir(exist_ok=True)
        buchi = dest / "missing.txt"
        noti = set(buchi.read_text().split()) if buchi.exists() else set()
        fine = ultimo if ultimo is not None else int(shape[0])
        todo = [
            i for i in range(primo, fine) if not (rr / f"{i}.0.0").exists() and str(i) not in noti
        ]
        sys.stderr.write(f"fotogrammi {primo}-{fine}: da scaricare {len(todo)}\n")
        sem = asyncio.Semaphore(conc)
        fatti = 0
        scritti = 0
        t0 = time.time()

        async def uno(i: int) -> None:
            nonlocal fatti, scritti
            async with sem:
                data = await _get(cl, f"RR/{i}.0.0")
            if data is None:
                with buchi.open("a") as f:
                    f.write(f"{i}\n")
            else:
                tmp = rr / f".{i}.0.0.tmp"
                tmp.write_bytes(data)
                tmp.rename(rr / f"{i}.0.0")
                scritti += len(data)
            fatti += 1
            if fatti % 20000 == 0:
                velocita = fatti / (time.time() - t0)
                sys.stderr.write(
                    f"{fatti}/{len(todo)}  {scritti / 1e9:.1f} GB  {velocita:.0f} fotogrammi/s\n"
                )

        for k in range(0, len(todo), 5000):
            await asyncio.gather(*(uno(i) for i in todo[k : k + 5000]))
    sys.stderr.write("fatto\n")


if __name__ == "__main__":
    a = sys.argv[1:]
    asyncio.run(
        main(
            Path(a[0]),
            int(a[1]) if len(a) > 1 else 32,
            int(a[2]) if len(a) > 2 else 0,
            int(a[3]) if len(a) > 3 else None,
        )
    )
