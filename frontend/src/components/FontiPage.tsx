// "Fonti" (#277): tutte le fonti dei dati di Limen, per ruolo, dall'elenco
// unico di `lib/fonti.ts`. Il logo solo dove il titolare lo concede; per gli
// altri il nome, in un riquadro uguale per tutti.

import { useEffect } from "react";
import type { JSX } from "react";

import {
  FONTI,
  fontiCopernicus,
  NOME_RUOLO,
  NOME_SERVIZIO,
  ORDINE_RUOLI,
  SPIEGAZIONE_RUOLO,
} from "../lib/fonti";
import type { Fonte } from "../lib/fonti";
import { NOMI_PERICOLO } from "../lib/hazard";
import { testi, useLingua, useTesti } from "../lib/i18n";

const T = testi(
  {
    occhiello: "Fonti dei dati",
    titolo: "Da dove vengono i numeri",
    lede:
      "Ogni punteggio sulla mappa è calcolato da dati aperti di enti pubblici, programmi europei e progetti comunitari. Qui ci sono tutti, con cosa danno a Limen e con quale licenza.",
    nonAffiliato:
      "Limen è un progetto indipendente: citare una fonte non vuol dire che l'ente approvi Limen o le sue stime. Nomi e marchi appartengono ai rispettivi titolari; il logo compare solo dove le regole del titolare lo permettono.",
    pericoli: "Pericoli",
    accesso: "Come si legge",
    interpretazione: "Come la usa Limen",
    copernicusTitolo: "Copernicus: i dati aperti europei",
    copernicusTesto:
      "Una parte grande di Limen viene da Copernicus, il programma europeo di osservazione della Terra: dati gratuiti e aperti, senza registrazione o con una chiave gratuita. Ecco quali, da quale servizio e come Limen li legge.",
    copernicusNota:
      "Limen non è un servizio Copernicus né è approvato dalla Commissione europea: usa i dati alle condizioni della loro licenza.",
    ruolo: "Ruolo",
    licenza: "Licenza",
    attribuzione: "Attribuzione",
    facoltativa: "Facoltativa: la usa solo chi ospita Limen con il file o la chiave.",
    sito: "Sito della fonte",
    regole: "Regole d'uso del logo",
    geografia: "geografia",
  },
  {
    occhiello: "Data sources",
    titolo: "Where the numbers come from",
    lede:
      "Every score on the map is computed from open data by public bodies, European programmes and community projects. They are all here, with what they give Limen and under which licence.",
    nonAffiliato:
      "Limen is an independent project: citing a source does not mean that the body endorses Limen or its estimates. Names and trademarks belong to their owners; a logo appears only where the owner's rules allow it.",
    pericoli: "Hazards",
    accesso: "How it is read",
    interpretazione: "How Limen uses it",
    copernicusTitolo: "Copernicus: Europe's open data",
    copernicusTesto:
      "A large part of Limen comes from Copernicus, the European Earth observation programme: free and open data, without registration or with a free key. Here is which, from which service and how Limen reads them.",
    copernicusNota:
      "Limen is not a Copernicus service and is not endorsed by the European Commission: it uses the data under the terms of their licence.",
    ruolo: "Role",
    licenza: "Licence",
    attribuzione: "Attribution",
    facoltativa: "Optional: used only where whoever hosts Limen has the file or the key.",
    sito: "Source website",
    regole: "Logo usage rules",
    geografia: "geography",
  },
);

function Marchio({ f }: { f: Fonte }): JSX.Element {
  const { lingua } = useLingua();
  const t = useTesti(T);
  if (f.logo) {
    // OpenStreetMap concede il logo solo come link al progetto.
    return (
      <div className="fonte-marchio">
        <a href={f.url} target="_blank" rel="noreferrer">
          <img src={`${import.meta.env.BASE_URL}${f.logo.file}`} alt={f.ente} width={48} height={48} />
        </a>
        <small>
          {f.logo.nota[lingua]}{" "}
          <a href={f.logo.regole} target="_blank" rel="noreferrer">
            {t.regole}
          </a>
        </small>
      </div>
    );
  }
  return (
    <div className="fonte-marchio">
      <span className="fonte-nome">{f.ente}</span>
    </div>
  );
}

