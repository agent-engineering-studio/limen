# `data/` — dataset statici nazionali (layout theme-first)

> Questa cartella contiene **i drop statici nazionali** (gitignorata,
> ~25 GB nel riempimento italiano) e **lo storico radar per il backtest**
> (`radar/`, ~51 GB). I feed dinamici — meteo Open-Meteo, incendi EFFIS,
> sismica FDSN, radar DPC degli ultimi mesi — arrivano via API e non
> risiedono qui. Cosa c'è davvero su questo server, e dove, è in fondo:
> [Inventario del server](#inventario-del-server). Il riempimento italiano, completo, è il **template di
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
├── sealing/clms_imd_2018/         # suolo sigillato → ramo pluviale (make imperviousness-data)
├── geology/                       # slot pronto (carta geolitologica)
├── osm/                           # rete strade/ferrovie OSM (make osm-data)
├── radar/it_dpc_sri/              # radar DPC 2010-2025, Zarr (make radar-data) → backtest
├── radar/dpc_merging/             # radar+pluviometri DPC da giugno 2026 (limen radar-archivio)
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
| `sealing/` | opzionale | ramo pluviale (alluvione) | GeoTIFF uint8, % sigillato 0-100 | `LIMEN_IMPERVIOUSNESS_RASTER` | nessuna amplificazione urbana |
| `geology/` | opzionale | S (litho_weight) | shapefile con campo litologia | `LIMEN_GEOLOGICAL_SHAPEFILE` + `_FIELD` | skip |
| `osm/` | opzionale | esposizione alert (priorità) | GPKG linee (estratti PBF) | `LIMEN_OSM_ROADS` + `LIMEN_OSM_RAILWAYS` | fallback flag CORINE 12x |
| `radar/` | per backtest | pioggia misurata nel backtest frane | Zarr v2, un chunk per istante | `LIMEN_BACKTEST_PIOGGIA=radar` (+ `LIMEN_BACKTEST_RADAR_ZARR`) | backtest sulla rianalisi Open-Meteo |

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

### `sealing/` — suolo sigillato (impermeabilizzazione)

GeoTIFF **uint8** con la percentuale di superficie sigillata per pixel
(0-100); qualunque valore fuori intervallo è "non so" e viene scartato,
mai letto come 0 — zero affermerebbe suolo permeabile dove il dato
manca. Amplifica il **solo** ramo pluviale dell'alluvione: il cemento
non fa crescere un fiume, fa scorrere la stessa pioggia invece di
lasciarla infiltrare.

**Italia** (e tutta l'area EEA): `make imperviousness-data` scarica
l'HRL Imperviousness Density 2018 di Copernicus Land dall'ImageServer
pubblico dell'EEA — **senza account**, a differenza di quanto suggerisce
la pagina del prodotto. Copre il riquadro delle AOI seminate a 100 m in
EPSG:3035; l'Italia intera sta in ~4,6 MB. **Altrove**: GHSL BUILT-S
(JRC, globale, superficie costruita in m² per pixel — va riscalata a
0-100), oppure la classe "built-up" di ESA WorldCover come frazione.

Attivazione: `LIMEN_IMPERVIOUSNESS_RASTER=./data/sealing/<slug>/<file>.tif`.

### `geology/` — litologia

Shapefile poligonale con un campo litologico testuale; i pesi litologici
si configurano in `regional_thresholds.yaml`. **Italia**: Carta
Geolitologica 1:500k (PCN/MASE, CC-BY) — attenzione all'ordine assi
lat/lon del WFS 1.1 (`SwapCoords`). **Altrove**: BRGM 1:50k (FR),
OneGeology come indice globale. Attivazione:
`LIMEN_GEOLOGICAL_SHAPEFILE` + `LIMEN_GEOLOGICAL_FIELD`.

### `osm/` — rete strade/ferrovie (esposizione alert)

Linee della viabilità principale (`highway=motorway|trunk|primary|
secondary`) e ferrovie (`railway=rail`): alimentano
`distance_to_road_m` / `distance_to_rail_m` per cella e il fattore di
esposizione graduato nella priorità degli alert. © OpenStreetMap
contributors (ODbL, attribuzione nel footer UI). **Italia**: estratto
Geofabrik `europe/italy` — `make osm-data` scarica il PBF ed estrae i
due GPKG (idempotente, serve GDAL host). **Altrove**: identico con
l'estratto Geofabrik della nazione (`OSM_PBF_URL=...`). Ricetta manuale:

```bash
curl -L -o data/osm/italy-latest.osm.pbf \
  https://download.geofabrik.de/europe/italy-latest.osm.pbf
ogr2ogr -f GPKG data/osm/osm_roads.gpkg data/osm/italy-latest.osm.pbf lines \
  -where "highway IN ('motorway','trunk','primary','secondary')"
ogr2ogr -f GPKG data/osm/osm_rails.gpkg data/osm/italy-latest.osm.pbf lines \
  -where "railway = 'rail'"
```

Attivazione: `LIMEN_OSM_ROADS` + `LIMEN_OSM_RAILWAYS`; poi
`limen bootstrap-static` carica la rete e calcola le distanze. Senza
questo slot l'esposizione degrada ai flag CORINE 12x.

### `radar/` — pioggia misurata storica (solo backtest)

L'API pubblica del DPC serve solo gli ultimi mesi (misurato il 14 ottobre
2026: da giugno 2026 in poi; prima risponde 403). Lo storico è
**IT-DPC-SRI** (Fondazione Bruno Kessler su dati DPC, CC BY-SA 4.0,
attribuzione «© Dipartimento della Protezione Civile», Zenodo
10.5281/zenodo.18637608, arXiv 2602.15088): il mosaico SRI nazionale —
intensità in mm/h, **solo radar, senza pluviometri** — dal 2010 al 2025, 1 km,
un fotogramma ogni 15 minuti fino al 2014, 10 fino al 2020, 5 dopo.
`make radar-data` lo copia dall'object store di ECMWF (anonimo, qualche ora);
Zenodo dà lo stesso archivio come un unico `.tar.zst` a ~0,1 MB/s.

Il «Merging» (radar **più pluviometri**, quello che la produzione legge) non
ha un archivio pubblico: l'API lo tiene circa cinque mesi. Il passo notturno
`radar_archivio` (cartella `RADAR_ARCHIVE__CARTELLA`) salva `CUM3` alle 00, 03,
…, 21 UTC e `SRT1` a ogni ora; il backtest (`LIMEN_BACKTEST_PIOGGIA=merging`)
ne ricava la pioggia oraria riscalando SRT1 perché ogni blocco di tre ore
sommi al CUM3. Verificato il 10 ottobre 2026: a Melito 175,4 mm ricostruiti
contro 176,0 del CUM24 ufficiale (solo radar: 137). ~17 MB al giorno.

Due limiti da tenere accanto a ogni numero di IT-DPC-SRI: fino al 2014-2015 la copertura è
scarsa (su dodici eventi ITALICA del 2010-2011 il radar leggeva fra lo 0 e il
30 % della pioggia dei pluviometri), e un mosaico senza pluviometri
sottostima nelle valli schermate. Il controllo indipendente è CERRA-Land
(Copernicus, giornaliero a 5,5 km dal 1984, corretto con i pluviometri),
sul CDS con la stessa chiave Copernicus del `.env`.

## Inventario del server

Cosa sta su questo host oltre al codice, aggiornato al **14 ottobre 2026**.
Niente di questo è in git: si rigenera con il comando a destra.

| Dove | Cosa | Dimensione | Fonte e licenza | Si rigenera con |
|---|---|---|---|---|
| `data/boundaries/istat_2023/` | confini comunali, provinciali, regionali | 20 MB | ISTAT, CC-BY 3.0 | download manuale (sopra) |
| `data/inventory/iffi/<regione>/` | inventario frane IFFI, 21 territori | 2,7 GB | ISPRA, CC-BY | download per regione |
| `data/hazard/landslide/pai_frane_2020_2021/` | mosaicatura PAI frane | 1,9 GB | ISPRA, CC-BY 4.0 | idrogeo.isprambiente.it |
| `data/hazard/hydraulic/pai_idraulica_2020/` | mosaicatura PAI idraulica | 22 MB | ISPRA, CC-BY 4.0 | `geodata/datasets.yaml` |
| `data/events/italica/ITALICA_v4.csv` | catalogo frane datate | 1 MB | CNR-IRPI, CC-BY 4.0 | `limen ingest-events` |
| `data/flood_events/EMSR*/` | perimetri allagati osservati, 13 attivazioni | 59 MB | Copernicus EMS | `limen ingest-events --hazard flood` |
| `data/fires/firms/` | archivio incendi MODIS/VIIRS 2000- | 34 MB | NASA FIRMS | `limen ingest-fire-history` |
| `data/sealing/clms_imd_2018/` | suolo sigillato 100 m | 4,5 MB | Copernicus Land (EEA) | `make imperviousness-data` |
| `data/osm/` | PBF Italia + GPKG strade e ferrovie | 2,3 GB | © OpenStreetMap, ODbL | `make osm-data` |
| `data/radar/it_dpc_sri/` | radar DPC 2010-2025, Zarr | ~51 GB | FBK su dati DPC, CC BY-SA 4.0 | `make radar-data` |
| `/srv/data/limen-datasets/radar/dpc_merging/` | radar DPC «Merging» (CUM3 + SRT1) da fine maggio 2026, cresce ogni notte | ~0,5 GB/mese | DPC, CC BY-SA 4.0 | passo notturno `radar_archivio` / `limen radar-archivio` |
| `data/backups/` | dump del training ML e di MLflow (luglio 2026) | 15 MB | prodotti da Limen | `make dump-training` |
| `/srv/appdata/git/mcp-geo-server/data/` | shapefile serviti da GeoServer (PAI, IFFI, confini) | 5,8 GB | come sopra | repo `mcp-geo-server` |
| `/srv/data/limen-datasets/` | dataset montati nel worker (`/var/lib/limen/datasets`) | 1 MB | ITALICA | `limen ingest-events` |
| volume Docker `limen-openmeteo-data` | cache dei modelli Open-Meteo (ECMWF IFS 0,25°, ICON-EU, ERA5-Land) | variabile | Open-Meteo, CC-BY 4.0 | `make meteo-sync` |
| `/srv/pgfast/postgis/limen-pgdata` | il database PostGIS | — | — | `make seed` + ingest |
