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

export type GruppoOverlay = "landslide" | "flood" | "wildfire";

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
}

export const OVERLAYS: readonly Overlay[] = [
  {
    id: "pai",
    gruppo: "landslide",
    label: "Pericolosità frana (PAI)",
    fonte: "ISPRA",
    layerIds: ["wms-pai-layer"],
  },
  {
    id: "iffi",
    gruppo: "landslide",
    label: "Frane censite (IFFI)",
    fonte: "ISPRA",
    layerIds: ["wms-iffi-layer"],
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
  },
  {
    id: "alluvioni",
    gruppo: "flood",
    label: "Alluvioni osservate",
    fonte: "Copernicus EMS, 2023-2026",
    layerIds: ["ovl-alluvioni-fill", "ovl-alluvioni-line"],
    minzoom: 8,
  },
  {
    id: "bruciate",
    gruppo: "wildfire",
    label: "Aree bruciate",
    fonte: "EFFIS, 2012-2026",
    layerIds: ["ovl-bruciate-fill", "ovl-bruciate-line"],
    minzoom: 6,
  },
];

export const NOME_GRUPPO: Record<GruppoOverlay, string> = {
  landslide: "Frane",
  flood: "Alluvioni",
  wildfire: "Incendi",
};
