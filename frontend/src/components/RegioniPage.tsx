// «Regioni da monitorare»: la pagina dove vive la spiegazione dell'AI.
//
// Prima la spiegazione, che è per regione, compariva nell'ispettore di ogni
// cella: aprire tre comuni del Piemonte voleva dire leggere tre volte lo
// stesso testo, presentato come se parlasse di quel punto. Qui sta una volta
// sola, accanto ai numeri da cui nasce. L'ordine delle regioni lo decidono i
// numeri (classe più alta, adesso o prevista, poi aree in classe alta); l'AI
// racconta una regione, non la sceglie.

import { useEffect, useMemo, useRef, useState } from "react";
import type { JSX } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { defaultApiClient } from "../lib/api-client";
import { BASEMAP_LAYER, BASEMAP_SOURCE } from "../lib/basemap";
import { config } from "../lib/env";
import { COLORE_ALLERTA } from "../lib/overlays";
import { RISK_COLOR_BY_LEVEL, RISK_LABEL_IT_BY_LEVEL, RISK_SCURE } from "../lib/risk-colors";
import type { HazardType, RegioneMonitorata } from "../types";
import { modelloLeggibile } from "./ComeNasce";

const ROUTE = "#/regioni";

export const NOME_PERICOLO: Record<HazardType, string> = {
  landslide: "Frane",
  flood: "Allagamenti",
  wildfire: "Incendi",
};

const LETTERA: Record<HazardType, string> = { landslide: "F", flood: "A", wildfire: "I" };

const ALLERTA = ["nessuna", "gialla", "arancione", "rossa"] as const;

const CAUSA: Record<string, string> = {
  static_susceptibility: "la fragilità del terreno",
  meteo_trigger: "la pioggia",
  seismic_event: "le scosse recenti",
  post_fire_destabilization: "gli incendi recenti",
  human_activity: "l'attività umana",
  pluvial_rain: "la pioggia prevista",
  river_discharge: "la portata dei fiumi",
  hydraulic_susceptibility: "quanto la zona è allagabile",
  fire_weather: "il tempo secco e ventoso",
  fuel_load: "la vegetazione che brucia",
  terrain_slope: "la pendenza",
};

/** La regione chiesta dall'hash: `#/regioni/<aoi>`, o nessuna. */
export function regioneDaHash(hash: string): string | null {
  if (!hash.startsWith(`${ROUTE}/`)) return null;
  return hash.slice(ROUTE.length + 1) || null;
}

function giorno(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { weekday: "short", day: "numeric" });
}

