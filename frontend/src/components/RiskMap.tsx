import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { config } from "../lib/env";
import { maplibreColorMatch } from "../lib/risk-colors";

const SOURCE_ID = "limen-risk";
const LAYER_ID = "limen-risk-fill";

export interface RiskMapProps {
  /** Override the pg_tileserv base URL; useful in tests. */
  readonly tileservUrl?: string;
  /** Layer/function name pg_tileserv exposes the matview as. */
  readonly tileLayer?: string;
  /** Callback when the user clicks a cell — surfaces the cell_id. */
  readonly onCellClick?: (cellId: string) => void;
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
  const tileLayer = props.tileLayer ?? "public.mv_latest_risk";
  const onCellClick = props.onCellClick;

  useEffect(() => {
    if (!containerRef.current) return;

    const tilesUrl = `${tileserv}/${tileLayer}/{z}/{x}/{y}.pbf`;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
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
        },
        layers: [
          { id: "osm", type: "raster", source: "osm" },
          {
            id: LAYER_ID,
            type: "fill",
            source: SOURCE_ID,
            "source-layer": tileLayer.replace(/^public\./, ""),
            paint: {
              "fill-color": maplibreColorMatch() as never,
              "fill-opacity": 0.55,
              "fill-outline-color": "#333",
            },
          },
        ],
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

    return () => {
      map.remove();
      if (props.mapRef) {
        props.mapRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tileserv, tileLayer]);

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
