#!/usr/bin/env bash
# Installa i timer di colibrì: acceso 20:50-02:05 UTC, spento il resto del
# giorno. colibri.service resta com'è ma non parte più al boot.
#   sudo infra/inference/systemd/installa.sh
set -euo pipefail
cd "$(dirname "$0")"
install -m 0644 colibri-accendi.timer colibri-spegni.timer colibri-spegni.service /etc/systemd/system/
systemctl daemon-reload
systemctl disable colibri.service
systemctl enable --now colibri-accendi.timer colibri-spegni.timer
# Fuori finestra si spegne subito; dentro la finestra resta acceso.
ora=$(date -u +%H%M)
if [ "$ora" -ge 0205 ] && [ "$ora" -lt 2050 ]; then
  systemctl stop colibri.service
fi
systemctl list-timers 'colibri-*' --no-pager
systemctl is-active colibri.service || true
