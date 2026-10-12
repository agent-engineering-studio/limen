import * as k from "../../iso/iso-kit";
import type { Flat, Plan, Plane, SolidPaths } from "../../iso/iso-kit";
import { CLASSI } from "./model";
import {
  ARCO,
  ARCO_DA,
  ASTA_CORSA,
  ASTA_R,
  CONDOTTA_H,
  CONDOTTA_MEZZA,
  CONDOTTA_Z,
  FONTE_R,
  FONTE_TOP,
  FONTE_Y,
  IDROMETRO_X,
  MONTANTE_W,
  MONTANTE_X,
  P,
  PARATOIA_D,
  PARATOIA_Y,
  PIASTRA,
  PIASTRA_GATE_H,
  PIASTRA_H,
  PIEDE_H,
  PLUVIOMETRO_X,
  QUADRANTE_H,
  QUADRANTE_R,
  QUADRANTE_TOP,
  QUADRANTE_Y,
  QUADRANTE_Z,
  TRAVERSA_H,
  TRAVERSA_Z,
  VALVOLA,
  VALVOLA_H,
  VOLANTINO_R,
} from "./view";

const slab = (plan: Plan, z: number, h: number, steps = 4, bevel = 0) => k.slabOf(plan, z, h, P, steps, bevel);
const byDepth = (points: Plane[]) => [...points].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
const top = (point: Plane, z: number): Flat => k.iso([point[0], point[1], z], P);

// ---- Base ------------------------------------------------------------------

export const BASE = {
  halo: k.haloOf(PIASTRA, -PIASTRA_H - PIEDE_H, PIASTRA_H, P),
  feet: byDepth(k.corners(PIASTRA, 20)).map(([x, y]) => ({
    flange: k.cylinder(x, y, 7, -PIASTRA_H - PIEDE_H, 1.6, P, 28),
    foot: k.cylinder(x, y, 5.4, -PIASTRA_H - PIEDE_H + 1.6, PIEDE_H - 1.6, P, 28),
  })),
  slab: slab(PIASTRA, -PIASTRA_H, PIASTRA_H, 8, 1.6),
  seam: k.sideSeam(PIASTRA, -PIASTRA_H + 3.5, P, 8),
  groove: k.planOutline(k.insetPlan(PIASTRA, 5), 0, P),
  screws: k.corners(PIASTRA, 10).map(([x, y]) => k.ring(x, y, 2, 0, P, 16)).join(""),
  screwDots: k.corners(PIASTRA, 10).map((point) => top(point, 0)),
};

const RIGHELLO: Plan = { x: 26, y: 70, w: 66, d: 6, r: 1 };
const tacche = k.topTicks(RIGHELLO.x + 3, RIGHELLO.x + RIGHELLO.w - 3, 3, 5, RIGHELLO.y + 0.6, 0.6, [1.8, 3.4], P);
export const RULER = { strip: slab(RIGHELLO, 0, 0.6, 3), minor: tacche.minor, major: tacche.major };

const TARGA: Plan = { x: -94, y: 58, w: 36, d: 15, r: 1.5 };
export const LABEL = {
  plate: slab(TARGA, 0, 0.8, 4),
  inset: k.planOutline(k.insetPlan(TARGA, 1.6), 0.8, P),
  rules: [
    k.lineOnTop([TARGA.x + 5, TARGA.y + 4.5], [TARGA.x + 29, TARGA.y + 4.5], 0.8, P),
    k.lineOnTop([TARGA.x + 5, TARGA.y + 7.5], [TARGA.x + 22, TARGA.y + 7.5], 0.8, P),
    k.lineOnTop([TARGA.x + 5, TARGA.y + 10.5], [TARGA.x + 26, TARGA.y + 10.5], 0.8, P),
  ].join(""),
  screws: [top([TARGA.x + 2.8, TARGA.y + TARGA.d / 2], 0.8), top([TARGA.x + TARGA.w - 2.8, TARGA.y + TARGA.d / 2], 0.8)],
};

// ---- Le due sorgenti ------------------------------------------------------

export interface Fonte {
  x: number;
  base: number;
  flange: SolidPaths;
  body: SolidPaths;
  seams: string;
  head: SolidPaths[];
  headLines: string;
  headDots: Flat[];
  staff: SolidPaths;
  staffCap: SolidPaths;
  staffMinor: string;
  staffMajor: string;
  arm: SolidPaths;
  armTip: SolidPaths;
}

const STAFF_DY = 15;

