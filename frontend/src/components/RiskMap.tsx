import { useEffect, useRef, useState } from "react";
import type { JSX } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";

import { copernicusModificato } from "../lib/attribuzioni";
import { BASEMAP_LAYER, BASEMAP_SOURCE } from "../lib/basemap";
import { config } from "../lib/env";
import { NOMI_PERICOLO, useHazard } from "../lib/hazard";
import { testi, useLingua, useTesti } from "../lib/i18n";
import { useMapStateOpzionale } from "../lib/map-state";
import { COLORE_ALLERTA, OVERLAYS } from "../lib/overlays";
import { posizioneInItalia, ZOOM_POSIZIONE } from "../lib/posizione";
import { COLORE_LIVELLO, popupStazione, RAGGIO_LIVELLO } from "../lib/stazioni";
import type { ProprietaStazione } from "../lib/stazioni";
import {
  maplibreColorMatch,
  maplibreMultiHazardColorMatch,
  maplibreWorstHazardLine,
} from "../lib/risk-colors";
import { LETTERE } from "./HazardSelector";

const SOURCE_ID = "limen-risk";
const LAYER_ID = "limen-risk-fill";
const SELECTED_LAYER_ID = "limen-risk-selected";
// Il comune scelto dalla colonna. Una sorgente GeoJSON e non le tile dei
// comuni: quelle esistono solo fra gli zoom 7 e 11, e il comune va
// evidenziato anche a zoom 13, quando le celle riempiono la vista.
const HIGHLIGHT_SOURCE_ID = "limen-comune-evidenziato";
const HIGHLIGHT_MASK_ID = "limen-comune-maschera";
const HIGHLIGHT_CASING_ID = "limen-comune-bordo-fondo";
const HIGHLIGHT_LINE_ID = "limen-comune-bordo";

type Anello = [number, number][];
type Poligono = Anello[];

/** Il mondo meno il comune: scurire **fuori** fa risaltare la zona senza
 *  coprire le celle che ci stanno dentro, che sono ciò che si vuole leggere. */
export function maschera(feature: GeoJSON.Feature | null): GeoJSON.FeatureCollection {
  if (feature === null || feature.geometry === null) {
    return { type: "FeatureCollection", features: [] };
  }
  const g = feature.geometry;
  const poligoni: Poligono[] =
    g.type === "Polygon"
      ? [g.coordinates as Poligono]
      : g.type === "MultiPolygon"
        ? (g.coordinates as Poligono[])
        : [];
  const mondo: Anello = [
    [-180, -85],
    [180, -85],
    [180, 85],
    [-180, 85],
    [-180, -85],
  ];
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { ruolo: "maschera" },
        geometry: {
          type: "Polygon",
          // L'anello esterno di ogni parte del comune diventa un buco nel
          // mondo. I buchi del comune stesso — un'enclave — restano velati,
          // ed è giusto: non sono suoi.
          coordinates: [mondo, ...poligoni.flatMap((pg) => (pg[0] ? [pg[0]] : []))],
        },
      },
      { ...feature, properties: { ...(feature.properties ?? {}), ruolo: "confine" } },
    ],
  };
}
const REGION_SOURCE_ID = "limen-region";
const REGION_LAYER_ID = "limen-region-fill";
const COMUNE_SOURCE_ID = "limen-comune";
const COMUNE_LAYER_ID = "limen-comune-fill";
const COMUNE_BADGE_ID = "limen-comune-badge";
const WORST_HAZARD_LAYER_ID = "limen-worst-hazard";
const WORST_HAZARD_LETTER_ID = "limen-worst-hazard-lettera";
const COMUNE_MIN_ZOOM = 7;
const COMUNE_MAX_ZOOM = 11;
// Sotto questo zoom una cella da 1 km è sub-pixel: mostriamo il
// choropleth regionale (20 poligoni) invece dei 312k poligoni cella.
//
// Otto e non sette, misurato sul peso della tile che il browser deve
// scaricare per disegnarla: 1,85 MB a zoom 5, 726 kB a 7, 848 kB a 8, 165 kB
// a 9, 4 kB a 11. A sette il tile server superava il proprio limite di 5 s e
// rispondeva 500, quindi la mappa restava vuota — e le richieste a vuoto
// saturavano il pool, facendo cadere anche le tile leggere delle regioni.
// A otto la tile e' grossa ma arriva in 1,6 s: una schermata costa qualche
// MB, il prezzo scelto per vedere le celle una scala prima.
//
// Il livello dei comuni ora segue tutti i pericoli (migrazione 051): mostra
// il peggiore dei tre, che è la stessa lettura della colonna a fianco.
// `v_region_tiles` invece è ancora fissata in SQL sul pericolo di default,
// quindi per incendio e alluvione le celle restano l'unico livello che segue
// il selettore, e la soglia resta a sette: alzarla lascerebbe in pagina i
// colori delle frane sotto l'etichetta di un altro pericolo, che è peggio di
// una mappa lenta.
const CELL_MIN_ZOOM_DEFAULT = 8;
const CELL_MIN_ZOOM_OTHER = 7;
const WMS_PAI_LAYER = "ispra:mosaicatura_ispra_2020_2021_aree_pericolosita_frana_pai";
const IFFI_REGIONS = [
  "abruzzo", "basilicata", "bolzano", "calabria", "campania",
  "emilia_romagna", "friuli_venezia_giulia", "lazio", "liguria",
  "lombardia", "marche", "molise", "piemonte", "puglia", "sardegna",
  "sicilia", "toscana", "trento", "umbria", "valle_d_aosta", "veneto",
];
const WMS_IFFI_LAYERS = IFFI_REGIONS.map(
  (r) => `ispra:frane_poly_${r}_opendata`,
).join(",");

