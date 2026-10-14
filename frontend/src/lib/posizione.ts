import { CONTORNO_ITALIA } from "./italia-contorno";

export const ZOOM_POSIZIONE = 10;

function dentroAnello(lon: number, lat: number, anello: readonly (readonly [number, number])[]): boolean {
  let dentro = false;
  for (let i = 0, j = anello.length - 1; i < anello.length; j = i++) {
    const [xi, yi] = anello[i]!;
    const [xj, yj] = anello[j]!;
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}

/** Il territorio, non il suo riquadro: nel rettangolo dell'Italia stanno
 *  anche Nizza, la Corsica, il Ticino, Lubiana, l'Istria, Malta e Tunisi, e
 *  volarci sopra darebbe una mappa senza celle. */
export function dentroItalia(lon: number, lat: number): boolean {
  return CONTORNO_ITALIA.some((anello) => dentroAnello(lon, lat, anello));
}

/** Chiede la posizione del browser e la passa solo se cade in Italia.
 *  Rifiuto, timeout o posizione all'estero lasciano la mappa dov'è: la
 *  vista di partenza resta quella configurata. `onFatto` segna il tentativo
 *  come chiuso in ogni esito, così una ricostruzione della mappa non chiede
 *  di nuovo il permesso; una richiesta annullata non lo chiama, perché la
 *  sua risposta non è stata usata. Restituisce l'annullamento. */
export function posizioneInItalia(
  onPosizione: (lon: number, lat: number) => void,
  onFatto: () => void,
): () => void {
  let attiva = true;
  if (typeof navigator === "undefined" || !navigator.geolocation) return () => {};
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => {
      if (!attiva) return;
      onFatto();
      if (dentroItalia(coords.longitude, coords.latitude)) onPosizione(coords.longitude, coords.latitude);
    },
    () => {
      if (attiva) onFatto();
    },
    { enableHighAccuracy: false, timeout: 8000, maximumAge: 5 * 60 * 1000 },
  );
  return () => {
    attiva = false;
  };
}