function Scheda({ f }: { f: Fonte }): JSX.Element {
  const { lingua } = useLingua();
  const t = useTesti(T);
  const esterno = f.url.startsWith("http");
  return (
    <li className="fonte" id={`fonte-${f.id}`}>
      <Marchio f={f} />
      <div className="fonte-testo">
        <h4>
          {f.dataset[lingua]}
          {f.copernicus ? <span className="fonte-copernicus">Copernicus · {f.copernicus}</span> : null}
        </h4>
        {f.logo ? <p className="fonte-ente">{f.ente}</p> : null}
        <p>{f.cosa[lingua]}</p>
        <p className="fonte-tag">
          {f.pericoli.length > 0 ? (
            f.pericoli.map((p) => (
              <span key={p} className={`hz-${p}`}>
                {NOMI_PERICOLO[lingua][p]}
              </span>
            ))
          ) : (
            <span>{t.geografia}</span>
          )}
        </p>
        <dl className="fonte-meta">
          <dt>{t.accesso}</dt>
          <dd>{f.accesso[lingua]}</dd>
          <dt>{t.interpretazione}</dt>
          <dd>{f.interpretazione[lingua]}</dd>
          <dt>{t.licenza}</dt>
          <dd>{f.licenza}</dd>
          {f.attribuzione ? (
            <>
              <dt>{t.attribuzione}</dt>
              <dd>«{f.attribuzione[lingua]}»</dd>
            </>
          ) : null}
        </dl>
        {f.facoltativa ? <p className="fonte-nota">{t.facoltativa}</p> : null}
        <a href={f.url} {...(esterno ? { target: "_blank", rel: "noreferrer" } : {})}>
          {esterno ? t.sito : f.dataset[lingua]}
        </a>
      </div>
    </li>
  );
}

function Copernicus(): JSX.Element {
  const { lingua } = useLingua();
  const t = useTesti(T);
  return (
    <section className="fonti-copernicus" aria-labelledby="fonti-copernicus">
      <h3 id="fonti-copernicus">{t.copernicusTitolo}</h3>
      <p>{t.copernicusTesto}</p>
      <table>
        <thead>
          <tr>
            <th>Copernicus</th>
            <th>{t.occhiello}</th>
            <th>{t.ruolo}</th>
            <th>{t.accesso}</th>
          </tr>
        </thead>
        <tbody>
          {fontiCopernicus().map((f) => (
            <tr key={f.id}>
              <td title={f.copernicus ? NOME_SERVIZIO[f.copernicus][lingua] : undefined}>
                {f.copernicus}
              </td>
              <td>
                <a href={`#/fonti/${f.id}`}>{f.dataset[lingua]}</a>
              </td>
              <td>{NOME_RUOLO[f.ruolo][lingua]}</td>
              <td>{f.accesso[lingua]}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="fonte-nota">{t.copernicusNota}</p>
    </section>
  );
}

// Il link a una scheda resta dentro la rotta (`#/fonti/<id>`): un `#fonte-…`
// nudo cambierebbe l'hash, e `pageFromHash` riporterebbe alla home.
function scorriAllaScheda(): void {
  const id = /^#\/fonti\/([\w-]+)/.exec(window.location.hash)?.[1];
  if (id) document.getElementById(`fonte-${id}`)?.scrollIntoView?.({ block: "start" });
}

export function FontiPage(): JSX.Element {
  const { lingua } = useLingua();
  const t = useTesti(T);
  useEffect(() => {
    scorriAllaScheda();
    window.addEventListener("hashchange", scorriAllaScheda);
    return () => window.removeEventListener("hashchange", scorriAllaScheda);
  }, []);
  return (
    <article className="explainer fonti">
      <div className="exp-eyebrow">{t.occhiello}</div>
      <h2>{t.titolo}</h2>
      <p className="exp-lede">{t.lede}</p>
      <p className="fonti-avviso">{t.nonAffiliato}</p>
      <Copernicus />
      {ORDINE_RUOLI.map((ruolo) => {
        const elenco = FONTI.filter((f) => f.ruolo === ruolo);
        if (elenco.length === 0) return null;
        return (
          <section key={ruolo} aria-labelledby={`ruolo-${ruolo}`}>
            <h3 id={`ruolo-${ruolo}`}>{NOME_RUOLO[ruolo][lingua]}</h3>
            <p>{SPIEGAZIONE_RUOLO[ruolo][lingua]}</p>
            <ul className="fonti-elenco">
              {elenco.map((f) => (
                <Scheda key={f.id} f={f} />
              ))}
            </ul>
          </section>
        );
      })}
    </article>
  );
}

export default FontiPage;
