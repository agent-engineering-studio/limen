// Le stazioni dei sensori sulla mappa (#255): il simbolo e il popup.
//
// Il simbolo distingue i tre livelli di fiducia con grigi e dimensioni, mai
// con la rampa del rischio né con le tinte dei pericoli: una stazione non è
// una classe di pericolo, e un pallino arancione si leggerebbe come tale.
// Il popup si costruisce con nodi di testo, non con HTML: l'id l'ha scelto
// chi ha registrato il sensore.

import { locale, testi } from "./i18n";
import type { Lingua } from "./i18n";

export type LivelloStazione = 0 | 1 | 2;

/** Le proprietà che `/api/sensori/stazioni` mette su ogni punto. */
export interface ProprietaStazione {
  id: string;
  tipo: string;
  livello: LivelloStazione;
  stato: "online" | "offline" | "quarantined";
  arrotondata: boolean;
  ultima_grandezza: string | null;
  ultimo_valore: number | null;
  ultima_unita: string | null;
  ultimo_istante: string | null;
  valide_24h: number;
  segnalate_24h: number;
}

/** Riempimento per livello: dal grigio scuro (osservatore) al bianco (ente). */
export const COLORE_LIVELLO: Record<LivelloStazione, string> = {
  0: "#7d8794",
  1: "#c3ccd6",
  2: "#ffffff",
};

/** Raggio per livello: il livello si legge anche senza distinguere i grigi. */
export const RAGGIO_LIVELLO: Record<LivelloStazione, number> = { 0: 4, 1: 5.5, 2: 7 };

const T = testi(
  {
    livello: {
      0: "Osservatore",
      1: "Verificata",
      2: "Istituzionale",
    } as Record<LivelloStazione, string>,
    spiegazione: {
      0: "Questa stazione non fa scattare allerte e non cambia i punteggi: serve alle verifiche e al confronto con il radar.",
      1: "Contribuisce alla stima della pioggia insieme ad altre stazioni di persone diverse, entro un tetto. Non fa scattare allerte da sola.",
      2: "Stazione di un ente: entra nei punteggi e può far scattare un'allerta.",
    } as Record<LivelloStazione, string>,
    stato: {
      online: "in linea",
      offline: "non in linea",
      quarantined: "sospesa per una verifica",
    } as Record<ProprietaStazione["stato"], string>,
    grandezza: {
      rainfall: "pioggia",
      soil_moisture: "umidità del suolo",
      pore_pressure: "pressione interstiziale",
      displacement: "spostamento",
      velocity: "velocità di spostamento",
      acceleration: "accelerazione",
      water_level: "livello idrometrico",
      air_temperature: "temperatura dell'aria",
      relative_humidity: "umidità relativa",
      wind_speed: "velocità del vento",
    } as Record<string, string>,
    ultimo: "Ultimo dato",
    nessunDato: "Nessun dato negli ultimi 30 giorni.",
    qc: (valide: number, segnalate: number) =>
      valide + segnalate === 0
        ? "Nessuna misura nelle ultime 24 ore."
        : `Ultime 24 ore: ${valide} misure valide, ${segnalate} segnalate dal controllo di qualità.`,
    arrotondata: "Posizione arrotondata a circa un chilometro.",
  },
  {
    livello: {
      0: "Observer",
      1: "Verified",
      2: "Institutional",
    },
    spiegazione: {
      0: "This station does not trigger alerts and does not change scores: it serves the checks and the comparison with radar.",
      1: "It contributes to the rainfall estimate together with other stations owned by different people, within a cap. It does not trigger alerts by itself.",
      2: "Station of an institution: it enters the scores and can trigger an alert.",
    },
    stato: {
      online: "online",
      offline: "offline",
      quarantined: "suspended for a check",
    },
    grandezza: {
      rainfall: "rain",
      soil_moisture: "soil moisture",
      pore_pressure: "pore pressure",
      displacement: "displacement",
      velocity: "displacement rate",
      acceleration: "acceleration",
      water_level: "water level",
      air_temperature: "air temperature",
      relative_humidity: "relative humidity",
      wind_speed: "wind speed",
    },
    ultimo: "Last reading",
    nessunDato: "No data in the last 30 days.",
    qc: (valide: number, segnalate: number) =>
      valide + segnalate === 0
        ? "No measurements in the last 24 hours."
        : `Last 24 hours: ${valide} valid measurements, ${segnalate} flagged by quality control.`,
    arrotondata: "Position rounded to about one kilometre.",
  },
);

/** Le righe del popup, nell'ordine in cui si leggono. */
export function righeStazione(p: ProprietaStazione, lingua: Lingua): string[] {
  const t = T[lingua];
  const livello = (p.livello in t.livello ? p.livello : 0) as LivelloStazione;
  const righe = [`${p.id} · ${t.livello[livello]} · ${t.stato[p.stato] ?? p.stato}`];
  righe.push(t.spiegazione[livello]);
  // MapLibre può togliere dalle proprietà i valori null: si controlla il tipo.
  if (
    typeof p.ultimo_valore === "number" &&
    typeof p.ultimo_istante === "string" &&
    typeof p.ultima_grandezza === "string"
  ) {
    const valore = new Intl.NumberFormat(locale(lingua), { maximumFractionDigits: 3 }).format(
      p.ultimo_valore,
    );
    const quando = new Intl.DateTimeFormat(locale(lingua), {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(p.ultimo_istante));
    const nome = t.grandezza[p.ultima_grandezza] ?? p.ultima_grandezza;
    righe.push(`${t.ultimo}: ${nome} ${valore} ${p.ultima_unita ?? ""}, ${quando}`.trim());
  } else {
    righe.push(t.nessunDato);
  }
  righe.push(t.qc(Number(p.valide_24h) || 0, Number(p.segnalate_24h) || 0));
  if (p.arrotondata === true) righe.push(t.arrotondata);
  return righe;
}

/** Il contenuto del popup, solo nodi di testo. */
export function popupStazione(p: ProprietaStazione, lingua: Lingua): HTMLElement {
  const div = document.createElement("div");
  div.className = "popup-stazione";
  righeStazione(p, lingua).forEach((riga, i) => {
    const el = document.createElement(i === 0 ? "strong" : "p");
    el.textContent = riga;
    div.appendChild(el);
  });
  return div;
}
