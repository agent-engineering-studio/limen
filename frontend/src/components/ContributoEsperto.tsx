// «Sei un esperto?»: il modulo sotto la cella per chi conosce il territorio.
//
// Un geologo che non scrive codice non apre una issue su GitHub: dice cosa
// non torna in questa cella e lascia la fonte. Il contributo arriva per mail
// a chi cura il progetto, con i numeri che l'esperto stava guardando, e Limen
// non lo salva; nessun contributo cambia la mappa da solo.

import { useRef, useState } from "react";
import type { FormEvent, JSX } from "react";

import { ApiClientError, defaultApiClient } from "../lib/api-client";
import type { HazardType, TipoContributo } from "../types";

const TIPI: ReadonlyArray<readonly [TipoContributo, string]> = [
  ["valutazione", "La valutazione di questa cella non torna"],
  ["frana_non_censita", "C'è una frana che non è nei dati"],
  ["pesi_soglie", "Un peso o una soglia da rivedere"],
  ["mitigazione", "C'è un'opera di mitigazione"],
  ["altro", "Altro"],
];

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

function messaggioErrore(e: unknown): string {
  if (e instanceof ApiClientError) {
    if (e.status === 429) return "Troppi invii in poco tempo: riprova fra un'ora.";
    if (e.status === 422)
      return "Controlla i campi: il testo deve avere almeno 20 caratteri, l'email deve essere valida, i link devono iniziare con http:// o https://, e serve il nome o il profilo LinkedIn.";
    if (e.status === 404) return "Questa cella non risulta più sulla mappa: ricarica la pagina.";
  }
  return "Il contributo non è partito. Riprova fra qualche minuto.";
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
  const [errore, setErrore] = useState<string | null>(null);
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
      <section className="contributo" aria-label="Contributo di un esperto">
        <button
          type="button"
          className="contributo-apri"
          onClick={() => {
            apertoAlle.current = Date.now();
            setStato("aperto");
          }}
        >
          Sei un esperto? Correggi questa valutazione
        </button>
      </section>
    );
  }

  if (stato === "inviato") {
    return (
      <section className="contributo" aria-label="Contributo di un esperto">
        <p className="verdict verdict-ok" role="status">
          Grazie: il contributo è arrivato per mail a chi cura Limen, insieme ai
          numeri di questa cella. Se serve un chiarimento ti scriverà all'indirizzo
          che hai lasciato.
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
      setErrore(messaggioErrore(e));
      setStato("aperto");
    }
  };


  return (
    <section className="contributo" aria-label="Contributo di un esperto">
      <span className="eyebrow">Il tuo contributo su questa cella</span>
      <p className="contributo-nota">
        Conosci questo territorio? Dicci cosa non torna e da dove lo sai. Non
        serve saper programmare: il contributo arriva per mail a chi cura Limen
        insieme ai numeri che stai guardando, e lo legge una persona prima che
        cambi qualcosa.
      </p>
      <form className="contributo-form" onSubmit={(ev) => void invia(ev)}>
        <label>
          Di cosa si tratta
          <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoContributo)}>
            {TIPI.map(([v, etichetta]) => (
              <option key={v} value={v}>
                {etichetta}
              </option>
            ))}
          </select>
        </label>
        <label>
          Cosa vedi
          <textarea
            value={testo}
            onChange={(e) => setTesto(e.target.value)}
            rows={4}
            maxLength={4000}
            required
            placeholder="Per esempio: il versante è in argille e ha avuto un movimento nel 2019, la classe bassa mi sembra sottostimata."
          />
          {mancanoCaratteri > 0 && testo.length > 0 ? (
            <span className="contributo-aiuto">ancora {mancanoCaratteri} caratteri</span>
          ) : null}
        </label>
        <label>
          Fonte (facoltativa)
          <input
            type="url"
            value={fonte}
            onChange={(e) => setFonte(e.target.value)}
            pattern={LINK}
            placeholder="https:// link a pubblicazione, relazione o carta"
          />
        </label>
        <label>
          Nome e cognome
          <input
            type="text"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            maxLength={120}
            autoComplete="name"
          />
        </label>
        <label>
          Profilo LinkedIn (in alternativa al nome)
          <input
            type="url"
            value={linkedin}
            onChange={(e) => setLinkedin(e.target.value)}
            pattern={LINK}
            placeholder="https://www.linkedin.com/in/…"
          />
        </label>
        <label>
          Email
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
          Dipartimento o ente (facoltativo)
          <input
            type="text"
            value={affiliazione}
            onChange={(e) => setAffiliazione(e.target.value)}
            maxLength={160}
            placeholder="es. dipartimento universitario, ufficio tecnico comunale, studio"
          />
        </label>
        <label className="contributo-esca" aria-hidden="true">
          Sito web
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
          Ho letto la nota qui sotto e acconsento al trattamento dei dati per
          questo contributo
        </label>
        <p className="contributo-privacy">
          Nome, profilo, dipartimento ed email viaggiano solo nella mail a chi
          cura Limen, per ricontattarti su questo contributo: Limen non li salva
          e non li pubblica. Nessun allegato: la fonte è un link.
        </p>
        {errore ? (
          <p className="contributo-errore" role="alert">
            {errore}
          </p>
        ) : null}
        <div className="contributo-azioni">
          <button
            type="submit"
            disabled={stato === "invio" || !consenso || mancanoCaratteri > 0 || !chiScrive}
          >
            {stato === "invio" ? "invio…" : "Invia il contributo"}
          </button>
          <button type="button" className="contributo-annulla" onClick={() => setStato("chiuso")}>
            annulla
          </button>
        </div>
      </form>
    </section>
  );
}
