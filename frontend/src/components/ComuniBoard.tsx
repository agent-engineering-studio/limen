import { useCallback, useEffect, useMemo, useState } from "react";
import type { JSX } from "react";
import {
  Alert,
  Box,
  Collapse,
  Group,
  Popover,
  Progress,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";

import { defaultApiClient } from "../lib/api-client";
import { useForecastSchedule } from "../lib/forecast-schedule";
import { useHazard } from "../lib/hazard";
import type { PanelFailure } from "../lib/panel-state";
import { describeFailure } from "../lib/panel-state";
import {
  RISK_CLASSES,
  RISK_COLOR_BY_LEVEL,
  RISK_LABEL_IT_BY_LEVEL,
  RISK_TEXT_BY_LEVEL,
} from "../lib/risk-colors";
import ComuneTrend from "./ComuneTrend";
import { COLORE_ALLERTA } from "../lib/overlays";
import { LETTERA } from "./HazardSelector";
import type {
  AllertaGiorno,
  AllertaUfficiale,
  ComuneCell,
  ComuneForecast,
  ComuneHazard,
  ComuneRisk,
  HazardType,
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
              Il numero accanto al nome, da 0 a 1
            </Text>
            <Text size="xs" c="dimmed">
              Il pericolo peggiore del comune, con il suo nome e la sua classe:
              la stessa scala di tutti gli altri numeri. Non è una media — un
              incendio in classe Alta non diventa «basso» perché oggi non piove.
            </Text>
          </Box>
          <Box>
            <Text size="xs" fw={700}>
              L&apos;ordine della lista
            </Text>
            <Text size="xs" c="dimmed">
              Prima i comuni dove il pericolo peggiore è vicino a case, strade e
              ferrovie, e quelli con più di un pericolo oltre soglia nello stesso
              momento. Per questo un comune con 0,56 può stare sopra uno con 0,67:
              la riga «In cima per» dice il perché.
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

/** La lettera del pericolo nel chip, con il nome per intero a chi non vede
 *  la lettera: «F» è una sigla, «Frana» è un'informazione. */
function Sigla({ hazard, etichetta }: { hazard: string; etichetta: string }): JSX.Element {
  return (
    <>
      <span className={`cb-sigla hz-${hazard}`} aria-hidden>
        {LETTERA[hazard as HazardType] ?? etichetta.charAt(0)}
      </span>
      <span className="sr-only">{etichetta}</span>
    </>
  );
}

function Indicatore({
  hazard,
  etichetta,
  dato,
}: {
  hazard: string;
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
          <Sigla hazard={hazard} etichetta={etichetta} />
          <Text span size="xs" fs="italic" c="dimmed">
            non misurato
          </Text>
        </Group>
      </Tooltip>
    );
  }
  const classe = dato.class;
  // Solo per l'alluvione arrivano pioggia e soglia. Frane e incendio hanno un
  // punteggio continuo che si muove ogni giorno; l'alluvione è una soglia, e
  // un «0,00» ripetuto per settimane non dice quanto manca.
  const pioggia =
    dato.rain_mm != null && dato.rain_threshold_mm != null
      ? `${Math.round(dato.rain_mm)} mm previsti in 72 h, soglia ${Math.round(dato.rain_threshold_mm)}`
      : null;
  const senzaFiumi = dato.discharge_known === false;
  const stagione = rispettoAlSolito(dato.fwi_percentile, dato.fwi_month);
  // L'incendio è un pericolo potenziale: detto qui, dove il numero si legge
  // per primo, «alto» non suona come un fuoco in corso.
  const spiegaIncendio =
    hazard === "wildfire"
      ? " È il pericolo meteo potenziale — quanto si propagherebbe un fuoco se partisse — sulla scala FWI di Copernicus EFFIS." +
        (stagione ? ` ${stagione.lungo}` : "")
      : "";
  const spiegaAlluvione =
    pioggia === null
      ? ""
      : ` Il numero dell'alluvione guarda avanti: è calcolato sulla pioggia prevista nelle prossime 72 ore (${pioggia} mm), non su quella che cade adesso — sotto la soglia il ramo pluviale vale zero.` +
        (senzaFiumi
          ? " La portata dei fiumi oggi non è disponibile (GloFAS), quindi conta solo la pioggia."
          : "");
  return (
    <Tooltip
      label={`${etichetta}: ${numero(dato.score)} su 1 — ${RISK_LABEL_IT_BY_LEVEL[classe]} (${banda(classe)}). ${dato.n_cells} celle valutate, ${dato.n_alert} sopra la soglia di allerta.${spiegaAlluvione}${spiegaIncendio}`}
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
        <Sigla hazard={hazard} etichetta={etichetta} />
        <Text span size="xs" fw={700} className="mono">
          {numero(dato.score)}
        </Text>
        <Text span size="xs" c="dimmed">
          {ABBREVIAZIONE[classe]}
        </Text>
        {hazard === "wildfire" && dato.fwi != null ? (
          <Text
            span
            size="xs"
            c="dimmed"
            className={`cb-pioggia ${stagione?.insolito ? "cb-insolito" : ""}`}
          >
            · FWI {Math.round(dato.fwi)}
            {stagione ? ` · ${stagione.testo}` : ""}
          </Text>
        ) : null}
        {pioggia !== null ? (
          <Text span size="xs" c="dimmed" className="cb-pioggia">
            · {pioggia}
            {senzaFiumi ? " · fiumi n.d." : ""}
          </Text>
        ) : null}
      </Group>
    </Tooltip>
  );
}

const MESI = [
  "gennaio",
  "febbraio",
  "marzo",
  "aprile",
  "maggio",
  "giugno",
  "luglio",
  "agosto",
  "settembre",
  "ottobre",
  "novembre",
  "dicembre",
];

/** L'FWI rispetto ai giorni dello stesso mese in quel punto (2016-2025).
 *  Le classi dell'incendio sono assolute, come quelle di EFFIS: FWI 24 è
 *  «alto» ad agosto come a ottobre, ma a ottobre brucia l'1 % dell'area
 *  dell'anno. `null` senza climatologia: «non lo so», non «nella norma». */
export function rispettoAlSolito(
  percentile: number | null | undefined,
  mese: number | null | undefined,
): { testo: string; lungo: string; insolito: boolean } | null {
  if (percentile == null || mese == null) return null;
  const nome = MESI[mese - 1] ?? "";
  const lungo = `Qui l'FWI di oggi è più alto del ${percentile}% dei giorni di ${nome} degli ultimi dieci anni.`;
  if (percentile >= 90) return { testo: `insolito per ${nome} (${percentile}°)`, lungo, insolito: true };
  if (percentile >= 60) return { testo: `sopra il solito per ${nome}`, lungo, insolito: false };
  return { testo: `nella norma per ${nome}`, lungo, insolito: false };
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

/** Il pericolo peggiore del comune, sulla stessa scala 0–1 di tutto il resto.
 *
 *  Prima qui c'era l'«attenzione», che arrivava fino a 3 perché moltiplicava
 *  il punteggio per l'esposizione e per i pericoli concomitanti: accanto a
 *  punteggi che arrivano a 1, un 1,37 non si sapeva leggere. Quel numero
 *  resta, ma solo come **ordine** della lista; il perché dell'ordine lo dice
 *  la riga `PercheInCima`, a parole.
 *
 *  Non la media dei tre: con Ispani — frana 0,37, alluvione 0,00, incendio
 *  0,56 alto — la media fa 0,31 «basso», cioè un comune con un incendio in
 *  classe Alta presentato come quasi tranquillo perché oggi non piove. */
interface Picco {
  hazard: string;
  score: number;
  level: RiskLevel;
}

function piccoDi(c: ComuneRisk, prevista: boolean): Picco | null {
  const voci: Picco[] = prevista
    ? Object.entries(c.forecast ?? {}).map(([h, f]) => ({
        hazard: h,
        score: f.score,
        level: f.class,
      }))
    : Object.entries(c.hazards)
        .filter(([, v]) => v.measured)
        .map(([h, v]) => ({ hazard: h, score: v.score, level: v.class }));
  if (voci.length === 0) return null;
  return voci.reduce((a, b) => (b.score > a.score ? b : a));
}

function Testata({
  picco,
  prevista,
  etichette,
}: {
  picco: Picco | null;
  prevista: boolean;
  etichette: Record<string, string>;
}): JSX.Element {
  if (picco === null) {
    return (
      <Text size="xs" fs="italic" c="dimmed">
        {prevista ? "previsto sotto moderato" : "non misurato"}
      </Text>
    );
  }
  const nome = (etichette[picco.hazard] ?? NOME_PERICOLO[picco.hazard] ?? picco.hazard).toLowerCase();
  return (
    <Tooltip
      label={`${prevista ? "Picco previsto a 72 ore" : "Pericolo peggiore del comune"}: ${nome} ${numero(picco.score)} su 1, ${RISK_LABEL_IT_BY_LEVEL[picco.level]} (${banda(picco.level)}).`}
      withArrow
      multiline
      w={250}
    >
      <Group gap={4} wrap="nowrap" align="baseline">
        <Text span size="xs" c="dimmed">
          {prevista ? `previsto ${nome}` : nome}
        </Text>
        <Text
          span
          size="sm"
          fw={700}
          c={RISK_TEXT_BY_LEVEL[picco.level]}
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {numero(picco.score)}
        </Text>
        <Text span size="xs" c="dimmed">
          {ABBREVIAZIONE[picco.level]}
        </Text>
      </Group>
    </Tooltip>
  );
}

const RANGO: Record<RiskLevel, number> = { None: 0, Low: 1, Moderate: 2, High: 3, VeryHigh: 4 };

/** Perché il comune è a questa altezza della lista, a parole.
 *
 *  L'ordine tiene conto di due cose che il numero di testata non mostra:
 *  quanto c'è intorno — case, strade, ferrovie — e quanti pericoli sono
 *  insieme oltre soglia. Senza questa riga un comune con 0,56 sopra uno con
 *  0,67 sembrerebbe un errore. */
function PercheInCima({
  c,
  picco,
  prevista,
  etichette,
  celle,
}: {
  c: ComuneRisk;
  picco: Picco | null;
  prevista: boolean;
  etichette: Record<string, string>;
  celle: number;
}): JSX.Element | null {
  const quante = `${celle.toLocaleString("it-IT")} celle`;
  if (picco === null) {
    return (
      <Text size="xs" c="dimmed" mt={3}>
        {quante}
      </Text>
    );
  }
  const nome = (etichette[picco.hazard] ?? NOME_PERICOLO[picco.hazard] ?? picco.hazard).toLowerCase();
  const oltre = prevista
    ? Object.values(c.forecast ?? {}).filter((f) => RANGO[f.class] >= RANGO.Moderate).length
    : Object.values(c.hazards).filter((v) => v.measured && RANGO[v.class] >= RANGO.Moderate)
        .length;
  const motivi: JSX.Element[] = [
    <span key="p">
      {nome} {ABBREVIAZIONE[picco.level]}
    </span>,
  ];
  if (c.exposure_rank > 0) {
    motivi.push(
      <Tooltip
        key="e"
        label={`Esposizione ${numero(c.exposure_rank)}: tessuto urbano, strade e ferrovie nella cella peggiore. Pesa sull'ordine: a parità di pericolo, prima dove ci sono persone.`}
        withArrow
        multiline
        w={250}
      >
        <span className="cb-motivo-esp">abitato o strade vicine</span>
      </Tooltip>,
    );
  }
  if (oltre >= 2) motivi.push(<span key="n">{oltre} pericoli oltre soglia</span>);
  return (
    <Text size="xs" c="dimmed" mt={3} className="cb-perche">
      {quante} · In {prevista ? "cima fra 72 h" : "cima"} per:{" "}
      {motivi.flatMap((m, k) => (k === 0 ? [m] : [<span key={`s${k}`}> · </span>, m]))}
    </Text>
  );
}

const COLORE_NOME = ["nessuna", "gialla", "arancione", "rossa"] as const;

function giornoAllerta(g: AllertaGiorno | null | undefined): string {
  if (!g) return "n.d.";
  if (g.livello === 0) return "nessuna";
  const rischi = (
    [
      ["idrogeologico", g.idrogeologico],
      ["idraulico", g.idraulico],
      ["temporali", g.temporali],
    ] as const
  )
    .filter(([, v]) => v > 0)
    .map(([nome]) => nome);
  return `${COLORE_NOME[g.livello] ?? "?"} (${rischi.join(", ")})`;
}

/** L'allerta ufficiale della zona del comune, accanto al nostro numero.
 *
 *  È l'unica che vale: Limen la affianca, non la sostituisce. Quando le due
 *  letture divergono lo si dice, e si dice quale vale — il 6 ottobre Trieste
 *  era a 0,75 per alluvione sulle 72 ore e in «nessuna allerta» nel
 *  bollettino per oggi e domani. */
/** Il pericolo di Limen e il rischio del bollettino che parlano della stessa
 *  cosa. Il bollettino idrogeologico/idraulico non copre gli incendi. */
const TIPO_BOLLETTINO: Record<string, "idrogeologico" | "idraulico"> = {
  landslide: "idrogeologico",
  flood: "idraulico",
};

const NOME_HAZ: Record<string, string> = {
  landslide: "frana",
  flood: "alluvione",
  wildfire: "incendio",
};

export interface ConfrontoBollettino {
  tono: "oltre" | "concorde" | "sotto" | "solo-limen";
  testo: string;
}

function fineDomani(emesso: string): number {
  // Il bollettino copre oggi e domani, ora italiana: basta la mezzanotte di
  // dopodomani, con un margine che non sposta il giorno.
  const d = new Date(emesso);
  d.setHours(0, 0, 0, 0);
  return d.getTime() + 2 * 86_400_000;
}

/** Cosa Limen aggiunge al bollettino per questo comune, o dove il bollettino
 *  è più severo. Il confronto è per tipo di rischio — frane con
 *  idrogeologico, alluvione con idraulico — mai il pericolo peggiore contro
 *  il livello complessivo: un incendio alto non contraddice un bollettino
 *  idrogeologico verde. */
export function confrontoBollettino(
  allerta: AllertaUfficiale,
  comune: Pick<ComuneRisk, "hazards" | "forecast">,
): ConfrontoBollettino | null {
  const giorni = [allerta.oggi, allerta.domani].filter((g): g is AllertaGiorno => g != null);
  const bollettino = (tipo: "idrogeologico" | "idraulico"): number =>
    Math.max(0, ...giorni.map((g) => Math.max(g[tipo], g.temporali)));

  const oltre: string[] = [];
  const concordi: string[] = [];
  const sotto: string[] = [];
  for (const [hazard, tipo] of Object.entries(TIPO_BOLLETTINO)) {
    const ora = comune.hazards[hazard];
    const previsto = comune.forecast?.[hazard];
    const rangoOra = ora?.measured ? RANGO[ora.class] : 0;
    const rangoPrevisto = previsto ? RANGO[previsto.class] : 0;
    const livello = bollettino(tipo);
    const nome = NOME_HAZ[hazard] ?? hazard;
    if (Math.max(rangoOra, rangoPrevisto) >= RANGO.High && livello === 0) {
      const dove = ora && ora.n_alert > 0 ? ` su ${ora.n_alert} celle` : "";
      const perche =
        hazard === "flood" && ora?.rain_mm != null ? ` (${Math.round(ora.rain_mm)} mm previsti in 72 h)` : "";
      const quando =
        previsto && RANGO[previsto.class] >= RANGO.High && new Date(previsto.target_at).getTime() >= fineDomani(allerta.emesso)
          ? `, con il picco ${new Date(previsto.target_at).toLocaleDateString("it-IT", { weekday: "short", day: "numeric" })}: oltre i due giorni del bollettino`
          : "";
      const stato =
        ora && rangoOra >= RANGO.High
          ? `in classe ${ora.class === "VeryHigh" ? "molto alta" : "alta"}`
          : "prevista in classe alta";
      oltre.push(`${nome} ${stato}${dove}${perche}${quando}`);
    } else if (livello > 0 && Math.max(rangoOra, rangoPrevisto) >= RANGO.Moderate) {
      concordi.push(`${nome}${ora && ora.n_alert > 0 ? `: ${ora.n_alert} celle sopra soglia` : ""}`);
    } else if (livello >= 2 && Math.max(rangoOra, rangoPrevisto) < RANGO.Moderate) {
      sotto.push(nome);
    }
  }
  if (oltre.length > 0) {
    return {
      tono: "oltre",
      testo: `Limen vede prima: ${oltre.join("; ")}. Il bollettino di zona non ha allerta: è un segnale locale da tenere d'occhio, non un'allerta.`,
    };
  }
  if (sotto.length > 0) {
    return {
      tono: "sotto",
      testo: `Il bollettino è più severo di Limen per ${sotto.join(" e ")}: segui il bollettino.`,
    };
  }
  if (concordi.length > 0) {
    return { tono: "concorde", testo: `Limen conferma il bollettino e dice dove — ${concordi.join("; ")}.` };
  }
  const fuoco = comune.hazards["wildfire"];
  if (fuoco?.measured && RANGO[fuoco.class] >= RANGO.High) {
    return {
      tono: "solo-limen",
      testo: "Incendio alto: il bollettino idrogeologico non copre gli incendi, questo segnale è solo di Limen.",
    };
  }
  return null;
}

export function RigaAllerta({
  allerta,
  comune,
}: {
  allerta: AllertaUfficiale | null | undefined;
  comune: Pick<ComuneRisk, "hazards" | "forecast">;
}): JSX.Element | null {
  if (!allerta) return null;
  const massima = Math.max(allerta.oggi?.livello ?? 0, allerta.domani?.livello ?? 0);
  const confronto = confrontoBollettino(allerta, comune);
  return (
    <Box mt={4} className="cb-allerta">
      <Group gap={6} wrap="nowrap" align="baseline">
        <span
          className="cb-allerta-punto"
          style={{ background: COLORE_ALLERTA[massima] }}
          aria-hidden
        />
        <Text span size="xs">
          <strong>Allerta ufficiale</strong>{" "}
          <Text span size="xs" c="dimmed">
            ({allerta.zona})
          </Text>
          : oggi {giornoAllerta(allerta.oggi)} · domani {giornoAllerta(allerta.domani)}
        </Text>
      </Group>
      {confronto ? (
        <Text size="xs" className={`cb-confronto is-${confronto.tono}`}>
          {confronto.testo}
        </Text>
      ) : null}
    </Box>
  );
}

/** «it-emilia-romagna» → «Emilia-Romagna». La provincia non arriva dal
 *  servizio: la regione basta a distinguere i comuni omonimi. */
function regione(aoi: string): string {
  return aoi
    .replace(/^it-/, "")
    .split("-")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

/** Il verso fra adesso e il picco previsto, accanto al numero. Tace quando
 *  la previsione non c'è: una freccia piatta direbbe «stabile», ed è un'altra
 *  cosa da «non lo so». */
function Tendenza({
  comune,
  previsti,
}: {
  comune: ComuneRisk;
  previsti: Set<string>;
}): JSX.Element | null {
  if (previsti.size === 0) return null;
  // Solo i pericoli che hanno una previsione, da entrambe le parti: un
  // incendio a 0,8 senza futuro contro una frana prevista in salita darebbe
  // una freccia in calo che non dice niente di nessuno dei due.
  const ora = Object.entries(comune.hazards)
    .filter(([h, v]) => previsti.has(h) && v.measured)
    .reduce<number | null>((m, [, v]) => (m === null || v.score > m ? v.score : m), null);
  if (ora === null) return null;
  // Senza riga previsionale un pericolo previsto sta sotto Moderato.
  const poi = Object.entries(comune.forecast ?? {})
    .filter(([h]) => previsti.has(h))
    .reduce((m, [, f]) => Math.max(m, f.score), 0);
  const delta = poi - ora;
  // Senza righe previsionali il futuro è sotto Moderato: se oggi si è sopra,
  // si scende.
  const verso = delta > 0.02 ? "su" : delta < -0.02 ? "giu" : "piatto";
  const segno = { su: "↗", giu: "↘", piatto: "→" }[verso];
  const parola = { su: "in salita", giu: "in calo", piatto: "stabile" }[verso];
  return (
    <span className={`cb-tendenza is-${verso}`} title={`Fra 72 ore: ${parola}`}>
      <span aria-hidden>{segno}</span>
      <span className="sr-only">{parola}</span>
    </span>
  );
}

export function ComuniBoard({
  onComune,
  onCella,
  cerca = "",
}: {
  /** Il testo della ricerca, che sta nella barra in alto (#155). */
  cerca?: string;
  /** Porta la mappa sul comune. Cliccare una riga senza che la mappa si
   *  muova è la cosa che rende inutile una classifica geografica. */
  onComune?: (c: ComuneRisk) => void;
  onCella?: (c: ComuneCell) => void;
} = {}): JSX.Element {
  const [comuni, setComuni] = useState<ComuneRisk[] | null>(null);
  const [failure, setFailure] = useState<PanelFailure | null>(null);
  const [aperto, setAperto] = useState<string | null>(null);
  const [tentativo, setTentativo] = useState(0);
  // Adesso o previsto: la stessa lista, due domande. «Chi è messo peggio»
  // e «chi sta per esserlo» — la seconda è quella per cui esiste la
  // previsione, e trova il comune che oggi è sotto soglia e domani no.
  const [ordine, setOrdine] = useState<"now" | "forecast">("now");
  const schedule = useForecastSchedule();
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
    <section className="comuni-board rail-sezione" aria-label="Rischio per comune">
      <div className="rail-testa">
        <Group gap={6} wrap="nowrap">
          <h2>{termine ? "Comuni trovati" : "Comuni più esposti"}</h2>
          <ComeSiLegge />
        </Group>
        <SegmentedControl
          size="xs"
          value={ordine}
          onChange={(v) => setOrdine(v as "now" | "forecast")}
          data={[
            { value: "now", label: "Adesso" },
            { value: "forecast", label: "Fra 72 h" },
          ]}
          aria-label="Ordina i comuni"
        />
      </div>
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
          {comuni.map((c, posizione) => {
            const apertoQui = aperto === c.istat_code;
            const picco = piccoDi(c, ordine === "forecast");
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
                  <Group justify="space-between" wrap="nowrap" align="baseline" gap={8}>
                    <Group gap={8} wrap="nowrap" align="baseline" style={{ minWidth: 0 }}>
                      <span className="cb-rank mono" aria-hidden>
                        {String(posizione + 1).padStart(2, "0")}
                      </span>
                      <Text fw={700} size="sm" truncate>
                        {c.name}
                      </Text>
                      <Text size="xs" c="dimmed" className="cb-regione">
                        {regione(c.aoi_id)}
                      </Text>
                    </Group>
                    <Group gap={6} wrap="nowrap" align="baseline">
                      <Testata
                        picco={picco}
                        prevista={ordine === "forecast"}
                        etichette={etichette}
                      />
                      <Tendenza comune={c} previsti={previsti} />
                    </Group>
                  </Group>
                  {((pk) =>
                    pk === null ? (
                      <Box className="cb-bar is-unknown cb-rientro" mt={6} aria-hidden />
                    ) : (
                      // La barra è lo stesso numero della testata, su 0–1: prima
                      // era l'attenzione su 3, e la barra piena voleva dire una
                      // cosa diversa dal numero che le stava accanto.
                      <Progress
                        value={Math.min(100, pk.score * 100)}
                        size={4}
                        mt={6}
                        className="cb-rientro"
                        color={RISK_COLOR_BY_LEVEL[pk.level]}
                        aria-label={`${numero(pk.score)} su 1`}
                      />
                    ))(picco)}
                  <Group gap={6} mt={6} wrap="wrap" className="cb-rientro">
                    {colonne.map((col) => (
                      <Indicatore
                        key={col.hazard}
                        hazard={col.hazard}
                        etichetta={col.label}
                        dato={c.hazards[col.hazard]}
                      />
                    ))}
                  </Group>
                  <Box className="cb-rientro">
                    <RigaAllerta allerta={c.allerta_ufficiale} comune={c} />
                    <RigaPrevisione comune={c} previsti={previsti} etichette={etichette} />
                    <PercheInCima
                      c={c}
                      picco={picco}
                      prevista={ordine === "forecast"}
                      etichette={etichette}
                      celle={c.n_cells}
                    />
                  </Box>
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
