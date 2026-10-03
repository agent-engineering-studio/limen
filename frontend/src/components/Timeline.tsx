import { useEffect, useState } from "react";
import type { JSX } from "react";
import { UnstyledButton } from "@mantine/core";
import { useInterval } from "@mantine/hooks";

import { useForecastSchedule } from "../lib/forecast-schedule";
import { useHazard } from "../lib/hazard";

/** Gli orizzonti della timeline: quelli che la corsa notturna scrive. */
export const ORIZZONTI = [0, 24, 48, 72] as const;

/** «sab 02:00»: il momento a cui si riferisce un orizzonte. */
function quando(ms: number): string {
  return new Date(ms).toLocaleString("it-IT", { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

/** La timeline sulla mappa (#155, fase 3): adesso e le tre scadenze della
 *  previsione per cella, con un pulsante che le fa scorrere.
 *
 *  Sotto ogni scadenza c'è il momento vero a cui si riferisce, calcolato
 *  dall'ultima corsa e non dall'ora attuale: se la corsa notturna salta,
 *  «+24 h» è un momento già passato, e la timeline lo deve dire invece di
 *  presentarlo come futuro. */
export function Timeline({
  orizzonte,
  onCambia,
}: {
  orizzonte: number;
  onCambia: (h: number) => void;
}): JSX.Element {
  const schedule = useForecastSchedule();
  const { multi, selected, available } = useHazard();
  const [gira, setGira] = useState(false);
  const corse = schedule?.cells.last_run_by_hazard ?? {};
  // Il pericolo scelto ha una previsione per cella? Per l'alluvione no: la
  // sua previsione esiste solo per comune.
  const previsto = multi ? Object.keys(corse).length > 0 : selected in corse;
  const nome = available.find((h) => h.hazard === selected)?.label_it ?? selected;
  const ultima = Object.entries(corse)
    .filter(([h]) => multi || h === selected)
    .map(([, t]) => new Date(t).getTime())
    .reduce((a, b) => Math.max(a, b), 0);

  const scorre = useInterval(
    () => {
      const i = ORIZZONTI.indexOf(orizzonte as (typeof ORIZZONTI)[number]);
      onCambia(ORIZZONTI[(i + 1) % ORIZZONTI.length] ?? 0);
    },
    2500,
  );

  // Passando a un pericolo senza previsione per cella si torna all'adesso:
  // restare su «+48 h» mostrerebbe una mappa vuota che sembra tranquilla.
  useEffect(() => {
    if (schedule !== null && !previsto && orizzonte > 0) onCambia(0);
  }, [schedule, previsto, orizzonte, onCambia]);

  const avvia = (): void => {
    if (gira) {
      scorre.stop();
      setGira(false);
    } else {
      scorre.start();
      setGira(true);
    }
  };

  return (
    <div className="timeline" role="group" aria-label="Momento mostrato sulla mappa">
      <UnstyledButton
        className="timeline-play"
        onClick={avvia}
        disabled={!previsto}
        aria-label={gira ? "Ferma" : "Fai scorrere le scadenze"}
        title={previsto ? undefined : `Per ${nome.toLowerCase()} la previsione c'è solo per comune`}
      >
        {gira ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <path d="M6 4h4v16H6zM14 4h4v16h-4z" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <path d="M7 4l13 8-13 8z" />
          </svg>
        )}
      </UnstyledButton>
      {ORIZZONTI.map((h) => {
        const bersaglio = ultima > 0 ? ultima + h * 3600_000 : null;
        const passato = h > 0 && bersaglio !== null && bersaglio < Date.now();
        const sotto =
          h === 0
            ? "adesso"
            : !previsto
              ? "solo per comune"
              : bersaglio === null
                ? "—"
                : passato
                  ? `${quando(bersaglio)} · passato`
                  : quando(bersaglio);
        return (
          <UnstyledButton
            key={h}
            className={`timeline-tappa ${orizzonte === h ? "on" : ""} ${passato ? "is-passato" : ""}`}
            aria-pressed={orizzonte === h}
            disabled={h > 0 && !previsto}
            onClick={() => {
              scorre.stop();
              setGira(false);
              onCambia(h);
            }}
          >
            <span className="timeline-etichetta mono">{h === 0 ? "Ora" : `+${h} h`}</span>
            <span className="timeline-sotto">{sotto}</span>
          </UnstyledButton>
        );
      })}
    </div>
  );
}

export default Timeline;
