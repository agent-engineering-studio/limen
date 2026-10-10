#!/usr/bin/env bash
# Scrive in .env la password della casella che manda la posta di Limen e
# verifica l'accesso al server SMTP, senza spedire niente. La password si
# digita qui, nascosta: non passa da chat, log o storia della shell.
set -euo pipefail
umask 077

cd "$(dirname "$0")/../.."
ENV=.env
[ -f "$ENV" ] || { echo "Manca $ENV nella radice del repository." >&2; exit 1; }

valore() { grep -oP "^$1=\K.*" "$ENV" | tail -1; }
HOST=$(valore NOTIFICATIONS__EMAIL__SMTP_HOST)
PORTA=$(valore NOTIFICATIONS__EMAIL__SMTP_PORT)
UTENTE=$(valore NOTIFICATIONS__EMAIL__USERNAME)
[ -n "$HOST" ] && [ -n "$UTENTE" ] || {
  echo "Imposta prima NOTIFICATIONS__EMAIL__SMTP_HOST e __USERNAME in $ENV." >&2; exit 1; }

read -rsp "Password di $UTENTE: " PW; echo
[ -n "$PW" ] || { echo "Password vuota: niente da fare." >&2; exit 1; }

LIMEN_PW="$PW" python3 - "$HOST" "${PORTA:-465}" "$UTENTE" <<'PY'
import os, smtplib, ssl, sys
host, porta, utente = sys.argv[1], int(sys.argv[2]), sys.argv[3]
ctx = ssl.create_default_context()
try:
    if porta == 465:
        s = smtplib.SMTP_SSL(host, porta, timeout=20, context=ctx)
    else:
        s = smtplib.SMTP(host, porta, timeout=20); s.starttls(context=ctx)
    s.login(utente, os.environ["LIMEN_PW"]); s.quit()
except Exception as e:
    sys.exit(f"Accesso a {host}:{porta} non riuscito: {type(e).__name__}: {e}")
print(f"Accesso a {host}:{porta} come {utente}: ok")
PY

# Sostituisce la riga se c'è, altrimenti la aggiunge. Il valore va fra apici
# singoli perché docker compose non interpreti `$` o `#` della password; un
# apice singolo dentro non ha modo di essere protetto, quindi si rifiuta.
case "$PW" in *"'"*)
  echo "La password contiene un apice singolo, che il file .env di compose non sa proteggere: cambiala." >&2
  exit 1 ;;
esac
grep -v '^NOTIFICATIONS__EMAIL__PASSWORD=' "$ENV" > "$ENV.tmp"
printf "NOTIFICATIONS__EMAIL__PASSWORD='%s'\n" "$PW" >> "$ENV.tmp"
mv "$ENV.tmp" "$ENV"
chmod 600 "$ENV"
echo "Password salvata in $ENV. Ora serve il riavvio dell'API."
