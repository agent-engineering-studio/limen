#!/usr/bin/env bash
# Limen su un server nuovo (#306, epic #308). Rieseguibile: ogni passo controlla
# cosa c'è già e salta il lavoro fatto.
#
#   ./scripts/nuovo_host.sh --controlla    solo i prerequisiti, non tocca niente
#   ./scripts/nuovo_host.sh --ripristina   dal backup notturno (#304): stato, poi lo stack
#   ./scripts/nuovo_host.sh --da-zero      stack nuovo: seed, eventi, calibrazione, FWI
#
# Prima: Docker, il repository, e un .env (cp .env.example .env, poi almeno
# LIMEN_DATA_ROOT; per --ripristina anche le BACKUP__*). I comandi `limen`
# girano nel container del worker: sull'host serve solo Docker.
#
# Variabili:
#   NUOVO_HOST_DISCO_GB      spazio libero minimo sotto LIMEN_DATA_ROOT (50)
#   NUOVO_HOST_FSYNC_MS_MAX  latenza massima di una scrittura sincrona (20)
set -euo pipefail

cd "$(dirname "$0")/.."
DISCO_GB="${NUOVO_HOST_DISCO_GB:-50}"
FSYNC_MS_MAX="${NUOVO_HOST_FSYNC_MS_MAX:-20}"
MODO="${1:-}"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok() { printf '  [ok]    %s\n' "$*"; }
no() { printf '  [NO]    %s\n' "$*" >&2; }
stop() { no "$*"; exit 1; }

case "$MODO" in
  --controlla | --ripristina | --da-zero) ;;
  *) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2 ;;
esac

# --- 1. Prerequisiti ----------------------------------------------------------
say "prerequisiti"
command -v docker >/dev/null || stop "manca Docker"
docker info >/dev/null 2>&1 || stop "Docker non risponde (servizio fermo, o utente fuori dal gruppo docker)"
ok "Docker $(docker version --format '{{.Server.Version}}')"
docker compose version >/dev/null 2>&1 || stop "manca il plugin compose v2 (docker compose)"
ok "Compose $(docker compose version --short)"

[ -f .env ] || stop "manca .env: cp .env.example .env, poi almeno LIMEN_DATA_ROOT"
# Le variabili che servono qui si chiedono a compose, già risolte come lui le
# risolverà per i bind mount: virgolette, riferimenti (${HOME}/limen,
# ${LIMEN_DATA_ROOT}/datasets) e precedenza dell'ambiente sul file. Un lettore
# a mano sbagliava un caso dopo l'altro (Codex, #314), e con `. ./.env` la
# shell rovinava i valori JSON. Niente si esporta: compose e `limen` il .env
# lo leggono da soli.
AMBIENTE="$(docker compose --env-file .env -f infra/docker/docker-compose.demo.yml config --environment)" ||
  stop "compose non riesce a leggere il .env: docker compose --env-file .env -f infra/docker/docker-compose.demo.yml config"
dotenv() {  # dotenv NOME: il valore che compose userà
  printf '%s' "$AMBIENTE" | grep -E "^$1=" | tail -n 1 | cut -d= -f2-
}
for nome in LIMEN_DATA_ROOT LIMEN_DATASETS_DIR LIMEN_REPORTS_HOST_DIR LIMEN_MLRUNS_DIR \
  LIMEN_SENSORI_DIR BACKUP__BUCKET BACKUP__ROOT SCHEDULER__NIGHTLY_HOUR_UTC POSTGIS_BASE; do
  printf -v "$nome" '%s' "$(dotenv "$nome")"
done
RADICE="${LIMEN_DATA_ROOT:-$(pwd)/data}"
case "$RADICE" in
  /*) ok "LIMEN_DATA_ROOT=$RADICE" ;;
  *) stop "LIMEN_DATA_ROOT deve essere assoluta (compose e Makefile la risolvono da cartelle diverse)" ;;
esac
if grep -qs '^DB__TILES_PASSWORD=[0-9a-f]\{32,\}$' .env; then
  ok "DB__TILES_PASSWORD presente"
elif [ "$MODO" = "--controlla" ]; then
  no "manca DB__TILES_PASSWORD: le altre modalità la generano"
else
  # La riga vuota di .env.example si sostituisce, non si duplica: compose
  # legge il file, e una riga vuota nell'ambiente vincerebbe (Codex, #314).
  [ -z "${DB__TILES_PASSWORD:-}" ] || stop "DB__TILES_PASSWORD nell'ambiente non è valida: toglila (unset) e rilancia"
  DB__TILES_PASSWORD="$(openssl rand -hex 24)"
  if grep -q '^DB__TILES_PASSWORD=' .env; then
    sed -i "s/^DB__TILES_PASSWORD=.*/DB__TILES_PASSWORD=$DB__TILES_PASSWORD/" .env
  else
    printf '\n# Generata da nuovo_host.sh (#269): la password del ruolo di pg_tileserv.\nDB__TILES_PASSWORD=%s\n' \
      "$DB__TILES_PASSWORD" >>.env
  fi
  ok "DB__TILES_PASSWORD generata nel .env"
