import * as k from "../../iso/iso-kit";
import type { Flat, Plan, Point3, SolidPaths } from "../../iso/iso-kit";
import { CLASSI, COMPONENTI, PESI, type Componente } from "./model";

export const WIDTH = 600;
export const HEIGHT = 290;
const AZIMUTH = 56;
const ELEVAZIONE = 36;

// Punteggio 1 = 160 unità di corsa: ogni carrello scorre sopra quello sotto
// per al più peso × 160, quindi la posizione dell'ultimo è la somma pesata.
export const SCALA = 160;
const FERMO = 2;
const ZONA_POMELLO = 12;
const LIVELLO_H = 9;
const ROTAIA_H = 5;

export const CORSA: Record<Componente, number> = Object.fromEntries(COMPONENTI.map((c) => [c, PESI[c] * SCALA])) as Record<Componente, number>;

// Lunghezze dal carrello in cima verso il basso: ognuno deve portare la corsa
// del successivo, il successivo stesso, due fermi e il suo pomello.
const LUNGHEZZE: number[] = [];
{
  let sopra = 20;
  LUNGHEZZE[4] = sopra;
  for (let i = 3; i >= 0; i--) {
    sopra = FERMO + CORSA[COMPONENTI[i + 1]!] + sopra + FERMO + ZONA_POMELLO;
    LUNGHEZZE[i] = sopra;
  }
}
const BASE_L = FERMO + CORSA.s + LUNGHEZZE[0]! + FERMO;
const XB = -BASE_L / 2;
const PROFONDITA = [30, 26, 22, 18, 14];

export interface Carrello {
  componente: Componente;
  x: number;
  z: number;
  plan: Plan;
}

export const CARRELLI: Carrello[] = COMPONENTI.map((componente, i) => {
  const x = XB + FERMO * (i + 1);
  const d = PROFONDITA[i]!;
  return { componente, x, z: ROTAIA_H + LIVELLO_H * i, plan: { x, y: -d / 2, w: LUNGHEZZE[i]!, d, r: 1.2 } };
});

const CIMA = ROTAIA_H + LIVELLO_H * 5;
export const X_INDICE = CARRELLI[4]!.x + 6;
const FRONTE_SCALA = 22;

const PIASTRA: Plan = { x: XB - 16, y: -28, w: BASE_L + 32, d: 68, r: 8 };
const PIASTRA_H = 9;
const PIEDE_H = 4;

export const P = k.fitProjection(
  [...k.boxCorners(PIASTRA, -PIASTRA_H - PIEDE_H, 0), [XB, 0, CIMA + 3] as Point3, [XB + BASE_L, 0, CIMA + 3] as Point3],
  WIDTH,
  HEIGHT,
  { pad: 18, azimuth: AZIMUTH, elevation: ELEVAZIONE },
);

const slab = (plan: Plan, z: number, h: number, steps = 3, bevel = 0.3) => k.slabOf(plan, z, h, P, steps, bevel);
const top = (x: number, y: number, z: number): Flat => k.iso([x, y, z], P);

// ---- Base ------------------------------------------------------------------

const TARGA: Plan = { x: X_INDICE + SCALA + 14, y: FRONTE_SCALA - 1, w: 40, d: 13, r: 1.5 };
export const BASE = {
  halo: k.haloOf(PIASTRA, -PIASTRA_H - PIEDE_H, PIASTRA_H, P),
  feet: [...k.corners(PIASTRA, 16)]
    .sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P))
    .map(([x, y]) => ({ flange: k.cylinder(x, y, 6.5, -PIASTRA_H - PIEDE_H, 1.6, P, 28), foot: k.cylinder(x, y, 5, -PIASTRA_H - PIEDE_H + 1.6, PIEDE_H - 1.6, P, 28) })),
  slab: slab(PIASTRA, -PIASTRA_H, PIASTRA_H, 8, 1.6),
  seam: k.sideSeam(PIASTRA, -PIASTRA_H + 3, P, 8),
  groove: k.planOutline(k.insetPlan(PIASTRA, 5), 0, P),
  screws: k.corners(PIASTRA, 9).map(([x, y]) => k.ring(x, y, 2, 0, P, 16)).join(""),
  screwDots: k.corners(PIASTRA, 9).map(([x, y]) => top(x, y, 0)),
  label: slab(TARGA, 0, 0.8, 4, 0),
  labelInset: k.planOutline(k.insetPlan(TARGA, 1.6), 0.8, P),
  labelRules: [26, 18, 22].map((w, i) => k.lineOnTop([TARGA.x + 5, TARGA.y + 4 + i * 2.6], [TARGA.x + 5 + w, TARGA.y + 4 + i * 2.6], 0.8, P)).join(""),
  labelScrews: [top(TARGA.x + 2.6, TARGA.y + TARGA.d / 2, 0.8), top(TARGA.x + TARGA.w - 2.6, TARGA.y + TARGA.d / 2, 0.8)],
};

