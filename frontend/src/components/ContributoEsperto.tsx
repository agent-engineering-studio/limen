// «Sei un esperto?»: il modulo sotto la cella per chi conosce il territorio.
//
// Un geologo che non scrive codice non apre una issue su GitHub: dice cosa
// non torna in questa cella e lascia la fonte. Il contributo arriva per mail
// a chi cura il progetto, con i numeri che l'esperto stava guardando, e Limen
// non lo salva; nessun contributo cambia la mappa da solo.

import { useRef, useState } from "react";
import type { FormEvent, JSX } from "react";

import { ApiClientError, defaultApiClient } from "../lib/api-client";
import { testi, useTesti } from "../lib/i18n";
import type { HazardType, TipoContributo } from "../types";

const ORDINE_TIPI: readonly TipoContributo[] = [
  "valutazione",
  "frana_non_censita",
  "pesi_soglie",
  "mitigazione",
  "altro",
];

const T = testi(
  {
    tipi: {
      valutazione: "La valutazione di questa cella non torna",
      frana_non_censita: "C'è una frana che non è nei dati",
      pesi_soglie: "Un peso o una soglia da rivedere",
      mitigazione: "C'è un'opera di mitigazione",
      altro: "Altro",
    } as Record<TipoContributo, string>,
    errori: {
      e429: "Troppi invii in poco tempo: riprova fra un'ora.",
      e422: "Controlla i campi: il testo deve avere almeno 20 caratteri, l'email deve essere valida, i link devono iniziare con http:// o https://, e serve il nome o il profilo LinkedIn.",
      e404: "Questa cella non risulta più sulla mappa: ricarica la pagina.",
      generico: "Il contributo non è partito. Riprova fra qualche minuto.",
    },
    sezione: "Contributo di un esperto",
    apri: "Sei un esperto? Correggi questa valutazione",
    grazie:
      "Grazie: il contributo è arrivato per mail a chi cura Limen, insieme ai " +
      "numeri di questa cella. Se serve un chiarimento ti scriverà all'indirizzo " +
      "che hai lasciato.",
    titolo: "Il tuo contributo su questa cella",
    nota:
      "Conosci questo territorio? Dicci cosa non torna e da dove lo sai. Non " +
      "serve saper programmare: il contributo arriva per mail a chi cura Limen " +
      "insieme ai numeri che stai guardando, e lo legge una persona prima che " +
      "cambi qualcosa.",
    tipo: "Di cosa si tratta",
    testo: "Cosa vedi",
    testoEsempio:
      "Per esempio: il versante è in argille e ha avuto un movimento nel 2019, la classe bassa mi sembra sottostimata.",
    mancano: (n: number) => `ancora ${n} caratteri`,
    fonte: "Fonte (facoltativa)",
    fonteEsempio: "https:// link a pubblicazione, relazione o carta",
    nome: "Nome e cognome",
    linkedin: "Profilo LinkedIn (in alternativa al nome)",
    email: "Email",
    affiliazione: "Dipartimento o ente (facoltativo)",
    affiliazioneEsempio: "es. dipartimento universitario, ufficio tecnico comunale, studio",
    sitoWeb: "Sito web",
    consenso:
      "Ho letto la nota qui sotto e acconsento al trattamento dei dati per " +
      "questo contributo",
    privacy:
      "Nome, profilo, dipartimento ed email viaggiano solo nella mail a chi " +
      "cura Limen, per ricontattarti su questo contributo: Limen non li salva " +
      "e non li pubblica. Nessun allegato: la fonte è un link.",
    invio: "invio…",
    invia: "Invia il contributo",
    annulla: "annulla",
  },
  {
    tipi: {
      valutazione: "The assessment of this cell is wrong",
      frana_non_censita: "There is a landslide missing from the data",
      pesi_soglie: "A weight or threshold to review",
      mitigazione: "There is a mitigation work",
      altro: "Other",
    },
    errori: {
      e429: "Too many submissions in a short time: try again in an hour.",
      e422: "Check the fields: the text needs at least 20 characters, the email must be valid, links must start with http:// or https://, and a name or LinkedIn profile is required.",
      e404: "This cell is no longer on the map: reload the page.",
      generico: "The contribution was not sent. Try again in a few minutes.",
    },
    sezione: "Expert contribution",
    apri: "Are you an expert? Correct this assessment",
    grazie:
      "Thank you: your contribution has been emailed to the Limen maintainers, " +
      "together with this cell's figures. If they need clarification they will " +
      "write to the address you left.",
    titolo: "Your contribution on this cell",
    nota:
      "Do you know this area? Tell us what is wrong and how you know. No " +
      "coding needed: the contribution is emailed to the Limen maintainers " +
      "together with the figures you are looking at, and a person reads it " +
      "before anything changes.",
    tipo: "What is it about",
    testo: "What you see",
    testoEsempio:
      "For example: the slope is in clay and moved in 2019, the low class looks underestimated to me.",
    mancano: (n: number) => `${n} more ${n === 1 ? "character" : "characters"}`,
    fonte: "Source (optional)",
    fonteEsempio: "https:// link to a publication, report or map",
    nome: "Full name",
    linkedin: "LinkedIn profile (instead of the name)",
    email: "Email",
    affiliazione: "Department or organisation (optional)",
    affiliazioneEsempio: "e.g. university department, municipal technical office, firm",
    sitoWeb: "Website",
    consenso:
      "I have read the note below and consent to the processing of my data for " +
      "this contribution",
    privacy:
      "Name, profile, department and email travel only in the email to the " +
      "Limen maintainers, so they can contact you about this contribution: " +
      "Limen does not store or publish them. No attachments: the source is a link.",
    invio: "sending…",
    invia: "Send the contribution",
    annulla: "cancel",
  },
);

