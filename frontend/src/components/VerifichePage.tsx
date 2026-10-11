// «Verifiche»: gli eventi dei giornali messi accanto alla previsione di
// Limen. Diventa un articolo solo l'evento previsto in anticipo — con quante
// ore, su quali dati e perché. Gli altri non spariscono: finiscono nel
// riquadro d'inefficienza, contati sul totale, perché una pagina che mostra
// solo i successi senza dire quanti sono misura la fortuna, non il modello.

import { useEffect, useState } from "react";
import type { JSX } from "react";

import { VERIFICHE } from "../content/verifiche";
import type { Esito, Verifica } from "../content/verifiche";
import {
  RISK_COLOR_BY_LEVEL,
  RISK_LABEL_IT_BY_LEVEL,
} from "../lib/risk-colors";
import type { HazardType } from "../types";

const ROUTE = "#/verifiche";

const PERICOLO: Record<HazardType, string> = {
  landslide: "Frana",
  flood: "Alluvione",
  wildfire: "Incendio",
};

export const ESITO: Record<Esito, string> = {
  anticipata: "Prevista in anticipo",
  contemporanea: "Vista mentre accadeva",
  mancata: "Non prevista",
  non_verificabile: "Non verificabile",
};

/** La verifica chiesta dall'hash: `#/verifiche/<slug>`, o nessuna. */
export function verificaDaHash(hash: string): string | null {
  const rotta = hash.split("?")[0] ?? "";
  if (!rotta.startsWith(`${ROUTE}/`)) return null;
  return decodeURIComponent(rotta.slice(ROUTE.length + 1)) || null;
}

