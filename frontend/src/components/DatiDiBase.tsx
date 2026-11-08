// Il dato di base di ogni ingrediente della cella, con la fonte accanto (#422).
//
// In italiano il testo è quello del backend, lo stesso che legge un agente via
// MCP: un solo posto lo scrive. In inglese si ricompone qui dal valore grezzo,
// perché il catalogo dei dati è scritto in italiano.

import type { JSX } from "react";

import { testi, useLingua } from "../lib/i18n";
import type { DatoDiBase } from "../types";

const T = testi(
  { titolo: "Dati di base", licenza: "licenza" },
  { titolo: "Base data", licenza: "licence" },
);

const NOMI_EN: Record<string, string> = {
  iffi: "historical landslides (IFFI)",
  pai_frana: "PAI landslide hazard",
  idraulica: "ISPRA flood hazard",
  dtm: "slope (DTM)",
  corine: "land cover (CORINE)",
  impermeabilizzazione: "sealed soil (CLMS)",
  wui: "wildland-urban interface",
  strade: "roads",
  litologia: "lithology",
};

const CLASSI_EN: Record<string, string> = {
  P4: "very high",
  P3: "high",
  P2: "medium",
  P1: "low",
  AA: "attention area",
};

function numero(x: number, decimali: number): string {
  return x.toLocaleString("en-GB", {
    minimumFractionDigits: decimali,
    maximumFractionDigits: decimali,
  });
}

function letturaEn(d: DatoDiBase): string {
  if (d.stato === "non_caricato") return "not loaded";
  if (d.stato === "assente_qui") {
    if (d.colonna === "flood_hazard_norm") return "outside the flood-hazard areas";
    if (d.colonna === "pai_class_norm") return "outside the PAI areas";
    return "no value for this cell";
  }
  const v = d.valore;
  if (typeof v !== "number") return d.colonna === "landuse_code" ? `CORINE class ${v}` : String(v);
  switch (d.colonna) {
    case "iffi_density_500":
      return `${Math.round(v)} mapped landslides within 500 m`;
    case "pai_class_norm":
    case "flood_hazard_norm":
      return d.classe ? `${d.classe} ${CLASSI_EN[d.classe] ?? ""}`.trim() : "class not given";
    case "slope_deg":
      return `slope ${numero(v, 1)}°`;
    case "imperviousness_norm":
      return `${Math.round(v * 100)} % sealed soil`;
    case "wui_proximity_norm":
      return `wildland-urban interface proximity ${numero(v, 2)} of 1`;
    case "distance_to_road_m":
      return v >= 1000 ? `nearest road ${numero(v / 1000, 1)} km` : `nearest road ${Math.round(v)} m`;
    case "litho_weight":
      return d.classe ? `${d.classe} (weight ${numero(v, 2)})` : `lithology weight ${numero(v, 2)}`;
    default:
      return numero(v, 2);
  }
}

export default function DatiDiBase({ dati }: { readonly dati?: readonly DatoDiBase[] }): JSX.Element | null {
  const { lingua } = useLingua();
  const t = T[lingua];
  if (!dati || dati.length === 0) return null;
  return (
    <div className="dati-di-base">
      <span className="eyebrow">{t.titolo}</span>
      <ul>
        {dati.map((d) => {
          const nome = lingua === "en" ? (NOMI_EN[d.id] ?? d.nome) : d.nome;
          const lettura = lingua === "en" ? letturaEn(d) : d.lettura;
          const citazione = d.attribuzione ?? d.fonte;
          return (
            <li key={d.id}>
              <span className="db-nome">{nome}: </span>
              <span className={d.stato === "presente" ? undefined : "is-vuoto"}>{lettura}</span>
              <span className="db-fonte">
                {d.url ? (
                  <a href={d.url} target="_blank" rel="noreferrer">
                    {citazione}
                  </a>
                ) : (
                  citazione
                )}
                {` · ${t.licenza} ${d.licenza}`}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
