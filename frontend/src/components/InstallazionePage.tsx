// «Installazione» (#404, epic #409): cosa serve a Limen, a che punto è, e cosa
// manca a ogni pericolo. La legge chi installa (il tecnico IT dell'ente) e chi
// usa Limen (l'operatore), quindi in primo piano c'è la risposta — il pericolo
// è pronto o no, e perché — e i dettagli tecnici stanno sotto.
//
// Leggere è pubblico come il resto della mappa. Avviare un download chiede il
// token di installazione (#403): arriva con il link stampato da
// `nuovo_host.sh` (`#/installazione?token=…`, dopo il `#`, quindi non passa
// dal server né dai log del proxy), si tiene in sessionStorage e si toglie
// subito dall'indirizzo.

import { useCallback, useEffect, useState } from "react";
import type { JSX } from "react";

import { ApiClientError, defaultApiClient } from "../lib/api-client";
import { NOMI_PERICOLO } from "../lib/hazard";
import { testi, useLingua, useTesti } from "../lib/i18n";
import SalutePanel from "./SalutePanel";
import type {
  DownloadDato,
  HazardType,
  InstallazioneStato,
  LivelloDato,
  VoceDato,
} from "../types";

const CHIAVE_TOKEN = "limen-installazione-token";
const AGGIORNA_OGNI_MS = 5000;
const ORDINE_PERICOLI: HazardType[] = ["landslide", "flood", "wildfire"];
const ORDINE_LIVELLI: LivelloDato[] = ["essenziale", "consigliato", "avanzato"];

export type Semaforo = "verde" | "giallo" | "rosso";

/** Il colore di un pericolo e le voci che lo spiegano. */
export function semaforo(
  pericolo: HazardType,
  stato: InstallazioneStato,
): { colore: Semaforo; mancano: VoceDato[] } {
  const voci = new Map(stato.voci.map((v) => [v.id, v]));
  const essenziali = stato.pericoli.find((p) => p.pericolo === pericolo)?.mancano ?? [];
  if (stato.celle_totali === 0 || essenziali.length > 0) {
    return {
      colore: "rosso",
      mancano: essenziali.flatMap((id) => (voci.has(id) ? [voci.get(id)!] : [])),
    };
  }
  const consigliati = stato.voci.filter(
    (v) => v.livello === "consigliato" && v.pericoli.includes(pericolo) && v.copertura === 0,
  );
  return { colore: consigliati.length ? "giallo" : "verde", mancano: consigliati };
}

/** Percentuale scaricata, o `null` se il totale non si conosce. */
export function percentuale(d: DownloadDato): number | null {
  if (!d.byte_totali) return null;
  return Math.min(100, Math.round((d.byte_fatti / d.byte_totali) * 100));
}

/** Scaricata ma non ancora nelle celle: la carica l'elaborazione del worker (#405). */
export function daCaricare(v: VoceDato): boolean {
  return v.download?.stato === "fatto" && v.copertura === 0 && v.deriva_da === null;
}

function peso(byte: number): string {
  return byte < 1e9 ? `${Math.max(1, Math.round(byte / 1e6))} MB` : `${(byte / 1e9).toFixed(1)} GB`;
}

