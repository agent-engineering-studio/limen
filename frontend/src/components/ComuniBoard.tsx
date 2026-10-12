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
import { locale, testi, useLingua, useLocale, useTesti, type Lingua } from "../lib/i18n";
import { describeFailure } from "../lib/panel-state";
import {
  RISK_CLASSES,
  RISK_COLOR_BY_LEVEL,
  RISK_TEXT_BY_LEVEL,
  useEtichetteRischio,
} from "../lib/risk-colors";
import ComuneTrend from "./ComuneTrend";
import { COLORE_ALLERTA } from "../lib/overlays";
import { LETTERE } from "./HazardSelector";
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

const T = testi(
  {
    abbr: {
      None: "nessuno",
      Low: "basso",
      Moderate: "moderato",
      High: "alto",
      VeryHigh: "molto alto",
    } as Record<RiskLevel, string>,
    nomi: { landslide: "frana", flood: "allagamento", wildfire: "incendio" } as Record<
      string,
      string
    >,
    adesso: "adesso",
    minFa: (n: number) => `${n} min fa`,
    oreFa: (n: number) => `${n} ${n === 1 ? "ora" : "ore"} fa`,
    giorniFa: (n: number) => `${n} ${n === 1 ? "giorno" : "giorni"} fa`,
    aiuto: {
      aria: "Come si leggono i numeri",
      numeroTitolo: "Il numero accanto al nome, da 0 a 1",
      numero:
        "Il pericolo peggiore del comune, con il suo nome e la sua classe: " +
        "la stessa scala di tutti gli altri numeri. Non è una media — un " +
        "incendio in classe Alta non diventa «basso» perché oggi non piove.",
      ordineTitolo: "L'ordine della lista",
      ordine:
        "Prima i comuni dove il pericolo peggiore è vicino a case, strade e " +
        "ferrovie, e quelli con più di un pericolo oltre soglia nello stesso " +
        "momento. Per questo un comune con 0,56 può stare sopra uno con 0,67: " +
        "la riga «In cima per» dice il perché.",
      punteggioTitolo: "Punteggio, da 0 a 1",
      punteggio: (classi: string) =>
        "Il numero accanto a ogni pericolo, e quello delle celle. È la " +
        "cella peggiore del comune. Le classi sono bande di questo " +
        `numero: ${classi}.`,
      nonMisuratoTitolo: "Non misurato",
      nonMisurato:
        "Il dato che quel pericolo richiede non è arrivato. Il punteggio " +
        "varrebbe zero per assenza di misura, non perché non ci sia " +
        "pericolo: per questo non viene mostrato come «nessuno», e non " +
        "entra nel conto dell'attenzione.",
    },
    nonArrivato: (etichetta: string) =>
      `${etichetta}: il dato non è arrivato. Il punteggio varrebbe zero per assenza di misura, non perché non ci sia pericolo.`,
    nonMisurato: "non misurato",
    pioggia: (mm: number, soglia: number) => `${mm} mm previsti in 72 h, soglia ${soglia}`,
    spiegaIncendio:
      " È il pericolo meteo potenziale — quanto si propagherebbe un fuoco se partisse — sulla scala FWI di Copernicus EFFIS.",
    spiegaAlluvione: (pioggia: string) =>
      ` Il numero degli allagamenti guarda avanti: è calcolato sulla pioggia prevista nelle prossime 72 ore (${pioggia} mm), non su quella che cade adesso — sotto la soglia il ramo pluviale vale zero.`,
    senzaFiumi:
      " La portata dei fiumi oggi non è disponibile (GloFAS), quindi conta solo la pioggia.",
    indicatore: (
      etichetta: string,
      score: string,
      classe: string,
      banda: string,
      celle: number,
      allerta: number,
    ) =>
      `${etichetta}: ${score} su 1 — ${classe} (${banda}). ${celle} celle valutate, ${allerta} sopra la soglia di allerta.`,
    fiumiNd: " · fiumi n.d.",
    mesi: [
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
    ] as readonly string[],
    volteAnno: (n: number) => `qui capita ~${n} volte l'anno`,
    unaVolta: "qui capita circa una volta l'anno",
    ogniAnni: (n: number) => `qui capita una volta ogni ~${n} anni`,
    rarissima: "qui più rara di una volta in dieci anni",
    fwiLungo: (p: number, mese: string) =>
      `Qui l'FWI di oggi è più alto del ${p}% dei giorni di ${mese} degli ultimi dieci anni.`,
    insolito: (mese: string, p: number) => `insolito per ${mese} (${p}°)`,
    sopraSolito: (mese: string) => `sopra il solito per ${mese}`,
    normaSolito: (mese: string) => `nella norma per ${mese}`,
    previstoSotto: (nomi: string) => `Previsto: ${nomi} sotto moderato fino a +72 h`,
    verso: { su: "in salita", giu: "in calo", piatto: "stabile" },
    piccoPrevisto: (nome: string, score: string, classe: string, h: number, ora: string) =>
      `Picco previsto di ${nome}: ${score} (${classe}) a +${h} ore, contro ${ora} di adesso. È un calcolo sulla pioggia attesa, non un fatto.`,
    previsto: "Previsto:",
    dettaglioNd: "Dettaglio non disponibile.",
    nessunaCella: "Nessuna cella valutata in questo comune.",
    celleTitolo: "Celle peggiori · punteggio da 0 a 1",
    mostraCella: "Mostra questa cella sulla mappa",
    previstoSottoModerato: "previsto sotto moderato",
    testata: {
      prevista: "Picco previsto a 72 ore",
      scelto: "Pericolo scelto",
      peggiore: "Pericolo peggiore del comune",
    },
    testataTooltip: (tipo: string, nome: string, score: string, classe: string, banda: string) =>
      `${tipo}: ${nome} ${score} su 1, ${classe} (${banda}).`,
    previstoNome: (nome: string) => `previsto ${nome}`,
    celle: (n: string) => `${n} celle`,
    esposizione: (e: string) =>
      `Esposizione ${e}: tessuto urbano, strade e ferrovie nella cella peggiore. Pesa sull'ordine: a parità di pericolo, prima dove ci sono persone.`,
    abitato: "abitato o strade vicine",
    oltreSoglia: (n: number) => `${n} pericoli oltre soglia`,
    inCima: (prevista: boolean) => `In ${prevista ? "cima fra 72 h" : "cima"} per:`,
    allertaNd: "n.d.",
    coloreAllerta: ["nessuna", "gialla", "arancione", "rossa"] as readonly string[],
    rischiAllerta: {
      idrogeologico: "idrogeologico",
      idraulico: "idraulico",
      temporali: "temporali",
    },
    suCelle: (n: number) => ` su ${n} celle`,
    mmPrevisti: (mm: number) => ` (${mm} mm previsti in 72 h)`,
    piccoOltre: (giorno: string) =>
      `, con il picco ${giorno}: oltre i due giorni del bollettino`,
    classeMoltoAlta: "in classe molto alta",
    classeAlta: "in classe alta",
    previstaAlta: "prevista in classe alta",
    celleSopra: (n: number) => `: ${n} celle sopra soglia`,
    e: " e ",
    confrontoOltre: (lista: string) =>
      `Limen vede prima: ${lista}. Il bollettino di zona non ha allerta: è un segnale locale da tenere d'occhio, non un'allerta.`,
    confrontoSotto: (lista: string) =>
      `Il bollettino è più severo di Limen per ${lista}: segui il bollettino.`,
    confrontoConcorde: (lista: string) => `Limen conferma il bollettino e dice dove — ${lista}.`,
    soloLimen:
      "Incendio alto: il bollettino idrogeologico non copre gli incendi, questo segnale è solo di Limen.",
    allertaUfficiale: "Allerta ufficiale",
    oggiDomani: (oggi: string, domani: string) => `: oggi ${oggi} · domani ${domani}`,
    fra72: (parola: string) => `Fra 72 ore: ${parola}`,
    sezione: "Rischio per comune",
    trovati: "Comuni trovati",
    esposti: "Comuni più esposti",
    adessoOrdine: "Adesso",
    fra72h: "Fra 72 h",
    ordina: "Ordina i comuni",
    riprova: "Riprova",
    nessunTrovato: (termine: string) => `Nessun comune trovato per «${termine}»`,
    nessunSopra: "Nessun comune sopra la soglia",
    controllaNome: "Controlla il nome: la ricerca è sul nome ufficiale del comune.",
    nessunoPer: (nome: string, prossime: boolean) =>
      `Nessun comune ha celle in classe Moderata o superiore per ${nome}${prossime ? " nelle prossime 72 ore" : ""}.`,
    nessunoTutti:
      "Nessun comune ha celle in classe Moderata o superiore, per nessuno dei pericoli sorvegliati.",
    suUno: (n: string) => `${n} su 1`,
  },
  {
    abbr: {
      None: "none",
      Low: "low",
      Moderate: "moderate",
      High: "high",
      VeryHigh: "very high",
    },
    nomi: { landslide: "landslide", flood: "flood", wildfire: "wildfire" },
    adesso: "just now",
    minFa: (n: number) => `${n} min ago`,
    oreFa: (n: number) => `${n} ${n === 1 ? "hour" : "hours"} ago`,
    giorniFa: (n: number) => `${n} ${n === 1 ? "day" : "days"} ago`,
    aiuto: {
      aria: "How to read the numbers",
      numeroTitolo: "The number next to the name, from 0 to 1",
      numero:
        "The municipality's worst hazard, with its name and class: the same " +
        "scale as every other number. It is not an average — a wildfire in " +
        "High class does not become «low» because it is not raining today.",
      ordineTitolo: "The order of the list",
      ordine:
        "First the municipalities where the worst hazard is close to houses, " +
        "roads and railways, and those with more than one hazard above " +
        "threshold at the same time. That is why a municipality at 0.56 can " +
        "sit above one at 0.67: the «Top because» line says why.",
      punteggioTitolo: "Score, from 0 to 1",
      punteggio: (classi: string) =>
        "The number next to each hazard, and the one of the cells. It is the " +
        "municipality's worst cell. The classes are bands of this " +
        `number: ${classi}.`,
      nonMisuratoTitolo: "Not measured",
      nonMisurato:
        "The data that hazard needs has not arrived. The score would be zero " +
        "for lack of a measurement, not because there is no hazard: that is " +
        "why it is not shown as «none», and it does not count towards the " +
        "attention index.",
    },
    nonArrivato: (etichetta: string) =>
      `${etichetta}: the data has not arrived. The score would be zero for lack of a measurement, not because there is no hazard.`,
    nonMisurato: "not measured",
    pioggia: (mm: number, soglia: number) => `${mm} mm forecast in 72 h, threshold ${soglia}`,
    spiegaIncendio:
      " This is the potential fire-weather hazard — how far a fire would spread if one started — on the Copernicus EFFIS FWI scale.",
    spiegaAlluvione: (pioggia: string) =>
      ` The flood number looks ahead: it is computed on the rain forecast for the next 72 hours (${pioggia}), not on the rain falling now — below the threshold the pluvial branch is zero.`,
    senzaFiumi:
      " River discharge is not available today (GloFAS), so only rain counts.",
    indicatore: (
      etichetta: string,
      score: string,
      classe: string,
      banda: string,
      celle: number,
      allerta: number,
    ) =>
      `${etichetta}: ${score} out of 1 — ${classe} (${banda}). ${celle} cells assessed, ${allerta} above the alert threshold.`,
    fiumiNd: " · rivers n/a",
    mesi: [
      "January",
      "February",
      "March",
      "April",
      "May",
      "June",
      "July",
      "August",
      "September",
      "October",
      "November",
      "December",
    ],
    volteAnno: (n: number) => `happens here ~${n} times a year`,
    unaVolta: "happens here about once a year",
    ogniAnni: (n: number) => `happens here once every ~${n} years`,
    rarissima: "rarer than once in ten years here",
    fwiLungo: (p: number, mese: string) =>
      `Here today's FWI is higher than ${p}% of ${mese} days over the last ten years.`,
    insolito: (mese: string, p: number) => `unusual for ${mese} (P${p})`,
    sopraSolito: (mese: string) => `above normal for ${mese}`,
    normaSolito: (mese: string) => `normal for ${mese}`,
    previstoSotto: (nomi: string) => `Forecast: ${nomi} below moderate up to +72 h`,
    verso: { su: "rising", giu: "falling", piatto: "stable" },
    piccoPrevisto: (nome: string, score: string, classe: string, h: number, ora: string) =>
      `Forecast ${nome} peak: ${score} (${classe}) at +${h} hours, against ${ora} now. It is a computation on expected rain, not a fact.`,
    previsto: "Forecast:",
    dettaglioNd: "Detail not available.",
    nessunaCella: "No cell assessed in this municipality.",
    celleTitolo: "Worst cells · score from 0 to 1",
    mostraCella: "Show this cell on the map",
    previstoSottoModerato: "forecast below moderate",
    testata: {
      prevista: "Forecast peak at 72 hours",
      scelto: "Selected hazard",
      peggiore: "Worst hazard in the municipality",
    },
    testataTooltip: (tipo: string, nome: string, score: string, classe: string, banda: string) =>
      `${tipo}: ${nome} ${score} out of 1, ${classe} (${banda}).`,
    previstoNome: (nome: string) => `forecast ${nome}`,
    celle: (n: string) => `${n} ${n === "1" ? "cell" : "cells"}`,
    esposizione: (e: string) =>
      `Exposure ${e}: urban fabric, roads and railways in the worst cell. It weighs on the order: for an equal hazard, places with people come first.`,
    abitato: "homes or roads nearby",
    oltreSoglia: (n: number) => `${n} hazards above threshold`,
    inCima: (prevista: boolean) => (prevista ? "Top in 72 h because:" : "Top because:"),
    allertaNd: "n/a",
    coloreAllerta: ["none", "yellow", "orange", "red"],
    rischiAllerta: {
      idrogeologico: "hydrogeological",
      idraulico: "hydraulic",
      temporali: "thunderstorms",
    },
    suCelle: (n: number) => ` on ${n} cells`,
    mmPrevisti: (mm: number) => ` (${mm} mm forecast in 72 h)`,
    piccoOltre: (giorno: string) => `, peaking ${giorno}: beyond the bulletin's two days`,
    classeMoltoAlta: "in very high class",
    classeAlta: "in high class",
    previstaAlta: "forecast in high class",
    celleSopra: (n: number) => `: ${n} cells above threshold`,
    e: " and ",
    confrontoOltre: (lista: string) =>
      `Limen sees it first: ${lista}. The zone bulletin has no warning: this is a local signal to keep an eye on, not a warning.`,
    confrontoSotto: (lista: string) =>
      `The bulletin is more severe than Limen for ${lista}: follow the bulletin.`,
    confrontoConcorde: (lista: string) => `Limen confirms the bulletin and says where — ${lista}.`,
    soloLimen:
      "High wildfire hazard: the hydrogeological bulletin does not cover wildfires, this signal comes from Limen alone.",
    allertaUfficiale: "Official warning",
    oggiDomani: (oggi: string, domani: string) => `: today ${oggi} · tomorrow ${domani}`,
    fra72: (parola: string) => `In 72 hours: ${parola}`,
    sezione: "Risk by municipality",
    trovati: "Municipalities found",
    esposti: "Most exposed municipalities",
    adessoOrdine: "Now",
    fra72h: "In 72 h",
    ordina: "Sort municipalities",
    riprova: "Retry",
    nessunTrovato: (termine: string) => `No municipality found for «${termine}»`,
    nessunSopra: "No municipality above the threshold",
    controllaNome: "Check the name: the search uses the official municipality name.",
    nessunoPer: (nome: string, prossime: boolean) =>
      `No municipality has cells in Moderate class or above for ${nome}${prossime ? " in the next 72 hours" : ""}.`,
    nessunoTutti:
      "No municipality has cells in Moderate class or above, for any of the monitored hazards.",
    suUno: (n: string) => `${n} out of 1`,
  },
);

