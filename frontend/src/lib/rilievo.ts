// La vista «Rilievo» (#319): la stessa mappa con il terreno sotto il rischio.
//
// Le costanti stanno qui e non nel componente perché il test di contrasto
// (`risk-colors.test.ts`) le legge: le celle al 70 % si dipingono sopra
// l'ombreggiatura, e la scala va verificata sul fondo in ombra e in luce, non
// solo su quello piatto (#322).

import { useMemo } from "react";

import { config } from "./env";
import { testi, useLingua, type Lingua } from "./i18n";

export const DEM_SOURCE_ID = "limen-dem";
export const HILLSHADE_LAYER_ID = "limen-rilievo-ombre";

/** Le esagerazioni che si possono scegliere: ×1 è il rilievo vero, e deve
 *  esserci sempre (#322). Quella di partenza è dichiarata in legenda. */
export const ESAGERAZIONI: readonly number[] = [1, 1.5];
export const ESAGERAZIONE_RILIEVO: number = 1.5;

/** Inclinazione della camera in «Rilievo»: il massimo di MapLibre è 60°. */
export const INCLINAZIONE_RILIEVO = 60;

/** I colori dell'ombreggiatura, quasi uguali al fondo piatto (#10161d).
 *
 *  Le celle sono trasparenti al 30 %, e due celle vicine su un crinale
 *  stanno una in luce e l'altra in ombra: la scala va distinta anche fra
 *  fondi diversi, non solo sullo stesso. Sul fondo piatto la coppia più
 *  stretta vale 1,511:1 (protanopia, «basso» e «molto alto»), quindi resta
 *  pochissimo margine: con l'ombra a #0b1118 e la luce uguale al fondo il
 *  minimo fra fondi è 1,503:1; con l'ombra a #06090d e la luce a #141b23
 *  scendeva a 1,469:1. Il rilievo lo dà soprattutto il terreno inclinato,
 *  non l'ombreggiatura. */
export const OMBREGGIATURA = {
  ombra: "#0b1118",
  luce: "#10161d",
  accento: "#0d131a",
} as const;

const T = testi(
  {
    senzaDem: "Rilievo non disponibile: questo sito non ha le tile del terreno (VITE_DEM_PMTILES_URL).",
    senzaWebgl2: "Rilievo non disponibile: il browser non supporta WebGL2.",
    senza3d: "La vista 3D arriva con #321.",
  },
  {
    senzaDem: "Relief unavailable: this site has no terrain tiles (VITE_DEM_PMTILES_URL).",
    senzaWebgl2: "Relief unavailable: the browser does not support WebGL2.",
    senza3d: "The 3D view comes with #321.",
  },
);

export function supportaWebgl2(): boolean {
  try {
    return document.createElement("canvas").getContext("webgl2") != null;
  } catch {
    return false;
  }
}

/** Perché «Rilievo» non si può accendere, o `null` se si può. */
export function motivoSenzaRilievo(
  lingua: Lingua,
  demUrl: string | undefined = config.demPmtilesUrl,
  webgl2: () => boolean = supportaWebgl2,
): string | null {
  if (!demUrl) return T[lingua].senzaDem;
  if (!webgl2()) return T[lingua].senzaWebgl2;
  return null;
}

export function useMotivoSenzaRilievo(): string | null {
  const { lingua } = useLingua();
  return useMemo(() => motivoSenzaRilievo(lingua), [lingua]);
}

export function motivoSenza3d(lingua: Lingua): string {
  return T[lingua].senza3d;
}

/** Chi chiede meno movimento non si vede la camera volare (#322). */
export function durataCamera(ms: number): number {
  return typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ? 0
    : ms;
}
