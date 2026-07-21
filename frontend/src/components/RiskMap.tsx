import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";

import { config } from "../lib/env";
import { maplibreColorMatch } from "../lib/risk-colors";

const SOURCE_ID = "limen-risk";
const LAYER_ID = "limen-risk-fill";
const SELECTED_LAYER_ID = "limen-risk-selected";
const REGION_SOURCE_ID = "limen-region";
const REGION_LAYER_ID = "limen-region-fill";
const COMUNE_SOURCE_ID = "limen-comune";
const COMUNE_LAYER_ID = "limen-comune-fill";
const COMUNE_BADGE_ID = "limen-comune-badge";
const COMUNE_MIN_ZOOM = 7;
const COMUNE_MAX_ZOOM = 11;
// Sotto questo zoom una cella da 1 km è sub-pixel: mostriamo il
// choropleth regionale (20 poligoni) invece dei 312k poligoni cella.
const CELL_MIN_ZOOM = 7;
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

export interface RiskMapProps {
  /** Override the pg_tileserv base URL; useful in tests. */
  readonly tileservUrl?: string;
  /** Layer/function name pg_tileserv exposes the matview as. */
  readonly tileLayer?: string;
  /** Callback when the user clicks a cell — surfaces the cell_id. */
  readonly onCellClick?: (cellId: string) => void;
  /** Cell to outline on the map (selection from the sidebar or a click). */
  readonly selectedCellId?: string | null;
  /** Imperative ref for tests / parent controls (e.g. fly-to). */
  readonly mapRef?: { current: maplibregl.Map | null };
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
  const containerRef = useRef<HTMLDivElement | null>(null);
  const tileserv = (props.tileservUrl ?? config.tileservUrl).replace(/\/+$/, "");
  const tileLayer = props.tileLayer ?? "public.v_risk_tiles";
  const onCellClick = props.onCellClick;

