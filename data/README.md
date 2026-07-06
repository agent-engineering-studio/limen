# `data/` — dataset statici nazionali (layout theme-first)

> Questa cartella contiene **solo i drop statici nazionali** (gitignorata,
> ~25 GB nel riempimento italiano). I feed dinamici — meteo Open-Meteo,
> incendi EFFIS, sismica FDSN, radar DPC — arrivano via API e non
> risiedono qui. Il riempimento italiano, completo, è il **template di
> riferimento** per usare Limen in un'altra nazione: un clone = una
> nazione, si riempiono gli slot con i dataset locali disponibili e gli
> slot vuoti degradano (il bootstrap logga `static_bootstrap.skip`).

## Principi

1. **Theme-first, country-agnostic**: struttura per ruolo nello scoring
   (`dem/`, `hazard/`, `inventory/`, …), mai per paese.
2. **Il nome del dataset sta nello slug interno** (`dem/hrdtm5m/`),
   mai nella struttura: la Francia avrà `dem/rge_alti_5m/` senza
   cambiare nulla a monte.
3. **Ogni slot è un contratto**: formato atteso, componente alimentata,
   env var che lo attiva, comportamento se assente.
4. **Zero modifiche al codice**: tutti i path passano da env var; la
   nazionalizzazione tocca solo filesystem + `.env`.

## Layout

```
data/
├── README.md                      ← questo file (unico tracciato in git)
├── boundaries/istat_2023/         # confini amministrativi → seed AOI + griglia
├── dem/hrdtm5m/HRDTM5m.tif        # DEM → slope/aspect/curvature/TWI (S)
├── hazard/
│   ├── landslide/pai_frane_2020_2021/    # pericolosità frana (S)
│   └── hydraulic/pai_idraulica_2020/     # pericolosità idraulica (H)
├── inventory/iffi/{regione}/{frane_poly,frane_line,frane_piff,aree_poly,dgpv_poly}/
├── events/italica/ITALICA_v4.csv  # catalogo eventi datati → backtest + ML
├── landcover/                     # slot pronto (CORINE quando prodotto)
├── geology/                       # slot pronto (carta geolitologica)
└── backups/                       # dump training ML (make dump-training)
```

## Contratto degli slot

| Slot | Obbligatorio | Alimenta | Formato | Attivazione | Se assente |
|---|---|---|---|---|---|
| `boundaries/` | **sì** | seed AOI + griglia 1 km | shapefile/GeoJSON poligonale, CRS dichiarato | rigenerazione seed GeoJSON | niente seed nazione |
| `hazard/landslide/` | consigliato | S | poligoni con classe ordinale | GeoServer (`GEOSERVER_SOURCE__DB_DSN`) | S su inventory+DEM |
| `inventory/` | consigliato | S (densità frane) | poligoni/linee/punti | GeoServer | S su hazard+DEM |
| `dem/` | opzionale | S (derivate morfometriche) | GeoTIFF **tiled** | `LIMEN_DEM_RASTER` | derivate NULL |
| `hazard/hydraulic/` | opzionale | H | poligoni con classi | manifest `geodata/datasets.yaml` | H neutra |
| `events/` | per backtest/ML | truth set §2.5 + feature store | CSV con data+lat/lon | `LIMEN_ITALICA_CSV` | niente backtest/training |
| `landcover/` | opzionale | S/K | GeoTIFF Int16 codici classe | `LIMEN_CORINE_RASTER` | skip |
| `geology/` | opzionale | S (litho_weight) | shapefile con campo litologia | `LIMEN_GEOLOGICAL_SHAPEFILE` + `_FIELD` | skip |

Le geometrie vengono riproiettate a EPSG:4326 in ingestione; i calcoli
metrici avvengono in EPSG:3035. Il CRS sorgente è libero purché
dichiarato (`.prj` / header GeoTIFF).

## Come produrre i dati per ogni slot

### `boundaries/` — confini amministrativi

