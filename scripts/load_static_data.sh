#!/usr/bin/env bash
# Carica i layer statici per cella, e dice chiaramente cosa non può caricare.
#
# Ogni sorgente sta dietro una variabile d'ambiente e ha un'origine diversa.
# Tre di esse richiedono una registrazione presso l'ente che le pubblica: lo
# script non può scaricarle al posto tuo, ma non deve nemmeno fallire in
# silenzio — quindi le elenca, esegue tutto il resto, e chiude con il quadro
# di cosa è entrato davvero.
#
# Uso:  make static-data          tutti i layer configurati
#       make flood-data           come sopra, con il focus sull'alluvione
#
# I comandi `limen` girano sull'host con uv se c'è, altrimenti in un container
# usa e getta dell'immagine del worker (#306: sull'host basta Docker).
# LIMEN_STATICI=host|docker sceglie a mano; `qui` è il worker che lo lancia dopo
# i download della pagina di installazione (#405), dentro il suo container.
# LIMEN_STATICI_SCARICA=0 salta i passi che vanno in rete: lì i file li ha già
# scaricati la coda, e solo quelli chiesti da chi installa.
set -uo pipefail
# Il worker scarica nelle stesse cartelle (setgid, #402): i file nuovi
# restano scrivibili dal gruppo, così ognuno riprende i `.part` dell'altro.
umask 002

UV="${UV:-uv}"
SCARICA="${LIMEN_STATICI_SCARICA:-1}"
FOCUS="${1:-tutti}"

