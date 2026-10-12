import { boxCorners, fitProjection, iso, type Plan, type Point3 } from "../../iso/iso-kit";

export const WIDTH = 600;
export const HEIGHT = 380;
export const AZIMUTH = 45;

// Il banco: una piastra su quattro piedi. x a destra-avanti, y a sinistra-avanti, z in su.
export const PIASTRA: Plan = { x: -104, y: -50, w: 208, d: 130, r: 8 };
export const PIASTRA_H = 10;
export const PIEDE_H = 4;

// Le due sorgenti, dietro: il pluviometro a sinistra, l'idrometro a destra.
export const FONTE_Y = -26;
export const PLUVIOMETRO_X = -80;
export const IDROMETRO_X = 80;
export const FONTE_R = 12;
export const FONTE_TOP = 36;
export const ASTA_R = 1.5;
export const ASTA_CORSA = 30;

// La valvola a navetta, al centro dietro: ingressi sulle due teste, uscita davanti.
export const VALVOLA: Plan = { x: -26, y: FONTE_Y - 9, w: 52, d: 18, r: 3 };
export const VALVOLA_H = 16;
export const NAVETTA_CORSA = 13;

// Le condotte: sezione 6 × 6, appoggiate su selle.
export const CONDOTTA_Z = 4;
export const CONDOTTA_H = 6;
export const CONDOTTA_MEZZA = 3;

// La paratoia: sbarra la condotta d'uscita.
export const PARATOIA_Y = 20;
export const PARATOIA_D = 5;
export const MONTANTE_X = 7;
export const MONTANTE_W = 4;
export const TRAVERSA_Z = 34;
export const TRAVERSA_H = 5;
export const PIASTRA_GATE_H = 20;
export const VOLANTINO_R = 8;

// Il manometro, davanti: segna il punteggio.
export const QUADRANTE_Y = 60;
export const QUADRANTE_R = 17;
export const QUADRANTE_Z = 12;
export const QUADRANTE_H = 8;
export const QUADRANTE_TOP = QUADRANTE_Z + QUADRANTE_H;
export const ARCO_DA = -0.75 * Math.PI;
export const ARCO = 1.5 * Math.PI;

export const P = fitProjection(
  [
    ...boxCorners(PIASTRA, -PIASTRA_H - PIEDE_H, 0),
    [PLUVIOMETRO_X, FONTE_Y, FONTE_TOP + 4 + ASTA_CORSA + 3] as Point3,
    [IDROMETRO_X, FONTE_Y, FONTE_TOP + 4 + ASTA_CORSA + 3] as Point3,
    [0, PARATOIA_Y, TRAVERSA_Z + TRAVERSA_H + 22] as Point3,
  ],
  WIDTH,
  HEIGHT,
  { pad: 26, azimuth: AZIMUTH },
);

export const at = (point: Point3) => iso(point, P);