  useEffect(() => {
    if (!containerRef.current) return;

    // Register the `pmtiles://` protocol once — required only when the
    // PAI / IFFI overlays are configured, but cheap to do unconditionally.
    if (config.paiPmtilesUrl || config.iffiPmtilesUrl) {
      ensurePmtilesProtocol();
    }

    const tilesUrl = `${tileserv}/${tileLayer}/{z}/{x}/{y}.pbf`;

    // Build the source set lazily so optional PMTiles overlays only
    // appear when their env URL is set — see `docs/geodata.md`.
    const sources: maplibregl.StyleSpecification["sources"] = {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors",
      },
      [SOURCE_ID]: {
        type: "vector",
        tiles: [tilesUrl],
        minzoom: 5,
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
        tiles: [`${tileserv}/public.mv_comune_risk/{z}/{x}/{y}.pbf`],
        minzoom: 6,
        maxzoom: 12,
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
      { id: "osm", type: "raster", source: "osm" },
      {
        id: "wms-pai-layer",
        type: "raster",
        source: "wms-pai",
        paint: { "raster-opacity": 0.6 },
        layout: { visibility: "none" },
      },
      {
        id: "wms-iffi-layer",
        type: "raster",
        source: "wms-iffi",
        paint: { "raster-opacity": 0.7 },
        layout: { visibility: "none" },
      },
      {
        id: REGION_LAYER_ID,
        type: "fill",
        source: REGION_SOURCE_ID,
        "source-layer": "public.v_region_tiles",
        maxzoom: CELL_MIN_ZOOM,
        paint: {
          "fill-color": maplibreColorMatch() as never,
          "fill-opacity": 0.45,
          "fill-outline-color": "#555",
        },
      },
      {
        id: COMUNE_LAYER_ID,
        type: "fill",
        source: COMUNE_SOURCE_ID,
        "source-layer": "public.mv_comune_risk",
        minzoom: COMUNE_MIN_ZOOM,
        maxzoom: COMUNE_MAX_ZOOM,
        paint: {
          "fill-color": maplibreColorMatch("worst_class") as never,
          "fill-opacity": 0.5,
          "fill-outline-color": "#ffffff",
        },
      },
      {
        // Count of alerting cells — only on High+ comuni (keeps it uncluttered).
        id: COMUNE_BADGE_ID,
        type: "symbol",
        source: COMUNE_SOURCE_ID,
        "source-layer": "public.mv_comune_risk",
        minzoom: COMUNE_MIN_ZOOM,
        maxzoom: COMUNE_MAX_ZOOM,
        filter: ["in", ["get", "worst_class"], ["literal", ["High", "VeryHigh"]]],
        layout: {
          "text-field": ["to-string", ["get", "n_alert"]],
          "text-size": 12,
        },
        paint: {
          "text-color": "#ffffff",
          "text-halo-color": "#1a2733",
          "text-halo-width": 1.5,
        },
      },
      {
        id: LAYER_ID,
        type: "fill",
        source: SOURCE_ID,
        "source-layer": tileLayer,
        minzoom: CELL_MIN_ZOOM,
        paint: {
          "fill-color": maplibreColorMatch() as never,
          "fill-opacity": 0.55,
          "fill-outline-color": "#333",
        },
      },
      {
        // Selection outline: the filter starts matching nothing and is
        // swapped in the selectedCellId effect below.
        id: SELECTED_LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        "source-layer": tileLayer,
        paint: {
          "line-color": "#2456a3",
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
          "fill-outline-color": "#555",
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
          "circle-color": "#7a0177",
          "circle-stroke-color": "#ffffff",
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
        sources,
        layers,
      },
      center: [config.defaultLon, config.defaultLat],
      zoom: config.defaultZoom,
    });

    if (props.mapRef) {
      props.mapRef.current = map;
    }

    map.addControl(new maplibregl.NavigationControl(), "top-right");

    if (onCellClick) {
      map.on("click", LAYER_ID, (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
        const cellId = e.features?.[0]?.properties?.["cell_id"];
        if (typeof cellId === "string") {
          onCellClick(cellId);
        }
      });
    }
    // Click su una regione a zoom nazionale → zoom fino alle celle.
    map.on("click", REGION_LAYER_ID, (e: maplibregl.MapMouseEvent) => {
      map.easeTo({ center: e.lngLat, zoom: CELL_MIN_ZOOM + 1 });
    });
    map.on("mouseenter", REGION_LAYER_ID, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", REGION_LAYER_ID, () => {
      map.getCanvas().style.cursor = "";
    });

    // Comune drill-down: click a comune → zoom into its cells.
    map.on("click", COMUNE_LAYER_ID, (e: maplibregl.MapMouseEvent) => {
      map.easeTo({ center: e.lngLat, zoom: CELL_MIN_ZOOM + 2 });
    });
    map.on("mouseenter", COMUNE_LAYER_ID, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", COMUNE_LAYER_ID, () => {
      map.getCanvas().style.cursor = "";
    });

    return () => {
      map.remove();
      if (props.mapRef) {
        props.mapRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tileserv, tileLayer]);

  // Update the selection outline without rebuilding the map.
  useEffect(() => {
    const map = props.mapRef?.current;
    if (!map) return;
    const apply = (): void => {
      if (!map.getLayer(SELECTED_LAYER_ID)) return;
      map.setFilter(SELECTED_LAYER_ID, [
        "==",
        ["get", "cell_id"],
        props.selectedCellId ?? "__none__",
      ]);
    };
    if (map.isStyleLoaded()) apply();
    else map.once("idle", apply);
  }, [props.selectedCellId, props.mapRef]);

  return (
    <div
      ref={containerRef}
      className="map-container"
      data-testid="risk-map"
      data-tile-url={`${tileserv}/${tileLayer}/{z}/{x}/{y}.pbf`}
      style={{ width: "100%", height: "100%" }}
      aria-label="Mappa interattiva del rischio frane"
    />
  );
}

export default RiskMap;
