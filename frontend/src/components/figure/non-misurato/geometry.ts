import * as k from "../../iso/iso-kit";
import type { Flat, Plan, Point3 } from "../../iso/iso-kit";
import { RISK_CLASSES } from "../../../lib/risk-colors";

export const WIDTH = 600;
export const HEIGHT = 360;

const PIASTRA: Plan = { x: -84, y: -46, w: 168, d: 100, r: 8 };
const PIASTRA_H = 9;
const PIEDE_H = 4;

const CY = 22;
export const CENTRI = { a: -38, b: 38 } as const;
const R = 15;
const QZ = 12;
const QH = 8;
const QTOP = QZ + QH;
const ARCO_DA = -0.75 * Math.PI;
const ARCO = 1.5 * Math.PI;

// La bandierina: incernierata dietro il quadrante, in piedi quando c'è il
// segnale, abbattuta sul quadrante quando manca.
const CERNIERA_Y = CY - 19;
const CERNIERA_Z = QTOP + 2;
const BANDIERA_L = 31;
const BANDIERA_MEZZA = 12.5;

export const P = k.fitProjection(
  [...k.boxCorners(PIASTRA, -PIASTRA_H - PIEDE_H, 0), [CENTRI.a, CERNIERA_Y, CERNIERA_Z + BANDIERA_L] as Point3, [CENTRI.b, CERNIERA_Y, CERNIERA_Z + BANDIERA_L] as Point3, [16, -33, 36] as Point3],
  WIDTH,
  HEIGHT,
  { pad: 20 },
);

const at = (point: Point3): Flat => k.iso(point, P);
const slab = (plan: Plan, z: number, h: number, steps = 3, bevel = 0.3) => k.slabOf(plan, z, h, P, steps, bevel);

// ---- Base ------------------------------------------------------------------

const TARGA: Plan = { x: -78, y: 40, w: 30, d: 10, r: 1.2 };
export const BASE = {
  halo: k.haloOf(PIASTRA, -PIASTRA_H - PIEDE_H, PIASTRA_H, P),
  feet: [...k.corners(PIASTRA, 18)]
    .sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P))
    .map(([x, y]) => ({ flange: k.cylinder(x, y, 6.5, -PIASTRA_H - PIEDE_H, 1.6, P, 28), foot: k.cylinder(x, y, 5, -PIASTRA_H - PIEDE_H + 1.6, PIEDE_H - 1.6, P, 28) })),
  slab: slab(PIASTRA, -PIASTRA_H, PIASTRA_H, 8, 1.6),
  seam: k.sideSeam(PIASTRA, -PIASTRA_H + 3, P, 8),
  groove: k.planOutline(k.insetPlan(PIASTRA, 5), 0, P),
  screws: k.corners(PIASTRA, 9).map(([x, y]) => k.ring(x, y, 2, 0, P, 16)).join(""),
  screwDots: k.corners(PIASTRA, 9).map(([x, y]) => at([x, y, 0])),
  label: slab(TARGA, 0, 0.8, 4, 0),
  labelInset: k.planOutline(k.insetPlan(TARGA, 1.4), 0.8, P),
  labelRules: [20, 13, 17].map((w, i) => k.lineOnTop([TARGA.x + 4, TARGA.y + 3 + i * 2.2], [TARGA.x + 4 + w, TARGA.y + 3 + i * 2.2], 0.8, P)).join(""),
};

// ---- La centralina: il dato meteo che arriva --------------------------------

const SCATOLA: Plan = { x: -22, y: -38, w: 44, d: 16, r: 2 };
export const BOX = {
  body: slab(SCATOLA, 0, 14, 4, 0.8),
  seam: k.sideSeam(SCATOLA, 4, P, 4),
  lid: k.planOutline(k.insetPlan(SCATOLA, 2.5), 14, P, 4),
  sockets: [-10, 10].map((x) => slab({ x: x - 3.5, y: -22, w: 7, d: 2.5, r: 0.6 }, 3, 6)),
  leds: { a: at([-10, -24.5, 14]), b: at([10, -24.5, 14]) },
  ledRings: [-10, 10].map((x) => k.ring(x, -24.5, 1.4, 14, P, 14)).join(""),
  mastCollar: k.cylinder(14, -32, 2.4, 14, 2, P, 20, 0.3),
  mast: k.cylinder(14, -32, 0.9, 16, 18, P, 12),
  mastCap: k.cylinder(14, -32, 3, 34, 1.2, P, 24, 0.3),
  screws: k.corners(SCATOLA, 2.6).map(([x, y]) => at([x, y, 14])),
};

// ---- I due strumenti -------------------------------------------------------------

const sulQuadrante = (cx: number, angolo: number, raggio: number): [number, number] => [cx + Math.sin(angolo) * raggio, CY - Math.cos(angolo) * raggio];
const angoloDi = (valore: number) => ARCO_DA + ARCO * valore;

