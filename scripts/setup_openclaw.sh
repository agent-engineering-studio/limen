#!/usr/bin/env bash
# Limen ⇄ OpenClaw hookup — idempotent, driven by env vars.
#
# Run this ON the machine where the OpenClaw gateway lives, after the
# Limen stack is up (`make up`). Re-runnable: every step overwrites the
# previous configuration. Full guide: docs/openclaw.md
#
# Variables (all optional — defaults assume same-host deployment):
#   LIMEN_MCP_URL         limen-ops MCP endpoint      (default http://127.0.0.1:8766/mcp)
#   LIMEN_GEODATA_MCP_URL ispra-geo MCP endpoint      (default http://127.0.0.1:8765/mcp)
#   LIMEN_A2A_URL         A2A base URL of the API     (default http://127.0.0.1:8080)
#   OPENCLAW_GATEWAY_URL  OpenClaw gateway base URL   (default http://127.0.0.1:18789)
#   OPENCLAW_HOOK_TOKEN   hooks shared secret         (default: generated)
#   OPENCLAW_HOOK_MODE    wake | agent                (default wake)
#   MCP_SERVER_NAME       name inside OpenClaw        (default limen-ops)
set -euo pipefail

LIMEN_MCP_URL="${LIMEN_MCP_URL:-http://127.0.0.1:8766/mcp}"
LIMEN_GEODATA_MCP_URL="${LIMEN_GEODATA_MCP_URL:-http://127.0.0.1:8765/mcp}"
LIMEN_A2A_URL="${LIMEN_A2A_URL:-http://127.0.0.1:8080}"
OPENCLAW_GATEWAY_URL="${OPENCLAW_GATEWAY_URL:-http://127.0.0.1:18789}"
OPENCLAW_HOOK_MODE="${OPENCLAW_HOOK_MODE:-wake}"
MCP_SERVER_NAME="${MCP_SERVER_NAME:-limen-ops}"

if [ -z "${OPENCLAW_HOOK_TOKEN:-}" ]; then
  OPENCLAW_HOOK_TOKEN="$(openssl rand -hex 24)"
  GENERATED_TOKEN=1
else
  GENERATED_TOKEN=0
fi

say()  { printf '\033[1;34m[openclaw-setup]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[openclaw-setup] ERRORE:\033[0m %s\n' "$*" >&2; exit 1; }

command -v openclaw >/dev/null 2>&1 || fail "CLI 'openclaw' non trovata nel PATH. Installa OpenClaw prima (https://docs.openclaw.ai)."

# --- 1. Register the limen-ops MCP server (pull: agent queries Limen) ---
say "registro l'MCP '${MCP_SERVER_NAME}' → ${LIMEN_MCP_URL}"
openclaw mcp set "${MCP_SERVER_NAME}" \
  "{\"url\":\"${LIMEN_MCP_URL}\",\"transport\":\"streamable-http\"}"
openclaw mcp status "${MCP_SERVER_NAME}" || say "ATTENZIONE: probe MCP fallita — verifica che il servizio compose 'mcp' di Limen sia su (docker ps | grep limen-mcp)"

# --- 1b. Register the ispra-geo MCP server (geodata profile, VPS-only) ---
# Best-effort: the `geodata` compose profile is optional and often absent on
# the operational host. A failed probe is a warning, not a fatal error.
say "registro l'MCP 'ispra-geo' → ${LIMEN_GEODATA_MCP_URL} (opzionale — profilo geodata)"
if openclaw mcp set "ispra-geo" \
     "{\"url\":\"${LIMEN_GEODATA_MCP_URL}\",\"transport\":\"streamable-http\"}"; then
  openclaw mcp status "ispra-geo" || say "nota: 'ispra-geo' non risponde — attivo solo con 'docker compose --profile geodata up'. Registrazione conservata."
fi

# --- 2. Enable the hooks endpoint (push: Limen alerts wake the agent) ---
say "abilito gli hooks del gateway (hooks.enabled/token/path)"
if openclaw config set hooks.enabled true 2>/dev/null \
   && openclaw config set hooks.token "${OPENCLAW_HOOK_TOKEN}" 2>/dev/null \
   && openclaw config set hooks.path "/hooks" 2>/dev/null; then
  say "hooks configurati via CLI — riavvia il gateway per applicare"
else
  say "la CLI non espone 'config set' in questa versione: aggiungi a mano nel config del gateway:"
  cat <<JSON5
  {
    hooks: {
      enabled: true,
      token: "${OPENCLAW_HOOK_TOKEN}",
      path: "/hooks",
    },
  }
JSON5
fi

# --- 3. Verify the hook endpoint (after gateway restart) ---
HOOK_URL="${OPENCLAW_GATEWAY_URL}/hooks/${OPENCLAW_HOOK_MODE}"
say "verifica hook: POST ${HOOK_URL}"
if curl -sf -X POST "${HOOK_URL}" \
     -H "Authorization: Bearer ${OPENCLAW_HOOK_TOKEN}" \
     -H 'Content-Type: application/json' \
     -d '{"text":"Limen setup test","message":"Limen setup test"}' >/dev/null; then
  say "hook OK — l'agente ha ricevuto l'evento di test"
else
  say "hook non ancora raggiungibile (gateway da riavviare?). Riprova: "
  say "  curl -X POST ${HOOK_URL} -H 'Authorization: Bearer <token>' -d '{\"text\":\"test\"}'"
fi

# --- 4. Print the Limen side of the config ---
say "aggiungi (o verifica) queste righe nel .env di Limen, poi 'make up':"
cat <<ENV

NOTIFICATIONS__ENABLED_CHANNELS=["webhook"]
NOTIFICATIONS__WEBHOOK__URL=${HOOK_URL}
NOTIFICATIONS__WEBHOOK__TOKEN=${OPENCLAW_HOOK_TOKEN}
ENV
if [ "${GENERATED_TOKEN}" -eq 1 ]; then
  say "(token generato ora — conservalo: non verrà rimostrato)"
fi

# --- 5. Report on-demand + A2A interop (informational) ---
say "report statici on-demand: con MCP_ADMIN_TOKEN impostato lato Limen l'agente"
say "  può chiamare i tool 'tool_build_report' e 'tool_forecast_history' via MCP."
say "  La generazione ricorrente è già gestita da APScheduler (JOB_DAILY_REPORT /"
say "  JOB_HTML_REPORT / JOB_FORECAST_HISTORY) — nessun cron lato OpenClaw serve."
say "interoperabilità A2A (Agent2Agent) per altri agent:"
say "  agent card:  ${LIMEN_A2A_URL}/.well-known/agent-card.json"
say "  endpoint:    ${LIMEN_A2A_URL}/a2a  (JSON-RPC 2.0: message/send, message/stream, tasks/*)"
if command -v curl >/dev/null 2>&1; then
  curl -sf "${LIMEN_A2A_URL}/.well-known/agent-card.json" >/dev/null 2>&1 \
    && say "  ✓ agent card raggiungibile" \
    || say "  (agent card non ancora raggiungibile — avvia l'API: 'make up' / 'limen serve')"
fi
say "fatto. Guida completa e troubleshooting: docs/openclaw.md"
