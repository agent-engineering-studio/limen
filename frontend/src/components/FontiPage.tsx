// "Fonti" (#277): tutte le fonti dei dati di Limen, per ruolo, dall'elenco
// unico di `lib/fonti.ts`. Il logo solo dove il titolare lo concede; per gli
// altri il nome, in un riquadro uguale per tutti.

import type { JSX } from "react";

import { FONTI, NOME_RUOLO, ORDINE_RUOLI, SPIEGAZIONE_RUOLO } from "../lib/fonti";
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
        <h4>{f.dataset[lingua]}</h4>
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

export function FontiPage(): JSX.Element {
  const { lingua } = useLingua();
  const t = useTesti(T);
  return (
    <article className="explainer fonti">
      <div className="exp-eyebrow">{t.occhiello}</div>
      <h2>{t.titolo}</h2>
      <p className="exp-lede">{t.lede}</p>
      <p className="fonti-avviso">{t.nonAffiliato}</p>
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
