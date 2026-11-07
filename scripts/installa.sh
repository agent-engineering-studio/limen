#!/usr/bin/env bash
# Limen su una macchina nuova, con un solo comando (#405, epic #409): dal clone
# al link nel browser. I dati si scaricano dalla pagina che si apre alla fine.
#
#   ./scripts/installa.sh [--dominio limen.example.org]
#
# Serve solo Docker (e GNU make >= 4.3, che su macOS è `brew install make`).
# Rieseguibile: un .env esistente non si sovrascrive, si completano solo le
# chiavi che mancano. Il ripristino da backup resta `nuovo_host.sh --ripristina`.
set -euo pipefail

cd "$(dirname "$0")/.."

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok() { printf '  [ok]    %s\n' "$*"; }
nota() { printf '  [nota]  %s\n' "$*"; }
stop() { printf '  [NO]    %s\n' "$*" >&2; exit 1; }

DOMINIO=""
case "${1:-}" in
  "") ;;
  --dominio) DOMINIO="${2:?--dominio vuole il nome}" ;;
  *) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2 ;;
esac

# --- Prerequisiti ------------------------------------------------------------
say "prerequisiti"
command -v docker >/dev/null || stop "manca Docker: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || stop "Docker non risponde: avvialo, o aggiungi l'utente al gruppo docker"
docker compose version >/dev/null 2>&1 || stop "manca il plugin compose v2 (docker compose)"
command -v openssl >/dev/null || stop "manca openssl"
ok "Docker e compose"

# Il make di macOS (3.81, del 2006) non legge il Makefile.
make_recente() {
  command -v make >/dev/null || return 1
  local v
  v="$(make --version | sed -n 's/^GNU Make \([0-9]*\)\.\([0-9]*\).*/\1 \2/p')"
  [ -n "$v" ] || return 1
  # shellcheck disable=SC2086 # sono due numeri da dividere
  set -- $v
  [ "$1" -gt 4 ] || { [ "$1" -eq 4 ] && [ "$2" -ge 3 ]; }
}
if ! make_recente; then
  for d in /opt/homebrew/opt/make/libexec/gnubin /usr/local/opt/make/libexec/gnubin; do
    [ -x "$d/make" ] && PATH="$d:$PATH"
  done
fi
make_recente || stop "serve GNU make >= 4.3 (macOS: brew install make; Linux: il pacchetto make)"
ok "$(make --version | head -n 1)"

memoria_gb=$(($(docker info --format '{{.MemTotal}}') / 1024 / 1024 / 1024))
if [ "$memoria_gb" -lt 8 ]; then
  nota "Docker ha ${memoria_gb} GB di memoria: sotto gli 8 il caricamento dei dati può fallire."
fi
if [ "$(uname -s)" = Darwin ]; then
  nota "macOS: disattiva in Docker Desktop «Automatically check for updates»: un aggiornamento"
  nota "a metà caricamento riavvia tutto, e può azzerare i volumi."
  if pmset -g 2>/dev/null | grep -Eq '^ *sleep +[1-9]'; then
    nota "macOS: la sospensione è attiva e ferma i container: sudo pmset -a sleep 0"
  fi
fi

# --- .env --------------------------------------------------------------------
say "configurazione (.env)"
if [ ! -f .env ]; then
  # Conterrà dei segreti: nasce leggibile solo da chi installa.
  (umask 077 && cp .env.example .env)
  ok ".env creato da .env.example"
fi

scrivi() {  # scrivi NOME valore
  local nome="$1" valore="$2"
  if grep -q "^$nome=" .env; then
    # `cat >` e non `mv`, per tenere i permessi del file (come in nuovo_host.sh).
    (umask 077 && awk -v n="$nome" -v v="$valore" \
      'index($0, n "=") == 1 { print n "=" v; next } { print }' .env >.env.nuovo)
    cat .env.nuovo >.env
    rm -f .env.nuovo
  else
    printf '%s=%s\n' "$nome" "$valore" >>.env
  fi
  ok "$nome=$valore"
}
# Una chiave con un valore non si tocca; una vuota o assente prende il default.
imposta() {  # imposta NOME valore
  grep -qs "^$1=..*" .env || scrivi "$1" "$2"
}
# Una chiave assente non è un errore: con pipefail il grep a vuoto fermerebbe lo script.
valore() { { grep -s "^$1=" .env || true; } | tail -n 1 | cut -d= -f2-; }

imposta LIMEN_DATA_ROOT "$HOME/limen-data"

if [ -z "$DOMINIO" ] && [ -z "$(valore LIMEN_DOMINIO)" ] && [ -t 0 ]; then
  printf '  Dominio pubblico del server (Invio per usarlo solo da questa macchina): '
  read -r DOMINIO || DOMINIO=""
fi
# Il dominio chiesto con --dominio vince su quello del .env: è una scelta esplicita.
if [ -n "$DOMINIO" ] && [ "$DOMINIO" != "$(valore LIMEN_DOMINIO)" ]; then
  scrivi LIMEN_DOMINIO "$DOMINIO"
  scrivi LIMEN_PROXY_BIND 0.0.0.0