function fonte(x: number, pluviometro: boolean): Fonte {
  const y = FONTE_Y;
  const base = pluviometro ? FONTE_TOP + 5.5 : FONTE_TOP + 5;
  const head: SolidPaths[] = [];
  let headLines = "";
  const headDots: Flat[] = [];
  if (pluviometro) {
    // La bocca a imbuto del pluviometro e la sua retina.
    head.push(k.cylinder(x, y, FONTE_R + 2, FONTE_TOP, 4, P, 48, 0.6));
    headLines += k.ring(x, y, FONTE_R - 0.5, FONTE_TOP + 4, P, 48);
    for (let gx = -9; gx <= 9; gx += 3)
      for (let gy = -9; gy <= 9; gy += 3) if (Math.hypot(gx, gy) < 9.5 && Math.hypot(gx, gy) > 4) headDots.push(top([x + gx, y + gy], FONTE_TOP + 4));
    // La boccola che guida l'asta del galleggiante attraverso la retina.
    head.push(k.cylinder(x, y, 2.8, FONTE_TOP + 4, 1.5, P, 24, 0.2));
  } else {
    // Il coperchio imbullonato dell'idrometro e il premistoppa dell'asta.
    head.push(k.cylinder(x, y, FONTE_R + 1, FONTE_TOP, 2, P, 48, 0.5));
    head.push(k.cylinder(x, y, 3.4, FONTE_TOP + 2, 3, P, 24, 0.3));
    headLines += k.ring(x, y, ASTA_R + 0.4, FONTE_TOP + 5, P, 16);
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2 + Math.PI / 8;
      headDots.push(top([x + Math.cos(a) * 10.5, y + Math.sin(a) * 10.5], FONTE_TOP + 2));
    }
  }
  const staffPlan: Plan = { x: x - 1.5, y: y + STAFF_DY, w: 3, d: 3, r: 0.6 };
  const minor: string[] = [];
  const major: string[] = [];
  for (let i = 0; i <= 10; i++) {
    const z = base + (ASTA_CORSA * i) / 10;
    const big = i % 5 === 0;
    const face = x + 1.5;
    (big ? major : minor).push(k.segment([face, y + STAFF_DY + 3, z], [face, y + STAFF_DY + 3 - (big ? 3 : 1.8), z], P));
  }
  return {
    x,
    base,
    flange: k.cylinder(x, y, FONTE_R + 3, 0, 2, P, 48, 0.5),
    body: k.cylinder(x, y, FONTE_R, 2, FONTE_TOP - 2, P, 48, 0.6),
    seams: [k.sideArc(x, y, FONTE_R, 12, P, 32), k.sideArc(x, y, FONTE_R, 26, P, 32)].join(""),
    head,
    headLines,
    headDots,
    staff: slab(staffPlan, 0, base + ASTA_CORSA + 2, 3, 0.3),
    staffCap: slab({ x: x - 2, y: y + STAFF_DY - 0.5, w: 4, d: 4, r: 0.8 }, base + ASTA_CORSA + 2, 1.4, 3, 0.3),
    staffMinor: minor.join(""),
    staffMajor: major.join(""),
    // Il braccio sul cappello dell'asta, costruito a riposo e spostato in z.
    arm: slab({ x: x - 1, y: y - 2.2, w: 2, d: STAFF_DY + 2.2, r: 0.8 }, base, 1.4, 3, 0.2),
    armTip: k.cylinder(x, y, 2.6, base, 1.8, P, 20, 0.3),
  };
}

export const PLUVIOMETRO = fonte(PLUVIOMETRO_X, true);
export const IDROMETRO = fonte(IDROMETRO_X, false);

export const astaDi = (fonteData: Fonte, livello: number) =>
  k.cylinder(fonteData.x, FONTE_Y, ASTA_R, fonteData.base, Math.max(0.2, ASTA_CORSA * livello), P, 16);

// ---- Condotte ---------------------------------------------------------------

interface Condotta {
  saddle: SolidPaths;
  duct: SolidPaths;
  flanges: SolidPaths[];
  bolts: Flat[];
}

function condotta(asse: "x" | "y", da: number, a: number, altro: number): Condotta {
  const m = CONDOTTA_MEZZA;
  const plan = (s0: number, s1: number, half: number, r: number): Plan =>
    asse === "x" ? { x: s0, y: altro - half, w: s1 - s0, d: half * 2, r } : { x: altro - half, y: s0, w: half * 2, d: s1 - s0, r };
  const mezzo = (da + a) / 2;
  const flanges = [da, a].map((s) => slab(plan(s - 1.5, s + 1.5, m + 2, 0.8), CONDOTTA_Z - 2, CONDOTTA_H + 4, 3, 0.3));
  const bolts = [da, a].flatMap((s) =>
    [-1, 1].map((side) => (asse === "x" ? top([s, altro + side * (m + 0.8)], CONDOTTA_Z + CONDOTTA_H + 2) : top([altro + side * (m + 0.8), s], CONDOTTA_Z + CONDOTTA_H + 2))),
  );
  return {
    saddle: slab(plan(mezzo - 3, mezzo + 3, m + 2, 0.8), 0, CONDOTTA_Z, 3, 0.3),
    duct: slab(plan(da, a, m, 0.8), CONDOTTA_Z, CONDOTTA_H, 3, 0.3),
    flanges,
    bolts,
  };
}

