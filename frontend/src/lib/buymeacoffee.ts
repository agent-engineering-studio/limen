import { useEffect } from "react";

// Buy Me a Coffee: il pulsante galleggiante in basso a destra.
//
// Lo script ufficiale aspetta `DOMContentLoaded` su `window` e legge i suoi
// attributi dal proprio tag. In una SPA quell'evento è già passato quando lo
// si carica, quindi lo si ripete a script caricato: l'unico altro ascoltatore
// dell'app è di React, sta su `document` e non su `window`.
//
// Non si carica sulla dashboard: il pulsante e il fumetto del messaggio
// starebbero sopra lo zoom e la timeline della mappa. Caricato altrove, sulla
// dashboard il pulsante si nasconde.

export const BMC_SLUG = "f9t3zol";
export const BMC_PAGINA = `https://www.buymeacoffee.com/${BMC_SLUG}`;

const ATTRIBUTI: Record<string, string> = {
  name: "BMC-Widget",
  cfasync: "false",
  id: BMC_SLUG,
  description: "Sostieni Limen su Buy Me a Coffee",
  message:
    "Limen è gratuito e aperto a tutti. Se ti è utile, offrici un caffè: tiene acceso il server.",
  color: "#FF813F",
  position: "Right",
  x_margin: "18",
  y_margin: "18",
};

export function useBuyMeACoffee(attivo: boolean): void {
  useEffect(() => {
    const pulsante = document.getElementById("bmc-wbtn");
    if (pulsante) {
      pulsante.style.display = attivo ? "" : "none";
      return;
    }
    if (!attivo || document.querySelector('script[data-name="BMC-Widget"]')) return;
    const script = document.createElement("script");
    script.src = "https://cdnjs.buymeacoffee.com/1.0.0/widget.prod.min.js";
    script.async = true;
    for (const [k, v] of Object.entries(ATTRIBUTI)) script.dataset[k] = v;
    script.onload = () => window.dispatchEvent(new Event("DOMContentLoaded"));
    document.body.appendChild(script);
  }, [attivo]);
}
