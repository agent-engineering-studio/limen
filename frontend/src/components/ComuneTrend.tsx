import { useEffect, useState } from "react";
import type { JSX } from "react";
import { Box, Group, Skeleton, Text } from "@mantine/core";

import { defaultApiClient } from "../lib/api-client";
import { HAZARD_HUE } from "../lib/risk-colors";
import type { ComuneHistory, HazardType, SeriePunto } from "../types";

// L'andamento del comune: passato solido, **futuro tratteggiato**, una linea
// per pericolo sulla stessa scala.
//
// La previsione è il cuore dell'applicazione e finora viveva solo in un
// pannello a parte, per regione e in forma di elenco: «nessuna regione
// prevista sopra soglia» è una risposta, ma non dice se il *tuo* comune sta
// salendo. Qui la stessa linea attraversa l'adesso e prosegue, che è l'unico
// modo di vedere una tendenza invece di due numeri.
//
// Sulla stessa scala **di proposito**, anche se i tre punteggi hanno
// calibrazioni diverse e 0,4 di incendio non è la stessa quantità di pericolo
// di 0,4 di frana. La domanda a cui questo grafico risponde non è «quale dei
// tre è peggio» — per quella c'è il numero di attenzione — ma «qualcosa sta
// salendo?», e per vedere una salita serve un asse solo.
//
// È la storia della **cella peggiore di oggi**, non l'inviluppo del comune
// ricalcolato ora per ora: quella versione impiega 212 secondi su un comune
// da 134 celle, anche a cache calda. Il prezzo è che la cella peggiore di
// oggi poteva non esserlo cinque giorni fa; il vantaggio è che il grafico e
// il numero in testata parlano dello stesso punto.
//
// Il passato è sparso e resta sparso. Dalla #135 una cella lascia una riga
// solo quando cambia classe, si scosta oltre soglia o scade il battito di 24
// ore: sulle ore senza scrittura non c'è un punto, e la linea unisce quelli
// che esistono invece di inventare un livello per ogni ora.

const W = 300;
const H = 84;
const PAD_L = 22;
const PAD_R = 6;
const PAD_T = 6;
const PAD_B = 16;

const ORDINE: HazardType[] = ["landslide", "flood", "wildfire"];
const NOME: Record<string, string> = {
  landslide: "frane",
  flood: "alluvione",
  wildfire: "incendio",
};

/** Le soglie di classe, come righe orizzontali: senza, una linea a 0,4 non si
 *  sa se è alta. Sono quelle delle frane — le altre differiscono, e il
 *  grafico lo dice a parole invece di disegnare tre griglie sovrapposte. */
const SOGLIE = [
  { y: 0.35, label: "mod." },
  { y: 0.55, label: "alto" },
];

interface Punto {
  x: number;
  y: number;
}