function data(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function anticipo(ore: number | null): string {
  if (ore === null) return "—";
  if (ore < 48) return `${ore} ore`;
  const giorni = Math.floor(ore / 24);
  const resto = ore % 24;
  return resto === 0 ? `${giorni} giorni` : `${giorni} giorni e ${resto} ore`;
}

function Etichette({ v }: { v: Verifica }): JSX.Element {
  return (
    <p className="verifica-tag">
      <span className={`hz-${v.pericolo}`}>{PERICOLO[v.pericolo]}</span>
      <span className={`esito esito-${v.esito}`}>{ESITO[v.esito]}</span>
      <span>{v.evento.luogo}</span>
    </p>
  );
}

/** Solo l'evento previsto in anticipo diventa un articolo. */
export function pubblicabile(v: Verifica): boolean {
  return v.esito === "anticipata";
}

function Inefficienza({
  verifiche,
}: {
  verifiche: readonly Verifica[];
}): JSX.Element | null {
  const valutati = verifiche.filter((v) => v.esito !== "non_verificabile");
  const sfuggiti = valutati.filter((v) => !pubblicabile(v));
  const ignoti = verifiche.length - valutati.length;
  if (sfuggiti.length === 0 && ignoti === 0) return null;
  return (
    <section className="verifiche-inefficienza" aria-label="Inefficienza">
      <h3>Inefficienza: eventi che Limen non ha previsto</h3>
      {sfuggiti.length > 0 ? (
        <>
          <p>
            Eventi non previsti in anticipo: {sfuggiti.length} su{" "}
            {valutati.length} verificati. Nessun articolo per questi: restano
            qui, contati, perché sono il limite del sistema.
          </p>
          <ul>
            {sfuggiti.map((v) => (
              <li key={v.slug}>
                {new Date(v.evento.quando).toLocaleDateString("it-IT")} ·{" "}
                {PERICOLO[v.pericolo]} · {v.evento.luogo} —{" "}
                <span className={`esito esito-${v.esito}`}>
                  {ESITO[v.esito]}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {ignoti > 0 ? (
        <p className="exp-note">
          {ignoti === 1
            ? "Un evento non è verificabile"
            : `${ignoti} eventi non sono verificabili`}
          : fuori dalle regioni coperte o più vecchi dei 14 giorni di storico
          delle previsioni.
        </p>
      ) : null}
    </section>
  );
}

function Indice({
  verifiche,
}: {
  verifiche: readonly Verifica[];
}): JSX.Element {
  const articoli = verifiche.filter(pubblicabile);
  return (
    <article className="explainer verifiche">
      <div className="exp-eyebrow">Verifiche</div>
      <h2>Quello che è successo, e quello che Limen aveva visto prima</h2>
      <p className="exp-lede">
        Frane, alluvioni e incendi riportati dai quotidiani, confrontati con le
        previsioni che il sistema aveva pubblicato nelle ore precedenti.
      </p>
      {articoli.length === 0 ? (
        <p className="exp-note">Nessun evento previsto in anticipo, per ora.</p>
      ) : (
        <ul className="verifiche-lista">
          {articoli.map((v) => (
            <li key={v.slug}>
              <a href={`${ROUTE}/${encodeURIComponent(v.slug)}`}>
                {v.foto[0] ? (
                  <img src={v.foto[0].src} alt="" loading="lazy" />
                ) : null}
                <div>
                  <Etichette v={v} />
                  <h3>{v.titolo}</h3>
                  <p>{v.sommario}</p>
                  <p className="exp-note">
                    {data(v.evento.quando)} · anticipo{" "}
                    {anticipo(v.previsione.anticipo_ore_moderato)}
                  </p>
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
      <Inefficienza verifiche={verifiche} />
    </article>
  );
}

function Articolo({ v }: { v: Verifica }): JSX.Element {
  const p = v.previsione;
  return (
    <article className="explainer verifiche">
      <p className="exp-note">
        <a href={ROUTE}>← Tutte le verifiche</a>
      </p>
      <Etichette v={v} />
      <h2>{v.titolo}</h2>
      <p className="exp-lede">{v.sommario}</p>
      <p className="exp-note">
        Evento: {data(v.evento.quando)} · Pubblicato {data(v.pubblicato)}
        {v.aggiornato !== v.pubblicato
          ? ` · aggiornato ${data(v.aggiornato)}`
          : ""}
      </p>

      {v.foto.map((f) => (
        <figure key={f.src} className="verifica-foto">
          <img src={f.src} alt={f.didascalia} />
          <figcaption>
            {f.didascalia} — {f.autore},{" "}
            <a href={f.fonte_url} rel="noopener noreferrer" target="_blank">
              {f.licenza}
            </a>
          </figcaption>
        </figure>
      ))}

      <dl className="verifica-numeri">
        <div>
          <dt>Anticipo (≥ moderato)</dt>
          <dd>{anticipo(p.anticipo_ore_moderato)}</dd>
        </div>
        <div>
          <dt>Anticipo (≥ alto)</dt>
          <dd>{anticipo(p.anticipo_ore_alto)}</dd>
        </div>
        <div>
          <dt>Classe prevista massima</dt>
          <dd>
            {p.classe_max
              ? RISK_LABEL_IT_BY_LEVEL[p.classe_max]
              : "sotto moderato"}
          </dd>
        </div>
        <div>
          <dt>Primo avviso inviato</dt>
          <dd>{p.allerta_prima ? data(p.allerta_prima) : "nessuno"}</dd>
        </div>
      </dl>

      {v.corpo.map((par, i) => (
        <p key={i}>{par}</p>
      ))}

      {p.corse.length > 0 ? (
        <>
          <h3>Le previsioni che puntavano all&apos;evento</h3>
          <table className="int-table">
            <thead>
              <tr>
                <th>Calcolata il</th>
                <th>Orizzonte</th>
                <th>Classe</th>
                <th>Punteggio</th>
              </tr>
            </thead>
            <tbody>
              {p.corse.map((c) => (
                <tr key={`${c.run_at}-${c.horizon_h}`}>
                  <td>{data(c.run_at)}</td>
                  <td>+{c.horizon_h} h</td>
                  <td>
                    <span
                      className="verifica-pallino"
                      style={{ background: RISK_COLOR_BY_LEVEL[c.classe] }}
                    />
                    {RISK_LABEL_IT_BY_LEVEL[c.classe]}
                  </td>
                  <td>{c.score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {v.perche.length > 0 ? (
        <>
          <h3>Perché</h3>
          <ul>
            {v.perche.map((f) => (
              <li key={f.nome}>
                <strong>{f.nome}</strong> ({f.valore}): {f.spiegazione}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <h3>Fonti</h3>
      <ul>
        {v.fonti.map((f) => (
          <li key={f.url}>
            {f.testata},{" "}
            <a href={f.url} rel="noopener noreferrer" target="_blank">
              {f.titolo}
            </a>{" "}
            ({new Date(f.data).toLocaleDateString("it-IT")})
          </li>
        ))}
      </ul>
    </article>
  );
}

export default function VerifichePage({
  verifiche = VERIFICHE,
}: {
  verifiche?: readonly Verifica[];
}): JSX.Element {
  const [slug, setSlug] = useState<string | null>(() =>
    verificaDaHash(window.location.hash),
  );

  useEffect(() => {
    const onHash = (): void => setSlug(verificaDaHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // Un link diretto a un evento non previsto porta all'indice, dove sta
  // nel riquadro d'inefficienza: l'articolo esiste solo per gli anticipi.
  const scelta = slug
    ? verifiche.filter(pubblicabile).find((v) => v.slug === slug)
    : undefined;
  return scelta ? <Articolo v={scelta} /> : <Indice verifiche={verifiche} />;
}