# I comandi `limen` leggono `.env` da soli (pydantic-settings + python-dotenv),
# la shell no. Senza questo il preflight direbbe "manca" per variabili che il
# lavoro vero trova senza problemi — un modo perfetto per far cercare a
# qualcuno un dato che è già configurato.
# La chiave EGMS passata dalla shell va ricordata prima di leggere il .env:
# quella del .env il container la riceve già dal compose, intatta, mentre
# quella della shell andrebbe persa con l'ambiente pulito del container
# (Codex, #367).
egms_chiave_shell="${EGMS__SERVICE_KEY:-}"
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Una sola radice per i dati (#302): una sorgente non impostata si cerca lì,
# al nome che le producono `make dtm-vrt`, `make osm-data` e
# `make imperviousness-data`. Una variabile impostata vince sempre.
RADICE="${LIMEN_DATA_ROOT:-$(pwd)/data}"
# I dati di GeoServer stanno dove li monta il compose.
GEOSERVER_DATI="${GEOSERVER_SHAPEFILE_DIR:-$RADICE/geoserver}"
predefinito() {  # predefinito VARIABILE percorso
  if [ -z "${!1:-}" ] && [ -e "$2" ]; then
    export "$1=$2"
  fi
}
predefinito LIMEN_DEM_RASTER "$GEOSERVER_DATI/dtm/dtm5m.vrt"
predefinito LIMEN_DEM_RASTER "$GEOSERVER_DATI/dtm/HRDTM5m_v1.3.tif"
predefinito LIMEN_CORINE_RASTER "$GEOSERVER_DATI/clc2018_it/clc2018_it_100m.tif"
predefinito LIMEN_GEOLOGICAL_SHAPEFILE "$GEOSERVER_DATI/carta_geolitologica/carta_geolitologica.shp"
predefinito LIMEN_OSM_ROADS "$RADICE/osm/osm_roads.gpkg"
predefinito LIMEN_OSM_RAILWAYS "$RADICE/osm/osm_rails.gpkg"
predefinito LIMEN_IMPERVIOUSNESS_RASTER "$RADICE/sealing/clms_imd_2018/imd_2018_100m.tif"
# Le tile EGMS si tengono sotto la radice e non in /tmp (il default di
# EgmsSettings): con il container usa e getta qui sotto ogni `make up`
# riscaricherebbe ~7 GB. Con le tile già lì, un sync ripetuto non va in rete
# e non scrive niente (dataset_versions).
export EGMS__CARTELLA="${EGMS__CARTELLA:-$RADICE/egms}"
# I dati di base ISPRA (IFFI, mosaici PAI e idraulico) li scarica
# `limen geodati-sync` proprio dove `geoserver-init` li carica: la stessa
# GEOSERVER_SHAPEFILE_DIR, assoluta perché diventa anche un mount di Docker.
have_geodati=0
# Una cartella che non si crea non deve diventare un mount vuoto «-v :», che
# romperebbe ogni comando limen nel container, migrate compreso.
if mkdir -p "$GEOSERVER_DATI" && assoluta="$(cd "$GEOSERVER_DATI" && pwd)"; then
  have_geodati=1
  GEOSERVER_DATI="$assoluta"
  export GEOSERVER_SHAPEFILE_DIR="$GEOSERVER_DATI"
else
  echo "  [manca]   $GEOSERVER_DATI non si crea: dati di base ISPRA saltati" >&2
fi
have_egms=0
if [ -n "${EGMS__SERVICE_KEY:-}" ] || [ -n "${EGMS__SERVICE_KEY_FILE:-}" ]; then
  have_egms=1
fi

# Nel container le sorgenti si montano **allo stesso percorso**, in sola
# lettura: così le variabili del .env valgono dentro come fuori, e non serve
# una seconda serie di percorsi «visti dal container». Solo i percorsi: il DSN
# di GeoServer il worker ce l'ha già, nella rete di Docker.
MODO="${LIMEN_STATICI:-}"
if [ -z "$MODO" ]; then
  if command -v "$UV" >/dev/null 2>&1; then MODO=host; else MODO=docker; fi
fi
if [ "$MODO" = docker ]; then
  : "${LIMEN_COMPOSE:?lancialo da make (make static-data): serve LIMEN_COMPOSE}"
  CONTAINER=()
  # Una stringa e non `declare -A`: il bash di macOS è il 3.2, senza array
  # associativi, e lo script si fermava prima di definire `limen`.
  MONTATE=$'\n'
  for v in LIMEN_DEM_RASTER LIMEN_CORINE_RASTER LIMEN_GEOLOGICAL_SHAPEFILE \
    LIMEN_OSM_ROADS LIMEN_OSM_RAILWAYS LIMEN_IMPERVIOUSNESS_RASTER; do
    [ -n "${!v:-}" ] && [ -e "${!v}" ] || continue
    assoluto="$(cd "$(dirname "${!v}")" && pwd)/$(basename "${!v}")"
    cartella="$(dirname "$assoluto")"
    case "$MONTATE" in
      *$'\n'"$cartella"$'\n'*) ;;
      *)
        CONTAINER+=(-v "$cartella:$cartella:ro")
        MONTATE+="$cartella"$'\n'
        ;;
    esac
    CONTAINER+=(-e "$v=$assoluto")
  done
  # Le manopole dei comandi passano anche loro (Codex, #329): con l'ambiente
  # pulito un LIMEN_BOOTSTRAP_FORCE=1 o un LIMEN_EFFIS_GIORNI chiesti
  # dall'operatore sparirebbero in silenzio. Sono scalari, non JSON.
  for v in LIMEN_BOOTSTRAP_FORCE LIMEN_EFFIS_GIORNI LIMEN_VETTORI_FORZA; do
    [ -n "${!v:-}" ] && CONTAINER+=(-e "$v=${!v}")
  done
  # La cartella delle tile EGMS è l'unica in scrittura: il sync ci salva i
  # GeoTIFF, e deve ritrovarli al prossimo giro.
  if [ "$have_egms" -eq 1 ]; then
    mkdir -p "$EGMS__CARTELLA"
    CONTAINER+=(-v "$EGMS__CARTELLA:$EGMS__CARTELLA" -e "EGMS__CARTELLA=$EGMS__CARTELLA")
    # Il file della chiave, se è così che la si dà, montato in sola lettura.
    if [ -n "${EGMS__SERVICE_KEY_FILE:-}" ]; then
      CONTAINER+=(-v "$EGMS__SERVICE_KEY_FILE:$EGMS__SERVICE_KEY_FILE:ro" -e "EGMS__SERVICE_KEY_FILE=$EGMS__SERVICE_KEY_FILE")
    fi
    [ -n "$egms_chiave_shell" ] && CONTAINER+=(-e "EGMS__SERVICE_KEY=$egms_chiave_shell")
  fi
  # La cartella di GeoServer va in scrittura: ci scrive geodati-sync.
  if [ "$have_geodati" -eq 1 ]; then
    CONTAINER+=(-v "$GEOSERVER_DATI:$GEOSERVER_DATI" -e "GEOSERVER_SHAPEFILE_DIR=$GEOSERVER_DATI")
  fi
  # Con il proprio uid: le sorgenti sono di chi le ha scaricate, e l'utente
  # dell'immagine (999) non le leggerebbe. E con un ambiente pulito: il .env
  # caricato qui sopra come shell ha perso le virgolette dei valori JSON, e
  # compose preferisce l'ambiente al --env-file — il worker partirebbe con
  # impostazioni rotte.
  limen() {
    # shellcheck disable=SC2086 # LIMEN_COMPOSE sono opzioni da dividere
    env -i PATH="$PATH" HOME="$HOME" ${DOCKER_HOST:+DOCKER_HOST="$DOCKER_HOST"} \
      docker compose $LIMEN_COMPOSE run --rm --no-deps -T --user "$(id -u):$(id -g)" \
      ${CONTAINER[@]+"${CONTAINER[@]}"} worker limen "$@"
  }
