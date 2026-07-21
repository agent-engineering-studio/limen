"""A2A task store over the shared asyncpg pool (``a2a_tasks``, migration 024).

The full Task is kept as jsonb; ``state`` / ``context_id`` are lifted out for
lookup. asyncpg returns jsonb as text (no json codec is registered globally),
so rows round-trip through pydantic's ``model_validate_json``.
"""

from __future__ import annotations

from limen.a2a.models import PushNotificationConfig, Task
from limen.data.db import acquire


class A2ATaskStore:
    async def save(self, task: Task) -> None:
        async with acquire() as conn:
            await conn.execute(
                """
                INSERT INTO a2a_tasks (id, context_id, state, task, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, now())
                ON CONFLICT (id) DO UPDATE
                    SET state = EXCLUDED.state,
                        task = EXCLUDED.task,
                        updated_at = now()
                """,
                task.id,
                task.context_id,
                task.status.state,
                task.model_dump_json(by_alias=True),
            )

    async def get(self, task_id: str) -> Task | None:
        async with acquire() as conn:
            row = await conn.fetchrow("SELECT task FROM a2a_tasks WHERE id = $1", task_id)
        if row is None:
            return None
        return Task.model_validate_json(row["task"])

    async def set_push_config(self, task_id: str, cfg: PushNotificationConfig) -> bool:
        async with acquire() as conn:
            result = await conn.execute(
                "UPDATE a2a_tasks SET push_config = $2::jsonb, updated_at = now() WHERE id = $1",
                task_id,
                cfg.model_dump_json(by_alias=True),
            )
        return not str(result).endswith(" 0")

    async def get_push_config(self, task_id: str) -> PushNotificationConfig | None:
        async with acquire() as conn:
            row = await conn.fetchrow("SELECT push_config FROM a2a_tasks WHERE id = $1", task_id)
        if row is None or row["push_config"] is None:
            return None
        return PushNotificationConfig.model_validate_json(row["push_config"])
