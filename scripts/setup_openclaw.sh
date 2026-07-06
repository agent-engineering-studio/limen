#!/usr/bin/env bash
# Limen ⇄ OpenClaw hookup — idempotent, driven by env vars.
#
# Run this ON the machine where the OpenClaw gateway lives, after the
# Limen stack is up (`make up`). Re-runnable: every step overwrites the
# previous configuration. Full guide: docs/openclaw.md
#
# Variables (all optional — defaults assume same-host deployment):
#   LIMEN_MCP_URL         limen-ops MCP endpoint      (default http://127.0.0.1:8766/mcp)
#   OPENCLAW_GATEWAY_URL  OpenClaw gateway base URL   (default http://127.0.0.1:18789)
#   OPENCLAW_HOOK_TOKEN   hooks shared secret         (default: generated)
#   OPENCLAW_HOOK_MODE    wake | agent                (default wake)
#   MCP_SERVER_NAME       name inside OpenClaw        (default limen-ops)
set -euo pipefail

LIMEN_MCP_URL="${LIMEN_MCP_URL:-http://127.0.0.1:8766/mcp}"
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
say "fatto. Guida completa e troubleshooting: docs/openclaw.md"
