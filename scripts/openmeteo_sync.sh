#!/usr/bin/env bash
# Sincronizza i modelli meteo nell'istanza Open-Meteo propria (#142).
#
#   ./scripts/openmeteo_sync.sh --check      # non scarica: dice cosa risponde
#   ./scripts/openmeteo_sync.sh              # scarica in anticipo la previsione
#   ./scripts/openmeteo_sync.sh --archive    # anche ERA5-Land, per fwi-backfill e backtest
#
# Il sync NON serve ad accendere il servizio: con REMOTE_DATA_DIRECTORY
# l'istanza legge dal bucket alla richiesta e tiene una cache locale, e a
# volume appena creato risponde gia' su tutte le variabili. Serve a togliere
# la latenza della prima lettura e a funzionare senza rete.
#
# Rieseguibile: `sync` scarica solo cio' che manca o e' piu' recente, quindi
# e' anche il cron giornaliero.
set -euo pipefail

VOLUME="${OPENMETEO_VOLUME:-limen-openmeteo-data}"
IMAGE="${OPENMETEO_IMAGE:-ghcr.io/open-meteo/open-meteo:latest}"
BASE="${OPENMETEO_BASE_URL:-http://127.0.0.1:8085}"
PAST_DAYS="${OPENMETEO_PAST_DAYS:-7}"
ARCHIVE_PAST_DAYS="${OPENMETEO_ARCHIVE_PAST_DAYS:-1825}"

# ECMWF IFS 0.25°: l'unico modello di previsione sul bucket che porta *tutte*
# le variabili che il codice chiede, comprese le due bande di umidità del
# suolo in stile ERA5 (`soil_moisture_0_to_7cm`, `_7_to_28cm`) che ICON non
# ha — ICON usa 0-1/1-3/3-9/9-27/27-81 cm, nomi diversi e strati diversi.
FORECAST_MODEL="${OPENMETEO_FORECAST_MODEL:-ecmwf_ifs025}"
FORECAST_VARS="${OPENMETEO_FORECAST_VARS:-precipitation,temperature_2m,relative_humidity_2m,wind_u_component_10m,wind_v_component_10m,snow_depth,snowfall_water_equivalent,soil_moisture_0_to_7cm,soil_moisture_7_to_28cm}"

# ICON-EU a 7 km: più fine di IFS 0.25° sulla pioggia, che è il segnale su cui
# girano le due griglie grosse. Facoltativo e additivo — sincronizzarlo non
# toglie niente a IFS, e `best_match` sceglie il migliore per variabile.
ICON_MODEL="${OPENMETEO_ICON_MODEL:-dwd_icon_eu}"
ICON_VARS="${OPENMETEO_ICON_VARS:-precipitation,temperature_2m,relative_humidity_2m,wind_u_component_10m,wind_v_component_10m,snow_depth}"

# ERA5-Land a 0.1°: l'archivio. Non serve allo sweep orario — serve a
# `limen fwi-backfill` e ai backtest. È il pezzo grosso su disco.
ARCHIVE_MODEL="${OPENMETEO_ARCHIVE_MODEL:-copernicus_era5_land}"
ARCHIVE_VARS="${OPENMETEO_ARCHIVE_VARS:-temperature_2m,dew_point_2m,soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,snow_depth}"

sync() {
  local model="$1" vars="$2" days="$3"
  echo "==> sync ${model} (${days} giorni indietro)"
  docker run --rm -v "${VOLUME}:/app/data" "${IMAGE}" \
    sync "${model}" "${vars}" --past-days "${days}"
}

check() {
  echo "==> verifica su ${BASE}"
  # Una richiesta con ogni variabile che il codice chiede davvero. Le colonne
  # che tornano tutte `null` sono quelle che il modello sincronizzato non ha:
  # è questo il controllo che dice se il sync è servito, non il healthcheck
  # del container, che risponde anche a volume vuoto.
  local vars="precipitation,soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,snowfall,snow_depth,temperature_2m,relative_humidity_2m,wind_speed_10m"
  curl -sS --get "${BASE}/v1/forecast" \
    --data-urlencode "latitude=41.1" \
    --data-urlencode "longitude=16.8" \
    --data-urlencode "hourly=${vars}" \
    --data-urlencode "forecast_days=1" \
    --data-urlencode "timezone=UTC" \
  | python3 -c '
import json, sys
payload = json.load(sys.stdin)
hourly = payload.get("hourly") or {}
if not hourly:
    print("nessun dato:", payload)
    raise SystemExit(1)
largo = max(len(k) for k in hourly)
for nome, valori in hourly.items():
    if nome == "time":
        continue
    noti = [v for v in valori if v is not None]
    stato = f"{len(noti)}/{len(valori)} ore" if noti else "VUOTA — il modello non ha questa variabile"
    print(f"  {nome:<{largo}}  {stato}")
'
}

case "${1:-}" in
  --check)
    check
    ;;
  --archive)
    sync "${FORECAST_MODEL}" "${FORECAST_VARS}" "${PAST_DAYS}"
    sync "${ICON_MODEL}" "${ICON_VARS}" "${PAST_DAYS}"
    sync "${ARCHIVE_MODEL}" "${ARCHIVE_VARS}" "${ARCHIVE_PAST_DAYS}"
    check
    ;;
  "")
    sync "${FORECAST_MODEL}" "${FORECAST_VARS}" "${PAST_DAYS}"
    sync "${ICON_MODEL}" "${ICON_VARS}" "${PAST_DAYS}"
    check
    ;;
  *)
    echo "uso: $0 [--archive|--check]" >&2
    exit 2
    ;;
esac
