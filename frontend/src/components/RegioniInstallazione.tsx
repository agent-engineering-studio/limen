// «Quali regioni monitori?» (#407). Una Protezione Civile regionale non ha
// bisogno delle 312.550 celle di tutta Italia: `installa.sh` chiede le regioni
// all'inizio, e qui se ne aggiungono altre. Aggiungerne una costa solo quella:
// il worker la semina e poi porta i dati nelle sue celle, e i fattori già
// calcolati per le altre non si ricalcolano (impronta per regione, #101).

import { useState } from "react";
import type { JSX } from "react";

import { testi, useLocale, useTesti } from "../lib/i18n";
import type { RegioneInstallazione } from "../types";

const T = testi(
  {
    titolo: "Le regioni",
    monitorate: "Monitorate",
    nessuna: "Nessuna regione seminata: lancia `./scripts/installa.sh`.",
    celle: (n: string) => `${n} celle`,
    inSemina: "in preparazione: il server semina la griglia, poi carica i dati",
    aggiungi: "Aggiungi una regione",
    aggiungiSpiega:
      "Il server prepara la griglia della regione e poi porta nelle sue celle i dati già scaricati; le regioni che ci sono restano come sono.",
    aggiungiBottone: (n: number) =>
      n === 1 ? "Aggiungi la regione scelta" : `Aggiungi le ${n} regioni scelte`,
    serveToken: "Per aggiungere una regione serve il token di installazione, qui sotto.",
    tutte: "Limen monitora già tutte le regioni.",
  },
  {
    titolo: "Regions",
    monitorate: "Monitored",
    nessuna: "No region seeded: run `./scripts/installa.sh`.",
    celle: (n: string) => `${n} cells`,
    inSemina: "being prepared: the server seeds the grid, then loads the data",
    aggiungi: "Add a region",
    aggiungiSpiega:
      "The server prepares the region's grid and then loads the data already downloaded into its cells; the regions already there stay as they are.",
    aggiungiBottone: (n: number) =>
      n === 1 ? "Add the chosen region" : `Add the ${n} chosen regions`,
    serveToken: "Adding a region needs the installation token, below.",
    tutte: "Limen already monitors every region.",
  },
);

function inCorso(r: RegioneInstallazione): boolean {
  return r.semina?.stato === "in_coda" || r.semina?.stato === "in_corso";
}

export default function RegioniInstallazione({
  regioni,
  puoAgire,
  onAggiungi,
}: {
  regioni: RegioneInstallazione[];
  puoAgire: boolean;
  onAggiungi: (ids: string[]) => Promise<void>;
}): JSX.Element {
  const t = useTesti(T);
  const loc = useLocale();
  const [scelte, setScelte] = useState<Set<string>>(new Set());

  const monitorate = regioni.filter((r) => r.celle > 0 || inCorso(r));
  const altre = regioni.filter((r) => r.celle === 0 && !inCorso(r));

  const scegli = (id: string, si: boolean): void =>
    setScelte((prima) => {
      const dopo = new Set(prima);
      if (si) dopo.add(id);
      else dopo.delete(id);
      return dopo;
    });

  return (
    <section className="installazione-regioni">
      <h2>{t.titolo}</h2>
      <h3>{t.monitorate}</h3>
      {monitorate.length === 0 ? (
        <p className="installazione-nota">{t.nessuna}</p>
      ) : (
        <ul className="installazione-regioni-elenco">
          {monitorate.map((r) => (
            <li key={r.id}>
              <strong>{r.nome}</strong>{" "}
              <span className="installazione-nota">
                {inCorso(r) ? t.inSemina : t.celle(r.celle.toLocaleString(loc))}
              </span>
              {r.semina?.stato === "errore" && r.semina.errore && (
                <p className="installazione-errore">{r.semina.errore}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      <h3>{t.aggiungi}</h3>
      {altre.length === 0 ? (
        <p className="installazione-nota">{t.tutte}</p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const ids = [...scelte];
            setScelte(new Set());
            void onAggiungi(ids);
          }}
        >
          <p className="installazione-nota">{puoAgire ? t.aggiungiSpiega : t.serveToken}</p>
          <ul className="installazione-regioni-scelta">
            {altre.map((r) => (
              <li key={r.id}>
                <label>
                  <input
                    type="checkbox"
                    disabled={!puoAgire}
                    checked={scelte.has(r.id)}
                    onChange={(e) => scegli(r.id, e.target.checked)}
                  />{" "}
                  {r.nome}
                </label>
                {r.semina?.stato === "errore" && r.semina.errore && (
                  <p className="installazione-errore">{r.semina.errore}</p>
                )}
              </li>
            ))}
          </ul>
          <button type="submit" disabled={!puoAgire || scelte.size === 0}>
            {t.aggiungiBottone(scelte.size)}
          </button>
        </form>
      )}
    </section>
  );
}
