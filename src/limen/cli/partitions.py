"""``limen partitions`` — create the upcoming daily partitions and report state.

The scheduler does this on every cleanup tick and the API on every boot; the
command exists for the operator who wants to run it before a long sweep, or to
see how the hot tables are laid out without opening psql.
"""

from __future__ import annotations

from limen.core.logging import get_logger
from limen.data.db import acquire, lifespan_pool
from limen.data.repos import partitions_repo

log = get_logger(__name__)

_STATE_SQL = """
SELECT parent.relname AS table_name,
       count(*) FILTER (WHERE dated)                        AS daily,
       min(right(child.relname, 8)) FILTER (WHERE dated)    AS oldest,
       max(right(child.relname, 8)) FILTER (WHERE dated)    AS newest,
       pg_size_pretty(sum(pg_total_relation_size(child.oid))) AS total_size
FROM pg_inherits i
JOIN pg_class parent ON parent.oid = i.inhparent
JOIN pg_class child  ON child.oid = i.inhrelid
CROSS JOIN LATERAL (SELECT child.relname ~ '_[0-9]{8}$' AS dated) d
WHERE parent.relname = ANY($1::text[])
GROUP BY parent.relname
ORDER BY parent.relname
"""


async def run() -> int:
    async with lifespan_pool():
        created = await partitions_repo.ensure()
        await partitions_repo.warn_on_default_rows()
        async with acquire() as conn:
            rows = await conn.fetch(_STATE_SQL, list(partitions_repo.PARTITIONED_TABLES))
        for r in rows:
            default_rows = await partitions_repo.default_partition_rows(str(r["table_name"]))
            log.info(
                "cli.partitions.table",
                table=str(r["table_name"]),
                daily_partitions=int(r["daily"]),
                oldest=r["oldest"],
                newest=r["newest"],
                total_size=str(r["total_size"]),
                default_rows=default_rows,
                created_now=created.get(str(r["table_name"]), 0),
            )
    log.info("cli.partitions.done", created=created)
    return 0


def main() -> int:  # convenience for pyproject entry points
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
