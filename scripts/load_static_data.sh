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
set -uo pipefail

UV="${UV:-uv}"
FOCUS="${1:-tutti}"

# I comandi `limen` leggono `.env` da soli (pydantic-settings + python-dotenv),
# la shell no. Senza questo il preflight direbbe "manca" per variabili che il
# lavoro vero trova senza problemi — un modo perfetto per far cercare a
# qualcuno un dato che è già configurato.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  [ok]      %s\n' "$*"; }
skip() { printf '  [manca]   %s\n' "$*"; }

say "1/4  Cosa è configurato in questo ambiente"

have_geoserver=0; have_dem=0; have_imperv=0; have_corine=0
if [ -n "${GEOSERVER_SOURCE__DB_DSN:-}" ]; then
  # La variabile impostata non basta: se lo stack non è acceso il sync degrada
  # in silenzio e la mappa resta vuota. Meglio provarci qui, dove si può
  # ancora dire cosa fare, che scoprirlo in venti righe di warning.
  gs_host=$(printf '%s' "$GEOSERVER_SOURCE__DB_DSN" | sed -E 's#.*@([^:/]+).*#\1#')
  gs_port=$(printf '%s' "$GEOSERVER_SOURCE__DB_DSN" | sed -E 's#.*:([0-9]+)/.*#\1#')
  if timeout 3 bash -c "</dev/tcp/${gs_host}/${gs_port}" 2>/dev/null; then
    have_geoserver=1
    ok "GeoServer PostGIS raggiungibile su ${gs_host}:${gs_port}"
  else
    skip "GEOSERVER_SOURCE__DB_DSN impostata ma ${gs_host}:${gs_port} non risponde"
    echo "            → lo stack non è acceso. Avvialo con 'make geoserver-up' e,"
    echo "              la prima volta, 'make geoserver-init' per caricare gli"
    echo "              shapefile ISPRA in PostGIS."
  fi
else
  skip "GEOSERVER_SOURCE__DB_DSN non impostata"
  echo "            → senza, la suscettibilità idraulica resta vuota e la mappa"
  echo "              alluvione è uniforme. È lo stack mcp-geo-server: 'make geoserver-up'."
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

if [ "$FOCUS" = "flood" ] && [ "$have_geoserver" -eq 0 ]; then
  echo
  echo "  Nota: per l'alluvione il layer che conta è il mosaico idraulico."
  echo "  Senza GEOSERVER_SOURCE__DB_DSN questo comando non caricherà nulla di utile."
fi

say "2/4  Migrazioni"
$UV run limen migrate || exit 1

say "3/4  Sorgenti"
if [ "$have_geoserver" -eq 1 ]; then
  $UV run limen geoserver-sync || exit 1
else
  echo "  saltato: GEOSERVER_SOURCE__DB_DSN non impostata"
fi

say "4/4  Fattori per cella"
# bootstrap-static esegue da sé i passi la cui sorgente è configurata e
# registra `static_bootstrap.skip` per gli altri: una sola chiamata copre
# DTM, CORINE, imperviousness, WUI, distanze OSM e litologia.
$UV run limen bootstrap-static || exit 1

say "Risultato"
$UV run limen data-status
