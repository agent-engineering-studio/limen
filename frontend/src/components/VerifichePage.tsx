// «Verifiche»: gli eventi dei giornali che Limen aveva previsto in anticipo,
// con quante ore, su quali dati e perché. Solo quelli: un evento non
// previsto non ha articolo e non compare sulla pagina. Italiano e inglese:
// il testo dell'articolo viene dal JSON (`en`), le etichette da qui.

import { useEffect, useState } from "react";
import type { JSX } from "react";

import { AVVISO_DI_PIENA, copernicusModificato } from "../lib/attribuzioni";
import { NOMI_PERICOLO } from "../lib/hazard";
import type { Lingua } from "../lib/i18n";
import { testi, useLingua, useLocale, useTesti } from "../lib/i18n";
import { VERIFICHE } from "../content/verifiche";
import type { Fattore, Verifica } from "../content/verifiche";
import { RISK_COLOR_BY_LEVEL, useEtichetteRischio } from "../lib/risk-colors";

const ROUTE = "#/verifiche";

const T = testi(
  {
    occhiello: "Verifiche",
    titolo: "Quello che è successo, e quanto prima Limen l'aveva visto",
    lede: "Frane, alluvioni e incendi riportati dai quotidiani che il sistema aveva previsto nelle ore precedenti.",
    vuoto: "Nessun evento previsto in anticipo, per ora.",
    anticipo: "anticipo",
    tutte: "← Tutte le verifiche",
    evento: "Evento",
    pubblicato: "Pubblicato",
    aggiornato: "aggiornato",
    anticipoModerato: "Anticipo (≥ moderato)",
    anticipoAlto: "Anticipo (≥ alto)",
    classeMax: "Classe prevista massima",
    sottoModerato: "sotto moderato",
    primoAvviso: "Primo avviso inviato",
    nessuno: "nessuno",
    corse: "Le previsioni che puntavano all'evento",
    calcolata: "Calcolata il",
    orizzonte: "Orizzonte",
    classe: "Classe",
    punteggio: "Punteggio",
    perche: "Perché",
    fonti: "Fonti",
    prevista: "Prevista in anticipo",
    ore: (n: number) => `${n} ore`,
    giorni: (g: number, h: number) =>
      h === 0 ? `${g} giorni` : `${g} giorni e ${h} ore`,
  },
  {
    occhiello: "Checks",
    titolo: "What happened, and how early Limen saw it",
    lede: "Landslides, floods and wildfires reported by Italian newspapers that the system had forecast in the hours before.",
    vuoto: "No event forecast in advance, for now.",
    anticipo: "lead time",
    tutte: "← All checks",
    evento: "Event",
    pubblicato: "Published",
    aggiornato: "updated",
    anticipoModerato: "Lead time (≥ moderate)",
    anticipoAlto: "Lead time (≥ high)",
    classeMax: "Highest forecast class",
    sottoModerato: "below moderate",
    primoAvviso: "First alert sent",
    nessuno: "none",
    corse: "The forecasts aimed at the event",
    calcolata: "Computed on",
    orizzonte: "Horizon",
    classe: "Class",
    punteggio: "Score",
    perche: "Why",
    fonti: "Sources",
    prevista: "Forecast in advance",
    ore: (n: number) => `${n} hours`,
    giorni: (g: number, h: number) => (h === 0 ? `${g} days` : `${g} days and ${h} hours`),
  },
);

/** La verifica chiesta dall'hash: `#/verifiche/<slug>`, o nessuna. */
export function verificaDaHash(hash: string): string | null {
  const rotta = hash.split("?")[0] ?? "";
  if (!rotta.startsWith(`${ROUTE}/`)) return null;
  return decodeURIComponent(rotta.slice(ROUTE.length + 1)) || null;
}

export function anticipo(ore: number | null, lingua: Lingua = "it"): string {
  if (ore === null) return "—";
  const t = T[lingua];
  if (ore < 48) return t.ore(ore);
  return t.giorni(Math.floor(ore / 24), ore % 24);
}

/** I testi dell'articolo nella lingua attiva: l'italiano sta alla radice
 *  del JSON, l'inglese nel blocco `en`. */
function testo(
  v: Verifica,
  lingua: Lingua,
): { titolo: string; luogo: string; sommario: string; corpo: string[]; perche: Fattore[] } {
  return lingua === "en"
    ? v.en
    : {
        titolo: v.titolo,
        luogo: v.evento.luogo,
        sommario: v.sommario,
        corpo: v.corpo,
        perche: v.perche,
      };
}

