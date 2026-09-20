// Lightweight env-var accessor. Vite exposes variables prefixed VITE_
// at build time via `import.meta.env`; we centralise defaults here so
// components don't reimplement fallback logic.

interface ViteEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_TILESERV_URL?: string;
  readonly VITE_ENABLE_TIMELINE?: string;
  readonly VITE_ENABLE_GRAPH?: string;
  readonly VITE_DEFAULT_LON?: string;
  readonly VITE_DEFAULT_LAT?: string;
  readonly VITE_DEFAULT_ZOOM?: string;
  /** URL of the static `pai_landslide_hazard.pmtiles` produced by
   * `limen geodata make-pmtiles`. When unset the layer is not added. */
  readonly VITE_PAI_PMTILES_URL?: string;
  /** URL of the static `iffi_landslides.pmtiles`. Same opt-in semantics. */
  readonly VITE_IFFI_PMTILES_URL?: string;
  /** GeoServer WMS endpoint for the ISPRA overlays (PAI, IFFI). */
  readonly VITE_GEOSERVER_WMS_URL?: string;
  readonly VITE_MAP_GLYPHS_URL?: string;
}

const env: ViteEnv =
  typeof import.meta !== "undefined" && import.meta.env
    ? (import.meta.env as ViteEnv)
    : {};

export const num = (raw: string | undefined, fallback: number): number => {
  // Una variabile non impostata arriva da Docker come stringa **vuota**, e
  // `Number("")` vale 0, non NaN: con `VITE_DEFAULT_LON`/`_LAT` vuote la
  // mappa si apriva a 0°,0° — in mezzo all'Atlantico — invece che sull'area
  // configurata. Vuoto significa "non impostato", non "zero".
  if (raw === undefined || raw.trim() === "") return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export const bool = (raw: string | undefined, fallback: boolean): boolean => {
  // Stessa ragione di `num`: vuoto e' "non impostato", e un default `true`
  // non deve diventare `false` solo perche' il compose passa la variabile.
  if (raw === undefined || raw.trim() === "") return fallback;
  return ["1", "true", "yes", "on"].includes(raw.toLowerCase());
};

export const config = {
  apiUrl: env.VITE_API_URL ?? "http://localhost:8080",
  tileservUrl: env.VITE_TILESERV_URL ?? "http://localhost:7800",
  enableGraph: bool(env.VITE_ENABLE_GRAPH, false),
  defaultLon: num(env.VITE_DEFAULT_LON, 16.6),
  defaultLat: num(env.VITE_DEFAULT_LAT, 40.5),
  defaultZoom: num(env.VITE_DEFAULT_ZOOM, 7),
  // Phase 12 — optional static PMTiles produced by
  // `limen geodata make-pmtiles`. When unset the layers are not added.
  paiPmtilesUrl: env.VITE_PAI_PMTILES_URL,
  iffiPmtilesUrl: env.VITE_IFFI_PMTILES_URL,
  // `||` e non `??`: passata da Docker una variabile non impostata arriva
  // come stringa **vuota**, e `??` la considererebbe un valore valido. Con i
  // glifi il risultato e' uno stile senza caratteri, cioe' di nuovo la mappa
  // bianca — verificato sul bundle prodotto, che non conteneva l'URL.
  geoserverWmsUrl:
    env.VITE_GEOSERVER_WMS_URL || "http://localhost:8081/geoserver/ispra/wms",
  // Da dove MapLibre prende i caratteri per le etichette. Senza questa voce
  // lo stile non e' valido: un livello `symbol` con `text-field` la pretende,
  // e MapLibre rifiuta lo stile **intero** — mappa completamente bianca,
  // sfondo compreso, con un solo errore in console.
  // Il default e' un server pubblico perche' la mappa deve funzionare appena
  // installata, come gia' accade per lo sfondo OpenStreetMap; un deployment
  // che non vuole dipendenze esterne punta questa variabile ai propri glifi.
  mapGlyphsUrl:
    env.VITE_MAP_GLYPHS_URL || "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
} as const;
