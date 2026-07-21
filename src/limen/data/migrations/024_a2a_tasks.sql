-- A2A (Agent2Agent) task store.
--
-- Tasks are born from `message/send` | `message/stream` and fetched via
-- `tasks/get`. The full JSON-RPC Task object lives in `task` (jsonb); `state`
-- and `context_id` are lifted out for lookup / cancellation. `push_config`
-- holds the optional per-task push-notification webhook.
--
-- The A2A skills are read-only queries over the operational tables, so a task
-- is normally terminal within the same request — the store backs `tasks/get`,
-- `tasks/cancel` and push delivery rather than long-running async work.
CREATE TABLE IF NOT EXISTS a2a_tasks (
    id          text PRIMARY KEY,
    context_id  text NOT NULL,
    state       text NOT NULL,
    task        jsonb NOT NULL,
    push_config jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS a2a_tasks_context_idx ON a2a_tasks (context_id);
