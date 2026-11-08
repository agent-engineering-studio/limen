// Le clausole che la licenza CEMS-Floods (GloFAS/EFAS) chiede a chi pubblica
// dati derivati: citare la fonte con la formula «Contains modified Copernicus
// Emergency Management Service information [Year]», o una simile, e non far
// passare i dati per un avviso di piena — quello spetta alle istituzioni
// nazionali e regionali. Limen pubblica punteggi calcolati dalla portata
// GloFAS (alluvione) e, da CEMS Fire, il confronto con l'FWI ufficiale.

import type { Lingua } from "./i18n";

/** L'anno della notizia è quello in cui la pagina mostra i dati. In inglese
 *  la formula è quella che la licenza scrive. */
export function copernicusModificato(
  anno: number = new Date().getFullYear(),
  lingua: Lingua = "it",
): string {
  return lingua === "it"
    ? `Contiene informazioni modificate del Copernicus Emergency Management Service, ${anno}`
    : `Contains modified Copernicus Emergency Management Service information, ${anno}`;
}

export const AVVISO_DI_PIENA: Record<Lingua, string> = {
  it: "I dati GloFAS non sono un avviso di piena: l'allertamento spetta alle autorità nazionali e regionali.",
  en: "GloFAS data are not a flood warning: issuing warnings is the responsibility of national and regional authorities.",
};

export const NON_E_UN_AVVISO_DI_PIENA = AVVISO_DI_PIENA.it;

// I dati aperti ECMWF (IFS 0,25°, serviti dall'istanza Open-Meteo che Limen
// ospita) sono CC BY 4.0 con i Terms of Use di ECMWF, che chiedono «© [anno]
// ECMWF» e, testualmente, la frase di non responsabilità qui sotto: in
// inglese anche nella pagina italiana, perché è quella la formula richiesta.
export const ECMWF_NON_RESPONSABILITA =
  "ECMWF does not accept any liability whatsoever for any error or omission in the data";

/** Dove la pagina mostra la pioggia prevista o un punteggio calcolato da essa. */
export function meteoEcmwf(
  anno: number = new Date().getFullYear(),
  lingua: Lingua = "it",
): string {
  return lingua === "it"
    ? `Meteo: Open-Meteo.com, dati © ${anno} ECMWF (CC BY 4.0). ECMWF non risponde di errori od omissioni nei dati: «${ECMWF_NON_RESPONSABILITA}».`
    : `Weather data by Open-Meteo.com, © ${anno} ECMWF (CC BY 4.0). ${ECMWF_NON_RESPONSABILITA}.`;
}
