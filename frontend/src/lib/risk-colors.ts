// Five-class risk palette + legend labels.
//
// Palette: ColorBrewer "YlOrRd" 5-class (colorblind-safe; WCAG-AA
// contrast against white for the text labels rendered on top).
// Reference: https://colorbrewer2.org/?type=sequential&scheme=YlOrRd&n=5
//
// We use **labels** in the legend (not just colours) so the map stays
// readable without colour vision.

import type { RiskLevel } from "../types";

export interface RiskClass {
  level: RiskLevel;
  label: string;
  short: string;
  color: string;
  range: readonly [number, number];
}

export const RISK_CLASSES: readonly RiskClass[] = [
  {
    level: "None",
    label: "Nessuno",
    short: "Ø",
    color: "#ffffb2",
    range: [0.0, 0.15],
  },
  {
    level: "Low",
    label: "Basso",
    short: "L",
    color: "#fecc5c",
    range: [0.15, 0.35],
  },
  {
    level: "Moderate",
    label: "Moderato",
    short: "M",
    color: "#fd8d3c",
    range: [0.35, 0.55],
  },
  {
    level: "High",
    label: "Alto",
    short: "H",
    color: "#f03b20",
    range: [0.55, 0.75],
  },
  {
    level: "VeryHigh",
    label: "Molto alto",
    short: "VH",
    color: "#bd0026",
    range: [0.75, 1.0],
  },
] as const;

export const RISK_COLOR_BY_LEVEL: Record<RiskLevel, string> =
  Object.fromEntries(RISK_CLASSES.map((c) => [c.level, c.color])) as Record<
    RiskLevel,
    string
  >;

export const RISK_LABEL_IT_BY_LEVEL: Record<RiskLevel, string> =
  Object.fromEntries(RISK_CLASSES.map((c) => [c.level, c.label])) as Record<
    RiskLevel,
    string
  >;

/**
 * MapLibre `match` expression for paint-fill-color binding against the
 * pg_tileserv layer's `risk_level` attribute. Cells without an
 * assessment yet fall through to a neutral light grey.
 */
export function maplibreColorMatch(): unknown {
  const stops: unknown[] = ["match", ["get", "risk_level"]];
  for (const c of RISK_CLASSES) {
    stops.push(c.level, c.color);
  }
  stops.push("#dadcdf");
  return stops;
}
