// Il modulo di registrazione dei sensori in fondo a `#/sensori` (#253).
//
// Non c'è un login: la richiesta arriva per mail a chi cura Limen, che la
// approva dalla CLI. Si manda la CSR, non la chiave: il dispositivo tiene la
// sua chiave privata e riceve per mail il certificato firmato. Chiuso, il
// modulo non si mostra: dice solo che le registrazioni apriranno.

import { useEffect, useRef, useState } from "react";
import type { FormEvent, JSX } from "react";

import { ApiClientError, defaultApiClient } from "../lib/api-client";
import { testi, useTesti } from "../lib/i18n";
import type { TipoSensore } from "../types";

const T = testi(
  {
    sezione: "Registra un sensore",
    chiusa:
      "Le registrazioni dei sensori non sono ancora aperte: questa pagina " +
      "spiega già come costruirne uno e cosa dovrà mandare.",
    nota:
      "La richiesta arriva per mail a chi cura Limen e la legge una persona. " +
      "Se la approva, ricevi il certificato del dispositivo all'indirizzo che " +
      "lasci. Il sensore parte come osservatore: le sue misure non cambiano i " +
      "punteggi né le allerte.",
    tipo: "Tipo di sensore",
    tipi: {
      pluviometro: "Pluviometro",
      umidita_suolo: "Umidità del suolo",
    } as Record<TipoSensore, string>,
    lat: "Latitudine (gradi decimali)",
    lon: "Longitudine (gradi decimali)",
    csr: "CSR del dispositivo (PEM)",
    csrAiuto:
      "Il CN della CSR è l'id del dispositivo: minuscole, cifre e trattini. " +
      "È pubblico, sulla mappa delle stazioni: non metterci il tuo nome. " +
      "Non incollare mai la chiave privata.",
    email: "Email",
    note: "Note sull'installazione (facoltative)",
    noteEsempio: "es. sul tetto del garage, a 3 m da terra, lontano da alberi",
    foto: "Foto dell'installazione (JPEG o PNG, facoltativa)",
    sitoWeb: "Sito web",
    licenza: "Pubblico le misure con licenza CC BY 4.0",
    regole:
      "Ho letto le tre regole di sicurezza di questa pagina e le rispetto",
    informativa: "Ho letto l'informativa sui dati personali di questa pagina",
    invio: "invio…",
    invia: "Invia la richiesta",
    grazie:
      "Richiesta inviata. Ti scriveremo all'indirizzo che hai lasciato, con il " +
      "certificato se la richiesta è approvata.",
    errori: {
      e429: "Troppe richieste in poco tempo: riprova fra un'ora.",
      e422: "La richiesta non è valida",
      e503: "Le richieste non partono in questo momento: riprova fra qualche minuto.",
      chiaveNelCampo:
        "Hai incollato una chiave privata: serve la CSR. La chiave resta sul dispositivo.",
      generico: "La richiesta non è partita. Riprova fra qualche minuto.",
    },
  },
  {
    sezione: "Register a sensor",
    chiusa:
      "Sensor registration is not open yet: this page already explains how " +
      "to build one and what it will have to send.",
    nota:
      "The request is emailed to the Limen maintainers and a person reads it. " +
      "If they approve it, you receive the device certificate at the address " +
      "you leave. The sensor starts as an observer: its measurements do not " +
      "change scores or alerts.",
    tipo: "Sensor type",
    tipi: {
      pluviometro: "Rain gauge",
      umidita_suolo: "Soil moisture",
    },
    lat: "Latitude (decimal degrees)",
    lon: "Longitude (decimal degrees)",
    csr: "Device CSR (PEM)",
    csrAiuto:
      "The CSR's CN is the device id: lowercase letters, digits and hyphens. " +
      "It is public, on the station map: do not put your name in it. " +
      "Never paste the private key.",
    email: "Email",
    note: "Installation notes (optional)",
    noteEsempio: "e.g. on the garage roof, 3 m above ground, away from trees",
    foto: "Installation photo (JPEG or PNG, optional)",
    sitoWeb: "Website",
    licenza: "I publish the measurements under the CC BY 4.0 licence",
    regole: "I have read the three safety rules on this page and follow them",
    informativa: "I have read the personal data notice on this page",
    invio: "sending…",
    invia: "Send the request",
    grazie:
      "Request sent. We will write to the address you left, with the " +
      "certificate if the request is approved.",
    errori: {
      e429: "Too many requests in a short time: try again in an hour.",
      e422: "The request is not valid",
      e503: "Requests cannot be sent right now: try again in a few minutes.",
      chiaveNelCampo:
        "You pasted a private key: the CSR is needed. The key stays on the device.",
      generico: "The request was not sent. Try again in a few minutes.",
    },
  },
);

type Testi = (typeof T)["it"];

const ORDINE_TIPI: readonly TipoSensore[] = ["pluviometro", "umidita_suolo"];
const EMAIL = '[^@\\s<>,;"]+@[^@\\s<>,;"]+\\.[^@\\s<>,;"]{2,}';
// Il server scarta come automatico un modulo compilato in meno di
// IOT__CITTADINI__REGISTRAZIONE__SECONDI_MINIMI (20 s) e risponde comunque 201.
const ATTESA_MINIMA_MS = 21_000;

type Stato = "modulo" | "invio" | "inviato";