fi

# Lo spazio dove andranno i dati: la radice, o la cartella più vicina che esiste.
dove="$RADICE"
while [ ! -d "$dove" ]; do dove="$(dirname "$dove")"; done
liberi_gb=$(($(df -Pk "$dove" | awk 'NR==2 {print $4}') / 1024 / 1024))
[ "$liberi_gb" -ge "$DISCO_GB" ] || stop "solo ${liberi_gb} GB liberi in $dove (minimo ${DISCO_GB}: NUOVO_HOST_DISCO_GB)"
ok "${liberi_gb} GB liberi in $dove"

# La latenza delle scritture sincrone dove Docker tiene i volumi, cioè dove
# starà Postgres. Su questo progetto un disco a ~1 s per fsync ha fatto
# andare in timeout l'initdb e ogni test d'integrazione (sdb, 2026-10-15):
# meglio fermarsi qui che scoprirlo con il database a metà.
say "latenza di fsync del disco dei volumi Docker"
docker volume create limen-prova-fsync >/dev/null
trap 'docker volume rm -f limen-prova-fsync >/dev/null 2>&1 || true' EXIT
# pg_test_fsync, dall'immagine che lo stack usa comunque: fdatasync è il
# metodo di default di PostgreSQL su Linux.
# La stessa immagine che sceglie il Makefile: postgis/postgis non ha la
# variante arm64 (Codex, #314).
if [ -z "${POSTGIS_BASE:-}" ]; then
  case "$(uname -m)" in
    arm64 | aarch64) POSTGIS_BASE=imresamu/postgis:16-3.5 ;;
    *) POSTGIS_BASE=postgis/postgis:16-3.5 ;;
  esac
fi
us=$(docker run --rm -v limen-prova-fsync:/p "$POSTGIS_BASE" \
  pg_test_fsync -f /p/t -s 1 2>/dev/null | awk '$1 == "fdatasync" && !v {v = $(NF-1)} END {print v}')
docker volume rm -f limen-prova-fsync >/dev/null
trap - EXIT
[ -n "$us" ] || stop "pg_test_fsync non ha risposto: non so quanto è lento il disco"
ms="$((us / 1000)).$(printf '%03d' $((us % 1000)))"
[ "$us" -le $((FSYNC_MS_MAX * 1000)) ] || stop "${ms} ms per scrittura sincrona (massimo ${FSYNC_MS_MAX}: NUOVO_HOST_FSYNC_MS_MAX). Postgres su questo disco andrà in timeout."
ok "${ms} ms per scrittura sincrona"

if [ "$MODO" = "--controlla" ]; then
  say "prerequisiti a posto: nessuna modifica fatta"
  exit 0
fi

# --- 2. Struttura sotto la radice (#302) --------------------------------------
say "cartelle sotto $RADICE"
for d in datasets reports mlruns models geoserver osm sealing radar; do
  mkdir -p "$RADICE/$d"
done
ok "datasets reports mlruns models geoserver osm sealing radar"
make --no-print-directory gs-volumes
ok "volumi esterni di GeoServer"

# API e worker girano come l'utente `limen` dell'immagine, non come chi lancia
# lo script: le cartelle che scrivono (cataloghi, report, artefatti MLflow)
# devono essere sue, o ingest, calibrazione e ripristino falliscono su
# "Permission denied" (Codex, #314). L'uid si chiede all'immagine; il chown
# lo fa un container, così sull'host non serve sudo.
say "proprietario delle cartelle scritte dai container"
make --no-print-directory immagine
uid=$(docker run --rm --entrypoint id limen/api:0.1 -u)
gid=$(docker run --rm --entrypoint id limen/api:0.1 -g)
scritte=(
  "${LIMEN_DATASETS_DIR:-$RADICE/datasets}"
  "${LIMEN_REPORTS_HOST_DIR:-$RADICE/reports}"
  "${LIMEN_MLRUNS_DIR:-$RADICE/mlruns}"
)
for d in "${scritte[@]}"; do
  mkdir -p "$d"
  docker run --rm -v "$d:/d" alpine chown -R "$uid:$gid" /d