const T = testi(
  {
    occhiello: "Installazione",
    titolo: "Limen è pronto?",
    titoloInstallato: "Come sta Limen",
    lede:
      "Ogni pericolo ha bisogno di alcuni dati sul territorio. Qui si vede quali ci sono, quali mancano, da dove si scaricano e a che punto è il download.",
    caricamento: "Lettura dello stato…",
    errore: "Lo stato non si legge: l'API non risponde.",
    nonSeminato:
      "Le regioni non sono ancora state preparate: sul server esegui `limen seed`, poi torna qui.",
    regioni: (n: number, celle: number) =>
      `${n} regioni, ${celle.toLocaleString("it-IT")} celle da 1 km².`,
    pronto: "Pronto",
    parziale: "Parziale",
    nonPronto: "Non pronto",
    tuttoPresente: "Tutti i dati essenziali ci sono.",
    manca: "Manca:",
    migliora: "Si può migliorare con:",
    dati: "I dati",
    livello: { essenziale: "Essenziali", consigliato: "Consigliati", avanzato: "Avanzati" },
    livelloSpiega: {
      essenziale: "Senza, il pericolo non distingue un posto dall'altro.",
      consigliato: "Migliorano la precisione; la mappa ha senso anche senza.",
      avanzato: "Servono alle verifiche e al modello sperimentale, non alla mappa.",
    },
    copertura: (n: number) => `Presente su ${n.toLocaleString("it-IT")} celle`,
    righe: (n: number) => `${n.toLocaleString("it-IT")} elementi`,
    assente: "Non ancora presente",
    mancaIn: (n: number) => `manca in ${n} ${n === 1 ? "regione" : "regioni"}`,
    derivato: (da: string) => `Si calcola da «${da}»: non si scarica.`,
    pesoCirca: (p: string) => `circa ${p}`,
    statoDl: {
      in_coda: "In coda",
      in_corso: "In download",
      fatto: "Scaricato",
      errore: "Errore",
    },
    daCaricare: "Scaricato, non ancora caricato nelle celle.",
    elaborazioneInCorso:
      "Limen sta caricando nelle celle i dati scaricati. Per tutta Italia può durare qualche ora; la pagina si aggiorna da sola.",
    elaborazioneErrore: "Il caricamento nelle celle non è riuscito del tutto:",
    elaboraDaFare: "Ci sono dati scaricati da caricare nelle celle.",
    elabora: "Carica i dati scaricati",
    scarica: "Scarica",
    riprova: "Riprova",
    scaricaEssenziali: "Scarica tutti i dati essenziali che mancano",
    fonte: "Fonte",
    licenza: "Licenza",
    token: "Token di installazione",
    tokenSpiega:
      "Per avviare un download serve il token che il server ha nel file .env (INSTALLAZIONE__TOKEN). Il link stampato dallo script di installazione lo contiene già.",
    tokenSalva: "Usa questo token",
    tokenAttivo: "Token impostato per questa scheda del browser.",
    tokenTogli: "Togli",
    disabilitate:
      "Le azioni sono disabilitate: il server non ha un token di installazione (INSTALLAZIONE__TOKEN nel .env).",
    tokenErrato: "Il token non è valido: controlla quello nel .env del server.",
    accodate: (n: number) => `${n} download in coda: li esegue il server, uno alla volta.`,
    erroreAzione: "La richiesta non è andata a buon fine.",
  },
  {
    occhiello: "Installation",
    titolo: "Is Limen ready?",
    titoloInstallato: "How Limen is doing",
    lede:
      "Each hazard needs some data about the territory. This page shows which are there, which are missing, where they are downloaded from and how far each download has got.",
    caricamento: "Reading the state…",
    errore: "The state cannot be read: the API is not responding.",
    nonSeminato: "The regions have not been prepared yet: run `limen seed` on the server, then come back.",
    regioni: (n: number, celle: number) =>
      `${n} regions, ${celle.toLocaleString("en-GB")} cells of 1 km².`,
    pronto: "Ready",
    parziale: "Partial",
    nonPronto: "Not ready",
    tuttoPresente: "All essential data are present.",
    manca: "Missing:",
    migliora: "Can be improved with:",
    dati: "The data",
    livello: { essenziale: "Essential", consigliato: "Recommended", avanzato: "Advanced" },
    livelloSpiega: {
      essenziale: "Without them, the hazard cannot tell one place from another.",
      consigliato: "They improve precision; the map makes sense without them.",
      avanzato: "Used by the verification and the experimental model, not by the map.",
    },
    copertura: (n: number) => `Present on ${n.toLocaleString("en-GB")} cells`,
    righe: (n: number) => `${n.toLocaleString("en-GB")} items`,
    assente: "Not present yet",
    mancaIn: (n: number) => `missing in ${n} ${n === 1 ? "region" : "regions"}`,
    derivato: (da: string) => `Computed from «${da}»: not downloaded.`,
    pesoCirca: (p: string) => `about ${p}`,
    statoDl: { in_coda: "Queued", in_corso: "Downloading", fatto: "Downloaded", errore: "Error" },
    daCaricare: "Downloaded, not loaded into the cells yet.",
    elaborazioneInCorso:
      "Limen is loading the downloaded data into the cells. For all of Italy this can take a few hours; the page updates by itself.",
    elaborazioneErrore: "Loading into the cells did not fully succeed:",
    elaboraDaFare: "Some downloaded data still have to be loaded into the cells.",
    elabora: "Load the downloaded data",
    scarica: "Download",
    riprova: "Retry",
    scaricaEssenziali: "Download every missing essential dataset",
    fonte: "Source",
    licenza: "Licence",
    token: "Installation token",
    tokenSpiega:
      "Starting a download needs the token the server keeps in its .env file (INSTALLAZIONE__TOKEN). The link printed by the installation script already contains it.",
    tokenSalva: "Use this token",
    tokenAttivo: "Token set for this browser tab.",
    tokenTogli: "Remove",
    disabilitate:
      "Actions are disabled: the server has no installation token (INSTALLAZIONE__TOKEN in .env).",
    tokenErrato: "The token is not valid: check the one in the server's .env.",
    accodate: (n: number) => `${n} downloads queued: the server runs them one at a time.`,
    erroreAzione: "The request did not succeed.",
  },
);