// La scala del punteggio, davanti: cinque fasce delle classi, tacche ogni 0,05.
const STRISCIA: Plan = { x: X_INDICE - 4, y: FRONTE_SCALA, w: SCALA + 8, d: 9, r: 1 };
const minori: string[] = [];
const maggiori: string[] = [];
for (let i = 0; i <= 20; i++) {
  const x = X_INDICE + (SCALA * i) / 20;
  (i % 2 === 0 ? maggiori : minori).push(k.lineOnTop([x, FRONTE_SCALA], [x, FRONTE_SCALA + (i % 2 === 0 ? 3.4 : 2)], 0.7, P));
}
export const SCALE = {
  strip: slab(STRISCIA, 0, 0.7, 3, 0),
  bands: CLASSI.map((classe) => ({
    level: classe.level,
    d: k.onTop(k.ringOf({ x: X_INDICE + SCALA * classe.da, y: FRONTE_SCALA + 5, w: SCALA * (classe.a - classe.da), d: 2.6, r: 0 }, 1), 0.7, P, true),
  })),
  minor: minori.join(""),
  major: maggiori.join(""),
};

// ---- La rotaia di base e i carrelli -------------------------------------

export interface Livello {
  body: SolidPaths;
  seam: string;
  groove: string;
  ticksMinor: string;
  ticksMajor: string;
  stopLeft: SolidPaths;
  stopRight: SolidPaths;
  stopDots: Flat[];
  knob: SolidPaths;
  knobKnurl: string;
  knobMark: string;
  screws: Flat[];
}

// Il piano su cui scorre il carrello `sopra`, e la sua corsa misurata.
function piano(plan: Plan, zTop: number, sopra: number, corsa: number, lunghezzaSopra: number): Omit<Livello, "body" | "seam" | "knob" | "knobKnurl" | "knobMark" | "screws"> {
  const d = PROFONDITA[sopra]! + 2;
  const inizio = plan.x + FERMO;
  const fine = inizio + corsa + lunghezzaSopra;
  const minor: string[] = [];
  const major: string[] = [];
  const fronte = plan.y + plan.d;
  for (let i = 0; i * 0.05 * SCALA <= corsa + 1e-6; i++) {
    const x = inizio + i * 0.05 * SCALA;
    (i % 2 === 0 ? major : minor).push(k.lineOnTop([x, fronte], [x, fronte - (i % 2 === 0 ? 1.8 : 1.1)], zTop, P));
  }
  return {
    groove: k.planOutline({ x: inizio, y: -d / 2, w: fine - inizio, d, r: 0.6 }, zTop, P, 3),
    ticksMinor: minor.join(""),
    ticksMajor: major.join(""),
    stopLeft: slab({ x: plan.x, y: -d / 2, w: FERMO, d, r: 0.4 }, zTop, 3),
    stopRight: slab({ x: fine, y: -d / 2, w: FERMO, d, r: 0.4 }, zTop, 3),
    stopDots: [top(plan.x + FERMO / 2, 0, zTop + 3), top(fine + FERMO / 2, 0, zTop + 3)],
  };
}

const ROTAIA: Plan = { x: XB, y: -17, w: BASE_L, d: 34, r: 1.5 };
export const RAIL = {
  body: slab(ROTAIA, 0, ROTAIA_H, 4, 0.5),
  seam: k.sideSeam(ROTAIA, 1.4, P, 4),
  ...piano(ROTAIA, ROTAIA_H, 0, CORSA.s, LUNGHEZZE[0]!),
};

export const LIVELLI: Livello[] = CARRELLI.map((carrello, i) => {
  const zTop = carrello.z + LIVELLO_H;
  const { plan } = carrello;
  const kx = plan.x + plan.w - ZONA_POMELLO / 2;
  const base = {
    body: slab(plan, carrello.z, LIVELLO_H, 3, 0.5),
    seam: k.sideSeam(plan, carrello.z + 3, P, 3),
    knob: k.cylinder(kx, 0, 4.2, zTop, 5, P, 32, 0.3),
    knobKnurl: k.knurl(kx, 0, 4.2, zTop, zTop + 5, 32, P, 0.3),
    knobMark: k.lineOnTop([kx, 0], [kx + 4.2, 0], zTop + 5, P),
    screws: [top(plan.x + 1.6, plan.y + 1.6, zTop), top(plan.x + plan.w - 1.6, plan.y + 1.6, zTop), top(plan.x + plan.w - 1.6, plan.y + plan.d - 1.6, zTop)],
  };
  if (i === 4) return { ...base, groove: "", ticksMinor: "", ticksMajor: "", stopLeft: { fill: "", outline: "", crease: "", top: "", shades: [] }, stopRight: { fill: "", outline: "", crease: "", top: "", shades: [] }, stopDots: [] };
  return { ...base, ...piano(plan, zTop, i + 1, CORSA[COMPONENTI[i + 1]!], LUNGHEZZE[i + 1]!) };
});

// ---- L'indice, portato dal carrello in cima -----------------------------

export const POINTER = {
  arm: slab({ x: X_INDICE - 1.5, y: -2, w: 3, d: FRONTE_SCALA, r: 0.6 }, CIMA, 2),
  drop: slab({ x: X_INDICE - 1.5, y: FRONTE_SCALA - 2.4, w: 3, d: 2.4, r: 0.6 }, 1.2, CIMA + 2 - 1.2),
  tip: k.lineOnTop([X_INDICE, FRONTE_SCALA], [X_INDICE, FRONTE_SCALA + 9], 0.7, P),
};

export const shift = (dx: number) => k.translateAlong(P, [dx, 0, 0]);
