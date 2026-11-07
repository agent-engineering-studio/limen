// «Salute» (#408): la pagina di installazione, a installazione finita. Le
// domande del giorno dopo — i dati arrivano ancora? le quote reggono? c'è
// spazio? — con le risposte che prima stavano solo nei log del worker. Il
// 3 novembre 2026 Open-Meteo pubblico ha risposto 429 per ore e l'incendio è
// stato «non misurato» su tutta l'Italia senza che la mappa lo spiegasse.
//
// Pubblica e in sola lettura: niente chiavi, e dei consumi dell'AI solo i
// token (`ConsumiAi`), mai i dollari.

import { useEffect, useState } from "react";
import type { JSX } from "react";

import { defaultApiClient } from "../lib/api-client";
import { NOMI_PERICOLO } from "../lib/hazard";
import { testi, useLingua, useLocale, useTesti } from "../lib/i18n";
import type { DiscoSalute, PassoSalute, SaluteStato, StatoPasso } from "../types";
import ConsumiAi from "./ConsumiAi";

const AGGIORNA_OGNI_MS = 60_000;
/** Sotto questa quota di disco libero la riga diventa un avviso. */
const DISCO_MINIMO = 0.1;
/** Un battito più vecchio di così: il worker è fermo. */
const BATTITO_MASSIMO_MS = 5 * 60_000;

export function discoBasso(d: DiscoSalute): boolean {
  return d.totale_gb > 0 && d.libero_gb / d.totale_gb < DISCO_MINIMO;
}

export function workerFermo(battito: string | null, adesso: number = Date.now()): boolean {
  return battito === null || adesso - Date.parse(battito) > BATTITO_MASSIMO_MS;
}

const T = testi(
  {
    titolo: "Salute",
    lede: "Le fonti da cui arrivano i dati, le quote, le celle che non si riescono a misurare, il disco e il backup.",
    caricamento: "Lettura della salute…",
    errore: "La salute non si legge: l'API non risponde.",
    workerFermo: "Il worker non dà segni di vita da più di cinque minuti: nessun dato si aggiorna.",
    fonti: "Le fonti",
    nessunaFonte: "Nessuna chiamata registrata ancora: le fonti compaiono dopo il primo sweep.",
    funziona: "Funziona",
    inErrore: "In errore",
    ultimoOk: (q: string) => `ultimo dato: ${q}`,
    maiOk: "nessun dato ricevuto",
    dal: (q: string) => `dalle ${q}`,
    serve: (p: string) => `serve a: ${p}`,
    quote: "Le quote",
    meteoLocale: "Open-Meteo: istanza locale, senza tetto di chiamate.",
    meteoPubblica:
      "Open-Meteo: API pubblica, al massimo 10.000 chiamate al giorno. Lo sweep orario le supera: senza un'istanza locale incendio e alluvione restano spesso «non misurati».",
    glofasPausa: (q: string) =>
      `GloFAS ha esaurito la quota giornaliera: il ramo dei fiumi è sospeso fino alle ${q}.`,
    glofasOk: "GloFAS: quota disponibile.",
    nonMisurate: "Celle non misurate",
    tutteMisurate: "tutte misurate",
    celle: (n: string, tot: string) => `${n} celle su ${tot} senza il dato del giorno`,
    causa: (c: string) => `causa probabile: ${c}`,
    causaIgnota: "causa non nota dalle fonti: vedi i log del worker",
    nessunaValutazione: "Nessuna valutazione ancora: il primo sweep orario la scrive.",
    disco: "Spazio su disco",
    libero: (l: string, t: string) => `${l} GB liberi su ${t}`,
    db: (g: string) => `Database: ${g} GB`,
    discoIgnoto: "Lo spazio si misura col battito del worker: ancora nessun dato.",
    notte: "Backup e lavori notturni",
    backup: "Ultimo backup",
    maiBackup: "Nessun backup ancora: il primo è alle 2:00 UTC.",
    stato: {
      ok: "riuscito",
      avviso: "riuscito, con avvisi",
      errore: "fallito",
      saltato: "saltato",
      in_corso: "in corso",
    } satisfies Record<StatoPasso, string>,
  },
  {
    titolo: "Health",
    lede: "The sources the data come from, the quotas, the cells that cannot be measured, the disk and the backup.",
    caricamento: "Reading health…",
    errore: "Health cannot be read: the API is not answering.",
    workerFermo: "The worker has shown no sign of life for over five minutes: no data is being updated.",
    fonti: "Sources",
    nessunaFonte: "No calls recorded yet: sources appear after the first sweep.",
    funziona: "Working",
    inErrore: "Failing",
    ultimoOk: (q: string) => `last data: ${q}`,
    maiOk: "no data received",
    dal: (q: string) => `since ${q}`,
    serve: (p: string) => `used for: ${p}`,
    quote: "Quotas",
    meteoLocale: "Open-Meteo: local instance, no call limit.",
    meteoPubblica:
      "Open-Meteo: public API, at most 10,000 calls a day. The hourly sweep exceeds it: without a local instance wildfire and flood are often «not measured».",
    glofasPausa: (q: string) =>
      `GloFAS has used up its daily quota: the river branch is suspended until ${q}.`,
    glofasOk: "GloFAS: quota available.",
    nonMisurate: "Unmeasured cells",
    tutteMisurate: "all measured",
    celle: (n: string, tot: string) => `${n} of ${tot} cells without today's data`,
    causa: (c: string) => `likely cause: ${c}`,
    causaIgnota: "cause not known from the sources: see the worker logs",
    nessunaValutazione: "No assessment yet: the first hourly sweep writes it.",
    disco: "Disk space",
    libero: (l: string, t: string) => `${l} GB free of ${t}`,
    db: (g: string) => `Database: ${g} GB`,
    discoIgnoto: "Space is measured with the worker heartbeat: no data yet.",
    notte: "Backup and nightly jobs",
    backup: "Last backup",
    maiBackup: "No backup yet: the first one runs at 2:00 UTC.",
    stato: {
      ok: "succeeded",
      avviso: "succeeded, with warnings",
      errore: "failed",
      saltato: "skipped",
      in_corso: "running",
    } satisfies Record<StatoPasso, string>,
  },
);

