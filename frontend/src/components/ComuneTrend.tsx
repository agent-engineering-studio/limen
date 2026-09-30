import { useEffect, useState } from "react";
import type { JSX } from "react";
import { Box, Group, Skeleton, Text } from "@mantine/core";

import { defaultApiClient } from "../lib/api-client";
import { HAZARD_HUE } from "../lib/risk-colors";
import type { ComuneHistory, HazardType } from "../types";

// L'andamento del comune: tre linee, una per pericolo, sulla stessa scala.
//
// Sulla stessa scala **di proposito**, anche se i tre punteggi hanno
// calibrazioni diverse e 0,4 di incendio non è la stessa quantità di pericolo
// di 0,4 di frana. La domanda a cui questo grafico risponde non è «quale dei
// tre è peggio» — per quella c'è il numero di attenzione — ma «qualcosa sta
// salendo?», e per vedere una salita serve un asse solo.
//
// La serie è sparsa e resta sparsa. Dalla #135 una cella lascia una riga solo
// quando cambia classe, si scosta oltre soglia o scade il battito di 24 ore:
// sulle ore senza scrittura non c'è un punto, e la linea unisce quelli che
// esistono invece di inventare un livello per ogni ora. I pallini dicono dove
// una misura c'è davvero.
//
// È la storia della **cella peggiore di oggi**, non l'inviluppo del comune
// ricalcolato ora per ora: quella versione impiega oltre due minuti su un
// comune da 134 celle, anche a cache calda. Il prezzo è che la cella peggiore
// di oggi poteva non esserlo cinque giorni fa; il vantaggio è che il grafico
// e il numero in testata parlano dello stesso punto.

const W = 280;
const H = 72;
const PAD_L = 22;
const PAD_R = 6;
const PAD_T = 6;
const PAD_B = 14;

const ORDINE: HazardType[] = ["landslide", "flood", "wildfire"];
const NOME: Record<string, string> = {
  landslide: "frane",
  flood: "alluvione",
  wildfire: "incendio",
};

/** Le soglie di classe, come righe orizzontali: senza, una linea a 0,4 non si
 *  sa se è alta. Sono quelle delle frane — le altre differiscono, e il grafico
 *  lo dice a parole invece di disegnare tre griglie sovrapposte. */
const SOGLIE = [
  { y: 0.35, label: "mod." },
  { y: 0.55, label: "alto" },
];

interface Punto {
  x: number;
  y: number;
}

function scala(
  punti: { t: string; score: number }[],
  t0: number,
  t1: number,
): Punto[] {
  const durata = t1 - t0 || 1;
  return punti.map((p) => ({
    x: PAD_L + ((new Date(p.t).getTime() - t0) / durata) * (W - PAD_L - PAD_R),
    y: PAD_T + (1 - Math.min(1, Math.max(0, p.score))) * (H - PAD_T - PAD_B),
  }));
}

function tracciato(pts: Punto[]): string {
  return pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
}

function yDi(score: number): number {
  return PAD_T + (1 - score) * (H - PAD_T - PAD_B);
}

export default function ComuneTrend({
  istatCode,
  hours = 168,
}: {
  istatCode: string;
  hours?: number;
}): JSX.Element {
  const [serie, setSerie] = useState<ComuneHistory | null>(null);
  const [errore, setErrore] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    setSerie(null);
    setErrore(false);
    defaultApiClient
      .getComuneHistory(istatCode, hours, ctrl.signal)
      .then(setSerie)
      .catch(() => {
        if (!ctrl.signal.aborted) setErrore(true);
      });
    return () => ctrl.abort();
  }, [istatCode, hours]);

  if (errore) {
    return (
      <Text size="xs" c="dimmed">
        Andamento non disponibile.
      </Text>
    );
  }
  if (serie === null) return <Skeleton height={H} radius="sm" />;

  const presenti = ORDINE.filter((h) => (serie[h]?.length ?? 0) > 1);
  if (presenti.length === 0) {
    return (
      <Text size="xs" c="dimmed">
        Non ci sono ancora abbastanza misure per un andamento. Lo storico
        registra una cella quando cambia, non a ogni giro.
      </Text>
    );
  }

  const tempi = presenti.flatMap((h) =>
    (serie[h] ?? []).map((p) => new Date(p.t).getTime()),
  );
  const t0 = Math.min(...tempi);
  const t1 = Math.max(...tempi);
  const giorni = Math.max(1, Math.round((t1 - t0) / 86_400_000));

  return (
    <Box>
      <Text size="xs" c="dimmed" mb={2}>
        Andamento della cella peggiore · ultimi {giorni}{" "}
        {giorni === 1 ? "giorno" : "giorni"} · punteggio da 0 a 1
      </Text>
      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Andamento del rischio negli ultimi ${giorni} giorni: ${presenti
          .map((h) => {
            const s = serie[h] ?? [];
            const ultimo = s[s.length - 1]?.score ?? 0;
            return `${NOME[h]} ${ultimo.toFixed(2)}`;
          })
          .join(", ")}`}
      >
        {SOGLIE.map((s) => (
          <g key={s.label}>
            <line
              x1={PAD_L}
              x2={W - PAD_R}
              y1={yDi(s.y)}
              y2={yDi(s.y)}
              stroke="#e4e2dc"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <text x={0} y={yDi(s.y) + 3} fontSize={7} fill="#9a968c">
              {s.label}
            </text>
          </g>
        ))}
        {presenti.map((h) => {
          const pts = scala(serie[h] ?? [], t0, t1);
          return (
            <g key={h}>
              <path
                d={tracciato(pts)}
                fill="none"
                stroke={HAZARD_HUE[h]}
                strokeWidth={1.6}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {pts.map((p, i) => (
                <circle key={i} cx={p.x} cy={p.y} r={1.4} fill={HAZARD_HUE[h]} />
              ))}
            </g>
          );
        })}
      </svg>
      <Group gap={10} mt={2}>
        {presenti.map((h) => {
          const s = serie[h] ?? [];
          const ultimo = s[s.length - 1]?.score;
          return (
            <Group key={h} gap={4} wrap="nowrap">
              <Box
                style={{
                  width: 10,
                  height: 2,
                  background: HAZARD_HUE[h],
                  borderRadius: 1,
                }}
                aria-hidden
              />
              <Text span size="xs" c="dimmed">
                {NOME[h]}
                {ultimo === undefined
                  ? ""
                  : ` ${ultimo.toLocaleString("it-IT", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}`}
              </Text>
            </Group>
          );
        })}
      </Group>
    </Box>
  );
}