type Testi = (typeof T)["it"];

/** «3 ore fa», non un timestamp ISO. Un punteggio senza data non si sa se è
 *  di adesso o di ieri, e su un rischio è la differenza fra un'informazione e
 *  un numero. */
function quando(iso: string, t: Testi): string {
  const minuti = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (!Number.isFinite(minuti) || minuti < 0) return "";
  if (minuti < 2) return t.adesso;
  if (minuti < 60) return t.minFa(minuti);
  const ore = Math.round(minuti / 60);
  if (ore < 24) return t.oreFa(ore);
  const giorni = Math.round(ore / 24);
  return t.giorniFa(giorni);
}

function numero(n: number, loc: string, cifre = 2): string {
  return n.toLocaleString(loc, {
    minimumFractionDigits: cifre,
    maximumFractionDigits: cifre,
  });
}

/** La banda di punteggio di una classe, per dire cosa vuol dire «moderato». */
function banda(level: RiskLevel, loc: string): string {
  const c = RISK_CLASSES.find((r) => r.level === level);
  return c ? `${numero(c.range[0], loc)}–${numero(c.range[1], loc)}` : "";
}

/** Come si leggono i due numeri. Sta accanto al titolo perché è lì che la
 *  domanda nasce, e si apre solo a chi la fa. */
