import { useCallback, useEffect, useMemo, useState } from "react";
import type { JSX } from "react";
import {
  Alert,
  Badge,
  Box,
  Collapse,
  Group,
  Popover,
  Progress,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
  TextInput,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";

import { defaultApiClient } from "../lib/api-client";
import { useHazard } from "../lib/hazard";
import type { PanelFailure } from "../lib/panel-state";
import { describeFailure } from "../lib/panel-state";
import {
  RISK_CLASSES,
  RISK_COLOR_BY_LEVEL,
  RISK_LABEL_IT_BY_LEVEL,
} from "../lib/risk-colors";
import ComuneTrend from "./ComuneTrend";
import PrevisioneTesta from "./PrevisioneTesta";
import type {
  ComuneCell,
  ComuneForecast,
  ComuneHazard,
  ComuneRisk,
  ForecastSchedule,
  RiskLevel,
} from "../types";

// Il comune è l'unità di lettura, la cella è il dettaglio.
//
// A scala nazionale una cella da 1 km² non è leggibile: con un quarto del
// paese in classe Moderata la mappa è una coperta. Il comune invece è
// l'unità su cui si decide qualcosa — c'è un piano comunale, un ufficio
// tecnico, qualcuno che sa dove sono le case — e questa colonna ha
// sostituito due liste che dicevano cose sovrapposte: l'albero regione →
// comune → celle e la classifica dei comuni.
//
// Qui convivono **due scale**, e confonderle è il modo più facile di leggere
// male questa colonna:
//
//   · il **punteggio** di un pericolo va da 0 a 1 ed è quello delle celle;
//   · l'**attenzione** del comune va da 0 a 3, perché è il punteggio
//     moltiplicato per quanto c'è intorno (esposizione fino a 2) e poi
//     aumentato quando i pericoli concomitanti sono più di uno.
//
// Entrambe sono scritte accanto al numero, non lasciate indovinare.
//
// E un pericolo **non misurato** non è un pericolo basso (#143): il motore
// degrada a zero per costruzione, e quello zero, dipinto in fondo alla scala,
// si legge come una buona notizia. Qui ha uno stato suo.

/** Ordine di lettura delle colonne, stabile a prescindere dai dati. */
const ORDINE = ["landslide", "flood", "wildfire"] as const;

const ABBREVIAZIONE: Record<RiskLevel, string> = {
  None: "nessuno",
  Low: "basso",
  Moderate: "moderato",
  High: "alto",
  VeryHigh: "molto alto",
};

/** Il fondo scala dell'attenzione: il punteggio arriva a 1, l'esposizione
 *  moltiplica fino a 3. */
const ATTENZIONE_MAX = 3;

const NOME_PERICOLO: Record<string, string> = {
  landslide: "frana",
  flood: "alluvione",
  wildfire: "incendio",
};

/** «3 ore fa», non un timestamp ISO. Un punteggio senza data non si sa se è
 *  di adesso o di ieri, e su un rischio è la differenza fra un'informazione e
 *  un numero. */
function quando(iso: string): string {
  const minuti = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (!Number.isFinite(minuti) || minuti < 0) return "";
  if (minuti < 2) return "adesso";
  if (minuti < 60) return `${minuti} min fa`;
  const ore = Math.round(minuti / 60);
  if (ore < 24) return `${ore} ${ore === 1 ? "ora" : "ore"} fa`;
  const giorni = Math.round(ore / 24);
  return `${giorni} ${giorni === 1 ? "giorno" : "giorni"} fa`;
}

function numero(n: number, cifre = 2): string {
  return n.toLocaleString("it-IT", {
    minimumFractionDigits: cifre,
    maximumFractionDigits: cifre,
  });
}

/** La banda di punteggio di una classe, per dire cosa vuol dire «moderato». */
function banda(level: RiskLevel): string {
  const c = RISK_CLASSES.find((r) => r.level === level);
  return c ? `${numero(c.range[0])}–${numero(c.range[1])}` : "";
}

function Lente(): JSX.Element {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
      <path d="M16 16l5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/** Come si leggono i due numeri. Sta accanto al titolo perché è lì che la
 *  domanda nasce, e si apre solo a chi la fa. */
function ComeSiLegge(): JSX.Element {
  const [aperto, { toggle, close }] = useDisclosure(false);
  return (
    <Popover
      opened={aperto}
      onClose={close}
      width={300}
      position="bottom-end"
      withArrow
      shadow="md"
    >
      <Popover.Target>
        <UnstyledButton
          className="cb-help"
          onClick={toggle}
          aria-label="Come si leggono i numeri"
        >
          ?
        </UnstyledButton>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap={8}>
          <Box>
            <Text size="xs" fw={700}>
              Attenzione, da 0 a {ATTENZIONE_MAX}
            </Text>
            <Text size="xs" c="dimmed">
              Il numero grande accanto al nome. È il punteggio del pericolo
              peggiore moltiplicato per quanto c&apos;è intorno — case, strade,
              ferrovie — e aumentato del 15 % per ogni altro pericolo che sia
              anch&apos;esso almeno moderato. Serve solo a decidere chi guardare
              per primo: non è una probabilità.
            </Text>
          </Box>
          <Box>
            <Text size="xs" fw={700}>
              Punteggio, da 0 a 1
            </Text>
            <Text size="xs" c="dimmed">
              Il numero accanto a ogni pericolo, e quello delle celle. È la
              cella peggiore del comune. Le classi sono bande di questo
              numero: {RISK_CLASSES.map((c) => `${c.label.toLowerCase()} ${numero(c.range[0])}–${numero(c.range[1])}`).join(", ")}.
            </Text>
          </Box>
          <Box>
            <Text size="xs" fw={700}>
              Non misurato
            </Text>
            <Text size="xs" c="dimmed">
              Il dato che quel pericolo richiede non è arrivato. Il punteggio
              varrebbe zero per assenza di misura, non perché non ci sia
              pericolo: per questo non viene mostrato come «nessuno», e non
              entra nel conto dell&apos;attenzione.
            </Text>
          </Box>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}

function Indicatore({
  etichetta,
  dato,
}: {
  etichetta: string;
  dato: ComuneHazard | undefined;
}): JSX.Element {
  // Nessuna riga, o riga senza misura: sono la stessa cosa per chi legge —
  // di questo pericolo, su questo comune, oggi non sappiamo niente.
  if (dato === undefined || !dato.measured) {
    return (
      <Tooltip
        label={`${etichetta}: il dato non è arrivato. Il punteggio varrebbe zero per assenza di misura, non perché non ci sia pericolo.`}
        withArrow
        multiline
        w={250}
      >
        <Group gap={4} wrap="nowrap" className="cb-haz is-unknown">
          <Box className="cb-chip is-unknown" aria-hidden />
          <Text span size="xs" fw={500}>
            {etichetta}
          </Text>
          <Text span size="xs" fs="italic" c="dimmed">
            non misurato
          </Text>
        </Group>
      </Tooltip>
    );
  }
  const classe = dato.class;
  return (
    <Tooltip
      label={`${etichetta}: ${numero(dato.score)} su 1 — ${RISK_LABEL_IT_BY_LEVEL[classe]} (${banda(classe)}). ${dato.n_cells} celle valutate, ${dato.n_alert} sopra la soglia di allerta.`}
      withArrow
      multiline
      w={250}
    >
      <Group gap={4} wrap="nowrap" className="cb-haz">
        <Box
          className="cb-chip"
          style={{ background: RISK_COLOR_BY_LEVEL[classe] }}
          aria-hidden
        />
        <Text span size="xs" fw={500}>
          {etichetta}
        </Text>
        <Text span size="xs" fw={700} style={{ fontVariantNumeric: "tabular-nums" }}>
          {numero(dato.score)}
        </Text>
        <Text span size="xs" c="dimmed">
          {ABBREVIAZIONE[classe]}
        </Text>
      </Group>
    </Tooltip>
  );
}

/** Dove va il comune: il pericolo con il picco previsto più alto, di quanto
 *  sale rispetto ad adesso, e quando.
 *
 *  Un pericolo senza riga previsionale può voler dire due cose diverse, e
 *  qui si distinguono: se per quel pericolo la corsa previsionale c'è stata,
 *  vuol dire **previsto sotto Moderato**; se non c'è stata affatto — oggi è
 *  il caso di incendio e alluvione — vuol dire che non si sa, e la riga lo
 *  tace invece di dirlo tranquillo. */
function RigaPrevisione({
  comune,
  previsti,
  etichette,
}: {
  comune: ComuneRisk;
  previsti: Set<string>;
  etichette: Record<string, string>;
}): JSX.Element | null {
  if (previsti.size === 0) return null;
  const voci = Object.entries(comune.forecast ?? {}) as [string, ComuneForecast][];
  if (voci.length === 0) {
    const nomi = [...previsti].map((h) => (etichette[h] ?? NOME_PERICOLO[h] ?? h).toLowerCase());
    return (
      <Text size="xs" c="dimmed" mt={3} className="cb-prev">
        <span className="cb-prev-freccia" aria-hidden>→</span> Previsto: {nomi.join(", ")} sotto
        moderato fino a +72 h
      </Text>
    );
  }
  const [hazard, f] = voci.reduce((a, b) => (b[1].priority > a[1].priority ? b : a));
  const ora = comune.hazards[hazard]?.score ?? 0;
  const delta = f.score - ora;
  const freccia = delta > 0.02 ? "↗" : delta < -0.02 ? "↘" : "→";
  const verso = delta > 0.02 ? "in salita" : delta < -0.02 ? "in calo" : "stabile";
  const quando = new Date(f.target_at).toLocaleString("it-IT", {
    weekday: "short",
    hour: "2-digit",
  });
  return (
    <Tooltip
      label={`Picco previsto di ${(etichette[hazard] ?? NOME_PERICOLO[hazard] ?? hazard).toLowerCase()}: ${numero(f.score)} (${RISK_LABEL_IT_BY_LEVEL[f.class]}) a +${f.horizon_h} ore, contro ${numero(ora)} di adesso. È un calcolo sulla pioggia attesa, non un fatto.`}
      withArrow
      multiline
      w={260}
    >
      <Group gap={5} wrap="nowrap" mt={3} className={`cb-prev is-${verso.replace(" ", "-")}`}>
        <span className="cb-prev-freccia" aria-hidden>
          {freccia}
        </span>
        <Text span size="xs">
          Previsto:{" "}
          <strong>
            {(etichette[hazard] ?? NOME_PERICOLO[hazard] ?? hazard).toLowerCase()} {numero(f.score)}
          </strong>{" "}
          {ABBREVIAZIONE[f.class]}
        </Text>
        <Text span size="xs" c="dimmed">
          · {verso} · +{f.horizon_h} h ({quando})
        </Text>
      </Group>
    </Tooltip>
  );
}

/** Le celle peggiori del comune, caricate solo quando la riga si apre. */
function DettaglioCelle({
  istatCode,
  onCella,
}: {
  istatCode: string;
  onCella?: (c: ComuneCell) => void;
}): JSX.Element {
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
      {/* Il punteggio qui è la stessa scala 0–1 dei pericoli sopra, non
          l'attenzione: dirlo evita di leggere 0,40 come «poco» rispetto a
          un 1,37 che è un'altra grandezza. */}
      <Text size="xs" c="dimmed" mb={2}>
        Celle peggiori · punteggio da 0 a 1
      </Text>
      {celle.map((c) => (
        <UnstyledButton
          key={`${c.cell_id}-${c.hazard}`}
          className="cb-cella"
          onClick={() => onCella?.(c)}
          title="Mostra questa cella sulla mappa"
        >
          <Group gap={6} wrap="nowrap">
            <Box
              className="cb-chip"
              style={{ background: RISK_COLOR_BY_LEVEL[c.level] }}
              aria-hidden
            />
            <Text span size="xs" c="dimmed" style={{ fontVariantNumeric: "tabular-nums" }}>
              {numero(c.score)}
            </Text>
            <Text span size="xs">
              {RISK_LABEL_IT_BY_LEVEL[c.level]}
            </Text>
            <Text span size="xs" c="dimmed">
              · {NOME_PERICOLO[c.hazard] ?? c.hazard}
            </Text>
            <Text span size="xs" c="dimmed" className="cb-quando">
              {quando(c.computed_at)}
            </Text>
          </Group>
        </UnstyledButton>
      ))}
    </Stack>
  );
}

/** Il numero del comune, con il suo nome accanto. Senza la parola
 *  «attenzione» era un 1,37 che nessuno sapeva interpretare. */
function Attenzione({
  valore,
  classe,
  prevista = false,
}: {
  valore: number | null;
  classe: RiskLevel;
  /** Con l'ordine sul futuro il numero è l'attenzione **prevista**, e la
   *  parola accanto lo dice: due numeri diversi con lo stesso nome si
   *  confrontano come se fossero la stessa cosa. */
  prevista?: boolean;
}): JSX.Element {
  if (valore === null) {
    return (
      <Tooltip
        label={
          prevista
            ? "Nessun pericolo previsto sopra Moderato su questo comune, fra quelli per cui la previsione è disponibile."
            : "Nessuno dei pericoli ha ricevuto il dato che richiede: non c'è niente da ordinare. Non significa che il comune sia tranquillo."
        }
        withArrow
        multiline
        w={250}
      >
        <Text size="xs" fs="italic" c="dimmed">
          {prevista ? "sotto moderato" : "non misurato"}
        </Text>
      </Tooltip>
    );
  }
  return (
    <Tooltip
      label={`${prevista ? "Attenzione prevista a 72 ore" : "Attenzione"} ${numero(valore)} su ${ATTENZIONE_MAX}. È il punteggio del pericolo peggiore moltiplicato per quanto c'è intorno (case, strade), più il 15 % per ogni altro pericolo almeno moderato. Serve a decidere chi guardare per primo.`}
      withArrow
      multiline
      w={260}
    >
      <Group gap={4} wrap="nowrap" align="baseline">
        <Text span size="xs" c="dimmed">
          {prevista ? "prevista" : "attenzione"}
        </Text>
        <Text
          span
          size="sm"
          fw={700}
          c={RISK_COLOR_BY_LEVEL[classe]}
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {numero(valore)}
        </Text>
      </Group>
    </Tooltip>
  );
}

export function ComuniBoard({
  onComune,
  onCella,
}: {
  /** Porta la mappa sul comune. Cliccare una riga senza che la mappa si
   *  muova è la cosa che rende inutile una classifica geografica. */
  onComune?: (c: ComuneRisk) => void;
  onCella?: (c: ComuneCell) => void;
} = {}): JSX.Element {
  const [comuni, setComuni] = useState<ComuneRisk[] | null>(null);
  const [failure, setFailure] = useState<PanelFailure | null>(null);
  const [cerca, setCerca] = useState("");
  const [aperto, setAperto] = useState<string | null>(null);
  const [tentativo, setTentativo] = useState(0);
  // Adesso o previsto: la stessa lista, due domande. «Chi è messo peggio»
  // e «chi sta per esserlo» — la seconda è quella per cui esiste la
  // previsione, e trova il comune che oggi è sotto soglia e domani no.
  const [ordine, setOrdine] = useState<"now" | "forecast">("now");
  const [schedule, setSchedule] = useState<ForecastSchedule | null>(null);
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
      .getTopComuni(undefined, 30, ctrl.signal, termine || undefined, ordine)
      .then((r) => setComuni(r.comuni))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        console.error("comuni", err);
        setFailure(describeFailure(err));
      });
    return () => ctrl.abort();
  }, [termine, tentativo, ordine]);

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getForecastSchedule(ctrl.signal)
      .then(setSchedule)
      .catch(() => {
        if (!ctrl.signal.aborted) setSchedule(null);
      });
    return () => ctrl.abort();
  }, []);

  const previsti = useMemo(
    () => new Set(Object.keys(schedule?.cells.last_run_by_hazard ?? {})),
    [schedule],
  );
  const etichette = useMemo(
    () => Object.fromEntries(available.map((a) => [a.hazard, a.label_it])),
    [available],
  );

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
      <Group justify="space-between" wrap="nowrap" align="center">
        <h2>Comuni · adesso e previsione</h2>
        <ComeSiLegge />
      </Group>
      <PrevisioneTesta schedule={schedule} />
      <SegmentedControl
        fullWidth
        size="xs"
        mb="xs"
        value={ordine}
        onChange={(v) => setOrdine(v as "now" | "forecast")}
        data={[
          { value: "now", label: "Più esposti adesso" },
          { value: "forecast", label: "Più esposti fra 72 h" },
        ]}
        aria-label="Ordina i comuni"
      />
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
                  onClick={() => {
                    setAperto(apertoQui ? null : c.istat_code);
                    onComune?.(c);
                  }}
                  aria-expanded={apertoQui}
                >
                  <Group justify="space-between" wrap="nowrap" align="baseline">
                    <Text fw={650} size="sm">
                      {c.name}
                    </Text>
                    <Attenzione
                      valore={ordine === "forecast" ? c.forecast_attention : c.attention}
                      classe={c.worst_class}
                      prevista={ordine === "forecast"}
                    />
                  </Group>
                  {c.attention === null ? (
                    <Box className="cb-bar is-unknown" mt={3} aria-hidden />
                  ) : (
                    <Progress
                      value={Math.min(100, (c.attention / ATTENZIONE_MAX) * 100)}
                      size={3}
                      mt={3}
                      color={RISK_COLOR_BY_LEVEL[c.worst_class]}
                      aria-label={`Attenzione ${numero(c.attention)} su ${ATTENZIONE_MAX}`}
                    />
                  )}
                  <Group gap="xs" mt={5} wrap="wrap">
                    {colonne.map((col) => (
                      <Indicatore
                        key={col.hazard}
                        etichetta={col.label}
                        dato={c.hazards[col.hazard]}
                      />
                    ))}
                  </Group>
                  <RigaPrevisione comune={c} previsti={previsti} etichette={etichette} />
                  <Group gap={6} mt={3}>
                    <Text size="xs" c="dimmed">
                      {c.n_cells.toLocaleString("it-IT")} celle
                    </Text>
                    {c.exposure_rank > 0 ? (
                      <Tooltip
                        label={`Esposizione ${numero(c.exposure_rank)}: quanto tessuto urbano, quante strade e ferrovie ci sono nella cella peggiore. È il fattore che moltiplica il punteggio per fare l'attenzione.`}
                        withArrow
                        multiline
                        w={250}
                      >
                        <Badge size="xs" variant="light" color="gray">
                          abitato o strade vicine
                        </Badge>
                      </Tooltip>
                    ) : null}
                  </Group>
                </UnstyledButton>
                <Collapse expanded={apertoQui}>
                  <Box pl="xs" pb="xs">
                    {apertoQui ? (
                      <Stack gap={10}>
                        <ComuneTrend istatCode={c.istat_code} />
                        <DettaglioCelle istatCode={c.istat_code} onCella={onCella} />
                      </Stack>
                    ) : null}
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