function wmsTileUrl(base: string, layers: string): string {
  const params = new URLSearchParams({
    service: "WMS",
    version: "1.1.1",
    request: "GetMap",
    layers,
    srs: "EPSG:3857",
    width: "256",
    height: "256",
    format: "image/png",
    transparent: "true",
  });
  return `${base}?${params.toString()}&bbox={bbox-epsg-3857}`;
}
const PAI_SOURCE_ID = "limen-pai";
const PAI_LAYER_ID = "limen-pai-fill";
const IFFI_SOURCE_ID = "limen-iffi";
const IFFI_LAYER_ID = "limen-iffi-circle";

// pmtiles registers a custom `pmtiles://` URL scheme. The protocol is a
// singleton — calling `addProtocol` twice would throw, so we guard with a
// module-level flag.
let pmtilesProtocolRegistered = false;
function ensurePmtilesProtocol(): void {
  if (pmtilesProtocolRegistered) return;
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  pmtilesProtocolRegistered = true;
}

// PAI 5-class colour ladder — matches docs/scoring-model.md's
// ColorBrewer YlOrRd palette so PAI overlays are legible on top of the
// risk choropleth.
const PAI_FILL_COLOR: maplibregl.ExpressionSpecification = [
  "match",
  ["get", "hazard_class"],
  "AA",
  "#fed976",
  "P1",
  "#feb24c",
  "P2",
  "#fd8d3c",
  "P3",
  "#fc4e2a",
  "P4",
  "#bd0026",
  "#cccccc",
];

const T = testi(
  {
    mappa: (cosa: string) => `Mappa interattiva del rischio: ${cosa}`,
    tutti: "tutti i pericoli",
    frane: "frane",
    previsione: (h: number) => `, previsione a ${h} ore`,
    assente: "Il livello del rischio non è disponibile.",
    assenteSpiega:
      " Questa è solo la cartografia di base: le celle colorate mancano, non sono assenti perché il rischio è nullo.",
    fonteIdraulica: "ISPRA pericolosità idraulica (CC-BY-4.0)",
    fonteDpc: "Protezione Civile, bollettino di criticità (CC-BY 4.0)",
  },
  {
    mappa: (cosa: string) => `Interactive risk map: ${cosa}`,
    tutti: "all hazards",
    frane: "landslides",
    previsione: (h: number) => `, ${h}-hour forecast`,
    assente: "The risk layer is unavailable.",
    assenteSpiega:
      " This is only the base map: the coloured cells are missing, not absent because the risk is zero.",
    fonteIdraulica: "ISPRA hydraulic hazard (CC-BY-4.0)",
    fonteDpc: "Civil Protection, criticality bulletin (CC-BY 4.0)",
  },
);

/** Le props sono override: senza, la mappa legge lo stato condiviso
 *  (`MapStateProvider`, #317). Restano per i test e per chi monta la mappa
 *  fuori dalla dashboard. */
export interface RiskMapProps {
  /** Override the pg_tileserv base URL; useful in tests. */
  readonly tileservUrl?: string;
  /** Layer/function name pg_tileserv exposes the matview as. */
  readonly tileLayer?: string;
  /** Callback when the user clicks a cell — surfaces the cell_id and the
   *  clicked point, where the inspector opens. */
  readonly onCellClick?: (
    cellId: string,
    lngLat?: { lng: number; lat: number },
    proprieta?: Record<string, unknown>,
  ) => void;
  /** Cell to outline on the map (selection from the sidebar or a click). */
  readonly selectedCellId?: string | null;
  /** Imperative ref for tests / parent controls (e.g. fly-to). */
  readonly mapRef?: { current: maplibregl.Map | null };
  /** Il confine del comune scelto dalla colonna, da evidenziare. */
  readonly comuneEvidenziato?: GeoJSON.Feature | null;
  /** I livelli di contesto accesi (id di `lib/overlays`). */
  readonly overlayAttivi?: ReadonlySet<string>;
  /** Nasconde le aree sotto Moderato (#155). */
  readonly soloSopraSoglia?: boolean;
  /** Ore nel futuro: 0 è adesso, 24/48/72 la previsione per cella (#155). */
  readonly orizzonte?: number;
  /** Alla prima apertura porta la mappa sulla posizione del browser, se è in
   *  Italia. Spento quando un link diretto ha già un posto da mostrare. */
  readonly geolocalizza?: boolean;
}

/** Da questo zoom in su le celle previste: a 6 una tile pesava 2,4 MB e
 *  3,6 s, a 7 1 MB e mezzo secondo. */
const CELL_MIN_ZOOM_PREVISIONE = 7;

const NESSUN_OVERLAY: ReadonlySet<string> = new Set();

/** Le classi che restano con «solo sopra soglia». */
const SOPRA_SOGLIA = ["Moderate", "High", "VeryHigh"];

/** Il filtro di «solo sopra soglia» su un attributo di classe, o `null`.
 *
 *  Le aree non misurate restano: sono grigie perché non si sa, e toglierle
 *  insieme alle tranquille le farebbe passare per tranquille (#143). */
export function filtroSoglia(prop: string, attivo: boolean): maplibregl.FilterSpecification | null {
  if (!attivo) return null;
  return [
    "any",
    ["==", ["get", "measured"], false],
    ["in", ["get", prop], ["literal", SOPRA_SOGLIA]],
  ] as maplibregl.FilterSpecification;
}

// Le stazioni si scaricano solo a livello acceso: una sorgente GeoJSON con un
// URL lo chiede appena entra nello stile, e la mappa si ricostruisce a ogni
// cambio di pericolo (#255).
function caricaStazioni(map: maplibregl.Map, attivi: ReadonlySet<string>, url: string): void {
  if (!attivi.has("stazioni")) return;
  (map.getSource("ovl-stazioni") as maplibregl.GeoJSONSource | undefined)?.setData(url);
}

/**
 * MapLibre GL map wired to the pg_tileserv ``mv_latest_risk`` vector
 * tiles. The fill colour is bound to the ``risk_level`` attribute via
 * the palette in :mod:`risk-colors`.
 *
 * The map is non-interactive in tests (the `maplibre-gl` module is
 * mocked at the Vitest setup level) — the component still mounts and
 * exposes its props so the tile-URL composition can be asserted.
 */
