---
paths:
  - "src/limen/agents/llm_factory/**"
  - "src/limen/agents/chat_agents/**"
  - "src/limen/agents/grounding/**"
  - "src/limen/core/llm_resolver.py"
  - "src/limen/knowledge/**"
  - "src/limen/api/jobs/fedelta*"
  - "src/limen/api/jobs/briefing*"
  - "infra/inference/**"
  - "infra/docker/**"
---

# LLM, prompt, budget Claude, gateway, KG

Testo completo degli invarianti di cui `CLAUDE.md` tiene solo la riga breve:
la regola e il perché (misure, incidenti, issue). Vincolanti quanto la tabella.

| Topic | Rule |
|-------|------|
| LLM precedence | `LLM__PROVIDER` override > `ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > Foundry creds > **llama.cpp**. Resolver: `limen.agents.llm_factory.resolve_llm_factory`. A cloud key always wins over the local engine unless explicitly overridden. The fallback moved from Ollama to llama.cpp: deployments relying on the implicit Ollama fallback must now declare `LLM__PROVIDER=ollama`. |
| Prompts are per hazard, and no prompt means no prose | The Italian prompts are written for a specific danger — the briefing one opens with *"spiega il rischio frane"*, and the RiskAnalyst schema's `driver` enum lists only slope-failure causes. `has_narrative(hazard)` in `chat_agents/prompts_registry.py` gates both LLM nodes: a hazard without a prompt ships **without narrative**, because a landslide persona narrating a fire is worse than silence. Adding one is a file drop (`<agent>.<hazard>.it.md`) plus, for RiskAnalyst, extending the `driver` enum. Flood and wildfire have theirs since #155, and the agents now pick the prompt from `assessment.hazard_type` (before, they loaded the landslide one whatever the hazard). The async briefing re-narrates a region only when its dominant class changed or after `LLM__BRIEFING_MIN_HOURS` (24 — at 12, fourteen rewrites out of eighteen came from the timer, not from a class change): every hourly sweep is a new run, and with three hazards on a paid model that was up to 1,440 briefings a day. Both narrative roles run on `fast-cloud` (Claude Haiku 5.5, ~1–3 $/month); every response logs `llm.usage` with its tokens. |
| KG short timeout | `KG__TIMEOUT_SECONDS` (default 3s) is the per-call ceiling. `GroundingService.ground()` wraps it in a defensive `asyncio.wait_for`; an unhealthy sidecar can never extend the briefing's total wall time. |
| KG cache by (region, mechanism) | Same `(region, mechanism)` inside the TTL ⇒ same cached citations; different `top_k` requests reuse the cached set sliced client-side. Empty results are cached too, so an un-ingested sidecar doesn't generate repeat traffic. |
| The faithfulness reviewer is a Message Batch | `fedelta` (`api/jobs/fedelta_racconti.py`) is the one LLM call that bypasses the gateway: the whole evening sample goes to the Claude Message Batches API through the `anthropic` SDK (`agents` group, in the image), with `ANTHROPIC_API_KEY` and `LLM__MODELS__FEDELTA` a Claude id **other than** the briefing author (`fast-cloud` = Haiku 5.5, so the reviewer is Sonnet 5.5). The JSON is constrained by `output_config.format`; an unfinished batch is cancelled after `LLM__FEDELTA_ATTESA_MASSIMA_MINUTI` and every missing verdict is `null`, never «fedele». It replaced colibrì/GLM-5.2, removed after it OOM-killed the host on 28/10/2026: no local model that generates in tens of minutes is wired in anymore. |
| One monthly cap on Claude, checked on every call | `LLM__ANTHROPIC_BUDGET_MENSILE_USD` (10 $) covers **all** Claude spend — gateway roles on `fast-cloud`/`quality-cloud` and the batch reviewer. Every LLM call writes a `spesa_llm` row (migration 083) with the model that actually answered (`x-litellm-model-name`: a gateway fallback can make `fast-cloud` the local `chat`); before any call that can reach Claude, `agents/llm_factory/budget.py` sums the calendar month and raises `BudgetSuperatoError` at the cap, which callers treat like any model failure (deterministic text). Unreadable spend ⇒ the call does not run. LiteLLM's `max_budget` is **not** enforced (no database behind the gateway). Tokens are public (`/api/status/llm`, the Diagnostica page, «AI in pausa» in the header); dollars never are — `limen llm-spesa` and the logs only. |
| One inference endpoint | All LLM traffic goes to the LiteLLM gateway (`:8091`), never to llama-swap (`:8083`) directly (the only exception is the batch reviewer above) — routing, spend cap and local→cloud fallback all live in the gateway. `:8081` is GeoServer, not an LLM engine. From a container the host is `host.docker.internal`, never `127.0.0.1`. |
