import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Box,
  Collapse,
  Group,
  Progress,
  Skeleton,
  Stack,
  Text,
  TextInput,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";

import { defaultApiClient } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import type { PanelFailure } from "../lib/panel-state";
import { describeFailure } from "../lib/panel-state";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL } from "../lib/risk-colors";
import type { ComuneCell, ComuneRisk, RiskLevel } from "../types";

// Il comune è l'unità di lettura, la cella è il dettaglio.
//
// A scala nazionale una cella da 1 km² non è leggibile: con un quarto del
// paese in classe Moderata la mappa è una coperta. Il comune invece è
// l'unità su cui si decide qualcosa — c'è un piano comunale, un ufficio
// tecnico, qualcuno che sa dove sono le case — e questa colonna ha
// sostituito due liste che dicevano cose sovrapposte: l'albero regione →
// comune → celle e la classifica dei comuni.
//
// I tre pericoli stanno sulla stessa riga, sempre tutti. Accanto, il numero
// di attenzione: il massimo della priorità (punteggio pesato per quanto c'è
// intorno) con un incremento quando i pericoli oltre soglia sono più di uno.

/** Ordine di lettura delle colonne, stabile a prescindere dai dati. */
const ORDINE = ["landslide", "flood", "wildfire"] as const;

const ABBREVIAZIONE: Record<string, string> = {
  None: "—",
  Low: "basso",
  Moderate: "moderato",
  High: "alto",
  VeryHigh: "molto alto",
};

/** Il fondo scala della barra: oltre non si va, perché l'esposizione è
 *  limitata a 2 e il punteggio a 1. */
const ATTENZIONE_MAX = 3;

function Lente(): JSX.Element {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
      <path d="M16 16l5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function Indicatore({
  etichetta,
  classe,
  celle,
}: {
  etichetta: string;
  classe: RiskLevel;
  celle: number;
}): JSX.Element {
  const vuoto = classe === "None";
  return (
    <Tooltip
      label={
        vuoto
          ? `${etichetta}: nessuna cella sopra la soglia`
          : `${etichetta}: ${RISK_LABEL_IT_BY_LEVEL[classe]}, ${celle} celle valutate`
      }
      withArrow
    >
      <Group gap={4} wrap="nowrap" className={`cb-haz ${vuoto ? "is-quiet" : ""}`}>
        <Box
          className="cb-chip"
          style={{ background: RISK_COLOR_BY_LEVEL[classe] }}
          aria-hidden
        />
        <Text span size="xs" fw={500}>
          {etichetta}
        </Text>
        <Text span size="xs" fw={700}>
          {ABBREVIAZIONE[classe] ?? classe}
        </Text>
      </Group>
    </Tooltip>
  );
}