function numero(n: number): string {
  return n.toLocaleString("it-IT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function tracciato(pts: Punto[]): string {
  return pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
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

  const passato = serie.observed ?? {};
  const futuro = serie.forecast ?? {};
  const presenti = ORDINE.filter(
    (h) => (passato[h]?.length ?? 0) > 1 || (futuro[h]?.length ?? 0) > 0,
  );
  if (presenti.length === 0) {
    return (
      <Text size="xs" c="dimmed">
        Non ci sono ancora abbastanza misure per un andamento. Lo storico
        registra una cella quando cambia, non a ogni giro.
      </Text>
    );
  }

  const tutti = presenti.flatMap((h) =>
    [...(passato[h] ?? []), ...(futuro[h] ?? [])].map((p) =>
      new Date(p.t).getTime(),
    ),
  );
  const t0 = Math.min(...tutti);
  const t1 = Math.max(...tutti);
  const durata = t1 - t0 || 1;
  const adesso = Date.now();

  const x = (t: string): number =>
    PAD_L + ((new Date(t).getTime() - t0) / durata) * (W - PAD_L - PAD_R);
  const y = (score: number): number =>
    PAD_T + (1 - Math.min(1, Math.max(0, score))) * (H - PAD_T - PAD_B);
  const px = (pts: SeriePunto[]): Punto[] =>
    pts.map((p) => ({ x: x(p.t), y: y(p.score) }));

  const xAdesso = PAD_L + ((adesso - t0) / durata) * (W - PAD_L - PAD_R);
  const haFuturo = presenti.some((h) => (futuro[h]?.length ?? 0) > 0);
  const giorni = Math.max(1, Math.round((adesso - t0) / 86_400_000));

  return (
    <Box>
      <Text size="xs" c="dimmed" mb={2}>
        Andamento della cella peggiore · {giorni}{" "}
        {giorni === 1 ? "giorno" : "giorni"} indietro
        {haFuturo ? " e previsione" : ""} · punteggio da 0 a 1
      </Text>
      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Andamento del rischio: ${presenti
          .map((h) => {
            const o = passato[h] ?? [];
            const f = futuro[h] ?? [];
            const ora = o[o.length - 1]?.score;
            const poi = f[f.length - 1]?.score;
            return (
              `${NOME[h]} ${ora === undefined ? "non misurato" : ora.toFixed(2)}` +
              (poi === undefined ? "" : `, previsto ${poi.toFixed(2)}`)
            );
          })
          .join("; ")}`}
      >
        {SOGLIE.map((s) => (
          <g key={s.label}>
            <line
              x1={PAD_L}
              x2={W - PAD_R}
              y1={y(s.y)}
              y2={y(s.y)}
              stroke="#e4e2dc"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <text x={0} y={y(s.y) + 3} fontSize={7} fill="#9a968c">
              {s.label}
            </text>
          </g>
        ))}
        {haFuturo ? (
          <g>
            {/* Il confine fra ciò che è successo e ciò che è previsto. Senza,
                una linea che sale a destra si legge come un fatto. */}
            <line
              x1={xAdesso}
              x2={xAdesso}
              y1={PAD_T}
              y2={H - PAD_B}
              stroke="#b9b5ab"
              strokeWidth={1}
            />
            <text x={xAdesso + 2} y={H - PAD_B + 9} fontSize={7} fill="#9a968c">
              ora
            </text>
          </g>
        ) : null}
        {presenti.map((h) => {
          const o = px(passato[h] ?? []);
          const f = futuro[h] ?? [];
          // La previsione parte dall'ultima misura, non dal nulla: una linea
          // tratteggiata che comincia a mezz'aria sembra un'altra serie.
          const ultimo = (passato[h] ?? []).slice(-1);
          const fp = px([...ultimo, ...f]);
          return (
            <g key={h}>
              {o.length > 1 ? (
                <path
                  d={tracciato(o)}
                  fill="none"
                  stroke={HAZARD_HUE[h]}
                  strokeWidth={1.6}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              ) : null}
              {o.map((p, i) => (
                <circle key={i} cx={p.x} cy={p.y} r={1.4} fill={HAZARD_HUE[h]} />
              ))}
              {fp.length > 1 ? (
                <path
                  d={tracciato(fp)}
                  fill="none"
                  stroke={HAZARD_HUE[h]}
                  strokeWidth={1.6}
                  strokeDasharray="3 3"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  opacity={0.85}
                />
              ) : null}
              {px(f).map((p, i) => (
                <circle
                  key={`f${i}`}
                  cx={p.x}
                  cy={p.y}
                  r={1.8}
                  fill="#fff"
                  stroke={HAZARD_HUE[h]}
                  strokeWidth={1.2}
                />
              ))}
            </g>
          );
        })}
      </svg>
      <Group gap={10} mt={2}>
        {presenti.map((h) => {
          const o = passato[h] ?? [];
          const f = futuro[h] ?? [];
          const ora = o[o.length - 1]?.score;
          const poi = f[f.length - 1]?.score;
          // La differenza è ciò che si guarda davvero: un 0,42 previsto non
          // dice niente finché non si sa che adesso è 0,31.
          const delta = ora !== undefined && poi !== undefined ? poi - ora : undefined;
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
                {ora === undefined ? "" : ` ${numero(ora)}`}
                {delta === undefined || Math.abs(delta) < 0.005
                  ? ""
                  : ` → ${numero(poi as number)}`}
              </Text>
            </Group>
          );
        })}
      </Group>
      {haFuturo ? (
        <Text size="xs" c="dimmed" mt={2}>
          Tratteggio: previsione a +24/48/72 ore sulla pioggia attesa. È un
          calcolo, non un fatto.
        </Text>
      ) : null}
    </Box>
  );
}