function useData(): (iso: string) => string {
  const loc = useLocale();
  return (iso) =>
    new Date(iso).toLocaleString(loc, {
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
}

function Etichette({ v }: { v: Verifica }): JSX.Element {
  const { lingua } = useLingua();
  const t = useTesti(T);
  return (
    <p className="verifica-tag">
      <span className={`hz-${v.pericolo}`}>{NOMI_PERICOLO[lingua][v.pericolo]}</span>
      <span className={`esito esito-${v.esito}`}>{t.prevista}</span>
      <span>{testo(v, lingua).luogo}</span>
    </p>
  );
}

function Indice({ verifiche }: { verifiche: readonly Verifica[] }): JSX.Element {
  const { lingua } = useLingua();
  const t = useTesti(T);
  const data = useData();
  return (
    <article className="explainer verifiche">
      <div className="exp-eyebrow">{t.occhiello}</div>
      <h2>{t.titolo}</h2>
      <p className="exp-lede">{t.lede}</p>
      {verifiche.length === 0 ? (
        <p className="exp-note">{t.vuoto}</p>
      ) : (
        <ul className="verifiche-lista">
          {verifiche.map((v) => {
            const x = testo(v, lingua);
            return (
              <li key={v.slug}>
                <a href={`${ROUTE}/${encodeURIComponent(v.slug)}`}>
                  {v.foto[0] ? <img src={v.foto[0].src} alt="" loading="lazy" /> : null}
                  <div>
                    <Etichette v={v} />
                    <h3>{x.titolo}</h3>
                    <p>{x.sommario}</p>
                    <p className="exp-note">
                      {data(v.evento.quando)} · {t.anticipo}{" "}
                      {anticipo(v.previsione.anticipo_ore_moderato, lingua)}
                    </p>
                  </div>
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </article>
  );
}

function Articolo({ v }: { v: Verifica }): JSX.Element {
  const { lingua } = useLingua();
  const t = useTesti(T);
  const data = useData();
  const etichetta = useEtichetteRischio();
  const loc = useLocale();
  const x = testo(v, lingua);
  const p = v.previsione;
  return (
    <article className="explainer verifiche">
      <p className="exp-note">
        <a href={ROUTE}>{t.tutte}</a>
      </p>
      <Etichette v={v} />
      <h2>{x.titolo}</h2>
      <p className="exp-lede">{x.sommario}</p>
      <p className="exp-note">
        {t.evento}: {data(v.evento.quando)} · {t.pubblicato} {data(v.pubblicato)}
        {v.aggiornato !== v.pubblicato ? ` · ${t.aggiornato} ${data(v.aggiornato)}` : ""}
      </p>

      {v.foto.map((f, i) => {
        const didascalia = lingua === "en" ? (v.en.foto[i]?.didascalia ?? f.didascalia) : f.didascalia;
        return (
          <figure key={f.src} className="verifica-foto">
            <img src={f.src} alt={didascalia} />
            <figcaption>
              {didascalia} — {f.autore},{" "}
              <a href={f.fonte_url} rel="noopener noreferrer" target="_blank">
                {f.licenza}
              </a>
            </figcaption>
          </figure>
        );
      })}

      <dl className="verifica-numeri">
        <div>
          <dt>{t.anticipoModerato}</dt>
          <dd>{anticipo(p.anticipo_ore_moderato, lingua)}</dd>
        </div>
        <div>
          <dt>{t.anticipoAlto}</dt>
          <dd>{anticipo(p.anticipo_ore_alto, lingua)}</dd>
        </div>
        <div>
          <dt>{t.classeMax}</dt>
          <dd>{p.classe_max ? etichetta[p.classe_max] : t.sottoModerato}</dd>
        </div>
        <div>
          <dt>{t.primoAvviso}</dt>
          <dd>{p.allerta_prima ? data(p.allerta_prima) : t.nessuno}</dd>
        </div>
      </dl>

      {x.corpo.map((par, i) => (
        <p key={i}>{par}</p>
      ))}

      {p.corse.length > 0 ? (
        <>
          <h3>{t.corse}</h3>
          <table className="int-table">
            <thead>
              <tr>
                <th>{t.calcolata}</th>
                <th>{t.orizzonte}</th>
                <th>{t.classe}</th>
                <th>{t.punteggio}</th>
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
                    {etichetta[c.classe]}
                  </td>
                  <td>{c.score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {x.perche.length > 0 ? (
        <>
          <h3>{t.perche}</h3>
          <ul>
            {x.perche.map((f) => (
              <li key={f.nome}>
                <strong>{f.nome}</strong> ({f.valore}): {f.spiegazione}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {v.pericolo === "flood" ? (
        <p className="exp-note">
          {copernicusModificato(new Date(v.evento.quando).getFullYear(), lingua)}.{" "}
          {AVVISO_DI_PIENA[lingua]}
        </p>
      ) : null}

      <h3>{t.fonti}</h3>
      <ul>
        {v.fonti.map((f) => (
          <li key={f.url}>
            {f.testata},{" "}
            <a href={f.url} rel="noopener noreferrer" target="_blank" lang="it">
              {f.titolo}
            </a>{" "}
            ({new Date(f.data).toLocaleDateString(loc)})
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
  const [slug, setSlug] = useState<string | null>(() => verificaDaHash(window.location.hash));

  useEffect(() => {
    const onHash = (): void => setSlug(verificaDaHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const scelta = slug ? verifiche.find((v) => v.slug === slug) : undefined;
  return scelta ? <Articolo v={scelta} /> : <Indice verifiche={verifiche} />;
}