type Testi = (typeof T)["it"];

const MIN_TESTO = 20;
// Gli stessi vincoli del server, così il browser ferma prima quello che il
// server rifiuterebbe con un messaggio generico.
const EMAIL = "[^@\\s<>,;\"]+@[^@\\s<>,;\"]+\\.[^@\\s<>,;\"]{2,}";
const LINK = "https?://.+";
// Il server scarta come automatico un modulo compilato in meno di
// CONTRIBUTI__SECONDI_MINIMI (5 s di default) e risponde comunque 201: chi
// incolla un testo pronto e invia subito perderebbe il contributo credendolo
// arrivato. Qui si aspetta un margine sopra quella soglia prima di spedire.
const ATTESA_MINIMA_MS = 6000;

type Stato = "chiuso" | "aperto" | "invio" | "inviato";

function messaggioErrore(e: unknown, t: Testi): string {
  if (e instanceof ApiClientError) {
    if (e.status === 429) return t.errori.e429;
    if (e.status === 422) return t.errori.e422;
    if (e.status === 404) return t.errori.e404;
  }
  return t.errori.generico;
}

function vuotoANull(v: string): string | null {
  const t = v.trim();
  return t ? t : null;
}

export default function ContributoEsperto({
  cellId,
  hazard,
}: {
  cellId: string;
  hazard: HazardType | null;
}): JSX.Element {
  const [stato, setStato] = useState<Stato>("chiuso");
  // L'errore e non il messaggio: il messaggio segue la lingua scelta.
  const [errore, setErrore] = useState<{ e: unknown } | null>(null);
  const t = useTesti(T);
  const apertoAlle = useRef(0);

  const [tipo, setTipo] = useState<TipoContributo>("valutazione");
  const [testo, setTesto] = useState("");
  const [fonte, setFonte] = useState("");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [affiliazione, setAffiliazione] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [consenso, setConsenso] = useState(false);
  const [sitoWeb, setSitoWeb] = useState("");

  if (stato === "chiuso") {
    return (
      <section className="contributo" aria-label={t.sezione}>
        <button
          type="button"
          className="contributo-apri"
          onClick={() => {
            apertoAlle.current = Date.now();
            setStato("aperto");
          }}
        >
          {t.apri}
        </button>
      </section>
    );
  }

  if (stato === "inviato") {
    return (
      <section className="contributo" aria-label={t.sezione}>
        <p className="verdict verdict-ok" role="status">
          {t.grazie}
        </p>
      </section>
    );
  }

  const mancanoCaratteri = Math.max(0, MIN_TESTO - testo.trim().length);
  const chiScrive = nome.trim().length >= 2 || linkedin.trim() !== "";

  const invia = async (ev: FormEvent<HTMLFormElement>): Promise<void> => {
    ev.preventDefault();
    if (testo.trim().length < MIN_TESTO || !consenso || !chiScrive) return;
    setErrore(null);
    setStato("invio");
    const attesa = ATTESA_MINIMA_MS - (Date.now() - apertoAlle.current);
    if (attesa > 0) await new Promise((r) => setTimeout(r, attesa));
    try {
      await defaultApiClient.inviaContributo({
        cell_id: cellId,
        hazard,
        tipo,
        testo: testo.trim(),
        fonte_url: vuotoANull(fonte),
        nome: vuotoANull(nome),
        email: email.trim(),
        affiliazione: vuotoANull(affiliazione),
        linkedin_url: vuotoANull(linkedin),
        consenso: true,
        compilato_in_ms: Date.now() - apertoAlle.current,
        sito_web: sitoWeb,
      });
      setStato("inviato");
    } catch (e) {
      setErrore({ e });
      setStato("aperto");
    }
  };


  return (
    <section className="contributo" aria-label={t.sezione}>
      <span className="eyebrow">{t.titolo}</span>
      <p className="contributo-nota">{t.nota}</p>
      <form className="contributo-form" onSubmit={(ev) => void invia(ev)}>
        <label>
          {t.tipo}
          <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoContributo)}>
            {ORDINE_TIPI.map((v) => (
              <option key={v} value={v}>
                {t.tipi[v]}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t.testo}
          <textarea
            value={testo}
            onChange={(e) => setTesto(e.target.value)}
            rows={4}
            maxLength={4000}
            required
            placeholder={t.testoEsempio}
          />
          {mancanoCaratteri > 0 && testo.length > 0 ? (
            <span className="contributo-aiuto">{t.mancano(mancanoCaratteri)}</span>
          ) : null}
        </label>
        <label>
          {t.fonte}
          <input
            type="url"
            value={fonte}
            onChange={(e) => setFonte(e.target.value)}
            pattern={LINK}
            placeholder={t.fonteEsempio}
          />
        </label>
        <label>
          {t.nome}
          <input
            type="text"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            maxLength={120}
            autoComplete="name"
          />
        </label>
        <label>
          {t.linkedin}
          <input
            type="url"
            value={linkedin}
            onChange={(e) => setLinkedin(e.target.value)}
            pattern={LINK}
            placeholder="https://www.linkedin.com/in/…"
          />
        </label>
        <label>
          {t.email}
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            pattern={EMAIL}
            required
            autoComplete="email"
          />
        </label>
        <label>
          {t.affiliazione}
          <input
            type="text"
            value={affiliazione}
            onChange={(e) => setAffiliazione(e.target.value)}
            maxLength={160}
            placeholder={t.affiliazioneEsempio}
          />
        </label>
        <label className="contributo-esca" aria-hidden="true">
          {t.sitoWeb}
          <input
            type="text"
            tabIndex={-1}
            autoComplete="off"
            value={sitoWeb}
            onChange={(e) => setSitoWeb(e.target.value)}
          />
        </label>
        <label className="contributo-check">
          <input
            type="checkbox"
            checked={consenso}
            onChange={(e) => setConsenso(e.target.checked)}
            required
          />
          {t.consenso}
        </label>
        <p className="contributo-privacy">{t.privacy}</p>
        {errore ? (
          <p className="contributo-errore" role="alert">
            {messaggioErrore(errore.e, t)}
          </p>
        ) : null}
        <div className="contributo-azioni">
          <button
            type="submit"
            disabled={stato === "invio" || !consenso || mancanoCaratteri > 0 || !chiScrive}
          >
            {stato === "invio" ? t.invio : t.invia}
          </button>
          <button type="button" className="contributo-annulla" onClick={() => setStato("chiuso")}>
            {t.annulla}
          </button>
        </div>
      </form>
    </section>
  );
}
