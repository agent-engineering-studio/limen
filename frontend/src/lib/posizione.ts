/** Il riquadro dell'Italia, isole comprese: una posizione fuori non ha
 *  celle da mostrare, e volarci sopra darebbe una mappa vuota. */
const ITALIA: readonly [[number, number], [number, number]] = [
  [6.6, 35.4],
  [18.6, 47.1],
];

export const ZOOM_POSIZIONE = 10;

export function dentroItalia(lon: number, lat: number): boolean {
  return lon >= ITALIA[0][0] && lon <= ITALIA[1][0] && lat >= ITALIA[0][1] && lat <= ITALIA[1][1];
}

/** Chiede la posizione del browser e la passa solo se cade in Italia.
 *  Rifiuto, timeout o posizione all'estero lasciano la mappa dov'è: la
 *  vista di partenza resta quella configurata. Restituisce l'annullamento. */
export function posizioneInItalia(onPosizione: (lon: number, lat: number) => void): () => void {
  let attiva = true;
  if (typeof navigator === "undefined" || !navigator.geolocation) return () => {};
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => {
      if (attiva && dentroItalia(coords.longitude, coords.latitude)) {
        onPosizione(coords.longitude, coords.latitude);
      }
    },
    () => {},
    { enableHighAccuracy: false, timeout: 8000, maximumAge: 5 * 60 * 1000 },
  );
  return () => {
    attiva = false;
  };
}