const VALVOLA_FINE = VALVOLA.x + VALVOLA.w + 4;
export const CONDOTTA_PIOGGIA = condotta("x", PLUVIOMETRO_X + FONTE_R, VALVOLA.x - 4, FONTE_Y);
export const CONDOTTA_FIUME = condotta("x", VALVOLA_FINE, IDROMETRO_X - FONTE_R, FONTE_Y);
export const CONDOTTA_USCITA = condotta("y", VALVOLA.y + VALVOLA.d + 4, PARATOIA_Y, 0);
export const CONDOTTA_VALLE = condotta("y", PARATOIA_Y + PARATOIA_D, QUADRANTE_Y - QUADRANTE_R + 1, 0);

// ---- La valvola a navetta -----------------------------------------------------

const FENDITURA: Plan = { x: -19, y: FONTE_Y - 2.5, w: 38, d: 5, r: 2.5 };
export const VALVE = {
  capLeft: slab({ x: VALVOLA.x - 4, y: VALVOLA.y - 2, w: 4, d: VALVOLA.d + 4, r: 1 }, 0, VALVOLA_H + 1, 3, 0.4),
  capRight: slab({ x: VALVOLA.x + VALVOLA.w, y: VALVOLA.y - 2, w: 4, d: VALVOLA.d + 4, r: 1 }, 0, VALVOLA_H + 1, 3, 0.4),
  capBolts: [VALVOLA.x - 2, VALVOLA.x + VALVOLA.w + 2].flatMap((x) => [top([x, VALVOLA.y + 1], VALVOLA_H + 1), top([x, VALVOLA.y + VALVOLA.d - 1], VALVOLA_H + 1)]),
  body: slab(VALVOLA, 0, VALVOLA_H, 5, 1),
  bodySeam: k.sideSeam(VALVOLA, 5, P, 5),
  slot: k.onTop(k.ringOf(FENDITURA, 6), VALVOLA_H, P, true),
  bolts: k.corners(VALVOLA, 4).map((point) => top(point, VALVOLA_H)),
  outlet: slab({ x: -7, y: VALVOLA.y + VALVOLA.d, w: 14, d: 4, r: 1 }, 1, 12, 3, 0.4),
};

// La navetta vista dalla fenditura: costruita al centro, spostata in x.
export const SHUTTLE = slab({ x: -4, y: FONTE_Y - 2, w: 8, d: 4, r: 1 }, VALVOLA_H - 1.5, 3.5, 3, 0.4);
export const SHUTTLE_GRIP = k.lineOnTop([0, FONTE_Y - 2], [0, FONTE_Y + 2], VALVOLA_H + 2, P);

// ---- La paratoia --------------------------------------------------------------

const montante = (x: number): Plan => ({ x, y: PARATOIA_Y, w: MONTANTE_W, d: PARATOIA_D, r: 0.6 });
const CENTRO_Y = PARATOIA_Y + PARATOIA_D / 2;
export const GATE = {
  sill: slab({ x: -MONTANTE_X - MONTANTE_W - 1, y: PARATOIA_Y - 1, w: (MONTANTE_X + MONTANTE_W + 1) * 2, d: PARATOIA_D + 2, r: 1 }, 0, CONDOTTA_Z, 3, 0.4),
  postLeft: slab(montante(-MONTANTE_X - MONTANTE_W), CONDOTTA_Z, TRAVERSA_Z - CONDOTTA_Z, 3, 0.4),
  postRight: slab(montante(MONTANTE_X), CONDOTTA_Z, TRAVERSA_Z - CONDOTTA_Z, 3, 0.4),
  beam: slab({ x: -MONTANTE_X - MONTANTE_W - 2, y: PARATOIA_Y - 0.5, w: (MONTANTE_X + MONTANTE_W + 2) * 2, d: PARATOIA_D + 1, r: 1 }, TRAVERSA_Z, TRAVERSA_H, 3, 0.5),
  beamBolts: [-MONTANTE_X - 2, MONTANTE_X + 2].map((x) => top([x, CENTRO_Y], TRAVERSA_Z + TRAVERSA_H)),
  wheel: k.cylinder(0, CENTRO_Y, VOLANTINO_R, TRAVERSA_Z + TRAVERSA_H + 0.5, 2.4, P, 40, 0.4),
  wheelKnurl: k.knurl(0, CENTRO_Y, VOLANTINO_R, TRAVERSA_Z + TRAVERSA_H + 0.5, TRAVERSA_Z + TRAVERSA_H + 2.9, 40, P, 0.3),
  wheelSpokes: [0, 1, 2].map((i) => {
    const a = (i / 3) * Math.PI * 2 + 0.3;
    return k.lineOnTop([2.4 * Math.cos(a), CENTRO_Y + 2.4 * Math.sin(a)], [(VOLANTINO_R - 1.4) * Math.cos(a), CENTRO_Y + (VOLANTINO_R - 1.4) * Math.sin(a)], TRAVERSA_Z + TRAVERSA_H + 2.9, P);
  }).join(""),
  wheelRim: k.ring(0, CENTRO_Y, VOLANTINO_R - 1.4, TRAVERSA_Z + TRAVERSA_H + 2.9, P, 40),
  hub: k.cylinder(0, CENTRO_Y, 2.4, TRAVERSA_Z + TRAVERSA_H + 2.9, 1, P, 20, 0.2),
  collar: k.cylinder(0, CENTRO_Y, 2.2, TRAVERSA_Z - 1.5, 1.5, P, 20, 0.2),
};
export const GATE_HUB_TOP = TRAVERSA_Z + TRAVERSA_H + 3.9;
export const GATE_CORSA = CONDOTTA_H;