function leggiToken(): string {
  try {
    return sessionStorage.getItem(CHIAVE_TOKEN) ?? "";
  } catch {
    return "";
  }
}

function salvaToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(CHIAVE_TOKEN, token);
    else sessionStorage.removeItem(CHIAVE_TOKEN);
  } catch {
    // Archiviazione bloccata: il token resta solo in memoria per questa visita.
  }
}

/** Il token del link `#/installazione?token=…`, tolto subito dall'indirizzo. */
function tokenDalLink(): string {
  const [rotta, query = ""] = window.location.hash.split("?");
  const token = new URLSearchParams(query).get("token") ?? "";
  if (token) {
    window.history.replaceState(null, "", `${window.location.pathname}${rotta ?? ""}`);
  }
  return token;
}

export function InstallazionePage(): JSX.Element {
  const t = useTesti(T);
  const { lingua } = useLingua();
  const [stato, setStato] = useState<InstallazioneStato | null>(null);
  const [errore, setErrore] = useState(false);
  const [token, setToken] = useState(() => tokenDalLink() || leggiToken());
  const [bozza, setBozza] = useState("");
  const [messaggio, setMessaggio] = useState<string | null>(null);

  useEffect(() => salvaToken(token), [token]);

  const aggiorna = useCallback(async (signal?: AbortSignal) => {
    try {
      setStato(await defaultApiClient.getInstallazioneStato(signal));
      setErrore(false);
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) setErrore(true);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void aggiorna(ctrl.signal);
    const timer = window.setInterval(() => void aggiorna(ctrl.signal), AGGIORNA_OGNI_MS);
    return () => {
      ctrl.abort();
      window.clearInterval(timer);
    };
  }, [aggiorna]);

  const azione = async (chiama: () => Promise<string | null>): Promise<void> => {
    try {
      setMessaggio(await chiama());
      await aggiorna();
    } catch (e) {
      if (e instanceof ApiClientError && e.status === 401) {
        setToken("");
        setMessaggio(t.tokenErrato);
      } else if (e instanceof ApiClientError && e.status === 403) {
        setMessaggio(t.disabilitate);
      } else {
        setMessaggio(t.erroreAzione);
      }
    }
  };

  const scarica = (voci: string[]): Promise<void> =>
    azione(async () => {
      const r = await defaultApiClient.avviaDownload(voci, token);
      return t.accodate(r.accodate.length);
    });

  const elabora = (): Promise<void> =>
    azione(async () => {
      await defaultApiClient.avviaElaborazione(token);
      return null;
    });

  const puoAgire = Boolean(stato?.azioni_abilitate && token);

  if (!stato) {
    return (
      <main className="installazione">
        <p className="occhiello">{t.occhiello}</p>
        <h1>{t.titolo}</h1>
        <p role="status">{errore ? t.errore : t.caricamento}</p>
      </main>
    );
  }

  const nomeVoce = new Map(stato.voci.map((v) => [v.id, v.nome]));
  const essenzialiMancanti = stato.voci.filter(
    (v) =>
      v.livello === "essenziale" &&
      v.deriva_da === null &&
      v.copertura === 0 &&
      v.download?.stato !== "in_coda" &&
      v.download?.stato !== "in_corso",
  );
  const elaborazione = stato.elaborazione;
  const inElaborazione =
    elaborazione?.stato === "in_coda" || elaborazione?.stato === "in_corso";
  const scaricando = stato.voci.some(
    (v) => v.download?.stato === "in_coda" || v.download?.stato === "in_corso",
  );
  const daElaborare =
    !inElaborazione &&
    !scaricando &&
    (elaborazione?.stato === "errore" || stato.voci.some(daCaricare));

  // A installazione finita la pagina diventa «Salute» (#408): la prontezza
  // dei dati resta sotto, perché un'altra regione o un dato consigliato si
  // aggiungono anche dopo.
  const installato = stato.celle_totali > 0 && stato.pericoli.every((p) => p.pronto);

  return (
    <main className="installazione">
      <p className="occhiello">{t.occhiello}</p>
      <h1>{installato ? t.titoloInstallato : t.titolo}</h1>
      <p>
        {stato.celle_totali === 0 ? t.nonSeminato : t.regioni(stato.regioni, stato.celle_totali)}
      </p>
      {installato && <SalutePanel />}
      <p className="lede">{t.lede}</p>

      <section className="installazione-pericoli" aria-label={t.titolo}>
        {ORDINE_PERICOLI.map((h) => {
          const { colore, mancano } = semaforo(h, stato);
          const etichetta =
            colore === "verde" ? t.pronto : colore === "giallo" ? t.parziale : t.nonPronto;
          return (
            <article key={h} className={`installazione-pericolo semaforo-${colore}`}>
              <h2>
                {NOMI_PERICOLO[lingua][h]}: <span className="semaforo-etichetta">{etichetta}</span>
              </h2>
              {mancano.length === 0 ? (
                <p>{stato.celle_totali === 0 ? t.nonSeminato : t.tuttoPresente}</p>
              ) : (
                <>
                  <p>{colore === "rosso" ? t.manca : t.migliora}</p>
                  <ul>
                    {mancano.map((v) => (
                      <li key={v.id}>
                        <strong>{v.nome}</strong> — {v.a_cosa_serve}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </article>
          );
        })}
      </section>

      {(inElaborazione || daElaborare) && (
        <section className="installazione-elaborazione" role="status">
          {inElaborazione ? (
            <p>{t.elaborazioneInCorso}</p>
          ) : elaborazione?.stato === "errore" ? (
            <>
              <p>{t.elaborazioneErrore}</p>
              <p className="installazione-errore">{elaborazione.errore}</p>
            </>
          ) : (
            <p>{t.elaboraDaFare}</p>
          )}
          {daElaborare && puoAgire && (
            <button type="button" onClick={() => void elabora()}>
              {elaborazione?.stato === "errore" ? t.riprova : t.elabora}
            </button>
          )}
        </section>
      )}

      <section className="installazione-token">
        <h2>{t.token}</h2>
        {!stato.azioni_abilitate ? (
          <p>{t.disabilitate}</p>
        ) : token ? (
          <p>
            {t.tokenAttivo}{" "}
            <button type="button" onClick={() => setToken("")}>
              {t.tokenTogli}
            </button>
          </p>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setToken(bozza.trim());
              setBozza("");
            }}
          >
            <p>{t.tokenSpiega}</p>
            <label>
              {t.token}{" "}
              <input
                type="password"
                autoComplete="off"
                value={bozza}
                onChange={(e) => setBozza(e.target.value)}
              />
            </label>{" "}
            <button type="submit" disabled={!bozza.trim()}>
              {t.tokenSalva}
            </button>
          </form>
        )}
        {messaggio && <p role="status">{messaggio}</p>}
      </section>

      <section>
        <h2>{t.dati}</h2>
        {puoAgire && essenzialiMancanti.length > 0 && (
          <button
            type="button"
            className="installazione-tutti"
            onClick={() => void scarica(essenzialiMancanti.map((v) => v.id))}
          >
            {t.scaricaEssenziali}
          </button>
        )}
        {ORDINE_LIVELLI.map((livello) => {
          const voci = stato.voci.filter((v) => v.livello === livello);
          if (!voci.length) return null;
          return (
            <div key={livello} className="installazione-livello">
              <h3>{t.livello[livello]}</h3>
              <p className="installazione-nota">{t.livelloSpiega[livello]}</p>
              <ul className="installazione-voci">
                {voci.map((v) => (
                  <RigaVoce
                    key={v.id}
                    voce={v}
                    derivataDa={v.deriva_da ? (nomeVoce.get(v.deriva_da) ?? v.deriva_da) : null}
                    puoAgire={puoAgire}
                    onScarica={() => void scarica([v.id])}
                  />
                ))}
              </ul>
            </div>
          );
        })}
      </section>
    </main>
  );
}

function RigaVoce({
  voce,
  derivataDa,
  puoAgire,
  onScarica,
}: {
  voce: VoceDato;
  derivataDa: string | null;
  puoAgire: boolean;
  onScarica: () => void;
}): JSX.Element {
  const t = useTesti(T);
  const d = voce.download;
  const pct = d ? percentuale(d) : null;
  const inLavorazione = d?.stato === "in_coda" || d?.stato === "in_corso";
  const presente = voce.copertura > 0;
  return (
    <li className="installazione-voce">
      <div className="installazione-voce-testa">
        <strong>{voce.nome}</strong>
        <span className={presente && !voce.regioni_senza.length ? "presente" : "assente"}>
          {presente
            ? voce.id === "perimetri_effis"
              ? t.righe(voce.copertura)
              : t.copertura(voce.copertura)
            : t.assente}
          {presente && voce.regioni_senza.length > 0 && ` · ${t.mancaIn(voce.regioni_senza.length)}`}
        </span>
      </div>
      <p>{voce.a_cosa_serve}</p>
      <p className="installazione-nota">
        {t.fonte}:{" "}
        {voce.url ? (
          <a href={voce.url} target="_blank" rel="noreferrer">
            {voce.fonte}
          </a>
        ) : (
          voce.fonte
        )}{" "}
        · {t.licenza}: {voce.licenza}
        {voce.peso_gb > 0 && <> · {t.pesoCirca(peso(voce.peso_gb * 1e9))}</>}
      </p>
      {derivataDa !== null ? (
        <p className="installazione-nota">{t.derivato(derivataDa)}</p>
      ) : (
        <>
          {d && (
            <div className={`installazione-download dl-${d.stato}`}>
              <span>{t.statoDl[d.stato]}</span>
              {d.stato === "in_corso" && (
                <>
                  <progress
                    max={100}
                    value={pct ?? undefined}
                    aria-label={`${voce.nome}: ${t.statoDl.in_corso}`}
                  />
                  <span>
                    {peso(d.byte_fatti)}
                    {d.byte_totali ? ` / ${peso(d.byte_totali)}` : ""}
                  </span>
                </>
              )}
              {d.stato === "errore" && d.errore && <p className="installazione-errore">{d.errore}</p>}
            </div>
          )}
          {daCaricare(voce) && <p className="installazione-nota">{t.daCaricare}</p>}
          {puoAgire && !presente && !inLavorazione && (
            <button type="button" onClick={onScarica}>
              {d?.stato === "errore" ? t.riprova : t.scarica}
            </button>
          )}
        </>
      )}
    </li>
  );
}

export default InstallazionePage;