function messaggioErrore(e: unknown, t: Testi): string {
  if (e instanceof ApiClientError) {
    if (e.status === 429) return t.errori.e429;
    if (e.status === 503) return t.errori.e503;
    if (e.status === 422) {
      const detail = (e.body as { detail?: unknown } | null)?.detail;
      return typeof detail === "string"
        ? `${t.errori.e422}: ${detail}`
        : `${t.errori.e422}.`;
    }
  }
  return t.errori.generico;
}

function base64(file: File): Promise<string> {
  return new Promise((risolvi, rifiuta) => {
    const r = new FileReader();
    r.onload = () => risolvi(String(r.result).split(",", 2)[1] ?? "");
    r.onerror = () => rifiuta(r.error);
    r.readAsDataURL(file);
  });
}

export default function RegistrazioneSensore(): JSX.Element | null {
  const t = useTesti(T);
  const [aperta, setAperta] = useState<boolean | null>(null);
  const [stato, setStato] = useState<Stato>("modulo");
  const [errore, setErrore] = useState<{ e: unknown } | null>(null);
  const apertoAlle = useRef(Date.now());

  const [tipo, setTipo] = useState<TipoSensore>("pluviometro");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [csr, setCsr] = useState("");
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [foto, setFoto] = useState<File | null>(null);
  const [licenza, setLicenza] = useState(false);
  const [regole, setRegole] = useState(false);
  const [informativa, setInformativa] = useState(false);
  const [sitoWeb, setSitoWeb] = useState("");

  useEffect(() => {
    const ctl = new AbortController();
    defaultApiClient
      .getRegistrazioneSensori(ctl.signal)
      .then((r) => setAperta(r.aperta))
      .catch(() => setAperta(false));
    return () => ctl.abort();
  }, []);

  if (aperta === null) return null;
  if (!aperta) {
    return (
      <section className="contributo" aria-label={t.sezione}>
        <p className="contributo-nota">{t.chiusa}</p>
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

  const chiaveNelCampo = /PRIVATE KEY/.test(csr);
  const pronto = licenza && regole && informativa && !chiaveNelCampo;

  const invia = async (ev: FormEvent<HTMLFormElement>): Promise<void> => {
    ev.preventDefault();
    if (!pronto) return;
    setErrore(null);
    setStato("invio");
    try {
      const fotoB64 = foto ? await base64(foto) : null;
      const attesa = ATTESA_MINIMA_MS - (Date.now() - apertoAlle.current);
      if (attesa > 0) await new Promise((r) => setTimeout(r, attesa));
      await defaultApiClient.registraSensore({
        tipo,
        lat: Number(lat),
        lon: Number(lon),
        csr: csr.trim(),
        email: email.trim(),
        note: note.trim() || null,
        foto: fotoB64,
        licenza: "CC-BY-4.0",
        regole_sicurezza: true,
        informativa: true,
        compilato_in_ms: Date.now() - apertoAlle.current,
        sito_web: sitoWeb,
      });
      setStato("inviato");
    } catch (e) {
      setErrore({ e });
      setStato("modulo");
    }
  };

  return (
    <section className="contributo" aria-label={t.sezione}>
      <span className="eyebrow">{t.sezione}</span>
      <p className="contributo-nota">{t.nota}</p>
      <form className="contributo-form" onSubmit={(ev) => void invia(ev)}>
        <label>
          {t.tipo}
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoSensore)}
          >
            {ORDINE_TIPI.map((v) => (
              <option key={v} value={v}>
                {t.tipi[v]}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t.lat}
          <input
            type="number"
            step="any"
            min={-90}
            max={90}
            value={lat}
            onChange={(e) => setLat(e.target.value)}
            required
          />
        </label>
        <label>
          {t.lon}
          <input
            type="number"
            step="any"
            min={-180}
            max={180}
            value={lon}
            onChange={(e) => setLon(e.target.value)}
            required
          />
        </label>
        <label>
          {t.csr}
          <textarea
            value={csr}
            onChange={(e) => setCsr(e.target.value)}
            rows={6}
            maxLength={4000}
            required
            spellCheck={false}
            placeholder="-----BEGIN CERTIFICATE REQUEST-----"
          />
          <span className="contributo-aiuto">{t.csrAiuto}</span>
        </label>
        {chiaveNelCampo ? (
          <p className="contributo-errore" role="alert">
            {t.errori.chiaveNelCampo}
          </p>
        ) : null}
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
          {t.note}
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            maxLength={2000}
            placeholder={t.noteEsempio}
          />
        </label>
        <label>
          {t.foto}
          <input
            type="file"
            accept="image/jpeg,image/png"
            onChange={(e) => setFoto(e.target.files?.[0] ?? null)}
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
            checked={licenza}
            onChange={(e) => setLicenza(e.target.checked)}
          />
          {t.licenza}
        </label>
        <label className="contributo-check">
          <input
            type="checkbox"
            checked={regole}
            onChange={(e) => setRegole(e.target.checked)}
          />
          {t.regole}
        </label>
        <label className="contributo-check">
          <input
            type="checkbox"
            checked={informativa}
            onChange={(e) => setInformativa(e.target.checked)}
          />
          {t.informativa}
        </label>
        {errore ? (
          <p className="contributo-errore" role="alert">
            {messaggioErrore(errore.e, t)}
          </p>
        ) : null}
        <div className="contributo-azioni">
          <button type="submit" disabled={stato === "invio" || !pronto}>
            {stato === "invio" ? t.invio : t.invia}
          </button>
        </div>
      </form>
    </section>
  );
}
