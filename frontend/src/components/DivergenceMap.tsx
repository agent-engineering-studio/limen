// Mappa della divergenza champion↔IA (#26) — SOLO nell'area diagnostica
// ml-ops, mai nella dashboard operatore. Palette DIVERGENTE e neutra
// (blu↔grigio↔viola), deliberatamente diversa dalla YlOrRd del rischio: qui
// il colore significa "disaccordo tra modelli", non "pericolo".

import { useEffect, useRef } from "react";
import type { JSX } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { config } from "../lib/env";
import { testi, useTesti } from "../lib/i18n";

const SOURCE_ID = "limen-divergence";
const LAYER_ID = "limen-divergence-fill";
const TILE_LAYER = "public.v_shadow_divergence_tiles";

// Divergenza = prob. IA − punteggio ufficiale, in [-1, 1] ma concentrata
// attorno a piccoli valori: dominio grafico ±0.3 (satura oltre) per dare
// contrasto, altrimenti la mappa appare di un colore quasi piatto.
const DIVERGENCE_COLOR: maplibregl.ExpressionSpecification = [
  "interpolate",
  ["linear"],
  ["get", "divergence"],
  -0.3,
  "#2166ac", // IA vede molto MENO rischio
  0,
  "#3a4655", // d'accordo
  0.3,
  "#762a83", // IA vede molto PIÙ rischio
];

const T = testi(
  {
    mappa: "Mappa della divergenza tra sistema ufficiale e modello IA",
    legenda: "Legenda della divergenza",
    vede: "l'IA vede ",
    meno: "meno",
    piu: "più",
    rischio: " rischio",
    accordo: "d'accordo",
  },
  {
    mappa: "Map of the divergence between the official system and the AI model",
    legenda: "Divergence legend",
    vede: "the AI sees ",
    meno: "less",
    piu: "more",
    rischio: " risk",
    accordo: "in agreement",
  },
);

export interface DivergenceMapProps {
  readonly tileservUrl?: string;
}

export default function DivergenceMap(props: DivergenceMapProps): JSX.Element {
  const t = useTesti(T);
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
              "fill-outline-color": "#2c3846",
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
        aria-label={t.mappa}
      />
      <div className="divergence-legend" aria-label={t.legenda}>
        <span>
          <span className="dv-swatch" style={{ background: "#2166ac" }} aria-hidden />
          {t.vede}
          <strong>{t.meno}</strong>
          {t.rischio}
        </span>
        <span>
          <span className="dv-swatch" style={{ background: "#3a4655" }} aria-hidden />
          {t.accordo}
        </span>
        <span>
          <span className="dv-swatch" style={{ background: "#762a83" }} aria-hidden />
          {t.vede}
          <strong>{t.piu}</strong>
          {t.rischio}
        </span>
      </div>
    </div>
  );
}