function ComeSiLegge(): JSX.Element {
  const [aperto, { toggle, close }] = useDisclosure(false);
  const t = useTesti(T).aiuto;
  const loc = useLocale();
  const etichette = useEtichetteRischio();
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
          aria-label={t.aria}
        >
          ?
        </UnstyledButton>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap={8}>
          <Box>
            <Text size="xs" fw={700}>
              {t.numeroTitolo}
            </Text>
            <Text size="xs" c="dimmed">
              {t.numero}
            </Text>
          </Box>
          <Box>
            <Text size="xs" fw={700}>
              {t.ordineTitolo}
            </Text>
            <Text size="xs" c="dimmed">
              {t.ordine}
            </Text>
          </Box>
          <Box>
            <Text size="xs" fw={700}>
              {t.punteggioTitolo}
            </Text>
            <Text size="xs" c="dimmed">
              {t.punteggio(
                RISK_CLASSES.map(
                  (c) =>
                    `${etichette[c.level].toLowerCase()} ${numero(c.range[0], loc)}–${numero(c.range[1], loc)}`,
                ).join(", "),
              )}
            </Text>
          </Box>
          <Box>
            <Text size="xs" fw={700}>
              {t.nonMisuratoTitolo}
            </Text>
            <Text size="xs" c="dimmed">
              {t.nonMisurato}
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
  const { lingua } = useLingua();
  return (
    <>
      <span className={`cb-sigla hz-${hazard}`} aria-hidden>
        {LETTERE[lingua][hazard as HazardType] ?? etichetta.charAt(0)}
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
  const t = useTesti(T);
  const { lingua } = useLingua();
  const loc = locale(lingua);
  const etichetteRischio = useEtichetteRischio();
  // Nessuna riga, o riga senza misura: sono la stessa cosa per chi legge —
  // di questo pericolo, su questo comune, oggi non sappiamo niente.
  if (dato === undefined || !dato.measured) {
    return (
      <Tooltip
        label={t.nonArrivato(etichetta)}
        withArrow
        multiline
        w={250}
      >
        <Group gap={4} wrap="nowrap" className="cb-haz is-unknown">
          <Box className="cb-chip is-unknown" aria-hidden />
          <Sigla hazard={hazard} etichetta={etichetta} />
          <Text span size="xs" fs="italic" c="dimmed">
            {t.nonMisurato}
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
      ? t.pioggia(Math.round(dato.rain_mm), Math.round(dato.rain_threshold_mm))
      : null;
  const senzaFiumi = dato.discharge_known === false;
  const rarita = pioggia !== null ? raritaPioggia(dato.rain_volte_anno, lingua) : null;
  const stagione = rispettoAlSolito(dato.fwi_percentile, dato.fwi_month, lingua);
  // L'incendio è un pericolo potenziale: detto qui, dove il numero si legge
  // per primo, «alto» non suona come un fuoco in corso.
  const spiegaIncendio =
    hazard === "wildfire"
      ? t.spiegaIncendio +
        (stagione ? ` ${stagione.lungo}` : "")
      : "";
  const spiegaAlluvione =
    pioggia === null
      ? ""
      : t.spiegaAlluvione(pioggia) + (senzaFiumi ? t.senzaFiumi : "");
  return (
    <Tooltip
      label={`${t.indicatore(etichetta, numero(dato.score, loc), etichetteRischio[classe], banda(classe, loc), dato.n_cells, dato.n_alert)}${spiegaAlluvione}${spiegaIncendio}`}
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
          {numero(dato.score, loc)}
        </Text>
        <Text span size="xs" c="dimmed">
          {t.abbr[classe]}
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
            {rarita ? (
              <span className={rarita.rara ? "cb-insolito" : undefined}> · {rarita.testo}</span>
            ) : null}
            {senzaFiumi ? t.fiumiNd : ""}
          </Text>
        ) : null}
      </Group>
    </Tooltip>
  );
}

/** L'FWI rispetto ai giorni dello stesso mese in quel punto (2016-2025).
 *  Le classi dell'incendio sono assolute, come quelle di EFFIS: FWI 24 è
 *  «alto» ad agosto come a ottobre, ma a ottobre brucia l'1 % dell'area
 *  dell'anno. `null` senza climatologia: «non lo so», non «nella norma». */
/** Quanto è rara la pioggia prevista nel suo luogo (ERA5 2016-2025).
 *  Contesto, non punteggio: «105 mm» a Trieste capita ogni anno, a Bari mai.
 *  `null` quando non c'è climatologia o la pioggia è ordinaria. */
export function raritaPioggia(
  volte: number | null | undefined,
  lingua: Lingua = "it",
): { testo: string; rara: boolean } | null {
  const t = T[lingua];
  if (volte == null) return null;
  if (volte >= 1.5) return { testo: t.volteAnno(Math.round(volte)), rara: false };
  if (volte >= 0.5) return { testo: t.unaVolta, rara: false };
  if (volte >= 0.1) return { testo: t.ogniAnni(Math.round(1 / volte)), rara: true };
  return { testo: t.rarissima, rara: true };
}

export function rispettoAlSolito(
  percentile: number | null | undefined,
  mese: number | null | undefined,
  lingua: Lingua = "it",
): { testo: string; lungo: string; insolito: boolean } | null {
  const t = T[lingua];
  if (percentile == null || mese == null) return null;
  const nome = t.mesi[mese - 1] ?? "";
  const lungo = t.fwiLungo(percentile, nome);
  if (percentile >= 90) return { testo: t.insolito(nome, percentile), lungo, insolito: true };
  if (percentile >= 60) return { testo: t.sopraSolito(nome), lungo, insolito: false };
  return { testo: t.normaSolito(nome), lungo, insolito: false };
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
  const t = useTesti(T);
  const loc = useLocale();
  const etichetteRischio = useEtichetteRischio();
  if (previsti.size === 0) return null;
  const voci = Object.entries(comune.forecast ?? {}) as [string, ComuneForecast][];
  if (voci.length === 0) {
    const nomi = [...previsti].map((h) => (etichette[h] ?? t.nomi[h] ?? h).toLowerCase());
    return (
      <Text size="xs" c="dimmed" mt={3} className="cb-prev">
        <span className="cb-prev-freccia" aria-hidden>→</span> {t.previstoSotto(nomi.join(", "))}
      </Text>
    );
  }
  const [hazard, f] = voci.reduce((a, b) => (b[1].priority > a[1].priority ? b : a));
  const ora = comune.hazards[hazard]?.score ?? 0;
  const delta = f.score - ora;
  const freccia = delta > 0.02 ? "↗" : delta < -0.02 ? "↘" : "→";
  // La classe CSS resta sulla parola italiana: è un identificatore, non testo.
  const chiave = delta > 0.02 ? "su" : delta < -0.02 ? "giu" : "piatto";
  const classe = { su: "in-salita", giu: "in-calo", piatto: "stabile" }[chiave];
  const verso = t.verso[chiave];
  const nome = (etichette[hazard] ?? t.nomi[hazard] ?? hazard).toLowerCase();
  const quando = new Date(f.target_at).toLocaleString(loc, {
    weekday: "short",
    hour: "2-digit",
  });
  return (
    <Tooltip
      label={t.piccoPrevisto(nome, numero(f.score, loc), etichetteRischio[f.class], f.horizon_h, numero(ora, loc))}
      withArrow
      multiline
      w={260}
    >
      <Group gap={5} wrap="nowrap" mt={3} className={`cb-prev is-${classe}`}>
        <span className="cb-prev-freccia" aria-hidden>
          {freccia}
        </span>
        <Text span size="xs">
          {t.previsto}{" "}
          <strong>
            {nome} {numero(f.score, loc)}
          </strong>{" "}
          {t.abbr[f.class]}
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
  const t = useTesti(T);
  const loc = useLocale();
  const etichetteRischio = useEtichetteRischio();

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
        {t.dettaglioNd}
      </Text>
    );
  }
  if (celle === null) return <Skeleton height={44} radius="sm" />;
  if (celle.length === 0) {
    return (
      <Text size="xs" c="dimmed">
        {t.nessunaCella}
      </Text>
    );
  }
  return (
    <Stack gap={2}>
      {/* Il punteggio qui è la stessa scala 0–1 dei pericoli sopra, non
          l'attenzione: dirlo evita di leggere 0,40 come «poco» rispetto a
          un 1,37 che è un'altra grandezza. */}
      <Text size="xs" c="dimmed" mb={2}>
        {t.celleTitolo}
      </Text>
      {celle.map((c) => (
        <UnstyledButton
          key={`${c.cell_id}-${c.hazard}`}
          className="cb-cella"
          onClick={() => onCella?.(c)}
          title={t.mostraCella}
        >
          <Group gap={6} wrap="nowrap">
            <Box
              className="cb-chip"
              style={{ background: RISK_COLOR_BY_LEVEL[c.level] }}
              aria-hidden
            />
            <Text span size="xs" c="dimmed" style={{ fontVariantNumeric: "tabular-nums" }}>
              {numero(c.score, loc)}
            </Text>
            <Text span size="xs">
              {etichetteRischio[c.level]}
            </Text>
            <Text span size="xs" c="dimmed">
              · {t.nomi[c.hazard] ?? c.hazard}
            </Text>
            <Text span size="xs" c="dimmed" className="cb-quando">
              {quando(c.computed_at, t)}
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

/** Con un pericolo scelto nel quadro nazionale il picco è il suo, anche se
 *  un altro pericolo del comune è più alto: la lista è ordinata su quello. */
function piccoDi(c: ComuneRisk, prevista: boolean, pericolo?: string): Picco | null {
  const tutte: Picco[] = prevista
    ? Object.entries(c.forecast ?? {}).map(([h, f]) => ({
        hazard: h,
        score: f.score,
        level: f.class,
      }))
    : Object.entries(c.hazards)
        .filter(([, v]) => v.measured)
        .map(([h, v]) => ({ hazard: h, score: v.score, level: v.class }));
  const voci = pericolo ? tutte.filter((v) => v.hazard === pericolo) : tutte;
  if (voci.length === 0) return null;
  return voci.reduce((a, b) => (b.score > a.score ? b : a));
}

function Testata({
  picco,
  prevista,
  etichette,
  scelto = false,
}: {
  picco: Picco | null;
  prevista: boolean;
  etichette: Record<string, string>;
  /** Il picco è del pericolo scelto, non per forza il peggiore del comune. */
  scelto?: boolean;
}): JSX.Element {
  const t = useTesti(T);
  const loc = useLocale();
  const etichetteRischio = useEtichetteRischio();
  if (picco === null) {
    return (
      <Text size="xs" fs="italic" c="dimmed">
        {prevista ? t.previstoSottoModerato : t.nonMisurato}
      </Text>
    );
  }
  const nome = (etichette[picco.hazard] ?? t.nomi[picco.hazard] ?? picco.hazard).toLowerCase();
  const tipo = prevista ? t.testata.prevista : scelto ? t.testata.scelto : t.testata.peggiore;
  return (
    <Tooltip
      label={t.testataTooltip(
        tipo,
        nome,
        numero(picco.score, loc),
        etichetteRischio[picco.level],
        banda(picco.level, loc),
      )}
      withArrow
      multiline
      w={250}
    >
      <Group gap={4} wrap="nowrap" align="baseline">
        <Text span size="xs" c="dimmed">
          {prevista ? t.previstoNome(nome) : nome}
        </Text>
        <Text
          span
          size="sm"
          fw={700}
          c={RISK_TEXT_BY_LEVEL[picco.level]}
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {numero(picco.score, loc)}
        </Text>
        <Text span size="xs" c="dimmed">
          {t.abbr[picco.level]}
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
  scelto = false,
}: {
  c: ComuneRisk;
  picco: Picco | null;
  prevista: boolean;
  etichette: Record<string, string>;
  celle: number;
  /** Ordinata su un pericolo solo: la concomitanza non pesa sull'ordine, e
   *  dirla come motivo sarebbe falso. */
  scelto?: boolean;
}): JSX.Element | null {
  const t = useTesti(T);
  const loc = useLocale();
  const quante = t.celle(celle.toLocaleString(loc));
  if (picco === null) {
    return (
      <Text size="xs" c="dimmed" mt={3}>
        {quante}
      </Text>
    );
  }
  const nome = (etichette[picco.hazard] ?? t.nomi[picco.hazard] ?? picco.hazard).toLowerCase();
  const oltre = prevista
    ? Object.values(c.forecast ?? {}).filter((f) => RANGO[f.class] >= RANGO.Moderate).length
    : Object.values(c.hazards).filter((v) => v.measured && RANGO[v.class] >= RANGO.Moderate)
        .length;
  const motivi: JSX.Element[] = [
    <span key="p">
      {nome} {t.abbr[picco.level]}
    </span>,
  ];
  if (c.exposure_rank > 0) {
    motivi.push(
      <Tooltip
        key="e"
        label={t.esposizione(numero(c.exposure_rank, loc))}
        withArrow
        multiline
        w={250}
      >
        <span className="cb-motivo-esp">{t.abitato}</span>
      </Tooltip>,
    );
  }
  if (oltre >= 2 && !scelto) motivi.push(<span key="n">{t.oltreSoglia(oltre)}</span>);
  return (
    <Text size="xs" c="dimmed" mt={3} className="cb-perche">
      {quante} · {t.inCima(prevista)}{" "}
      {motivi.flatMap((m, k) => (k === 0 ? [m] : [<span key={`s${k}`}> · </span>, m]))}
    </Text>
  );
}

function giornoAllerta(g: AllertaGiorno | null | undefined, t: Testi): string {
  if (!g) return t.allertaNd;
  if (g.livello === 0) return t.coloreAllerta[0] ?? "";
  const rischi = (
    [
      [t.rischiAllerta.idrogeologico, g.idrogeologico],
      [t.rischiAllerta.idraulico, g.idraulico],
      [t.rischiAllerta.temporali, g.temporali],
    ] as const
  )
    .filter(([, v]) => v > 0)
    .map(([nome]) => nome);
  return `${t.coloreAllerta[g.livello] ?? "?"} (${rischi.join(", ")})`;
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
  lingua: Lingua = "it",
): ConfrontoBollettino | null {
  const t = T[lingua];
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
    const nome = t.nomi[hazard] ?? hazard;
    if (Math.max(rangoOra, rangoPrevisto) >= RANGO.High && livello === 0) {
      const dove = ora && ora.n_alert > 0 ? t.suCelle(ora.n_alert) : "";
      const perche =
        hazard === "flood" && ora?.rain_mm != null ? t.mmPrevisti(Math.round(ora.rain_mm)) : "";
      const quando =
        previsto && RANGO[previsto.class] >= RANGO.High && new Date(previsto.target_at).getTime() >= fineDomani(allerta.emesso)
          ? t.piccoOltre(
              new Date(previsto.target_at).toLocaleDateString(locale(lingua), {
                weekday: "short",
                day: "numeric",
              }),
            )
          : "";
      const stato =
        ora && rangoOra >= RANGO.High
          ? ora.class === "VeryHigh"
            ? t.classeMoltoAlta
            : t.classeAlta
          : t.previstaAlta;
      oltre.push(`${nome} ${stato}${dove}${perche}${quando}`);
    } else if (livello > 0 && Math.max(rangoOra, rangoPrevisto) >= RANGO.Moderate) {
      concordi.push(`${nome}${ora && ora.n_alert > 0 ? t.celleSopra(ora.n_alert) : ""}`);
    } else if (livello >= 2 && Math.max(rangoOra, rangoPrevisto) < RANGO.Moderate) {
      sotto.push(nome);
    }
  }
  if (oltre.length > 0) {
    return {
      tono: "oltre",
      testo: t.confrontoOltre(oltre.join("; ")),
    };
  }
  if (sotto.length > 0) {
    return {
      tono: "sotto",
      testo: t.confrontoSotto(sotto.join(t.e)),
    };
  }
  if (concordi.length > 0) {
    return { tono: "concorde", testo: t.confrontoConcorde(concordi.join("; ")) };
  }
  const fuoco = comune.hazards["wildfire"];
  if (fuoco?.measured && RANGO[fuoco.class] >= RANGO.High) {
    return {
      tono: "solo-limen",
      testo: t.soloLimen,
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
  const t = useTesti(T);
  const { lingua } = useLingua();
  if (!allerta) return null;
  const massima = Math.max(allerta.oggi?.livello ?? 0, allerta.domani?.livello ?? 0);
  const confronto = confrontoBollettino(allerta, comune, lingua);
  return (
    <Box mt={4} className="cb-allerta">
      <Group gap={6} wrap="nowrap" align="baseline">
        <span
          className="cb-allerta-punto"
          style={{ background: COLORE_ALLERTA[massima] }}
          aria-hidden
        />
        <Text span size="xs">
          <strong>{t.allertaUfficiale}</strong>{" "}
          <Text span size="xs" c="dimmed">
            ({allerta.zona})
          </Text>
          {t.oggiDomani(giornoAllerta(allerta.oggi, t), giornoAllerta(allerta.domani, t))}
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
  pericolo,
}: {
  comune: ComuneRisk;
  previsti: Set<string>;
  /** Con un pericolo scelto la freccia parla di quello, come il numero accanto. */
  pericolo?: string;
}): JSX.Element | null {
  const t = useTesti(T);
  const guardati = pericolo
    ? new Set([...previsti].filter((h) => h === pericolo))
    : previsti;
  if (guardati.size === 0) return null;
  // Solo i pericoli che hanno una previsione, da entrambe le parti: un
  // incendio a 0,8 senza futuro contro una frana prevista in salita darebbe
  // una freccia in calo che non dice niente di nessuno dei due.
  const ora = Object.entries(comune.hazards)
    .filter(([h, v]) => guardati.has(h) && v.measured)
    .reduce<number | null>((m, [, v]) => (m === null || v.score > m ? v.score : m), null);
  if (ora === null) return null;
  // Senza riga previsionale un pericolo previsto sta sotto Moderato.
  const poi = Object.entries(comune.forecast ?? {})
    .filter(([h]) => guardati.has(h))
    .reduce((m, [, f]) => Math.max(m, f.score), 0);
  const delta = poi - ora;
  // Senza righe previsionali il futuro è sotto Moderato: se oggi si è sopra,
  // si scende.
  const verso = delta > 0.02 ? "su" : delta < -0.02 ? "giu" : "piatto";
  const segno = { su: "↗", giu: "↘", piatto: "→" }[verso];
  const parola = t.verso[verso];
  return (
    <span className={`cb-tendenza is-${verso}`} title={t.fra72(parola)}>
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
  // L'errore e non la frase: la frase si scrive al rendering, nella lingua
  // di quel momento.
  const [errore, setErrore] = useState<{ err: unknown } | null>(null);
  const t = useTesti(T);
  const { lingua } = useLingua();
  const loc = locale(lingua);
  const [aperto, setAperto] = useState<string | null>(null);
  const [tentativo, setTentativo] = useState(0);
  // Adesso o previsto: la stessa lista, due domande. «Chi è messo peggio»
  // e «chi sta per esserlo» — la seconda è quella per cui esiste la
  // previsione, e trova il comune che oggi è sotto soglia e domani no.
  const [ordine, setOrdine] = useState<"now" | "forecast">("now");
  const schedule = useForecastSchedule();
  const { available, view } = useHazard();
  // «Tutti i pericoli» ordina sull'attenzione complessiva; un pericolo scelto
  // ordina su quello, e la testata di ogni riga mostra il suo numero. Con
  // meno di due pericoli il selettore non c'è, e non c'è niente da filtrare.
  const pericolo = view === "multi" || available.length < 2 ? undefined : view;
  // In italiano i nomi sono quelli del database; l'inglese il database non
  // l'ha, e li danno i testi del componente.
  const etichette = useMemo(
    () =>
      Object.fromEntries(
        available.map((a) => {
          const en = T.en.nomi[a.hazard] ?? a.hazard;
          return [a.hazard, lingua === "it" ? a.label_it : en.charAt(0).toUpperCase() + en.slice(1)];
        }),
      ),
    [available, lingua],
  );
  const nomePericolo = pericolo
    ? (etichette[pericolo] ?? t.nomi[pericolo] ?? pericolo).toLowerCase()
    : "";
  const riprova = useCallback(() => setTentativo((n) => n + 1), []);

  // La ricerca aspetta che chi scrive si fermi: una richiesta per tasto
  // premuto sono otto richieste per «Avezzano».
  const [termine] = useDebouncedValue(cerca.trim(), 300);

  useEffect(() => {
    const ctrl = new AbortController();
    setComuni(null);
    setErrore(null);
    defaultApiClient
      .getTopComuni(undefined, 30, ctrl.signal, termine || undefined, ordine, pericolo)
      .then((r) => setComuni(r.comuni))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        console.error("comuni", err);
        setErrore({ err });
      });
    return () => ctrl.abort();
  }, [termine, tentativo, ordine, pericolo]);

  const previsti = useMemo(
    () => new Set(Object.keys(schedule?.cells.last_run_by_hazard ?? {})),
    [schedule],
  );
  const failure = errore ? describeFailure(errore.err, lingua) : null;

  // Le etichette vengono dal backend; l'ordine no, perché una colonna che si
  // sposta fra un aggiornamento e l'altro non si legge.
  const colonne = useMemo(
    () =>
      ORDINE.map((h) => ({
        hazard: h,
        label: etichette[h] ?? h,
      })),
    [etichette],
  );

  return (
    <section className="comuni-board rail-sezione" aria-label={t.sezione}>
      <div className="rail-testa">
        <Group gap={6} wrap="nowrap">
          <h2>
            {termine ? t.trovati : t.esposti}
            {pericolo ? ` · ${nomePericolo}` : ""}
          </h2>
          <ComeSiLegge />
        </Group>
        <SegmentedControl
          size="xs"
          value={ordine}
          onChange={(v) => setOrdine(v as "now" | "forecast")}
          data={[
            { value: "now", label: t.adessoOrdine },
            { value: "forecast", label: t.fra72h },
          ]}
          aria-label={t.ordina}
        />
      </div>
      {failure ? (
        <Alert color="gray" title={failure.title} role="alert">
          <Text size="xs">{failure.detail}</Text>
          {failure.retryable ? (
            <UnstyledButton className="panel-retry" mt={8} onClick={riprova}>
              {t.riprova}
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
            {termine ? t.nessunTrovato(termine) : t.nessunSopra}
          </Text>
          <Text size="xs" c="dimmed">
            {termine
              ? t.controllaNome
              : pericolo
                ? t.nessunoPer(nomePericolo, ordine === "forecast")
                : t.nessunoTutti}
          </Text>
        </Box>
      ) : (
        <Stack gap={0}>
          {comuni.map((c, posizione) => {
            const apertoQui = aperto === c.istat_code;
            const picco = piccoDi(c, ordine === "forecast", pericolo);
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
                        scelto={pericolo !== undefined}
                      />
                      <Tendenza comune={c} previsti={previsti} pericolo={pericolo} />
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
                        aria-label={t.suUno(numero(pk.score, loc))}
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
                      scelto={pericolo !== undefined}
                    />
                  </Box>
                </UnstyledButton>
                <Collapse expanded={apertoQui}>
                  <Box pl="xs" pb="xs">
                    {apertoQui ? (
                      <Stack gap={10}>
                        <ComuneTrend istatCode={c.istat_code} hazard={pericolo} />
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
