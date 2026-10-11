// Le clausole che la licenza CEMS-Floods (GloFAS/EFAS) chiede a chi pubblica
// dati derivati: citare la fonte con la formula «Contains modified Copernicus
// Emergency Management Service information [Year]», o una simile, e non far
// passare i dati per un avviso di piena — quello spetta alle istituzioni
// nazionali e regionali. Limen pubblica punteggi calcolati dalla portata
// GloFAS (alluvione) e, da CEMS Fire, il confronto con l'FWI ufficiale.

/** L'anno della notizia è quello in cui la pagina mostra i dati. */
export function copernicusModificato(
  anno: number = new Date().getFullYear(),
): string {
  return `Contiene informazioni modificate del Copernicus Emergency Management Service, ${anno}`;
}

export const NON_E_UN_AVVISO_DI_PIENA =
  "I dati GloFAS non sono un avviso di piena: l'allertamento spetta alle autorità nazionali e regionali.";