export function RiskMap(props: RiskMapProps): JSX.Element {
  // La cartografia di base arriva da un servizio esterno, quindi quando il
  // nostro livello del rischio non carica la mappa resta *visivamente
  // perfetta* — strade, rilievi, etichette — e non dice niente. Un sistema di
  // allerta che sembra integro mentre non sa nulla è peggio di uno
  // palesemente rotto: questo stato serve a impedirlo.
  const [livelloAssente, setLivelloAssente] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const stato = useMapStateOpzionale();
  const comuneEvidenziato =
    props.comuneEvidenziato !== undefined ? props.comuneEvidenziato : (stato?.comune ?? null);
  const overlayAttivi = props.overlayAttivi ?? stato?.overlayAttivi ?? NESSUN_OVERLAY;
  const soloSopraSoglia = props.soloSopraSoglia ?? stato?.soloSoglia ?? false;
  const selectedCellId =
    props.selectedCellId !== undefined ? props.selectedCellId : (stato?.cella?.cellId ?? null);
  const geolocalizza = props.geolocalizza ?? stato?.geolocalizza ?? false;
  const onCellClick = props.onCellClick ?? stato?.cliccaCella;
  const evidenziatoRef = useRef<GeoJSON.Feature | null>(comuneEvidenziato);
  const overlayRef = useRef<ReadonlySet<string>>(overlayAttivi);
  const sogliaRef = useRef(soloSopraSoglia);
  // La mappa scrive l'area inquadrata nello stato a ogni fine movimento: un
  // ref, perché il gestore registrato alla creazione vive più del render.
  const impostaAreaRef = useRef(stato?.impostaArea);
  impostaAreaRef.current = stato?.impostaArea;
  // L'area di un link si legge solo quando la mappa nasce: dopo, la vista
  // la decide chi la muove.
  const areaLink = stato?.link.area ?? null;
  const areaApplicataRef = useRef(areaLink);
  const mappaRef = useRef<maplibregl.Map | null>(null);
  // La vista si conserva quando la mappa si ricostruisce (cambio di pericolo
  // o di sorgente): ripartire dal centro di default buttava via il comune
  // che si stava guardando.
  const cameraRef = useRef<{ center: [number, number]; zoom: number } | null>(null);
  // La vista della prima apertura, finché la posizione del browser non ha
  // risposto: un ref e non la vista della mappa corrente perché la mappa si
  // ricostruisce (e StrictMode la monta due volte) prima che la risposta arrivi.
  const partenzaRef = useRef<{ lng: number; lat: number; zoom: number } | null>(null);
  const posizioneFattaRef = useRef(false);
  // Visibilità di un livello di contesto, letta allo stato corrente: la mappa
  // si ricostruisce a ogni cambio di pericolo, e senza questo i livelli
  // tornerebbero spenti mentre la casella resta spuntata.
  const visibile = (layerId: string): "visible" | "none" =>
    OVERLAYS.some((o) => overlayRef.current.has(o.id) && o.layerIds.includes(layerId))
      ? "visible"
      : "none";
  const tileserv = (props.tileservUrl ?? config.tileservUrl).replace(/\/+$/, "");
  const { selected: hazard, view, multi, available } = useHazard();
  const { lingua } = useLingua();
  const t = useTesti(T);
  const urlStazioni = `${config.apiUrl.replace(/\/+$/, "")}/api/sensori/stazioni${
    multi ? "" : `?hazard=${encodeURIComponent(hazard)}`
  }`;
  const urlStazioniRef = useRef(urlStazioni);
  urlStazioniRef.current = urlStazioni;
  // Due sorgenti, non una. `v_risk_tiles` è fissata sul pericolo di default
  // in SQL (migrazione 028) perché una sorgente di tile deve dare una
  // geometria per cella e la vista ne ha una per (cella, pericolo): resta la
  // strada del caso di default, immutata. Per ogni altro pericolo si passa da
  // `risk_at(z,x,y,hours_ago,hazard)`, che pg_tileserv espone con i parametri
  // in query string.
  //
  // Non si è unificato tutto su `risk_at`: cambierebbe la sorgente della
  // mappa che oggi funziona, in cambio di simmetria e nient'altro.
  const isDefaultHazard = hazard === "landslide";
  // Le rollup regionali e comunali sono fissate sulle frane: quando il
  // selettore dice altro, le celle sono l'unica cosa che lo rispetta.
  const orizzonte = props.orizzonte ?? stato?.orizzonte ?? 0;
  const futuro = orizzonte > 0;
  const cellMinZoom = futuro
    ? CELL_MIN_ZOOM_PREVISIONE
    : isDefaultHazard && !multi
      ? CELL_MIN_ZOOM_DEFAULT
      : CELL_MIN_ZOOM_OTHER;
  // Tre sorgenti, non due: la vista d'insieme non è "un pericolo qualunque"
  // ma un'aggregazione, e `v_multi_hazard` (migrazione 037) è l'unica che dà
  // una riga per cella su tutti i pericoli insieme.
  // Il futuro ha una sorgente sua, `forecast_at()` (migrazione 060), che
  // legge la previsione per cella; senza `p_hazard` è il peggiore fra i
  // pericoli previsti, come `multi_hazard_at()` per l'adesso.
  const tileLayer =
    props.tileLayer ??
    (futuro
      ? "public.forecast_at"
      : multi
        ? "public.multi_hazard_at"
        : isDefaultHazard
          ? "public.v_risk_tiles"
          : "public.risk_at");
  const tileQuery = futuro
    ? `?p_horizon=${orizzonte}${multi ? "" : `&p_hazard=${encodeURIComponent(hazard)}`}`
    : multi || isDefaultHazard
      ? ""
      : `?p_hazard=${encodeURIComponent(hazard)}`;
  // Il nome del layer *dentro* il tile non è il path da cui lo si scarica.
  // `risk_at()` serializza con `ST_AsMVT(..., 'public.v_risk_tiles', ...)`
  // (migrazione 029), quindi puntare `source-layer` a "public.risk_at" darebbe
  // tile validi e una mappa vuota — un guasto silenzioso, perché la richiesta
  // riesce. Il layer MVT è sempre quello, qualunque sia la sorgente.
  // Ciò che obbliga a ricostruire la mappa: l'orizzonte no, si cambia con
  // `setTiles` (sotto).
  const chiaveSorgente = futuro ? tileQuery.replace(/p_horizon=\d+/, "p_horizon=*") : tileQuery;
  const sourceLayer =
    props.tileLayer ??
    (futuro
      ? "public.v_forecast_tiles"
      : multi
        ? "public.v_multi_hazard"
        : "public.v_risk_tiles");
  // In vista d'insieme la classe sta in `worst_level`, non in `risk_level`:
  // sono due sorgenti diverse, e il layer di selezione legge `cell_id` in
  // entrambe.
  const cellFillColor = futuro
    ? maplibreColorMatch("risk_level", hazard)
    : multi
    ? maplibreMultiHazardColorMatch()
    : maplibreColorMatch("risk_level", hazard);
  // Il nome lo dà il backend (`/api/hazards`); il ripiego serve al primo
  // render e a un backend irraggiungibile.
  // In inglese il database non ha il nome: lo dà la tabella condivisa.
  const nomeInLingua =
    lingua === "it"
      ? available.find((h) => h.hazard === hazard)?.label_it
      : NOMI_PERICOLO.en[hazard];
  const hazardLabel =
    (multi ? t.tutti : (nomeInLingua ?? (isDefaultHazard ? t.frane : hazard))) +
    (futuro ? t.previsione(orizzonte) : "");
  // Un ref e non il valore: la mappa non si ricostruisce fra una scadenza e
  // l'altra, e il gestore registrato alla creazione leggerebbe la callback
  // di allora — con l'orizzonte di allora.
  const onCellClickRef = useRef(onCellClick);
  useEffect(() => {
    onCellClickRef.current = onCellClick;
  }, [onCellClick]);
  const haClick = onCellClick !== undefined;
  // L'attributo che porta la classe, per livello. Le regioni non ci sono:
  // `v_region_tiles` non espone `measured`, e filtrarle toglierebbe proprio
  // le regioni senza dato insieme a quelle tranquille.
  const attributoClasse: Record<string, string> = {
    [COMUNE_LAYER_ID]: "worst_class",
    [LAYER_ID]: multi && !futuro ? "worst_level" : "risk_level",
  };

  useEffect(() => {
    if (!containerRef.current) return;

    // Register the `pmtiles://` protocol once — required only when the
    // PAI / IFFI overlays are configured, but cheap to do unconditionally.
    if (config.paiPmtilesUrl || config.iffiPmtilesUrl) {
      ensurePmtilesProtocol();
    }

    const tilesUrl = `${tileserv}/${tileLayer}/{z}/{x}/{y}.pbf${tileQuery}`;
    const conFiltro = (layerId: string): { filter?: maplibregl.FilterSpecification } => {
      const f = filtroSoglia(attributoClasse[layerId] ?? "risk_level", sogliaRef.current);
      return f ? { filter: f } : {};
    };

    // Build the source set lazily so optional PMTiles overlays only
    // appear when their env URL is set — see `docs/geodata.md`.
    const sources: maplibregl.StyleSpecification["sources"] = {
      [HIGHLIGHT_SOURCE_ID]: {
        type: "geojson",
        // Si riparte dal comune già scelto: la mappa si ricostruisce quando
        // cambia il pericolo, e il confine non deve sparire per questo.
        data: maschera(evidenziatoRef.current),
      },
      osm: BASEMAP_SOURCE,
      [SOURCE_ID]: {
        type: "vector",
        tiles: [tilesUrl],
        // L'alluvione (anche nella vista d'insieme) è calcolata dalla portata
        // GloFAS: la licenza CEMS-Floods chiede di dirlo sulla mappa.
        ...(multi || hazard === "flood" ? { attribution: copernicusModificato(undefined, lingua) } : {}),
        // La sorgente parte dallo stesso zoom del livello che la disegna.
        // Prima partiva da 5: il browser scaricava tile da 1,85 MB che poi
        // non mostrava a nessuno, e intanto il tile server andava in timeout.
        minzoom: cellMinZoom,
        maxzoom: 14,
      },
      [REGION_SOURCE_ID]: {
        type: "vector",
        tiles: [`${tileserv}/public.v_region_tiles/{z}/{x}/{y}.pbf`],
        minzoom: 0,
        maxzoom: 10,
      },
      [COMUNE_SOURCE_ID]: {
        type: "vector",
        tiles: [`${tileserv}/public.v_comune_tiles/{z}/{x}/{y}.pbf`],
        minzoom: 6,
        maxzoom: 12,
      },
      // Livelli di contesto per alluvione e incendio, dalle tabelle che
      // pg_tileserv pubblicava già. Solo gli attributi usati: le tile pesano
      // meno, e il resto delle colonne non serve a disegnare.
      "ovl-idraulica": {
        type: "vector",
        // La versione suddivisa: quella intera va in timeout a zoom 8.
        tiles: [`${tileserv}/public.flood_hazard_subdiv/{z}/{x}/{y}.pbf?properties=hazard_class`],
        minzoom: 10,
        attribution: t.fonteIdraulica,
      },
      "ovl-alluvioni": {
        type: "vector",
        tiles: [`${tileserv}/public.flood_events/{z}/{x}/{y}.pbf?properties=event_time,source`],
        minzoom: 8,
        attribution: "Copernicus EMS",
      },
      // Le allerte ufficiali di oggi (migrazione 063): 187 zone, leggere.
      "ovl-dpc": {
        type: "vector",
        tiles: [`${tileserv}/public.v_dpc_allerte_oggi/{z}/{x}/{y}.pbf?properties=zona,livello`],
        attribution: t.fonteDpc,
      },
      "ovl-bruciate": {
        type: "vector",
        tiles: [`${tileserv}/public.fire_perimeters/{z}/{x}/{y}.pbf?properties=fire_date,area_ha`],
        minzoom: 6,
        attribution: "EFFIS",
      },
      // Le stazioni dei sensori (#255): poche centinaia di punti, dall'API,
      // con la posizione dei privati già arrotondata.
      "ovl-stazioni": {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      },
      "wms-pai": {
        type: "raster",
        tiles: [wmsTileUrl(config.geoserverWmsUrl, WMS_PAI_LAYER)],
        tileSize: 256,
        attribution: "ISPRA PAI (CC-BY-4.0)",
      },
      "wms-iffi": {
        type: "raster",
        tiles: [wmsTileUrl(config.geoserverWmsUrl, WMS_IFFI_LAYERS)],
        tileSize: 256,
        attribution: "ISPRA IFFI (CC-BY-4.0)",
      },
    };
    const layers: maplibregl.StyleSpecification["layers"] = [
      BASEMAP_LAYER,
      {
        id: "wms-pai-layer",
        type: "raster",
        source: "wms-pai",
        paint: { "raster-opacity": 0.6 },
        layout: { visibility: visibile("wms-pai-layer") },
      },
      {
        id: "wms-iffi-layer",
        type: "raster",
        source: "wms-iffi",
        paint: { "raster-opacity": 0.7 },
        layout: { visibility: visibile("wms-iffi-layer") },
      },
      {
        id: REGION_LAYER_ID,
        type: "fill",
        source: REGION_SOURCE_ID,
        // Regioni e comuni dicono l'adesso: sotto una previsione direbbero
        // un'altra cosa con gli stessi colori.
        layout: { visibility: futuro ? "none" : "visible" },
        "source-layer": "public.v_region_tiles",
        maxzoom: cellMinZoom,
        paint: {
          // `v_region_tiles` è fissata sul pericolo di default in SQL, quindi
          // tiene la palette di default anche quando il selettore dice altro:
          // colorarla come l'incendio direbbe che mostra l'incendio.
          "fill-color": maplibreColorMatch() as never,
          "fill-opacity": 0.7,
          "fill-outline-color": "#2c3846",
        },
      },
      {
        id: COMUNE_LAYER_ID,
        type: "fill",
        source: COMUNE_SOURCE_ID,
        layout: { visibility: futuro ? "none" : "visible" },
        "source-layer": "public.v_comune_tiles",
        minzoom: COMUNE_MIN_ZOOM,
        maxzoom: COMUNE_MAX_ZOOM,
        paint: {
          "fill-color": maplibreColorMatch("worst_class") as never,
          "fill-opacity": 0.7,
          "fill-outline-color": "#2c3846",
        },
        ...conFiltro(COMUNE_LAYER_ID),
      },
      {
        // Count of alerting cells — only on High+ comuni (keeps it uncluttered).
        id: COMUNE_BADGE_ID,
        type: "symbol",
        source: COMUNE_SOURCE_ID,
        "source-layer": "public.v_comune_tiles",
        minzoom: COMUNE_MIN_ZOOM,
        maxzoom: COMUNE_MAX_ZOOM,
        filter: ["in", ["get", "worst_class"], ["literal", ["High", "VeryHigh"]]],
        layout: {
          visibility: futuro ? "none" : "visible",
          "text-field": ["to-string", ["get", "n_alert"]],
          // Dichiarato invece che lasciato al default ("Open Sans Regular"):
          // il default e' implicito e il server dei glifi potrebbe non averlo.
          "text-font": ["Open Sans Regular"],
          "text-size": 12,
        },
        paint: {
          "text-color": "#ffffff",
          "text-halo-color": "#0a0e13",
          "text-halo-width": 1.5,
        },
      },
      {
        id: LAYER_ID,
        type: "fill",
        source: SOURCE_ID,
        "source-layer": sourceLayer,
        minzoom: cellMinZoom,
        paint: {
          "fill-color": cellFillColor as never,
          // 0,7 e non meno: la scala è verificata a questa opacità sopra la
          // base scura, e più trasparente le classi si avvicinano.
          "fill-opacity": 0.7,
          "fill-outline-color": "#0a0e13",
        },
        ...conFiltro(LAYER_ID),
      },
      ...(multi
        ? [
            {
              // Quale pericolo, sulle sole celle in classe alta. È il secondo
              // canale che sostituisce la tinta: il colore ora dice quanto,
              // il bordo dice di cosa, e lo dice dove la domanda nasce
              // davvero — davanti a una cella scura. Su ogni cella
              // ridarebbe alla mappa il rumore che questa scelta toglie.
              id: WORST_HAZARD_LAYER_ID,
              type: "line" as const,
              source: SOURCE_ID,
              "source-layer": sourceLayer,
              minzoom: cellMinZoom,
              paint: {
                "line-color": maplibreWorstHazardLine() as never,
                "line-width": 1.6,
              },
              filter: [
                "in",
                ["get", "worst_level"],
                ["literal", ["High", "VeryHigh"]],
              ] as never,
            },
            {
              // La lettera del pericolo dentro la cella, da vicino. Il bordo
              // da solo non bastava: un operatore davanti a una cella rossa
              // chiedeva «allerta di che cosa?», e un bordo ciano su rosso a
              // 1,6 px non risponde. A, F, I come nella lista dei comuni;
              // in inglese F, L, W, e la mappa si ricostruisce al cambio.
              id: WORST_HAZARD_LETTER_ID,
              type: "symbol" as const,
              source: SOURCE_ID,
              "source-layer": sourceLayer,
              minzoom: 10,
              layout: {
                "text-field": [
                  "match",
                  ["get", "worst_hazard"],
                  "flood",
                  LETTERE[lingua].flood,
                  "landslide",
                  LETTERE[lingua].landslide,
                  "wildfire",
                  LETTERE[lingua].wildfire,
                  "",
                ] as never,
                "text-font": ["Open Sans Regular"],
                "text-size": 12,
                "text-allow-overlap": true,
              },
              paint: {
                "text-color": maplibreWorstHazardLine() as never,
                "text-halo-color": "#0a0e13",
                "text-halo-width": 1.6,
              },
              filter: [
                "in",
                ["get", "worst_level"],
                ["literal", ["High", "VeryHigh"]],
              ] as never,
            },
          ]
        : []),
      // Sopra le celle e non sotto come PAI e IFFI: con un riempimento
      // leggero e il bordo si leggono qualunque sia il colore della cella, e
      // il confine del comune resta comunque in cima.
      {
        id: "ovl-idraulica-fill",
        type: "fill",
        source: "ovl-idraulica",
        "source-layer": "public.flood_hazard_subdiv",
        paint: {
          "fill-color": [
            "match",
            ["get", "hazard_class"],
            "P3",
            "#08519c",
            "P2",
            "#3182bd",
            "P1",
            "#9ecae1",
            "#9ecae1",
          ],
          "fill-opacity": 0.45,
        },
        layout: {
          visibility: visibile("ovl-idraulica-fill"),
          // Gli scenari PGRA sono annidati: l'area P1 contiene la P2, che
          // contiene la P3 — su un campione di 200 pezzi P3, tutti e 200
          // stavano sotto un P1 o un P2. Senza un ordine, MapLibre dipinge
          // nell'ordine della tile, e un P1 azzurro poteva coprire il P3 blu
          // scuro: la zona più pericolosa mostrata come la meno. La chiave
          // più alta va sopra. Lo stesso criterio del punteggio, che di più
          // classi sovrapposte prende la massima.
          "fill-sort-key": [
            "match",
            ["get", "hazard_class"],
            "P3",
            3,
            "P2",
            2,
            1,
          ],
        },
      },
      {
        id: "ovl-idraulica-line",
        type: "line",
        source: "ovl-idraulica",
        "source-layer": "public.flood_hazard_subdiv",
        paint: { "line-color": "#9ecae1", "line-width": 0.6, "line-opacity": 0.6 },
        layout: { visibility: visibile("ovl-idraulica-line") },
      },
      {
        id: "ovl-alluvioni-fill",
        type: "fill",
        source: "ovl-alluvioni",
        "source-layer": "public.flood_events",
        paint: { "fill-color": "#00a6d6", "fill-opacity": 0.4 },
        layout: { visibility: visibile("ovl-alluvioni-fill") },
      },
      {
        id: "ovl-alluvioni-line",
        type: "line",
        source: "ovl-alluvioni",
        "source-layer": "public.flood_events",
        paint: { "line-color": "#6fd3ee", "line-width": 1 },
        layout: { visibility: visibile("ovl-alluvioni-line") },
      },
      {
        id: "ovl-bruciate-fill",
        type: "fill",
        source: "ovl-bruciate",
        "source-layer": "public.fire_perimeters",
        paint: { "fill-color": "#ff9ad5", "fill-opacity": 0.2 },
        layout: { visibility: visibile("ovl-bruciate-fill") },
      },
      {
        // Solo le zone in allerta si colorano: il verde su tutta Italia
        // coprirebbe la mappa per dire «niente».
        id: "ovl-dpc-fill",
        type: "fill",
        source: "ovl-dpc",
        "source-layer": "public.v_dpc_allerte_oggi",
        filter: [">", ["get", "livello"], 0],
        paint: {
          "fill-color": [
            "match",
            ["get", "livello"],
            1,
            COLORE_ALLERTA[1] ?? "",
            2,
            COLORE_ALLERTA[2] ?? "",
            COLORE_ALLERTA[3] ?? "",
          ],
          "fill-opacity": 0.25,
        },
        layout: { visibility: visibile("ovl-dpc-fill") },
      },
      {
        id: "ovl-dpc-line",
        type: "line",
        source: "ovl-dpc",
        "source-layer": "public.v_dpc_allerte_oggi",
        paint: { "line-color": "#c3ccd6", "line-width": 0.8, "line-opacity": 0.6 },
        layout: { visibility: visibile("ovl-dpc-line") },
      },
      {
        id: "ovl-bruciate-line",
        type: "line",
        source: "ovl-bruciate",
        "source-layer": "public.fire_perimeters",
        paint: { "line-color": "#ff9ad5", "line-width": 1.2 },
        layout: { visibility: visibile("ovl-bruciate-line") },
      },
      {
        id: "ovl-stazioni",
        type: "circle",
        source: "ovl-stazioni",
        paint: {
          "circle-color": [
            "match",
            ["get", "livello"],
            2,
            COLORE_LIVELLO[2],
            1,
            COLORE_LIVELLO[1],
            COLORE_LIVELLO[0],
          ],
          "circle-radius": [
            "match",
            ["get", "livello"],
            2,
            RAGGIO_LIVELLO[2],
            1,
            RAGGIO_LIVELLO[1],
            RAGGIO_LIVELLO[0],
          ],
          "circle-stroke-color": "#0a0e13",
          "circle-stroke-width": 1.5,
          // Una stazione che non trasmette resta, sbiadita: sparire direbbe
          // che non c'è mai stata.
          "circle-opacity": ["match", ["get", "stato"], "online", 1, 0.45],
          "circle-stroke-opacity": ["match", ["get", "stato"], "online", 1, 0.45],
        },
        layout: { visibility: visibile("ovl-stazioni") },
      },
      {
        // Fuori dal comune scelto: un velo, non un muro. Abbastanza da
        // staccare la zona, non tanto da nascondere il contesto intorno.
        id: HIGHLIGHT_MASK_ID,
        type: "fill",
        source: HIGHLIGHT_SOURCE_ID,
        filter: ["==", ["get", "ruolo"], "maschera"],
        paint: { "fill-color": "#000000", "fill-opacity": 0.5 },
      },
      {
        // Il bordo ha un fondo scuro sotto: sulle celle gialle una linea
        // bianca sola si perderebbe dove il colore è simile.
        id: HIGHLIGHT_CASING_ID,
        type: "line",
        source: HIGHLIGHT_SOURCE_ID,
        filter: ["==", ["get", "ruolo"], "confine"],
        paint: { "line-color": "#0a0e13", "line-width": 6, "line-opacity": 0.9 },
      },
      {
        id: HIGHLIGHT_LINE_ID,
        type: "line",
        source: HIGHLIGHT_SOURCE_ID,
        filter: ["==", ["get", "ruolo"], "confine"],
        paint: { "line-color": "#ffffff", "line-width": 2.5 },
      },
      {
        // Selection outline: the filter starts matching nothing and is
        // swapped in the selectedCellId effect below.
        id: SELECTED_LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        "source-layer": sourceLayer,
        paint: {
          "line-color": "#ffffff",
          "line-width": 3,
        },
        filter: ["==", ["get", "cell_id"], "__none__"],
      },
    ];

    if (config.paiPmtilesUrl) {
      sources[PAI_SOURCE_ID] = {
        type: "vector",
        url: `pmtiles://${config.paiPmtilesUrl}`,
        attribution: "ISPRA IdroGEO — PAI mosaic (CC-BY-4.0)",
      };
      layers.push({
        id: PAI_LAYER_ID,
        type: "fill",
        source: PAI_SOURCE_ID,
        "source-layer": "pai",
        paint: {
          "fill-color": PAI_FILL_COLOR,
          "fill-opacity": 0.25,
          "fill-outline-color": "#2c3846",
        },
        // Hidden by default; the LegendPanel can toggle visibility.
        layout: { visibility: "none" },
      });
    }
    if (config.iffiPmtilesUrl) {
      sources[IFFI_SOURCE_ID] = {
        type: "vector",
        url: `pmtiles://${config.iffiPmtilesUrl}`,
        attribution: "ISPRA IdroGEO — IFFI inventory (CC-BY-4.0)",
      };
      layers.push({
        id: IFFI_LAYER_ID,
        type: "circle",
        source: IFFI_SOURCE_ID,
        "source-layer": "iffi",
        minzoom: 8,
        paint: {
          "circle-radius": 3,
          "circle-color": "#c6a8ff",
          "circle-stroke-color": "#0a0e13",
          "circle-stroke-width": 0.5,
          "circle-opacity": 0.8,
        },
        layout: { visibility: "none" },
      });
    }

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        // Obbligatorio: il contatore sui comuni e' un livello `symbol` con
        // `text-field`, e senza `glyphs` MapLibre rifiuta lo stile intero —
        // niente celle, niente regioni, nemmeno lo sfondo.
        glyphs: config.mapGlyphsUrl,
        sources,
        layers,
      },
      center: cameraRef.current?.center ??
        (areaLink ? [areaLink.lon, areaLink.lat] : [config.defaultLon, config.defaultLat]),
      zoom: cameraRef.current?.zoom ?? areaLink?.zoom ?? config.defaultZoom,
    });

    mappaRef.current = map;
    if (props.mapRef) {
      props.mapRef.current = map;
    }

    // La posizione arriva dopo, a mappa già disegnata: aspettarla voleva dire
    // una pagina vuota per otto secondi a chi nega il permesso. Se intanto la
    // vista si è mossa (un trascinamento, un link, un comune dalla colonna) la
    // si lascia stare: strappare la mappa a chi la sta usando è peggio di Roma.
    let annullaPosizione = (): void => {};
    if (geolocalizza && !posizioneFattaRef.current) {
      if (!partenzaRef.current) {
        const c = map.getCenter();
        partenzaRef.current = { lng: c.lng, lat: c.lat, zoom: map.getZoom() };
      }
      const p = partenzaRef.current;
      annullaPosizione = posizioneInItalia(
        (lon, lat) => {
          const c = map.getCenter();
          if (c.lng !== p.lng || c.lat !== p.lat || map.getZoom() !== p.zoom) return;
          map.flyTo({ center: [lon, lat], zoom: ZOOM_POSIZIONE });
        },
        () => {
          posizioneFattaRef.current = true;
        },
      );
    }

    // In basso: in alto a destra stanno gli strumenti della mappa (#155).
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