elif [ "$MODO" = qui ]; then
  limen() { command limen "$@"; }
else
  limen() { $UV run limen "$@"; }
fi

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  [ok]      %s\n' "$*"; }
skip() { printf '  [manca]   %s\n' "$*"; }

say "1/7  Cosa è configurato in questo ambiente (comandi: $MODO)"

have_geoserver=0; have_dem=0; have_imperv=0; have_corine=0
gs_risponde() { timeout 3 bash -c "</dev/tcp/${gs_host:?}/${gs_port:?}" 2>/dev/null; }
# La sorgente che i comandi `limen` leggeranno davvero: nel container non è
# GEOSERVER_SOURCE__DB_DSN del .env (che è per l'host, `localhost:55433`) ma
# API_GEOSERVER_SOURCE_DSN del compose. Decidere con l'altra faceva saltare
# carica-vettori mentre geoserver-sync leggeva uno schema vuoto (#426).
if [ "$MODO" = docker ]; then
  DSN_VETTORI="${API_GEOSERVER_SOURCE_DSN:-}"
  if [ -n "${GEOSERVER_SOURCE__DB_DSN:-}" ] && [ -z "$DSN_VETTORI" ]; then
    skip "GEOSERVER_SOURCE__DB_DSN vale solo per l'host: nei container i vettori si leggono"
    echo "            dal database di Limen. Per GeoServer: API_GEOSERVER_SOURCE_DSN nel .env."
  fi
else
  DSN_VETTORI="${GEOSERVER_SOURCE__DB_DSN:-}"
fi
if [ -n "$DSN_VETTORI" ]; then
  # Vettori da un PostGIS esterno (quello di GeoServer): la variabile non
  # basta, se lo stack non è acceso il sync degrada in silenzio e la mappa
  # resta vuota. Meglio provarci qui, dove si può ancora dire cosa fare.
  gs_host=$(printf '%s' "$DSN_VETTORI" | sed -E 's#.*@([^:/]+).*#\1#')
  gs_port=$(printf '%s' "$DSN_VETTORI" | sed -E 's#.*:([0-9]+)/.*#\1#')
  if [ "$MODO" = docker ]; then
    # Un nome della rete di compose (geoserver-postgis): dall'host non si
    # risolve, e la prova direbbe «spento» anche a stack acceso.
    have_geoserver=1
    ok "vettori ISPRA dal PostGIS esterno ${gs_host}:${gs_port} (rete dei container)"
  elif gs_risponde; then
    have_geoserver=1
    ok "vettori ISPRA dal PostGIS esterno ${gs_host}:${gs_port}"
  else
    skip "la sorgente dei vettori ${gs_host}:${gs_port} non risponde"
    echo "            → toglila per leggere i vettori dal database di Limen (#426),"
    echo "              oppure accendi GeoServer: il passo 4/7 lo avvia con geoserver-init."
  fi
else
  # Il caso normale (#426): `carica-vettori` li porta nel database di Limen.
  have_geoserver=1
  ok "vettori ISPRA nel database di Limen (schema sorgenti, limen carica-vettori)"
fi

if [ -n "${LIMEN_DEM_RASTER:-}" ] && [ -e "${LIMEN_DEM_RASTER}" ]; then
  have_dem=1
  ok "DTM — pendenza per cella (serve a frane e incendio)"
