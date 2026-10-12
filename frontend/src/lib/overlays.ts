// I livelli di contesto della mappa, per pericolo, in un posto solo.
//
// Il pannello e la mappa li leggevano da due elenchi separati, e lo stato
// acceso/spento viveva solo nel pannello: quando la mappa si ricostruiva —
// a ogni cambio di pericolo — i livelli tornavano spenti mentre la casella
// restava spuntata. Ora l'elenco è questo, e lo stato sta in `App`.
//
// Per ogni pericolo due livelli, la stessa coppia: dove la **pericolosità**
// è mappata ufficialmente, e dove l'evento è **già successo**. Per le frane
// erano gli unici due; alluvione e incendio avevano i dati nel database — le
// tile le pubblicava già pg_tileserv — e nessun interruttore.

import type { Lingua } from "./i18n";

export type GruppoOverlay = "ufficiale" | "landslide" | "flood" | "wildfire";

export interface Overlay {
  /** Chiave dello stato acceso/spento. */
  id: string;
  gruppo: GruppoOverlay;
  label: string;
  fonte: string;
  /** I livelli MapLibre che l'interruttore accende insieme. */
  layerIds: readonly string[];
  /** Da che zoom il livello compare: sotto, le tile peserebbero troppo. */
  minzoom?: number;
  /** Le classi, per la legenda accanto all'interruttore. */
  classi?: readonly { colore: string; label: string }[];
  /** Nome, fonte e classi in inglese, nello stesso ordine. */
  en: { label: string; fonte: string; classi?: readonly string[] };
}

/** Nome, fonte e classi di un livello nella lingua chiesta. */
export function testoOverlay(
  o: Overlay,
  lingua: Lingua,
): { label: string; fonte: string; classi: readonly { colore: string; label: string }[] } {
  const classi = o.classi ?? [];
  if (lingua === "it") return { label: o.label, fonte: o.fonte, classi };
  return {
    label: o.en.label,
    fonte: o.en.fonte,
    classi: classi.map((c, i) => ({ colore: c.colore, label: o.en.classi?.[i] ?? c.label })),
  };
}

/** I colori delle allerte ufficiali: quelli della Protezione Civile, non la
 *  nostra scala — sono un'altra fonte, e devono leggersi come tale. */
export const COLORE_ALLERTA: Record<number, string> = {
  0: "#4caf50",
  1: "#ffd400",
  2: "#ff8c00",
  3: "#e2001a",
};

export const OVERLAYS: readonly Overlay[] = [
  {
    id: "dpc",
    gruppo: "ufficiale",
    label: "Allerte Protezione Civile (oggi)",
    fonte: "DPC, bollettino di criticità nazionale (CC-BY 4.0)",
    layerIds: ["ovl-dpc-fill", "ovl-dpc-line"],
    classi: [
      { colore: COLORE_ALLERTA[1] ?? "", label: "gialla" },
      { colore: COLORE_ALLERTA[2] ?? "", label: "arancione" },
      { colore: COLORE_ALLERTA[3] ?? "", label: "rossa" },
    ],
    en: {
      label: "Civil Protection warnings (today)",
      fonte: "DPC, national criticality bulletin (CC-BY 4.0)",
      classi: ["yellow", "orange", "red"],
    },
  },
  {
    id: "pai",
    gruppo: "landslide",
    label: "Pericolosità frana (PAI)",
    fonte: "ISPRA",
    layerIds: ["wms-pai-layer"],
    en: { label: "Landslide hazard (PAI)", fonte: "ISPRA" },
  },
  {
    id: "iffi",
    gruppo: "landslide",
    label: "Frane censite (IFFI)",
    fonte: "ISPRA",
    layerIds: ["wms-iffi-layer"],
    en: { label: "Mapped landslides (IFFI)", fonte: "ISPRA" },
  },
  {
    id: "idraulica",
    gruppo: "flood",
    label: "Pericolosità idraulica",
    fonte: "ISPRA, mosaico PGRA",
    layerIds: ["ovl-idraulica-fill", "ovl-idraulica-line"],
    // Da 10: a zoom 8 una tile pesa 1,1 MB e la versione non suddivisa va
    // in timeout. A 10 sono 350 KB in 0,15 s, a 12 40 KB in 36 ms.
    minzoom: 10,
    classi: [
      { colore: "#08519c", label: "P3 alta" },
      { colore: "#3182bd", label: "P2 media" },
      { colore: "#9ecae1", label: "P1 bassa" },
    ],
    en: {
      label: "Hydraulic hazard",
      fonte: "ISPRA, PGRA mosaic",
      classi: ["P3 high", "P2 medium", "P1 low"],
    },
  },
  {
    id: "alluvioni",
    gruppo: "flood",
    label: "Alluvioni osservate",
    fonte: "Copernicus EMS, 2023-2026",
    layerIds: ["ovl-alluvioni-fill", "ovl-alluvioni-line"],
    minzoom: 8,
    en: { label: "Observed floods", fonte: "Copernicus EMS, 2023-2026" },
  },
  {
    id: "bruciate",
    gruppo: "wildfire",
    label: "Aree bruciate",
    fonte: "EFFIS, 2012-2026",
    layerIds: ["ovl-bruciate-fill", "ovl-bruciate-line"],
    minzoom: 6,
    en: { label: "Burnt areas", fonte: "EFFIS, 2012-2026" },
  },
];

export const NOME_GRUPPO: Record<Lingua, Record<GruppoOverlay, string>> = {
  it: {
    ufficiale: "Allertamento ufficiale",
    landslide: "Frane",
    flood: "Allagamenti",
    wildfire: "Incendi",
  },
  en: {
    ufficiale: "Official warnings",
    landslide: "Landslides",
    flood: "Floods",
    wildfire: "Wildfires",
  },
};