function ora(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function numero(n: number): string {
  return n.toLocaleString("it-IT");
}

/** Le prime frasi di un testo: la scheda non deve diventare un muro. */
export function attacco(testo: string, frasi = 2): string {
  const parti = testo.replace(/\s+/g, " ").match(/[^.!?]+[.!?]+/g) ?? [testo];
  return parti
    .slice(0, frasi)
    .map((p) => p.trim())
    .join(" ");
}

/** Le righe dei numeri: un pericolo compare se ha qualcosa da dire. */
function righePericoli(r: RegioneMonitorata): string[] {
  const out: string[] = [];
  for (const h of ["flood", "landslide", "wildfire"] as HazardType[]) {
    const ora = r.pericoli[h];
    const poi = r.previsto[h];
    const parti: string[] = [];
    if (ora && ora.alte > 0) parti.push(`${numero(ora.alte)} aree in classe alta adesso`);
    else if (ora && ora.moderate > 0) parti.push(`${numero(ora.moderate)} aree moderate adesso`);
    if (poi) {
      parti.push(
        `picco previsto ${RISK_LABEL_IT_BY_LEVEL[poi.classe].toLowerCase()} ${giorno(poi.target_at)}`,
      );
    }
    if (parti.length > 0) out.push(`${NOME_PERICOLO[h]}: ${parti.join(" · ")}`);
  }
  return out;
}

function Scheda({
  r,
  posizione,
  scelta,
  onScegli,
}: {
  r: RegioneMonitorata;
  posizione: number;
  scelta: boolean;
  onScegli: () => void;
}): JSX.Element {
  const p = r.peggiore;
  const righe = righePericoli(r);
  const pericoliConTesto = (Object.keys(r.spiegazioni) as HazardType[]).sort((a) =>
    a === p?.hazard ? -1 : 1,
  );
  return (
    <article
      id={`regione-${r.aoi_id}`}
      className={`reg-scheda ${scelta ? "on" : ""}`}
      aria-labelledby={`regione-${r.aoi_id}-nome`}
    >
      <button type="button" className="reg-testa" onClick={onScegli}>
        <span className="reg-pos mono">{posizione}</span>
        <span className="reg-nome" id={`regione-${r.aoi_id}-nome`}>
          {r.nome}
        </span>
        {p ? (
          <span
            className={`level-chip ${RISK_SCURE.has(p.classe) ? "on-dark" : ""}`}
            style={{ background: RISK_COLOR_BY_LEVEL[p.classe] }}
          >
            {NOME_PERICOLO[p.hazard]} · {RISK_LABEL_IT_BY_LEVEL[p.classe].toLowerCase()}
            {p.previsto ? " previsto" : ""}
          </span>
        ) : (
          <span className="reg-quiete">nessun segnale</span>
        )}
      </button>

      {righe.length > 0 ? (
        <ul className="reg-numeri">
          {righe.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      ) : null}

      <p className="reg-allerta">
        <span
          className="cb-allerta-punto"
          style={{ background: COLORE_ALLERTA[r.allerta?.oggi ?? 0] }}
          aria-hidden
        />
        <strong>Allerta ufficiale</strong>: oggi{" "}
        {r.allerta?.oggi != null ? ALLERTA[r.allerta.oggi] : "n.d."} · domani{" "}
        {r.allerta?.domani != null ? ALLERTA[r.allerta.domani] : "non ancora emessa"}
      </p>

      {r.comuni.length > 0 ? (
        <p className="reg-comuni">
          Comuni da guardare:{" "}
          {r.comuni.map((c, i) => (
            <span key={c.istat_code}>
              {i > 0 ? ", " : ""}
              <strong>{c.nome}</strong>{" "}
              <span className="reg-lettera" title={NOME_PERICOLO[c.hazard]}>
                {LETTERA[c.hazard]}
              </span>
            </span>
          ))}
        </p>
      ) : null}

      {pericoliConTesto.map((h) => {
        const s = r.spiegazioni[h];
        if (!s) return null;
        return (
          <details key={h} className="reg-ai" open={scelta && h === p?.hazard}>
            <summary>
              <span className="reg-ai-titolo">
                {NOME_PERICOLO[h]} · il racconto dell&apos;AI
              </span>
              <span className="reg-ai-firma">
                {modelloLeggibile(s.modello)} · {ora(s.scritta)}
              </span>
              <span className="reg-ai-attacco">{attacco(s.testo)}</span>
            </summary>
            {s.analisi ? (
              <p className="reg-ai-analisi">
                Causa principale: <strong>{CAUSA[s.analisi.driver] ?? s.analisi.driver}</strong>
                {" · "}da tenere d&apos;occhio per {s.analisi.attention_window_hours} ore
              </p>
            ) : null}
            {s.testo.split(/\n{2,}/).map((par) => (
              <p key={par.slice(0, 40)}>{par}</p>
            ))}
          </details>
        );
      })}
    </article>
  );
}

function MappaRegioni({
  regioni,
  scelta,
  onScegli,
}: {
  regioni: RegioneMonitorata[];
  scelta: string | null;
  onScegli: (aoi: string) => void;
}): JSX.Element {
  const contenitore = useRef<HTMLDivElement | null>(null);
  const mappa = useRef<maplibregl.Map | null>(null);
  const onScegliRef = useRef(onScegli);
  onScegliRef.current = onScegli;

  const dati = useMemo(
    () => ({
      aree: {
        type: "FeatureCollection" as const,
        features: regioni.map((r) => ({
          type: "Feature" as const,
          geometry: r.geom,
          properties: {
            aoi_id: r.aoi_id,
            colore: r.peggiore ? RISK_COLOR_BY_LEVEL[r.peggiore.classe] : "#1d2631",
          },
        })),
      },
      etichette: {
        type: "FeatureCollection" as const,
        features: regioni.map((r) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [r.lon, r.lat] },
          properties: {
            testo: r.peggiore && r.peggiore.rango >= 3 ? LETTERA[r.peggiore.hazard] : "",
          },
        })),
      },
    }),
    [regioni],
  );

  useEffect(() => {
    if (!contenitore.current) return;
    const map = new maplibregl.Map({
      container: contenitore.current,
      style: {
        version: 8,
        glyphs: config.mapGlyphsUrl,
        sources: {
          osm: BASEMAP_SOURCE,
          aree: { type: "geojson", data: dati.aree },
          etichette: { type: "geojson", data: dati.etichette },
        },
        layers: [
          BASEMAP_LAYER,
          {
            id: "reg-fill",
            type: "fill",
            source: "aree",
            paint: { "fill-color": ["get", "colore"], "fill-opacity": 0.7 },
          },
          {
            id: "reg-line",
            type: "line",
            source: "aree",
            paint: { "line-color": "#0a0e13", "line-width": 1 },
          },
          {
            id: "reg-scelta",
            type: "line",
            source: "aree",
            paint: { "line-color": "#ffffff", "line-width": 2.5 },
            filter: ["==", ["get", "aoi_id"], ""],
          },
          {
            id: "reg-lettera",
            type: "symbol",
            source: "etichette",
            layout: {
              "text-field": ["get", "testo"],
              "text-font": ["Open Sans Regular"],
              "text-size": 14,
            },
            paint: {
              "text-color": "#ffffff",
              "text-halo-color": "#0a0e13",
              "text-halo-width": 1.6,
            },
          },
        ],
      },
      center: [12.6, 41.9],
      zoom: 4.6,
    });
    map.on("click", "reg-fill", (e: maplibregl.MapLayerMouseEvent) => {
      const aoi = e.features?.[0]?.properties?.["aoi_id"];
      if (typeof aoi === "string") onScegliRef.current(aoi);
    });
    mappa.current = map;
    return () => {
      map.remove();
      mappa.current = null;
    };
  }, [dati]);

  useEffect(() => {
    mappa.current?.setFilter("reg-scelta", ["==", ["get", "aoi_id"], scelta ?? ""]);
  }, [scelta]);

  return (
    <div
      ref={contenitore}
      className="reg-mappa"
      role="img"
      aria-label="Mappa delle regioni colorate per pericolo stimato"
    />
  );
}