elif [ -n "${LIMEN_DEM_RASTER:-}" ]; then
  skip "LIMEN_DEM_RASTER punta a ${LIMEN_DEM_RASTER}, che non esiste"
  echo "            → se hai le tessere, 'make dtm-vrt' costruisce il mosaico virtuale."
else
  skip "LIMEN_DEM_RASTER non impostata"
  echo "            → TINITALY (INGV) richiede registrazione: scarica le tessere,"
  echo "              poi 'make dtm-vrt' e punta LIMEN_DEM_RASTER al .vrt prodotto."
fi

if [ -n "${LIMEN_IMPERVIOUSNESS_RASTER:-}" ] && [ -e "${LIMEN_IMPERVIOUSNESS_RASTER}" ]; then
  have_imperv=1
  ok "CLMS Imperviousness — amplificazione del ramo pluviale"
else
  skip "LIMEN_IMPERVIOUSNESS_RASTER non impostata o file assente"
  echo "            → 'make imperviousness-data' lo scarica: l'EEA serve lo stesso"
  echo "              prodotto CLMS senza account. Poi punta la variabile al file."
fi

if [ -n "${LIMEN_CORINE_RASTER:-}" ] && [ -e "${LIMEN_CORINE_RASTER}" ]; then
  have_corine=1
  ok "CORINE Land Cover — combustibile per l'incendio, flag di esposizione"
else
  skip "LIMEN_CORINE_RASTER non impostata o file assente"
fi

if [ "$have_egms" -eq 1 ]; then
  ok "EGMS — velocità del terreno (tile in $EGMS__CARTELLA)"
else
  skip "né EGMS__SERVICE_KEY né EGMS__SERVICE_KEY_FILE"
  echo "            → chiave di servizio CLMS: land.copernicus.eu, EU Login, profilo"
  echo "              → «API Tokens». Senza, le feature InSAR del modello ML restano vuote."
fi

if [ "$FOCUS" = "flood" ] && [ "$have_geoserver" -eq 0 ]; then
  echo
  echo "  Nota: per l'alluvione il layer che conta è il mosaico idraulico,"
  echo "  e il PostGIS da cui leggerlo non risponde (passo 1/7)."
fi

say "2/7  Migrazioni"
limen migrate || exit 1

say "3/7  Dati geografici di base (IdroGEO, ISTAT, CORINE, geolitologia, DTM)"
# In GEOSERVER_SHAPEFILE_DIR: l'inventario frane IFFI di tutte le regioni e i
# mosaici PAI e idraulico (IdroGEO), i confini ISTAT, CORINE 2018 con il suo
# raster per cella, la carta geolitologica e, se LIMEN_DEM_RASTER non punta
# già a un file, il DTM a 5 m (34 GB, Zenodo). La prima volta ~37 GB; poi un
# file IdroGEO si richiede solo dopo GEODATI__RIVALIDA_DOPO_GIORNI (30), e gli
# altri, che non cambiano, mai più. Prima erano shapefile copiati a
# mano: un server nuovo non sapeva ricostruirli. Solo con GeoServer
# configurato (lo stack può essere ancora spento: i file aspettano lì), perché
# senza nessuno li caricherebbe.
geodati_fatto=0
if [ "$have_geodati" -eq 1 ]; then
  geodati_fatto=1
  if [ "$SCARICA" = 1 ]; then
    limen geodati-sync || echo "  (qualche file non è arrivato: il prossimo giro lo riprova)"
  fi
  # Su un server nuovo DTM, raster CORINE e geolitologia nascono adesso: i
  # fattori per cella (7/7) devono vederli già a questo giro. La cartella è
  # già montata nel container, basta la variabile.
  for coppia in \
    "LIMEN_DEM_RASTER:$GEOSERVER_DATI/dtm/HRDTM5m_v1.3.tif" \
    "LIMEN_CORINE_RASTER:$GEOSERVER_DATI/clc2018_it/clc2018_it_100m.tif" \
    "LIMEN_GEOLOGICAL_SHAPEFILE:$GEOSERVER_DATI/carta_geolitologica/carta_geolitologica.shp"; do
    v="${coppia%%:*}"; percorso="${coppia#*:}"
    if [ -z "${!v:-}" ] && [ -e "$percorso" ]; then
      export "$v=$percorso"
      if [ "$MODO" = docker ]; then CONTAINER+=(-e "$v=$percorso"); fi
    fi
  done
