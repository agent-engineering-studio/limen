#!/usr/bin/env bash
# Aggiunge `fast-cloud` (Claude Haiku 5.5) al gateway LiteLLM di sistema e lo
# riavvia. Da lanciare con sudo. Rilanciabile: se il modello c'e' gia' non
# tocca niente. Usa la stessa chiave Anthropic di quality-cloud
# (/etc/litellm/env).
set -euo pipefail

CONF=/etc/litellm/config.yaml

if grep -q "model_name: fast-cloud" "$CONF"; then
  echo "fast-cloud e' gia' nel gateway."
else
  cp "$CONF" "$CONF.bak.$(date +%Y%m%d%H%M%S)"
  # Subito dopo quality-cloud, prima di router_settings.
  python3 - "$CONF" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
ancora = "      model: anthropic/claude-sonnet-5-5\n"
assert ancora in s, "quality-cloud non trovato: aggiungi fast-cloud a mano"
blocco = (
    "\n  # Claude Haiku 5.5: racconti delle regioni e analisi di Limen.\n"
    "  - model_name: fast-cloud\n"
    "    litellm_params:\n"
    "      model: anthropic/claude-haiku-5-5\n"
)
s = s.replace(ancora, ancora + blocco, 1)
open(p, "w").write(s)
PY
  echo "fast-cloud aggiunto a $CONF"
fi

systemctl restart litellm
for i in $(seq 1 30); do
  curl -sf -o /dev/null http://127.0.0.1:8091/health/liveliness && break
  sleep 2
done
curl -s http://127.0.0.1:8091/v1/models | grep -o '"id":"fast-cloud"' \
  || echo "Attenzione: fast-cloud non compare nel catalogo del gateway."
