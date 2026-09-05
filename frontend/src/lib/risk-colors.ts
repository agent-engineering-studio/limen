// Five-class risk palette + legend labels.
//
// Palette: ColorBrewer "YlOrRd" 5-class (colorblind-safe; WCAG-AA
// contrast against white for the text labels rendered on top).
// Reference: https://colorbrewer2.org/?type=sequential&scheme=YlOrRd&n=5
//
// We use **labels** in the legend (not just colours) so the map stays
// readable without colour vision.

import type { HazardType, RiskLevel } from "../types";

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
 * MapLibre `match` expression for paint-fill-color binding against a
 * pg_tileserv layer's class attribute (`risk_level` for cell/region tiles,
 * `worst_class` for the comune rollup). Features without an assessment yet
 * fall through to a neutral light grey.
 */
// Una rampa per pericolo (#62, #63). Non decorazione: con tre pericoli sulla
// stessa mappa il colore è l'unico indizio immediato di *cosa* si sta
// guardando, e tre mappe rosso-arancio identiche si confondono.
//
// Tutte e tre sono sequenze ColorBrewer a 5 classi, scelte per restare
// distinguibili fra loro anche in simulazione daltonica: YlOrRd per le frane,
// YlOrBr per l'incendio (caldo, vicino ma più terroso), PuBu per l'alluvione
// — l'acqua è l'unica delle tre che non si legge come "caldo", ed è giusto
// che sia l'unica fredda.
//
// Le classi, le etichette e i range restano quelli: cambia solo la tinta.
const WILDFIRE_COLORS: Record<RiskLevel, string> = {
  None: "#ffffd4",
  Low: "#fed98e",
  Moderate: "#fe9929",
  High: "#d95f0e",
  VeryHigh: "#993404",
};

const FLOOD_COLORS: Record<RiskLevel, string> = {
  None: "#f1eef6",
  Low: "#bdc9e1",
  Moderate: "#74a9cf",
  High: "#2b8cbe",
  VeryHigh: "#045a8d",
};

const COLORS_BY_HAZARD: Record<string, Record<RiskLevel, string>> = {
  wildfire: WILDFIRE_COLORS,
  flood: FLOOD_COLORS,
};

export function riskClassesFor(hazard: HazardType): readonly RiskClass[] {
  const colors = COLORS_BY_HAZARD[hazard];
  if (!colors) return RISK_CLASSES;
  return RISK_CLASSES.map((c) => ({ ...c, color: colors[c.level] }));
}

export function riskColorsFor(hazard: HazardType): Record<RiskLevel, string> {
  return COLORS_BY_HAZARD[hazard] ?? RISK_COLOR_BY_LEVEL;
}

export function maplibreColorMatch(
  prop = "risk_level",
  hazard: HazardType = "landslide",
): unknown {
  const colors = riskColorsFor(hazard);
  const stops: unknown[] = ["match", ["get", prop]];
  for (const c of RISK_CLASSES) {
    stops.push(c.level, colors[c.level]);
  }
  stops.push("#dadcdf");
  return stops;
}