else
  echo "  saltato: la cartella dei dati di base non si crea (vedi sopra)"
fi

say "4/7  Sorgenti"
if [ "$geodati_fatto" -eq 1 ] && [ -z "$DSN_VETTORI" ]; then
  # Gli shapefile nel database di Limen (#426): quelli che geoserver-sync,
  # seed-comuni e il lookup dei comuni leggono. Salta quelli non cambiati.
  limen carica-vettori || echo "  (qualche shapefile non è entrato: il prossimo giro lo riprova)"
fi
if [ "$geodati_fatto" -eq 1 ] && [ "${LIMEN_GEOSERVER:-}" = 1 ]; then
  # GeoServer solo a richiesta, per i WMS di PAI e IFFI (o come sorgente con
  # GEOSERVER_SOURCE__DB_DSN). geoserver-init carica nel suo PostGIS i layer
  # che non ci sono ancora; `compose run` avvia da sé PostGIS e GeoServer, che
  # poi restano accesi. Per aggiornare un layer dopo un geodati-sync:
  # GEO_INIT_FORCE=true make geoserver-init.
  if [ -n "${LIMEN_COMPOSE:-}" ]; then
    # shellcheck disable=SC2086 # LIMEN_COMPOSE sono opzioni da dividere
    env -i PATH="$PATH" HOME="$HOME" ${DOCKER_HOST:+DOCKER_HOST="$DOCKER_HOST"} \
      GEO_INIT_UID="${GEO_INIT_UID:-$(id -u)}" GEO_INIT_GID="${GEO_INIT_GID:-$(id -g)}" \
      GEOSERVER_SHAPEFILE_DIR="$GEOSERVER_DATI" \
      docker compose $LIMEN_COMPOSE --profile geoserver run --rm geoserver-init \
      || echo "  (geoserver-init non riuscito: 'make geoserver-init' a mano)"
  fi
  if [ "$have_geoserver" -eq 0 ] && gs_risponde; then
    have_geoserver=1
    ok "GeoServer PostGIS acceso da geoserver-init"
  fi
fi
if [ "$have_geoserver" -eq 1 ]; then
  limen geoserver-sync || exit 1
else
  echo "  saltato: ${gs_host}:${gs_port} non risponde (vedi il passo 1/7)"
fi

say "5/7  Perimetri EFFIS e storico FIRMS (verità e storia degli incendi)"
# Comando a se' e non un passo del bootstrap: e' un dataset di verita', non un
# fattore per cella, e il bootstrap per cella non fa chiamate HTTP. Sta pero'
# in questa sequenza, che e' cio' che la #101 chiedeva.
if [ "$SCARICA" = 1 ]; then
  limen effis-sync || echo "  (EFFIS non raggiungibile: si prosegue)"
  # Lo storico FIRMS (#472): ~35 MB di CSV per l'Italia, nessuna credenziale.
  # Riscrive fire_events e fire_density; un archivio non cambiato salta le
  # scritture (impronta in dataset_versions).
  limen ingest-fire-history || echo "  (archivio FIRMS non completato: si prosegue)"
fi

say "6/7  Velocità del terreno EGMS (feature InSAR del modello ML)"
# La prima volta sono ~7 GB e circa un'ora; poi, con le tile già nella
# cartella, è un controllo senza rete. Una release nuova (il passo notturno
# `egms_release` la segnala) entra cambiando EGMS__RELEASE e rilanciando questo.
if [ "$SCARICA" != 1 ]; then
  echo "  saltato: niente download a questo giro"
elif [ "$have_egms" -eq 1 ]; then
  mkdir -p "$EGMS__CARTELLA"
  limen sync-egms || echo "  (EGMS non completato: si prosegue, il prossimo giro riprende dalle tile già scaricate)"
else
  echo "  saltato: né EGMS__SERVICE_KEY né EGMS__SERVICE_KEY_FILE"
fi

say "7/7  Fattori per cella"
# bootstrap-static esegue da sé i passi la cui sorgente è configurata e
# registra `static_bootstrap.skip` per gli altri: una sola chiamata copre
# DTM, CORINE, imperviousness, WUI, distanze OSM e litologia.
limen bootstrap-static || exit 1

say "Risultato"
limen data-status
