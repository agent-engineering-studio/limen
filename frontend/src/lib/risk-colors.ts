// Five-class risk palette + legend labels.
//
// Una scala per il fondo scuro della sala operativa (#155): nessuno quasi
// invisibile, basso un verde petrolio spento, poi giallo, arancio e rosso —
// l'ordine delle allerte della Protezione civile, che chi legge questa
// mappa conosce già.
//
// Non è la scala del design così com'era: lì alta e molto alta stavano a
// 1,36:1 fra loro e scendevano a 1,25:1 per un deuteranope. Questa è stata
// cercata perché **ogni coppia** di classi, non solo le adiacenti, resti
// sopra 1,5:1 di contrasto di luminanza anche in simulazione di
// deuteranopia, protanopia e tritanopia (Machado 2009), con le celle
// dipinte al 70 % sopra la base scura. La tinta aggiunge separazione a chi
// la vede; la luminanza è quello che resta a chi non la vede.
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
    color: "#151c25",
    range: [0.0, 0.15],
  },
  {
    level: "Low",
    label: "Basso",
    short: "L",
    color: "#134d47",
    range: [0.15, 0.35],
  },
  {
    level: "Moderate",
    label: "Moderato",
    short: "M",
    color: "#f2d45c",
    range: [0.35, 0.55],
  },
  {
    level: "High",
    label: "Alto",
    short: "H",
    color: "#f58a30",
    range: [0.55, 0.75],
  },
  {
    level: "VeryHigh",
    label: "Molto alto",
    short: "VH",
    color: "#e33f5a",
    range: [0.75, 1.0],
  },
] as const;

export const RISK_COLOR_BY_LEVEL: Record<RiskLevel, string> =
  Object.fromEntries(RISK_CLASSES.map((c) => [c.level, c.color])) as Record<
    RiskLevel,
    string
  >;

/**
 * Il colore di classe quando è **testo** sul fondo scuro.
 *
 * Nessuno e basso sono tinte scure per scelta — la mappa non deve
 * accendersi dove non succede niente — e come cifre su un pannello scuro
 * sparirebbero (1,9:1 il verde petrolio). Qui schiarite fin sopra 4,5:1;
 * dalla moderata in su la tinta della mappa basta già.
 */
export const RISK_TEXT_BY_LEVEL: Record<RiskLevel, string> = {
  ...Object.fromEntries(RISK_CLASSES.map((c) => [c.level, c.color])),
  None: "#94a3b4",
  Low: "#5fb3a3",
} as Record<RiskLevel, string>;

/** Le classi scure, su cui il testo di un chip va chiaro e non scuro. */
export const RISK_SCURE: ReadonlySet<RiskLevel> = new Set<RiskLevel>(["None", "Low"]);

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
// Una scala sola per i tre pericoli (#155). Con tre rampe diverse la stessa
// cella cambiava colore passando dalla vista d'insieme a quella del
// pericolo che la determina; ora quale pericolo lo dicono l'intestazione
// della mappa, il bordo e le lettere F/A/I, e il colore dice solo quanto.
// Le funzioni restano per pericolo perché è la domanda giusta da fare.
export function riskClassesFor(_hazard: HazardType): readonly RiskClass[] {
  return RISK_CLASSES;
}

export function riskColorsFor(_hazard: HazardType): Record<RiskLevel, string> {
  return RISK_COLOR_BY_LEVEL;
}

/**
 * Il grigio di «non lo so».
 *
 * Lo stesso per una cella non ancora valutata e per una valutata senza il
 * dato che le serviva (#143): a chi guarda dicono la stessa cosa, e la scala
 * del rischio ha cinque classi proprio perché una sesta tinta la renderebbe
 * illeggibile. Il perché della differenza sta nel popup e nella colonna,
 * dove c'è lo spazio per scriverlo a parole.
 */
export const COLORE_IGNOTO = "#4f5965";

export function maplibreColorMatch(
  prop = "risk_level",
  hazard: HazardType = "landslide",
): unknown {
  const colors = riskColorsFor(hazard);
  const stops: unknown[] = ["match", ["get", prop]];
  for (const c of RISK_CLASSES) {
    stops.push(c.level, colors[c.level]);
  }
  stops.push(COLORE_IGNOTO);
  // `measured` falso ⇒ neutro, prima di ogni classe. Un punteggio zero per
  // assenza di misura, dipinto in fondo alla scala, si legge come una buona
  // notizia: è l'unico posto in cui questo sistema sbaglierebbe in direzione
  // rassicurante. Le tile scritte prima che la colonna esistesse non hanno
  // l'attributo, e `!=` su un attributo assente è falso: restano colorate,
  // che è il comportamento giusto per «non lo sappiamo».
  return ["case", ["==", ["get", "measured"], false], COLORE_IGNOTO, stops];
}

/**
 * Colore per la vista "tutti i pericoli": **una scala sola**.
 *
 * Portava due informazioni in un canale — la tinta diceva quale pericolo
 * domina, l'intensità quanto è grave — e sono due dimensioni in un colore:
 * quella vista si guardava una volta e non si usava, perché per decodificarla
 * serviva la legenda a matrice 5×3 accanto.
 *
 * Ora il colore dice **quanto**, sempre e solo. Quale pericolo lo dicono il
 * bordo delle celle in classe alta (:func:`maplibreWorstHazardLine`), il
 * popup e la colonna, dove c'è lo spazio per scriverlo a parole.
 *
 * Le rampe per pericolo sono state unificate (#155): una cella ha lo stesso
 * colore nella vista d'insieme e in quella del pericolo che la determina.
 *
 * `worst_level` è l'attributo di `v_multi_hazard` (migrazione 037); il
 * ripiego copre le celle senza valutazione.
 */
export function maplibreMultiHazardColorMatch(): unknown {
  return maplibreColorMatch("worst_level", "landslide");
}

/**
 * Identità dei pericoli: le stesse di `--hz-*` in styles.css.
 *
 * Lilla, ciano e rosa, fuori dalle tinte della scala: il rosso del design
 * per l'incendio stava a 1,29:1 da «molto alto», e un chip «I» si leggeva
 * come un allarme. Sono anche il bordo delle celle in classe alta, dove un
 * bordo arancio su una cella arancio non si vedrebbe.
 */
export const HAZARD_HUE: Record<HazardType, string> = {
  landslide: "#c6a8ff",
  wildfire: "#ff9ad5",
  flood: "#6fd3ee",
};

/**
 * Bordo che dice **quale** pericolo, sulle sole celle in classe alta.
 *
 * Solo lì perché è dove la domanda nasce: davanti a una cella scura si vuole
 * sapere di cosa, davanti a una chiara no — e un bordo colorato su ogni cella
 * ridarebbe alla mappa il rumore che questa modifica toglie.
 */
export function maplibreWorstHazardLine(): unknown {
  const stops: unknown[] = ["match", ["get", "worst_hazard"]];
  for (const [hazard, hue] of Object.entries(HAZARD_HUE)) {
    stops.push(hazard, hue);
  }
  stops.push("#7a7f8a");
  return stops;
}
