import { useEffect, useState } from "react";
import type { JSX } from "react";
import { Box, Group, Text } from "@mantine/core";
import { useInterval } from "@mantine/hooks";

import { defaultApiClient } from "../lib/api-client";
import { RISK_COLOR_BY_LEVEL, useEtichetteRischio } from "../lib/risk-colors";
import { testi, useLingua, useLocale, useTesti, type Lingua } from "../lib/i18n";
import { useForecastSchedule } from "../lib/forecast-schedule";
import type { ForecastAlertItem, RiskLevel } from "../types";
import { RigaProvenienza } from "./ComeNasce";

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

const NOME: Record<Lingua, Record<string, string>> = {
  it: { landslide: "frane", flood: "allagamento", wildfire: "incendio" },
  en: { landslide: "landslides", flood: "flood", wildfire: "wildfire" },
};

/** «tra 2 h 14 min», «tra 8 min», o `null` se l'orario non è noto. */
export function traQuanto(
  iso: string | null,
  adesso: number,
  lingua: Lingua = "it",
): string | null {
  if (!iso) return null;
  const minuti = Math.round((new Date(iso).getTime() - adesso) / 60000);
  if (!Number.isFinite(minuti)) return null;
  const tra = lingua === "it" ? "tra" : "in";
  if (minuti <= 0) return lingua === "it" ? "a momenti" : "any moment now";
  if (minuti < 60) return `${tra} ${minuti} min`;
  const ore = Math.floor(minuti / 60);
  const resto = minuti % 60;
  return resto === 0 ? `${tra} ${ore} h` : `${tra} ${ore} h ${resto} min`;
}

/** «8 ore», «12 min»: quanto tempo è passato, senza il «fa». */
function durata(iso: string, adesso: number, lingua: Lingua): string | null {
  const minuti = Math.round((adesso - new Date(iso).getTime()) / 60000);
  if (minuti < 2) return null;
  if (minuti < 60) return `${minuti} min`;
  const ore = Math.round(minuti / 60);
  const [ora, oreN, giorno, giorniN] =
    lingua === "it" ? ["ora", "ore", "giorno", "giorni"] : ["hour", "hours", "day", "days"];
  if (ore < 24) return `${ore} ${ore === 1 ? ora : oreN}`;
  const giorni = Math.round(ore / 24);
  return `${giorni} ${giorni === 1 ? giorno : giorniN}`;
}

/** «8 ore fa», «12 min fa». */
export function quantoFa(iso: string, adesso: number, lingua: Lingua = "it"): string {
  const d = durata(iso, adesso, lingua);
  if (lingua === "it") return d === null ? "adesso" : `${d} fa`;
  return d === null ? "just now" : `${d} ago`;
}