done
ok "limen ($uid:$gid): ${scritte[*]}"

# --- 3. Stato ------------------------------------------------------------------
if [ "$MODO" = "--ripristina" ]; then
  # Prima solo il database, vuoto; poi lo stato; poi il resto dello stack, che
  # applica le migrazioni più nuove del backup e dà le password ai ruoli.
  say "ripristino dal backup (#304)"
  [ -n "${BACKUP__BUCKET:-}${BACKUP__ROOT:-}" ] || stop "manca BACKUP__BUCKET nel .env"
  if [ -n "${LIMEN_SENSORI_DIR:-}" ]; then
    # Prima del worker del ripristino, che monta sensori/client: se manca,
    # Docker la crea come root, e poi né ripristina-ca né sensori-ca-init ci
    # possono scrivere (Codex, #314). `ripristina-ca` accetta una ca/ vuota.
    mkdir -p "$LIMEN_SENSORI_DIR"/{ca,broker,client,data}
    ok "cartelle dei sensori in $LIMEN_SENSORI_DIR, dell'operatore"
  fi
  make --no-print-directory db-up
  make --no-print-directory restore CONFERMA=1
  ok "stato ripristinato"
  if [ -n "${LIMEN_SENSORI_DIR:-}" ] && [ ! -s "$LIMEN_SENSORI_DIR/ca/ca.key" ]; then
    say "CA dei sensori (#304)"
    if command -v uv >/dev/null; then
      uv run limen sensore ripristina-ca --dove "$LIMEN_SENSORI_DIR"
      make --no-print-directory sensori-ca-init
      ok "CA ripristinata, credenziali di broker e ingestore rifatte"
    else
      no "per la CA serve la CLI sull'host (la chiave non entra nei container): uv run limen sensore ripristina-ca --dove \"$LIMEN_SENSORI_DIR\", poi make sensori-ca-init"
    fi
  fi
fi

# Lo stack è obbligatorio: se non parte, lo script si ferma (Codex, #314).
# I dati statici no: senza i fattori per cella restano quelli del backup o
# vuoti, che è un degrado. Senza uv sull'host girano nel container del worker.
say "stack (make up-stack)"
make --no-print-directory up-stack || stop "lo stack non è partito: guarda sopra"
ok "API pronta, seed fatto"
say "dati statici (make static-data)"
make --no-print-directory static-data || no "dati statici incompleti: guarda sopra, poi make static-data"

limen() { docker exec limen-worker limen "$@"; }

if [ "$MODO" = "--da-zero" ]; then
  say "eventi, calibrazione e catena FWI (nel worker)"
  limen ingest-events || no "ingest-events: riprova più tardi, è idempotente"
  limen calibrate || no "calibrate: riprova dopo i dati statici"
  # La catena FWI parte da ERA5: un mese di spin-up prima che l'incendio
  # abbia numeri stabili. Con un backup c'è già (fwi_state).
  limen fwi-backfill || no "fwi-backfill: riprova più tardi, è idempotente"
fi

# --- 4. Verifica --------------------------------------------------------------
say "verifica"
esito=0
limen data-status || { no "limen data-status non ha risposto"; esito=1; }
limen jobs || { no "limen jobs non ha risposto"; esito=1; }
[ "$esito" = 0 ] || stop "verifica non riuscita: lo stack non risponde come dovrebbe"
cat <<FINE

Fatto. Cosa si riempie da sé, e quando:
  - la mappa: il primo sweep orario scrive latest_risk entro l'ora;
  - la previsione per cella: alle 02, 08, 14, 20 :20 UTC;
  - il backup notturno: alle ${SCHEDULER__NIGHTLY_HOUR_UTC:-2}:00 UTC, se BACKUP__BUCKET è impostato;
  - i riferimenti GloFAS: una quota di nodi ogni notte, settimane per tutti.
Il reverse proxy e i certificati: README, «Installing on a new server».
FINE
