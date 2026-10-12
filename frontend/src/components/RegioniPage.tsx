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
import { testi, useLocale, useTesti } from "../lib/i18n";
import { RISK_COLOR_BY_LEVEL, RISK_SCURE, useEtichetteRischio } from "../lib/risk-colors";
import type { HazardType, RegioneMonitorata, RiskLevel } from "../types";

const ROUTE = "#/regioni";

const T = testi(
  {
    pericolo: { landslide: "Frane", flood: "Allagamenti", wildfire: "Incendi" } as Record<
      HazardType,
      string
    >,
    lettera: { landslide: "F", flood: "A", wildfire: "I" } as Record<HazardType, string>,
    allerta: ["nessuna", "gialla", "arancione", "rossa"],
    causa: {
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
    } as Record<string, string>,
    alteAdesso: (n: string) => `${n} aree in classe alta adesso`,
    moderateAdesso: (n: string) => `${n} aree moderate adesso`,
    piccoPrevisto: (classe: string, quando: string) => `picco previsto ${classe} ${quando}`,
    previsto: " previsto",
    nessunSegnale: "nessun segnale",
    allertaUfficiale: "Allerta ufficiale",
    oggi: "oggi",
    domani: "domani",
    nd: "n.d.",
    nonEmessa: "non ancora emessa",
    pdfRegione: "PDF di questa regione",
    comuniDaGuardare: "Comuni da guardare:",
    raccontoAi: "il racconto dell'AI",
    causaPrincipale: "Causa principale:",
    finestra: (ore: number) => `da tenere d'occhio per ${ore} ore`,
    mappa: "Mappa delle regioni colorate per pericolo stimato",
    eyebrow: "Sala operativa",
    titolo: "Regioni da monitorare",
    scarica: "Scarica il rapporto (PDF)",
    marchio: "Racconti scritti con Claude, il modello di Anthropic",
    sotto:
      "Le regioni in ordine di pericolo stimato, adesso e nelle prossime 72 ore. L'ordine " +
      "lo decidono i numeri; il racconto di ogni regione è scritto dall'AI e non cambia " +
      "nessun numero. I colori sono il pericolo stimato da Limen, non l'allerta: quella " +
      "ufficiale è nella riga di ogni regione.",
    errore: "Il riepilogo delle regioni non è disponibile in questo momento.",
    caricamento: "Caricamento delle regioni…",
  },
  {
    pericolo: { landslide: "Landslides", flood: "Floods", wildfire: "Wildfires" },
    lettera: { landslide: "L", flood: "F", wildfire: "W" },
    allerta: ["none", "yellow", "orange", "red"],
    causa: {
      static_susceptibility: "how fragile the ground is",
      meteo_trigger: "rainfall",
      seismic_event: "recent earthquakes",
      post_fire_destabilization: "recent wildfires",
      human_activity: "human activity",
      pluvial_rain: "forecast rainfall",
      river_discharge: "river discharge",
      hydraulic_susceptibility: "how flood-prone the area is",
      fire_weather: "dry, windy weather",
      fuel_load: "burnable vegetation",
      terrain_slope: "the slope",
    },
    alteAdesso: (n: string) => `${n} areas in the high class now`,
    moderateAdesso: (n: string) => `${n} moderate areas now`,
    piccoPrevisto: (classe: string, quando: string) => `forecast peak ${classe} ${quando}`,
    previsto: " forecast",
    nessunSegnale: "no signal",
    allertaUfficiale: "Official warning",
    oggi: "today",
    domani: "tomorrow",
    nd: "n/a",
    nonEmessa: "not issued yet",
    pdfRegione: "PDF for this region",
    comuniDaGuardare: "Municipalities to watch:",
    raccontoAi: "the AI summary",
    causaPrincipale: "Main driver:",
    finestra: (ore: number) => `worth watching for ${ore} hours`,
    mappa: "Map of the regions coloured by estimated hazard",
    eyebrow: "Operations room",
    titolo: "Regions to watch",
    scarica: "Download the report (PDF)",
    marchio: "Summaries written with Claude, Anthropic's model",
    sotto:
      "Regions ordered by estimated hazard, now and over the next 72 hours. The order " +
      "is set by the numbers; each region's summary is written by AI and changes no " +
      "number. The colours are the hazard estimated by Limen, not the warning: the " +
      "official one is on each region's row.",
    errore: "The regional summary is not available right now.",
    caricamento: "Loading regions…",
  },
);

type Testi = (typeof T)["it"];

/** La regione chiesta dall'hash: `#/regioni/<aoi>`, o nessuna. */
export function regioneDaHash(hash: string): string | null {
  if (!hash.startsWith(`${ROUTE}/`)) return null;
  return hash.slice(ROUTE.length + 1) || null;
}

function giorno(iso: string, loc: string): string {
  return new Date(iso).toLocaleDateString(loc, { weekday: "short", day: "numeric" });
}