// La lama, costruita chiusa e sollevata della sua apertura.
export const BLADE = slab({ x: -MONTANTE_X, y: PARATOIA_Y + 1, w: MONTANTE_X * 2, d: PARATOIA_D - 2, r: 0.4 }, CONDOTTA_Z, PIASTRA_GATE_H, 3, 0.4);
export const BLADE_RIBS = [8, 14].map((z) => k.sideSeam({ x: -MONTANTE_X, y: PARATOIA_Y + 1, w: MONTANTE_X * 2, d: PARATOIA_D - 2, r: 0.4 }, CONDOTTA_Z + z, P, 3)).join("");

export const stemDi = (da: number, a: number) => k.cylinder(0, CENTRO_Y, 1.1, da, Math.max(0.2, a - da), P, 14);

// ---- Il manometro -------------------------------------------------------------

const CX = 0;
const CY = QUADRANTE_Y;
const R = QUADRANTE_R;
export const GAUGE = {
  halo: k.haloOf({ x: -18, y: QUADRANTE_Y - 18, w: 36, d: 36, r: 6 }, 0, 4, P),
  pedestal: slab({ x: -15, y: QUADRANTE_Y - 15, w: 30, d: 30, r: 4 }, 0, QUADRANTE_Z, 6, 0.8),
  pedestalSeam: k.sideSeam({ x: -15, y: QUADRANTE_Y - 15, w: 30, d: 30, r: 4 }, 4, P, 6),
  crown: slab({ x: R - 0.5, y: CY - 2, w: 3.5, d: 4, r: 0.8 }, QUADRANTE_Z + 2, 4, 3, 0.3),
  crownKnob: k.cylinder(R + 4, CY, 2.2, QUADRANTE_Z + 1.5, 5, P, 20, 0.3),
  puck: k.cylinder(CX, CY, R, QUADRANTE_Z, QUADRANTE_H, P, 64, 0.8),
  band: k.knurl(CX, CY, R, QUADRANTE_TOP - 3.4, QUADRANTE_TOP, 84, P, 0.3),
  bandSeam: k.sideArc(CX, CY, R, QUADRANTE_TOP - 3.4, P, 40),
  bezel: k.ring(CX, CY, R - 2.2, QUADRANTE_TOP, P, 64),
  hubRing: k.ring(CX, CY, 1.6, QUADRANTE_TOP, P, 16),
  hub: top([CX, CY], QUADRANTE_TOP),
  ticks: k.radialTicks(CX, CY, R - 3, 20, 5, QUADRANTE_TOP, [1.2, 2.6], P, ARCO_DA, ARCO),
};

const angoloDi = (valore: number) => ARCO_DA + ARCO * valore;
const sulQuadrante = (angolo: number, raggio: number): Plane => [CX + Math.sin(angolo) * raggio, CY - Math.cos(angolo) * raggio];

// I settori delle classi dell'allagamento, da 0,10 / 0,25 / 0,45 / 0,70.
export const SECTORS = CLASSI.map((classe) => {
  const passi = Math.max(2, Math.round((classe.a - classe.da) * 40));
  const punti = Array.from({ length: passi + 1 }, (_, i) => sulQuadrante(angoloDi(classe.da + ((classe.a - classe.da) * i) / passi), R - 5.6));
  return { level: classe.level, d: k.onTop(punti, QUADRANTE_TOP, P) };
});

export function needleDi(valore: number) {
  const a = angoloDi(valore);
  return k.pathOf([top(sulQuadrante(a + Math.PI, 3), QUADRANTE_TOP + 0.2), top(sulQuadrante(a, R - 4), QUADRANTE_TOP + 0.2)]);
}

export const shift = (dx: number, dz = 0) => k.translateAlong(P, [dx, 0, dz]);