export default function RegioniPage(): JSX.Element {
  const [regioni, setRegioni] = useState<RegioneMonitorata[] | null>(null);
  const [errore, setErrore] = useState(false);
  const [scelta, setScelta] = useState<string | null>(() => regioneDaHash(window.location.hash));

  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getRegioni(ctrl.signal)
      .then((r) => setRegioni(r.regioni))
      .catch(() => {
        if (!ctrl.signal.aborted) setErrore(true);
      });
    return () => ctrl.abort();
  }, []);

  useEffect(() => {
    const onHash = (): void => setScelta(regioneDaHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (scelta && regioni) {
      document.getElementById(`regione-${scelta}`)?.scrollIntoView({ block: "start" });
    }
  }, [scelta, regioni]);

  const scegli = (aoi: string): void => {
    window.location.hash = `${ROUTE}/${aoi}`;
  };

  return (
    <div className="regioni">
      <header className="reg-intestazione">
        <p className="exp-eyebrow">Sala operativa</p>
        <h2>Regioni da monitorare</h2>
        <p className="reg-sotto">
          Le regioni in ordine di pericolo stimato, adesso e nelle prossime 72 ore. L&apos;ordine
          lo decidono i numeri; il racconto di ogni regione è scritto dall&apos;AI e non cambia
          nessun numero. I colori sono il pericolo stimato da Limen, non l&apos;allerta: quella
          ufficiale è nella riga di ogni regione.
        </p>
      </header>
      {errore ? (
        <p role="alert">Il riepilogo delle regioni non è disponibile in questo momento.</p>
      ) : regioni === null ? (
        <p aria-busy="true">Caricamento delle regioni…</p>
      ) : (
        <div className="reg-corpo">
          <MappaRegioni regioni={regioni} scelta={scelta} onScegli={scegli} />
          <div className="reg-lista">
            {regioni.map((r, i) => (
              <Scheda
                key={r.aoi_id}
                r={r}
                posizione={i + 1}
                scelta={r.aoi_id === scelta}
                onScegli={() => scegli(r.aoi_id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