function ora(iso: string, loc: string): string {
  return new Date(iso).toLocaleString(loc, {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function numero(n: number, loc: string): string {
  return n.toLocaleString(loc);
}

/** Le prime frasi di un testo: la scheda non deve diventare un muro. */
export function attacco(testo: string, frasi = 2): string {
  // Una frase finisce su . ! ? seguiti da spazio e maiuscola: il punto delle
  // migliaia («23.214 aree») non chiude niente, e prima troncava il testo a
  // «Su 23.».
  return testo
    .replace(/\s+/g, " ")
    .trim()
    .split(/(?<=[.!?])\s+(?=[A-ZÀ-Ý«"])/)
    .slice(0, frasi)
    .join(" ");
}

/** Le righe dei numeri: un pericolo compare se ha qualcosa da dire. */
function righePericoli(
  r: RegioneMonitorata,
  t: Testi,
  etichette: Record<RiskLevel, string>,
  loc: string,
): { hazard: HazardType; testo: string }[] {
  const out: { hazard: HazardType; testo: string }[] = [];
  for (const h of ["flood", "landslide", "wildfire"] as HazardType[]) {
    const ora = r.pericoli[h];
    const poi = r.previsto[h];
    const parti: string[] = [];
    if (ora && ora.alte > 0) parti.push(t.alteAdesso(numero(ora.alte, loc)));
    else if (ora && ora.moderate > 0) parti.push(t.moderateAdesso(numero(ora.moderate, loc)));
    if (poi) {
      parti.push(
        t.piccoPrevisto(etichette[poi.classe].toLowerCase(), giorno(poi.target_at, loc)),
      );
    }
    if (parti.length > 0) out.push({ hazard: h, testo: parti.join(" · ") });
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
  const t = useTesti(T);
  const loc = useLocale();
  const etichette = useEtichetteRischio();
  const p = r.peggiore;
  const righe = righePericoli(r, t, etichette, loc);
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
            {t.pericolo[p.hazard]} · {etichette[p.classe].toLowerCase()}
            {p.previsto ? t.previsto : ""}
          </span>
        ) : (
          <span className="reg-quiete">{t.nessunSegnale}</span>
        )}
      </button>

      {righe.length > 0 ? (
        <ul className="reg-numeri">
          {righe.map((riga) => (
            <li key={riga.hazard}>
              <span className="reg-lettera" aria-hidden>
                {t.lettera[riga.hazard]}
              </span>
              <strong>{t.pericolo[riga.hazard]}</strong> {riga.testo}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="reg-allerta">
        <span
          className="cb-allerta-punto"
          style={{ background: COLORE_ALLERTA[r.allerta?.oggi ?? 0] }}
          aria-hidden
        />
        <strong>{t.allertaUfficiale}</strong>: {t.oggi}{" "}
        {r.allerta?.oggi != null ? t.allerta[r.allerta.oggi] : t.nd} · {t.domani}{" "}
        {r.allerta?.domani != null ? t.allerta[r.allerta.domani] : t.nonEmessa}
      </p>

      <a
        className="reg-pdf-regione"
        href={`${config.apiUrl.replace(/\/+$/, "")}/api/regioni/rapporto.pdf?aoi=${encodeURIComponent(r.aoi_id)}`}
        download
      >
        {t.pdfRegione}
      </a>
      {r.comuni.length > 0 ? (
        <p className="reg-comuni">
          {t.comuniDaGuardare}{" "}
          {r.comuni.map((c, i) => (
            <span key={c.istat_code}>
              {i > 0 ? ", " : ""}
              <strong>{c.nome}</strong>{" "}
              <span className="reg-lettera" title={t.pericolo[c.hazard]}>
                {t.lettera[c.hazard]}
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
                {t.pericolo[h]} · {t.raccontoAi} · {ora(s.scritta, loc)}
              </span>
              <span className="reg-ai-attacco">{attacco(s.testo)}</span>
            </summary>
            {s.analisi ? (
              <p className="reg-ai-analisi">
                {t.causaPrincipale}{" "}
                <strong>{t.causa[s.analisi.driver] ?? s.analisi.driver}</strong>
                {" · "}
                {t.finestra(s.analisi.attention_window_hours)}
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
  const t = useTesti(T);
  const contenitore = useRef<HTMLDivElement | null>(null);
  const mappa = useRef<maplibregl.Map | null>(null);
  const onScegliRef = useRef(onScegli);
  onScegliRef.current = onScegli;
  const sceltaRef = useRef(scelta);
  sceltaRef.current = scelta;

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
            testo: r.peggiore && r.peggiore.rango >= 3 ? t.lettera[r.peggiore.hazard] : "",
          },
        })),
      },
    }),
    [regioni, t],
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
            filter: ["==", ["get", "aoi_id"], sceltaRef.current ?? ""],
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

  // Solo a stile caricato: prima MapLibre lancia «Style is not done
  // loading», e un'eccezione in un effetto smontava l'intera applicazione —
  // la pagina restava nera. Prima del caricamento basta il filtro scritto
  // nello stile alla creazione.
  useEffect(() => {
    const map = mappa.current;
    if (!map) return;
    const applica = (): void => {
      map.setFilter("reg-scelta", ["==", ["get", "aoi_id"], scelta ?? ""]);
    };
    if (map.isStyleLoaded()) applica();
    else map.once("load", applica);
  }, [scelta]);

  return (
    <div
      ref={contenitore}
      className="reg-mappa"
      role="img"
      aria-label={t.mappa}
    />
  );
}

export default function RegioniPage(): JSX.Element {
  const t = useTesti(T);
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
        <p className="exp-eyebrow">{t.eyebrow}</p>
        <div className="reg-titolo">
          <h2>{t.titolo}</h2>
          <a
            className="reg-pdf"
            href={`${config.apiUrl.replace(/\/+$/, "")}/api/regioni/rapporto.pdf`}
            download
          >
            {t.scarica}
          </a>
          <span className="reg-ai-marchio">{t.marchio}</span>
        </div>
        <p className="reg-sotto">{t.sotto}</p>
      </header>
      {errore ? (
        <p role="alert">{t.errore}</p>
      ) : regioni === null ? (
        <p aria-busy="true">{t.caricamento}</p>
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