/** Le celle peggiori del comune, caricate solo quando la riga si apre. */
function DettaglioCelle({ istatCode }: { istatCode: string }): JSX.Element {
  const [celle, setCelle] = useState<ComuneCell[] | null>(null);
  const [errore, setErrore] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getComune(istatCode, ctrl.signal)
      .then((r) => setCelle(r.cells.slice(0, 8)))
      .catch(() => {
        if (!ctrl.signal.aborted) setErrore(true);
      });
    return () => ctrl.abort();
  }, [istatCode]);

  if (errore) {
    return (
      <Text size="xs" c="dimmed">
        Dettaglio non disponibile.
      </Text>
    );
  }
  if (celle === null) return <Skeleton height={44} radius="sm" />;
  if (celle.length === 0) {
    return (
      <Text size="xs" c="dimmed">
        Nessuna cella valutata in questo comune.
      </Text>
    );
  }
  return (
    <Stack gap={2}>
      {celle.map((c) => (
        <Group key={`${c.cell_id}-${c.hazard}`} gap={6} wrap="nowrap">
          <Box
            className="cb-chip"
            style={{ background: RISK_COLOR_BY_LEVEL[c.level] }}
            aria-hidden
          />
          <Text span size="xs" c="dimmed" style={{ fontVariantNumeric: "tabular-nums" }}>
            {c.score.toFixed(2)}
          </Text>
          <Text span size="xs">
            {RISK_LABEL_IT_BY_LEVEL[c.level]}
          </Text>
          <Text span size="xs" c="dimmed">
            · {c.hazard === "landslide" ? "frana" : c.hazard === "flood" ? "alluvione" : "incendio"}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}

export function ComuniBoard(): JSX.Element {
  const [comuni, setComuni] = useState<ComuneRisk[] | null>(null);
  const [failure, setFailure] = useState<PanelFailure | null>(null);
  const [cerca, setCerca] = useState("");
  const [aperto, setAperto] = useState<string | null>(null);
  const [tentativo, setTentativo] = useState(0);
  const { available } = useHazard();
  const riprova = useCallback(() => setTentativo((n) => n + 1), []);

  // La ricerca aspetta che chi scrive si fermi: una richiesta per tasto
  // premuto sono otto richieste per «Avezzano».
  const [termine] = useDebouncedValue(cerca.trim(), 300);

  useEffect(() => {
    const ctrl = new AbortController();
    setComuni(null);
    setFailure(null);
    defaultApiClient
      .getTopComuni(undefined, 30, ctrl.signal, termine || undefined)
      .then((r) => setComuni(r.comuni))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        console.error("comuni", err);
        setFailure(describeFailure(err));
      });
    return () => ctrl.abort();
  }, [termine, tentativo]);

  // Le etichette vengono dal backend; l'ordine no, perché una colonna che si
  // sposta fra un aggiornamento e l'altro non si legge.
  const colonne = useMemo(
    () =>
      ORDINE.map((h) => ({
        hazard: h,
        label: available.find((a) => a.hazard === h)?.label_it ?? h,
      })),
    [available],
  );

  return (
    <section className="comuni-board" aria-label="Rischio per comune">
      <h2>Comuni · dal più esposto</h2>
      <TextInput
        placeholder="Cerca il tuo comune"
        aria-label="Cerca il tuo comune"
        leftSection={<Lente />}
        value={cerca}
        onChange={(e) => setCerca(e.currentTarget.value)}
        size="xs"
        mb="sm"
      />
      {failure ? (
        <Alert color="gray" title={failure.title} role="alert">
          <Text size="xs">{failure.detail}</Text>
          {failure.retryable ? (
            <UnstyledButton className="panel-retry" mt={8} onClick={riprova}>
              Riprova
            </UnstyledButton>
          ) : null}
        </Alert>
      ) : comuni === null ? (
        <Stack gap={8} aria-busy>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} height={38} radius="sm" />
          ))}
        </Stack>
      ) : comuni.length === 0 ? (
        <Box className="panel-state is-empty">
          <Text fw={600} size="sm">
            {termine
              ? `Nessun comune trovato per «${termine}»`
              : "Nessun comune sopra la soglia"}
          </Text>
          <Text size="xs" c="dimmed">
            {termine
              ? "Controlla il nome: la ricerca è sul nome ufficiale del comune."
              : "Nessun comune ha celle in classe Moderata o superiore, per nessuno dei pericoli sorvegliati."}
          </Text>
        </Box>
      ) : (
        <Stack gap={0}>
          {comuni.map((c) => {
            const apertoQui = aperto === c.istat_code;
            return (
              <Box key={c.istat_code} className="cb-row">
                <UnstyledButton
                  className="cb-head"
                  onClick={() => setAperto(apertoQui ? null : c.istat_code)}
                  aria-expanded={apertoQui}
                >
                  <Group justify="space-between" wrap="nowrap" align="baseline">
                    <Text fw={650} size="sm">
                      {c.name}
                    </Text>
                    <Tooltip
                      label="Quanto merita attenzione: il pericolo peggiore, pesato per quante persone e quante strade ci sono intorno."
                      withArrow
                      multiline
                      w={240}
                    >
                      <Text size="xs" c="dimmed" style={{ fontVariantNumeric: "tabular-nums" }}>
                        {c.attention.toFixed(2)}
                      </Text>
                    </Tooltip>
                  </Group>
                  <Progress
                    value={Math.min(100, (c.attention / ATTENZIONE_MAX) * 100)}
                    size={3}
                    mt={3}
                    color={RISK_COLOR_BY_LEVEL[c.worst_class]}
                    aria-label={`Attenzione ${c.attention.toFixed(2)} su ${ATTENZIONE_MAX}`}
                  />
                  <Group gap="xs" mt={5} wrap="wrap">
                    {colonne.map((col) => {
                      const h = c.hazards[col.hazard];
                      return (
                        <Indicatore
                          key={col.hazard}
                          etichetta={col.label}
                          classe={h?.class ?? "None"}
                          celle={h?.n_cells ?? 0}
                        />
                      );
                    })}
                  </Group>
                  <Group gap={6} mt={3}>
                    <Text size="xs" c="dimmed">
                      {c.n_cells.toLocaleString("it-IT")} celle
                    </Text>
                    {c.exposure_rank > 0 ? (
                      <Badge size="xs" variant="light" color="gray">
                        abitato o strade vicine
                      </Badge>
                    ) : null}
                  </Group>
                </UnstyledButton>
                <Collapse in={apertoQui}>
                  <Box pl="xs" pb="xs">
                    {apertoQui ? <DettaglioCelle istatCode={c.istat_code} /> : null}
                  </Box>
                </Collapse>
              </Box>
            );
          })}
        </Stack>
      )}
    </section>
  );
}

export default ComuniBoard;
