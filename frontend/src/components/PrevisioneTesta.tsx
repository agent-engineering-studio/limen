import { useEffect, useState } from "react";
import type { JSX } from "react";
import { Box, Group, Text } from "@mantine/core";
import { useInterval } from "@mantine/hooks";

import { defaultApiClient } from "../lib/api-client";
import { RISK_COLOR_BY_LEVEL } from "../lib/risk-colors";
import type { ForecastAlertItem, ForecastSchedule, RiskLevel } from "../types";

// La testata della previsione, dentro la lista dei comuni e non in un
// pannello a parte.
//
// Stava da sola, sopra, e diceva una cosa per regione — «nessuna regione
// prevista sopra soglia» — mentre la domanda è per comune. Ora la lista ha la
// previsione in ogni riga, e questa testata dice solo le due cose che la riga
// non può dire: **quanto è fresca** la previsione e **quando arriva la
// prossima**.
//
// I calcoli sono due e il timer li mostra entrambi. La previsione per cella —
// quella delle righe e del grafico — gira una volta al giorno, nel job
// notturno; ogni sei ore gira l'allerta per regione. Un timer solo, quello da
// sei ore, lascerebbe credere che la curva di un comune si aggiorni quattro
// volte al giorno.

const NOME: Record<string, string> = {
  landslide: "frane",
  flood: "alluvione",
  wildfire: "incendio",
};

/** «tra 2 h 14 min», «tra 8 min», o `null` se l'orario non è noto. */
export function traQuanto(iso: string | null, adesso: number): string | null {
  if (!iso) return null;
  const minuti = Math.round((new Date(iso).getTime() - adesso) / 60000);
  if (!Number.isFinite(minuti)) return null;
  if (minuti <= 0) return "a momenti";
  if (minuti < 60) return `tra ${minuti} min`;
  const ore = Math.floor(minuti / 60);
  const resto = minuti % 60;
  return resto === 0 ? `tra ${ore} h` : `tra ${ore} h ${resto} min`;
}

/** «8 ore fa», «12 min fa». */
export function quantoFa(iso: string, adesso: number): string {
  const minuti = Math.round((adesso - new Date(iso).getTime()) / 60000);
  if (minuti < 2) return "adesso";
  if (minuti < 60) return `${minuti} min fa`;
  const ore = Math.round(minuti / 60);
  if (ore < 24) return `${ore} ${ore === 1 ? "ora" : "ore"} fa`;
  const giorni = Math.round(ore / 24);
  return `${giorni} ${giorni === 1 ? "giorno" : "giorni"} fa`;
}

function oraLocale(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function PrevisioneTesta({
  schedule,
}: {
  schedule: ForecastSchedule | null;
}): JSX.Element {
  const [allerte, setAllerte] = useState<ForecastAlertItem[] | null>(null);
  // Il conto alla rovescia si ridisegna ogni trenta secondi: al minuto basta,
  // e un secondo che scorre in una colonna laterale è rumore.
  const [adesso, setAdesso] = useState(() => Date.now());
  useInterval(() => setAdesso(Date.now()), 30_000, { autoInvoke: true });

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getForecastAlerts({ sinceHours: 72 }, ctrl.signal)
      .then((r) => setAllerte(r.items))
      .catch(() => {
        if (!ctrl.signal.aborted) setAllerte([]);
      });
    return () => ctrl.abort();
  }, []);

  const corseCelle = schedule?.cells.last_run_by_hazard ?? {};
  const ultimaCella = Object.values(corseCelle).sort().pop() ?? null;
  const prossimaCella = traQuanto(schedule?.cells.next_run_at ?? null, adesso);
  const prossimaRegione = traQuanto(schedule?.next_run_at ?? null, adesso);
  const conPrevisione = Object.keys(corseCelle).map((h) => NOME[h] ?? h);

  return (
    <Box className="prev-testa" aria-label="Stato della previsione">
      <Group justify="space-between" wrap="nowrap" align="baseline">
        <Text size="xs" fw={700} tt="uppercase" className="prev-titolo">
          Previsione a 72 ore
        </Text>
        {prossimaCella ? (
          <Text size="xs" fw={600} className="prev-timer">
            prossima {prossimaCella}
          </Text>
        ) : null}
      </Group>

      <Text size="xs" c="dimmed" mt={2}>
        {ultimaCella ? (
          <>
            Per comune: calcolata {quantoFa(ultimaCella, adesso)} (
            {oraLocale(ultimaCella)})
            {schedule?.cells.next_run_at
              ? `, prossima ${oraLocale(schedule.cells.next_run_at)}`
              : ""}
            . Gira una volta al giorno, di notte.
          </>
        ) : (
          "Per comune: nessuna previsione calcolata finora."
        )}
      </Text>

      {conPrevisione.length > 0 && conPrevisione.length < 3 ? (
        // Oggi la previsione per cella esiste solo per le frane. Dirlo qui
        // evita che una riga senza previsione d'incendio si legga come
        // «incendio previsto tranquillo».
        <Text size="xs" c="dimmed" mt={2}>
          Disponibile per: {conPrevisione.join(", ")}. Per gli altri pericoli
          la riga mostra solo l&apos;adesso.
        </Text>
      ) : null}

      <Text size="xs" c="dimmed" mt={4}>
        {schedule?.running_since ? (
          <>Allerta per regione: calcolo in corso da {quantoFa(schedule.running_since, adesso).replace(" fa", "")}.</>
        ) : prossimaRegione ? (
          <>
            Allerta per regione: ogni {schedule?.interval_hours ?? 6} ore,
            prossima {prossimaRegione}.
          </>
        ) : (
          // Il worker non ha pubblicato l'orario: è appena ripartito, o è
          // fermo. Meglio dirlo che indovinare dall'ultima corsa, che dopo un
          // riavvio sbaglia di ore.
          <>Allerta per regione: orario del prossimo calcolo non disponibile.</>
        )}
      </Text>

      {allerte === null ? null : allerte.length === 0 ? (
        <Text size="xs" mt={4}>
          Nessuna regione prevista sopra soglia nelle ultime 72 ore.
        </Text>
      ) : (
        <Box mt={4}>
          {allerte.slice(0, 4).map((a) => (
            <Group key={`${a.aoi_id}-${a.dispatched_at}`} gap={6} wrap="nowrap">
              <Box
                className="cb-chip"
                style={{
                  background: RISK_COLOR_BY_LEVEL[a.max_level as RiskLevel] ?? "#888",
                }}
                aria-hidden
              />
              <Text size="xs">
                <strong>{a.aoi_id.replace(/^it-/, "").replace(/-/g, " ")}</strong>{" "}
                · {a.cells_alerted} celle ≥ {a.max_level} a +{a.horizon_h} h
              </Text>
            </Group>
          ))}
        </Box>
      )}
    </Box>
  );
}