Poligoni dei livelli amministrativi usati come AOI, con nome + codice
ufficiale. **Italia**: ISTAT "Confini delle unità amministrative"
edizione generalizzata (CC-BY-3.0, EPSG:32632) —
https://www.istat.it/it/archivio/222527. **Altrove**: IGN ADMIN EXPRESS
(FR), oppure GADM / geoBoundaries (CC-BY 4.0) / OSM come fallback
universali. Rigenerare poi il GeoJSON di seed con le unità scelte.

### `dem/` — modello digitale di elevazione

Un **singolo GeoTIFF internamente tiled** (blocchi 256×256, DEFLATE):
le letture a finestra toccano solo i blocchi sotto ogni cella, quindi
la dimensione non conta (l'HR-DTM italiano è 21 GB e funziona
direttamente). CRS proiettato metrico preferibile; risoluzione 5–30 m
ideale, 25–90 m comunque utile. **Italia**: HR-DTM 5 m (EPSG:6875) o
TINITALY 10 m (INGV, CC-BY 4.0). **Altrove**: RGE ALTI 5 m (FR),
Copernicus EU-DEM 25 m / GLO-30 (globali). Ricetta:

```bash
gdalbuildvrt dem.vrt tiles/*.tif
gdal_translate -of GTiff -co TILED=YES -co BLOCKXSIZE=256 -co BLOCKYSIZE=256 \
  -co COMPRESS=DEFLATE -co BIGTIFF=YES dem.vrt data/dem/<slug>/dem.tif
```

Attivazione: `LIMEN_DEM_RASTER=./data/dem/<slug>/dem.tif`.

### `hazard/landslide/` e `hazard/hydraulic/` — perimetri di pericolosità

Poligoni con classe di pericolosità **ordinale** (es. AA/P1..P4): per
cella si aggrega la classe massima intersecata. **Italia**: mosaicature
nazionali ISPRA PAI frana e idraulica (idrogeo.isprambiente.it,
CC-BY 4.0). **Altrove**: i PPR francesi (Géorisques), o qualsiasi
zonazione suscettibilità/pericolosità nazionale; in mancanza, lo slot
resta vuoto e S si regge su inventario + DEM. L'ingestione passa dal
PostGIS di GeoServer (`limen geoserver-sync`) o dal manifest
`geodata/datasets.yaml` (idraulica).

### `inventory/` — inventario frane storiche

Geometrie delle frane note (poligoni/linee/punti), senza data
obbligatoria: alimenta la densità storica per cella (`iffi_density_500`,
`distance_to_iffi_m`). **Italia**: inventario IFFI completo
(5 famiglie × 20 regioni + Bolzano/Trento, CC-BY). **Altrove**:
BDMvT (FR), o il catalogo nazionale disponibile; fallback globale
COOLR/NASA (scarso ma esistente).

### `events/` — catalogo eventi datati

CSV con **data di accadimento + lat/lon** per evento: è la verità del
backtest §2.5 e la sorgente dei label del training ML. **Italia**:
e-ITALICA (CNR-IRPI, CC-BY 4.0, Zenodo DOI 10.5281/zenodo.14204473),
auto-scaricato da `limen ingest-events`. **Altrove**: qualsiasi
catalogo eventi datati; formato adattabile nel loader. Senza questo
slot il motore deterministico funziona, ma niente backtest né ML.

### `landcover/` — copertura del suolo

GeoTIFF Int16 con codici classe (rasterizzare il vettoriale a ~100 m).
**Italia**: CORINE CLC2018 Italia (SINAnet/ISPRA, CC-BY). **Altrove**:
CORINE europeo, ESA WorldCover 10 m (globale, CC-BY 4.0).
Attivazione: `LIMEN_CORINE_RASTER`.

### `geology/` — litologia

Shapefile poligonale con un campo litologico testuale; i pesi litologici
si configurano in `regional_thresholds.yaml`. **Italia**: Carta
Geolitologica 1:500k (PCN/MASE, CC-BY) — attenzione all'ordine assi
lat/lon del WFS 1.1 (`SwapCoords`). **Altrove**: BRGM 1:50k (FR),
OneGeology come indice globale. Attivazione:
`LIMEN_GEOLOGICAL_SHAPEFILE` + `LIMEN_GEOLOGICAL_FIELD`.
