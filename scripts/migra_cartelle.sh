#!/usr/bin/env bash
# Le cartelle dati di prima del 2026-11-25 nella disposizione di DATA_ROOT:
# ogni libreria che scarica scrive in $DATA_ROOT/<pacchetto>. Sposta una
# cartella solo se la vecchia c'è e la nuova no: rieseguirlo non fa niente.
#
#   make migra-cartelle        (lo lancia anche make static-data)
#
# Va lanciato con lo stack fermo o prima di `up -d`: il compose monta già le
# cartelle nuove, e una cartella nuova vuota creata da Docker bloccherebbe lo
# spostamento (lo dice e si ferma, senza toccare niente).
set -euo pipefail

RADICE="${RADICE:-${DATA_ROOT:-${LIMEN_DATA_ROOT:-$(pwd)/data}}}"

sposta() {  # sposta VECCHIA NUOVA
  local vecchia="$RADICE/$1" nuova="$RADICE/$2"
  [ -e "$vecchia" ] || return 0
  if [ -e "$nuova" ]; then
    if [ -d "$nuova" ] && [ -z "$(ls -A "$nuova")" ]; then
      rmdir "$nuova"
    else
      echo "  [migra] $vecchia e $nuova ci sono tutte e due: le unisci tu" >&2
      return 1
    fi
  fi
  mkdir -p "$(dirname "$nuova")"
  mv "$vecchia" "$nuova"
  echo "  [migra] $1 → $2"
}

unisci() {  # unisci VECCHIA NUOVA: file per file, senza sovrascrivere
  local vecchia="$RADICE/$1" nuova="$RADICE/$2" f
  [ -d "$vecchia" ] || return 0
  ( cd "$vecchia" && find . -type f ) | while IFS= read -r f; do
    [ -e "$nuova/$f" ] && continue
    mkdir -p "$(dirname "$nuova/$f")"
    mv "$vecchia/$f" "$nuova/$f"
  done
  find "$vecchia" -depth -type d -empty -delete
  if [ -e "$vecchia" ]; then
    echo "  [migra] $vecchia: restano file già presenti in $nuova, li togli tu" >&2
  else
    echo "  [migra] $1 → $2"
  fi
}

sposta egms egms-client
sposta radar/it_dpc_sri/italian-radar-dpc-sri.zarr dpc-radar/it_dpc_sri
sposta datasets/idrogeo ispra-idrogeo
sposta datasets/fires/firms firms-client
sposta datasets/landcover/worldcover firms-client/worldcover
# copernicus-ems: le immagini Sentinel-1 e i layer delle attivazioni finiscono
# nella stessa cartella (EMSR…/), quindi si uniscono file per file. Limen
# salvava i layer come <nome>.json; la libreria li legge come <nome>.geojson.
unisci datasets/copernicus-ems copernicus-ems
unisci flood_events copernicus-ems
if [ -d "$RADICE/copernicus-ems" ]; then
  find "$RADICE/copernicus-ems" -path '*/EMSR*' -name '*_PRODUCT_*.json' | while IFS= read -r f; do
    [ -e "${f%.json}.geojson" ] || mv "$f" "${f%.json}.geojson"
  done
fi
