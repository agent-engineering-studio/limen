// Mappa della divergenza champion↔IA (#26) — SOLO nell'area diagnostica
// ml-ops, mai nella dashboard operatore. Palette DIVERGENTE e neutra
// (blu↔grigio↔viola), deliberatamente diversa dalla YlOrRd del rischio: qui
// il colore significa "disaccordo tra modelli", non "pericolo".

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { config } from "../lib/env";

const SOURCE_ID = "limen-divergence";
const LAYER_ID = "limen-divergence-fill";
const TILE_LAYER = "public.v_shadow_divergence_tiles";

// Divergenza = prob. IA − punteggio ufficiale, in [-1, 1] (tipicamente piccola).
// Dominio grafico limitato a ±0.5: oltre, satura.
const DIVERGENCE_COLOR: maplibregl.ExpressionSpecification = [
  "interpolate",
  ["linear"],
  ["get", "divergence"],
  -0.5,
  "#2166ac", // IA vede molto MENO rischio
  0,
  "#e6e6e6", // d'accordo
  0.5,
  "#762a83", // IA vede molto PIÙ rischio
];

export interface DivergenceMapProps {
  readonly tileservUrl?: string;
}

export default function DivergenceMap(props: DivergenceMapProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const tileserv = (props.tileservUrl ?? config.tileservUrl).replace(/\/+$/, "");
  const tilesUrl = `${tileserv}/${TILE_LAYER}/{z}/{x}/{y}.pbf`;

  useEffect(() => {
    if (!containerRef.current) return;
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
            "source-layer": TILE_LAYER,
            paint: {
              "fill-color": DIVERGENCE_COLOR,
              "fill-opacity": 0.6,
              "fill-outline-color": "#888",
            },
          },
        ],
      },
      center: [config.defaultLon, config.defaultLat],
      zoom: config.defaultZoom,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    return () => map.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tileserv]);

  return (
    <div className="divergence-map-wrap">
      <div
        ref={containerRef}
        className="divergence-map"
        data-testid="divergence-map"
        data-tile-url={tilesUrl}
        aria-label="Mappa della divergenza tra sistema ufficiale e modello IA"
      />
      <div className="divergence-legend" aria-label="Legenda della divergenza">
        <span>
          <span className="dv-swatch" style={{ background: "#2166ac" }} aria-hidden />
          l&apos;IA vede <strong>meno</strong> rischio
        </span>
        <span>
          <span className="dv-swatch" style={{ background: "#e6e6e6" }} aria-hidden />
          d&apos;accordo
        </span>
        <span>
          <span className="dv-swatch" style={{ background: "#762a83" }} aria-hidden />
          l&apos;IA vede <strong>più</strong> rischio
        </span>
      </div>
    </div>
  );
}