function oraLocale(iso: string, loc: string): string {
  return new Date(iso).toLocaleString(loc, {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const T = testi(
  {
    sezione: "Stato della previsione",
    titolo: "Previsione 72 ore",
    prossima: (q: string) => `prossima ${q}`,
    quiete:
      "Nessun avviso previsionale nelle ultime 72 ore: nessuna regione con celle previste in classe alta. La mappa mostra anche le moderate.",
    inviati: "Avvisi previsionali inviati nelle ultime 72 ore",
    riga: (pericolo: string, celle: number, classe: string, h: number) =>
      ` · ${pericolo} · ${celle} celle ≥ ${classe} a +${h} h`,
    altri: (n: number) => `e altri ${n}`,
    perComune: (fa: string, ora: string, prossima: string | null) =>
      `Per comune: calcolata ${fa} (${ora})${prossima ? `, prossima ${prossima}` : ""}. Si ricalcola ogni 6 ore con le ultime corse dei modelli meteo.`,
    nessunaComune: "Per comune: nessuna previsione calcolata finora.",
    disponibile: (elenco: string) => ` Disponibile per: ${elenco}.`,
    inCorso: (da: string) => `Allerta per regione: calcolo in corso da ${da}.`,
    ogni: (ore: number, prossima: string) =>
      `Allerta per regione: ogni ${ore} ore, prossima ${prossima}.`,
    senzaOrario: "Allerta per regione: orario del prossimo calcolo non disponibile.",
  },
  {
    sezione: "Forecast status",
    titolo: "72-hour forecast",
    prossima: (q: string) => `next ${q}`,
    quiete:
      "No forecast notices in the last 72 hours: no region has cells forecast in a high class. The map also shows the moderate ones.",
    inviati: "Forecast notices sent in the last 72 hours",
    riga: (pericolo: string, celle: number, classe: string, h: number) =>
      ` · ${pericolo} · ${celle} ${celle === 1 ? "cell" : "cells"} ≥ ${classe} at +${h} h`,
    altri: (n: number) => `and ${n} more`,
    perComune: (fa: string, ora: string, prossima: string | null) =>
      `By municipality: computed ${fa} (${ora})${prossima ? `, next ${prossima}` : ""}. Recomputed every 6 hours with the latest weather model runs.`,
    nessunaComune: "By municipality: no forecast computed so far.",
    disponibile: (elenco: string) => ` Available for: ${elenco}.`,
    inCorso: (da: string) => `Regional alert: computing for ${da}.`,
    ogni: (ore: number, prossima: string) =>
      `Regional alert: every ${ore} hours, next ${prossima}.`,
    senzaOrario: "Regional alert: time of the next run not available.",
  },
);

export default function PrevisioneTesta(): JSX.Element {
  const schedule = useForecastSchedule();
  const t = useTesti(T);
  const { lingua } = useLingua();
  const loc = useLocale();
  const etichette = useEtichetteRischio();
  const [allerte, setAllerte] = useState<ForecastAlertItem[] | null>(null);
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
  const prossimaCella = traQuanto(schedule?.cells.next_run_at ?? null, adesso, lingua);
  const prossimaRegione = traQuanto(schedule?.next_run_at ?? null, adesso, lingua);
  const conPrevisione = Object.keys(corseCelle).map((h) => NOME[lingua][h] ?? h);

  return (
    <section className="rail-sezione prev-testa" aria-label={t.sezione}>
      <div className="rail-testa">
        <h2>{t.titolo}</h2>
        {prossimaCella ? (
          <span className="prev-timer mono">{t.prossima(prossimaCella)}</span>
        ) : null}
      </div>

      <RigaProvenienza />

      {allerte === null ? null : allerte.length === 0 ? (
        <div className="prev-stato is-quiet">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path d="M5 12l5 5L20 7" stroke="currentColor" strokeWidth="2" />
          </svg>
          <span>{t.quiete}</span>
        </div>
      ) : (
        <div className="prev-stato is-alert">
          <Text size="xs" c="dimmed">
            {t.inviati}
          </Text>
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
                <strong>{a.aoi_id.replace(/^it-/, "").replace(/-/g, " ")}</strong>
                {t.riga(
                  NOME[lingua][a.hazard_type] ?? a.hazard_type,
                  a.cells_alerted,
                  etichette[a.max_level as RiskLevel] ?? a.max_level,
                  a.horizon_h,
                )}
              </Text>
            </Group>
          ))}
          {allerte.length > 4 ? (
            <Text size="xs" c="dimmed">
              {t.altri(allerte.length - 4)}
            </Text>
          ) : null}
        </div>
      )}

      <Text size="xs" c="dimmed">
        {ultimaCella
          ? t.perComune(
              quantoFa(ultimaCella, adesso, lingua),
              oraLocale(ultimaCella, loc),
              schedule?.cells.next_run_at ? oraLocale(schedule.cells.next_run_at, loc) : null,
            )
          : t.nessunaComune}
        {conPrevisione.length > 0 && conPrevisione.length < 3
          ? t.disponibile(conPrevisione.join(", "))
          : ""}{" "}
        {schedule?.running_since
          ? t.inCorso(
              durata(schedule.running_since, adesso, lingua) ??
                quantoFa(schedule.running_since, adesso, lingua),
            )
          : prossimaRegione
            ? t.ogni(schedule?.interval_hours ?? 6, prossimaRegione)
            : t.senzaOrario}
      </Text>
    </section>
  );
}