function strumento(cx: number) {
  const piedistallo: Plan = { x: cx - 17, y: CY - 22, w: 34, d: 38, r: 4 };
  return {
    pedestal: slab(piedistallo, 0, QZ, 6, 0.8),
    pedestalSeam: k.sideSeam(piedistallo, 4, P, 6),
    puck: k.cylinder(cx, CY, R, QZ, QH, P, 64, 0.8),
    band: k.knurl(cx, CY, R, QTOP - 3, QTOP, 80, P, 0.3),
    bandSeam: k.sideArc(cx, CY, R, QTOP - 3, P, 40),
    bezel: k.ring(cx, CY, R - 2, QTOP, P, 64),
    ticks: k.radialTicks(cx, CY, R - 2, 20, 5, QTOP, [1.3, 2.6], P, ARCO_DA, ARCO),
    sectors: RISK_CLASSES.map((classe) => {
      const passi = Math.max(2, Math.round((classe.range[1] - classe.range[0]) * 40));
      const punti = Array.from({ length: passi + 1 }, (_, i) => sulQuadrante(cx, angoloDi(classe.range[0] + ((classe.range[1] - classe.range[0]) * i) / passi), R - 5.2));
      return { level: classe.level, d: k.onTop(punti, QTOP, P) };
    }),
    hubRing: k.ring(cx, CY, 1.5, QTOP, P, 16),
    hub: at([cx, CY, QTOP]),
    posts: [-1, 1].map((side) => slab({ x: cx + side * 14.2 - 1.5, y: CERNIERA_Y - 1.5, w: 3, d: 3, r: 0.5 }, QZ, CERNIERA_Z - QZ + 1)),
    bar: slab({ x: cx - 12.7, y: CERNIERA_Y - 1, w: 25.4, d: 2, r: 0.8 }, CERNIERA_Z - 1, 2, 3, 0.2),
  };
}

export const STRUMENTI = { a: strumento(CENTRI.a), b: strumento(CENTRI.b) };

export function agoDi(cx: number, valore: number) {
  const a = angoloDi(valore);
  const coda = sulQuadrante(cx, a + Math.PI, 2.8);
  const punta = sulQuadrante(cx, a, R - 3.6);
  return k.pathOf([at([coda[0], coda[1], QTOP + 0.2]), at([punta[0], punta[1], QTOP + 0.2])]);
}

// `giu` = 0 in piedi, 1 abbattuta sul quadrante.
export function bandieraDi(cx: number, giu: number) {
  const angolo = (giu * Math.PI) / 2;
  const punto = (x: number, s: number): Point3 => [x, CERNIERA_Y + Math.sin(angolo) * s, CERNIERA_Z + Math.cos(angolo) * s];
  const angoli = [punto(cx - BANDIERA_MEZZA, 0), punto(cx + BANDIERA_MEZZA, 0), punto(cx + BANDIERA_MEZZA, BANDIERA_L), punto(cx - BANDIERA_MEZZA, BANDIERA_L)];
  const righe = [0.3, 0.5, 0.7].map((t) => k.pathOf([at(punto(cx - BANDIERA_MEZZA, BANDIERA_L * t)), at(punto(cx + BANDIERA_MEZZA, BANDIERA_L * t))]));
  return { piastra: k.pathOf(angoli.map(at), true), righe: righe.join("") };
}

// ---- I cavi ---------------------------------------------------------------------

const SPINA_W = 5;
export const SPINA_CORSA = 6;
const PAVIMENTO = 1;

export const CAVO_A: Flat[] = [at([-10, -19.5, 5.5]), at([-10, -17, PAVIMENTO]), at([-10, CY, PAVIMENTO]), at([CENTRI.a + 17 + SPINA_W, CY, 2.6])];
export const SPINA_A = slab({ x: CENTRI.a + 17, y: CY - 2, w: SPINA_W, d: 4, r: 0.6 }, 0.6, 4);

// Il cavo di B corre dietro il suo piedistallo e gli gira intorno a destra:
// il tratto dietro si disegna prima del piedistallo, quello davanti dopo.
const X_GIRO = 66;
export const CAVO_B_DIETRO: Flat[] = [at([10, -19.5, 5.5]), at([10, -17, PAVIMENTO]), at([X_GIRO, -17, PAVIMENTO])];
export const cavoBDavanti = (fuori: number): Flat[] => [at([X_GIRO, -17, PAVIMENTO]), at([X_GIRO, CY, PAVIMENTO]), at([CENTRI.b + 17 + SPINA_W + fuori, CY, 2.6])];
export const SPINA_B = slab({ x: CENTRI.b + 17, y: CY - 2, w: SPINA_W, d: 4, r: 0.6 }, 0.6, 4);
// La presa sulla faccia del piedistallo, che si vede quando la spina è fuori.
const FACCIA_B = CENTRI.b + 17;
export const PRESA_B = k.pathOf([at([FACCIA_B, CY - 1.6, 1.2]), at([FACCIA_B, CY + 1.6, 1.2]), at([FACCIA_B, CY + 1.6, 4]), at([FACCIA_B, CY - 1.6, 4])], true);

export const shiftX = (dx: number) => k.translateAlong(P, [dx, 0, 0]);