fi
imposta LIMEN_DOMINIO localhost
# «Solo da questa macchina» deve esserlo: il default del compose è 0.0.0.0.
if [ "$(valore LIMEN_DOMINIO)" = localhost ]; then
  imposta LIMEN_PROXY_BIND 127.0.0.1
else
  imposta LIMEN_PROXY_BIND 0.0.0.0
fi

# Le credenziali Sentinel-1 (`limen ems-sentinel1`, opzionali) sono un segreto
# del compose: un file che non c'è ferma api e worker all'avvio. /dev/null, come
# la chiave CLMS, finché qualcuno non ne ha bisogno.
if [ ! -f secrets/cdse.json ]; then
  imposta LIMEN_CDSE_SECRET_FILE /dev/null
fi

# Le immagini seguono il commit di questo clone, anche con un tag già nel .env:
# compose e codice devono essere della stessa versione, e tornare indietro è un
# `git checkout`. CI le pubblica solo da main e solo per amd64: altrimenti si
# costruiscono qui, o si resta sul tag che c'è, dicendolo.
prefisso=ghcr.io/agent-engineering-studio/limen-
tag="sha-$(git rev-parse --short=7 HEAD)"
attuale="$(valore LIMEN_IMAGE_TAG)"
if [ "$attuale" = "$tag" ]; then
  ok "immagini $tag"
elif [ "$(uname -m)" = x86_64 ] && docker manifest inspect "${prefisso}api:$tag" >/dev/null 2>&1; then
  imposta LIMEN_IMAGE_PREFIX "$prefisso"
  scrivi LIMEN_IMAGE_TAG "$tag"
elif [ -n "$attuale" ]; then
  nota "nessuna immagine pubblicata per $tag: resto su $attuale, più vecchia di questo codice."
else
  nota "nessuna immagine pubblicata per $tag ($(uname -m)): le costruisco qui (qualche minuto)."
fi

# Open-Meteo locale: l'API pubblica ha un tetto che lo sweep supera in un tick,
# e senza meteo incendio e alluvione restano «non misurati» (#142).
imposta OPENMETEO__FORECAST_URL http://openmeteo:8080/v1/forecast
imposta OPENMETEO__ARCHIVE_URL http://openmeteo:8080/v1/archive
imposta OPENMETEO__MODELS ecmwf_ifs025

# Backup notturno: senza un bucket non se ne fa nessuno. Se non ce n'è uno
# esterno, un MinIO locale (make backup-up): protegge da errori e da un
# database rotto, non da un guasto del disco. I segreti non si stampano.
genera() {  # genera NOME
  grep -qs "^$1=..*" .env || { scrivi "$1" "$(openssl rand -hex 24)" >/dev/null && ok "$1 generata"; }
}
if [ -z "$(valore BACKUP__BUCKET)" ] || [ "$(valore BACKUP__ENDPOINT_URL)" = http://minio:9000 ]; then
  imposta BACKUP__BUCKET limen-backup
  imposta BACKUP__ENDPOINT_URL http://minio:9000
  imposta BACKUP__ACCESS_KEY_ID limen-backup
  genera BACKUP__SECRET_ACCESS_KEY
  imposta LIMEN_MINIO_ROOT_USER limen-admin
  genera LIMEN_MINIO_ROOT_PASSWORD
  imposta LIMEN_BACKUP_DIR "$HOME/limen-backup"
  case "$(valore LIMEN_BACKUP_DIR)" in
    /*) mkdir -p "$(valore LIMEN_BACKUP_DIR)" ;;
    *) stop "LIMEN_BACKUP_DIR nel .env deve essere un percorso assoluto" ;;
  esac
fi

if [ -n "$(valore GEOSERVER_SOURCE__DB_DSN)" ] && [ "$(valore LIMEN_GEOSERVER)" != 1 ]; then
  nota "GEOSERVER_SOURCE__DB_DSN nel .env vale per i comandi dall'host: senza GeoServer, toglila."
fi

# Prima di avviare o scaricare qualsiasi cosa. Una chiave vuota nel .env vince
# sul default del compose e arriva ai container così: meglio dirlo adesso che
# trovarla ore dopo. Solo i nomi: i valori di un .env non si stampano. Le due
# chiavi escluse le genera nuovo_host.sh.
say "controllo del .env"
vuote="$(awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=[[:space:]]*$/ &&
  $1 != "DB__TILES_PASSWORD" && $1 != "INSTALLAZIONE__TOKEN" { print "          " $1 }' .env)"
if [ -n "$vuote" ]; then
  printf '%s\n' "$vuote" >&2
  stop "queste variabili del .env sono vuote: dai loro un valore o togli la riga, poi rilancia"
fi
case "$(valore LIMEN_DATA_ROOT)" in
  /*) ;;
  *) stop "LIMEN_DATA_ROOT nel .env deve essere un percorso assoluto" ;;
esac
ok "tutte le variabili hanno un valore"

# --- Stack -------------------------------------------------------------------
# Segreti, cartelle, permessi, avvio, seed e link: li fa già nuovo_host.sh.
exec ./scripts/nuovo_host.sh --solo-stack