// MapLibre chiama tutti i listener dei livelli sotto il punto: un click su
    // una stazione non deve aprire anche la cella o spostare la mappa.
    const suStazione = (e: maplibregl.MapMouseEvent): boolean =>
      map.getLayer("ovl-stazioni") !== undefined &&
      map.queryRenderedFeatures(e.point, { layers: ["ovl-stazioni"] }).length > 0;

    if (haClick) {
      map.on("click", LAYER_ID, (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
        if (suStazione(e)) return;
        const cellId = e.features?.[0]?.properties?.["cell_id"];
        if (typeof cellId === "string") {
          onCellClickRef.current?.(cellId, e.lngLat, e.features?.[0]?.properties ?? undefined);
        }
      });
    }
    map.on("click", "ovl-stazioni", (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
      const f = e.features?.[0];
      if (!f || f.geometry.type !== "Point") return;
      new maplibregl.Popup({ maxWidth: "280px" })
        .setLngLat(f.geometry.coordinates as [number, number])
        .setDOMContent(popupStazione(f.properties as unknown as ProprietaStazione, lingua))
        .addTo(map);
    });
    map.on("mouseenter", "ovl-stazioni", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "ovl-stazioni", () => {
      map.getCanvas().style.cursor = "";
    });

    map.once("load", () => caricaStazioni(map, overlayRef.current, urlStazioniRef.current));
    map.on("moveend", () => {
      const c = map.getCenter();
      impostaAreaRef.current?.({ lon: c.lng, lat: c.lat, zoom: map.getZoom() });
    });

    // Click su una regione a zoom nazionale → zoom fino alle celle.
    map.on("click", REGION_LAYER_ID, (e: maplibregl.MapMouseEvent) => {
      if (suStazione(e)) return;
      map.easeTo({ center: e.lngLat, zoom: cellMinZoom + 1 });
    });
    map.on("mouseenter", REGION_LAYER_ID, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", REGION_LAYER_ID, () => {
      map.getCanvas().style.cursor = "";
    });

    // Comune drill-down: click a comune → zoom into its cells.
    map.on("click", COMUNE_LAYER_ID, (e: maplibregl.MapMouseEvent) => {
      if (suStazione(e)) return;
      map.easeTo({ center: e.lngLat, zoom: cellMinZoom + 2 });
    });
    map.on("mouseenter", COMUNE_LAYER_ID, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", COMUNE_LAYER_ID, () => {
      map.getCanvas().style.cursor = "";
    });

    // `error` copre anche le tile che tornano 500 o 404: MapLibre le segnala
    // con l'id della sorgente, che è l'unico modo di distinguere un guasto
    // del *nostro* livello da uno della cartografia di base.
    map.on("error", (e: unknown) => {
      const sourceId = (e as { sourceId?: string }).sourceId;
      if (sourceId === SOURCE_ID) setLivelloAssente(true);
    });
    map.on("sourcedata", (e: maplibregl.MapSourceDataEvent) => {
      if (e.sourceId === SOURCE_ID && e.isSourceLoaded) setLivelloAssente(false);
    });

    return () => {
      annullaPosizione();
      const c = map.getCenter();
      cameraRef.current = { center: [c.lng, c.lat], zoom: map.getZoom() };
      map.remove();
      mappaRef.current = null;
      if (props.mapRef) {
        props.mapRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tileserv, tileLayer, sourceLayer, chiaveSorgente, hazard, view, lingua]);

  // Fra una scadenza e l'altra cambia solo il parametro della tile: si
  // sostituiscono le tile della sorgente invece di ricostruire la mappa, che
  // durante la riproduzione voleva dire ricaricare tutto ogni 2,5 secondi.
  useEffect(() => {
    if (!futuro) return;
    const map = props.mapRef?.current;
    const src = map?.getSource(SOURCE_ID) as maplibregl.VectorTileSource | undefined;
    src?.setTiles([`${tileserv}/${tileLayer}/{z}/{x}/{y}.pbf${tileQuery}`]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tileQuery]);

  // Un link incollato con la mappa già aperta: il costruttore non lo rivede,
  // quindi la vista ci va con `jumpTo`. Solo l'area del link, non quella che
  // la mappa stessa scrive a fine movimento: altrimenti si inseguirebbero.
  useEffect(() => {
    if (areaLink === areaApplicataRef.current) return;
    areaApplicataRef.current = areaLink;
    if (!areaLink) return;
    mappaRef.current?.jumpTo({ center: [areaLink.lon, areaLink.lat], zoom: areaLink.zoom });
  }, [areaLink]);

  // I livelli di contesto, senza ricostruire la mappa.
  useEffect(() => {
    overlayRef.current = overlayAttivi;
    const map = props.mapRef?.current;
    if (!map) return;
    const apply = (): void => {
      for (const o of OVERLAYS) {
        for (const id of o.layerIds) {
          if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visibile(id));
        }
      }
      caricaStazioni(map, overlayRef.current, urlStazioniRef.current);
    };
    if (map.isStyleLoaded()) apply();
    else map.once("idle", apply);
  }, [overlayAttivi, props.mapRef]);

  // «Solo sopra soglia», senza ricostruire la mappa.
  useEffect(() => {
    sogliaRef.current = soloSopraSoglia;
    const map = props.mapRef?.current;
    if (!map) return;
    const apply = (): void => {
      for (const [id, prop] of Object.entries(attributoClasse)) {
        if (map.getLayer(id)) map.setFilter(id, filtroSoglia(prop, sogliaRef.current));
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("idle", apply);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [soloSopraSoglia, props.mapRef]);

  // Il confine del comune, senza ricostruire la mappa.
  useEffect(() => {
    evidenziatoRef.current = comuneEvidenziato;
    const map = props.mapRef?.current;
    if (!map) return;
    const apply = (): void => {
      const src = map.getSource(HIGHLIGHT_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      src?.setData(maschera(evidenziatoRef.current));
    };
    if (map.isStyleLoaded()) apply();
    else map.once("idle", apply);
  }, [comuneEvidenziato, props.mapRef]);

  // Update the selection outline without rebuilding the map.
  useEffect(() => {
    const map = props.mapRef?.current;
    if (!map) return;
    const apply = (): void => {
      if (!map.getLayer(SELECTED_LAYER_ID)) return;
      map.setFilter(SELECTED_LAYER_ID, [
        "==",
        ["get", "cell_id"],
        selectedCellId ?? "__none__",
      ]);
    };
    if (map.isStyleLoaded()) apply();
    else map.once("idle", apply);
  }, [selectedCellId, props.mapRef]);

  return (
    <div className="map-wrap">
      <div
        ref={containerRef}
        className="map-container"
        data-testid="risk-map"
        data-tile-url={`${tileserv}/${tileLayer}/{z}/{x}/{y}.pbf${tileQuery}`}
        style={{ width: "100%", height: "100%" }}
        aria-label={t.mappa(hazardLabel)}
      />
      {livelloAssente ? (
        <div className="map-banner" role="alert">
          <strong>{t.assente}</strong>
          {t.assenteSpiega}
        </div>
      ) : null}
    </div>
  );
}

export default RiskMap;