export default function SalutePanel(): JSX.Element {
  const t = useTesti(T);
  const { lingua } = useLingua();
  const loc = useLocale();
  const [stato, setStato] = useState<SaluteStato | null>(null);
  const [errore, setErrore] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    const leggi = (): void => {
      defaultApiClient
        .getSalute(ctrl.signal)
        .then((s) => {
          setStato(s);
          setErrore(false);
        })
        .catch(() => {
          if (!ctrl.signal.aborted) setErrore(true);
        });
    };
    leggi();
    const id = window.setInterval(leggi, AGGIORNA_OGNI_MS);
    return () => {
      ctrl.abort();
      window.clearInterval(id);
    };
  }, []);

  const quando = (iso: string): string =>
    new Date(iso).toLocaleString(loc, { dateStyle: "short", timeStyle: "short" });
  const numero = (n: number): string => n.toLocaleString(loc);

  if (!stato) {
    return (
      <section className="salute" aria-label={t.titolo}>
        <h2>{t.titolo}</h2>
        <p role="status">{errore ? t.errore : t.caricamento}</p>
      </section>
    );
  }

  return (
    <section className="salute" aria-label={t.titolo}>
      <h2>{t.titolo}</h2>
      <p className="lede">{t.lede}</p>
      {workerFermo(stato.battito) && (
        <p className="installazione-errore" role="alert">
          {t.workerFermo}
        </p>
      )}

      <h3>{t.fonti}</h3>
      {stato.fonti.length === 0 ? (
        <p className="installazione-nota">{t.nessunaFonte}</p>
      ) : (
        <ul className="salute-righe">
          {stato.fonti.map((f) => (
            <li key={f.id} className={`salute-riga semaforo-${f.in_errore ? "rosso" : "verde"}`}>
              <strong>{f.nome}</strong>:{" "}
              <span className="semaforo-etichetta">{f.in_errore ? t.inErrore : t.funziona}</span>
              <span className="installazione-nota">
                {" "}
                · {f.ultimo_ok ? t.ultimoOk(quando(f.ultimo_ok)) : t.maiOk} ·{" "}
                {t.serve(f.pericoli.map((p) => NOMI_PERICOLO[lingua][p]).join(", "))}
              </span>
              {f.in_errore && f.errore && (
                <p className="installazione-errore">
                  {f.errore} {f.ultimo_errore && `(${t.dal(quando(f.ultimo_errore))})`}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      <h3>{t.nonMisurate}</h3>
      {stato.non_misurate.length === 0 ? (
        <p className="installazione-nota">{t.nessunaValutazione}</p>
      ) : (
        <ul className="salute-righe">
          {stato.non_misurate.map((n) => (
            <li
              key={n.pericolo}
              className={`salute-riga semaforo-${n.celle > 0 ? "rosso" : "verde"}`}
            >
              <strong>{NOMI_PERICOLO[lingua][n.pericolo]}</strong>:{" "}
              <span className="semaforo-etichetta">
                {n.celle > 0 ? t.celle(numero(n.celle), numero(n.totali)) : t.tutteMisurate}
              </span>
              {n.celle > 0 && (
                <p className="installazione-nota">
                  {n.cause.length ? t.causa(n.cause.join(", ")) : t.causaIgnota}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      <h3>{t.quote}</h3>
      <ul className="salute-righe">
        <li
          className={`salute-riga semaforo-${stato.openmeteo === "locale" ? "verde" : "giallo"}`}
        >
          {stato.openmeteo === "locale" ? t.meteoLocale : t.meteoPubblica}
        </li>
        <li className={`salute-riga semaforo-${stato.glofas_in_pausa_fino ? "rosso" : "verde"}`}>
          {stato.glofas_in_pausa_fino
            ? t.glofasPausa(quando(stato.glofas_in_pausa_fino))
            : t.glofasOk}
        </li>
      </ul>
      <ConsumiAi />

      <h3>{t.disco}</h3>
      {stato.dischi.length === 0 ? (
        <p className="installazione-nota">{t.discoIgnoto}</p>
      ) : (
        <ul className="salute-righe">
          {stato.dischi.map((d) => (
            <li
              key={d.nome}
              className={`salute-riga semaforo-${discoBasso(d) ? "rosso" : "verde"}`}
            >
              <strong>{d.nome}</strong>:{" "}
              <span className="semaforo-etichetta">
                {t.libero(numero(d.libero_gb), numero(d.totale_gb))}
              </span>
            </li>
          ))}
        </ul>
      )}
      {stato.db_gb !== null && <p className="installazione-nota">{t.db(numero(stato.db_gb))}</p>}

      <h3>{t.notte}</h3>
      {stato.backup ? (
        <Passo passo={stato.backup} titolo={t.backup} quando={quando} />
      ) : (
        <p className="installazione-nota">{t.maiBackup}</p>
      )}
      <ul className="salute-righe">
        {stato.notturno
          .filter((p) => p.nome !== "backup")
          .map((p) => (
            <Passo key={p.nome} passo={p} titolo={p.nome} quando={quando} elemento="li" />
          ))}
      </ul>
    </section>
  );
}

const COLORE: Record<StatoPasso, string> = {
  ok: "verde",
  avviso: "giallo",
  errore: "rosso",
  saltato: "giallo",
  in_corso: "verde",
};

function Passo({
  passo,
  titolo,
  quando,
  elemento = "p",
}: {
  passo: PassoSalute;
  titolo: string;
  quando: (iso: string) => string;
  elemento?: "p" | "li";
}): JSX.Element {
  const t = useTesti(T);
  const Tag = elemento;
  return (
    <Tag className={`salute-riga semaforo-${COLORE[passo.stato]}`}>
      <strong>{titolo}</strong>:{" "}
      <span className="semaforo-etichetta">{t.stato[passo.stato]}</span>
      {passo.finito_il && <span className="installazione-nota"> · {quando(passo.finito_il)}</span>}
      {passo.nota && <span className="installazione-nota"> — {passo.nota}</span>}
    </Tag>
  );
}
