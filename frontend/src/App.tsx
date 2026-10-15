import { useCallback, useEffect, useRef, useState } from "react";
import type { JSX } from "react";
import type maplibregl from "maplibre-gl";
import { Popover, Switch, UnstyledButton } from "@mantine/core";

import CellPopup from "./components/CellPopup";
import ComuniBoard from "./components/ComuniBoard";
import ErroreLocale from "./components/ErroreLocale";
import GuidaPage from "./components/GuidaPage";
import RegioniPage from "./components/RegioniPage";
import { defaultApiClient } from "./lib/api-client";
import { RISK_TEXT_BY_LEVEL, useEtichetteRischio } from "./lib/risk-colors";
import { LINGUE, testi, useLingua, useLocale, useTesti } from "./lib/i18n";
import type {
  CellSelection,
  ComuneCell,
  ComuneGeometry,
  ComuneRisk,
  RiskLevel,
} from "./types";
import FreshnessBadge from "./components/FreshnessBadge";
import HomePage from "./components/HomePage";
import IntegrationsPage from "./components/IntegrationsPage";
import SensoriPage from "./components/SensoriPage";
import LegendPanel from "./components/LegendPanel";
import NationalStrip from "./components/NationalStrip";
import OverlayControl from "./components/OverlayControl";
import PrevisioneTesta from "./components/PrevisioneTesta";
import RicercaComune from "./components/RicercaComune";
import RiskMap from "./components/RiskMap";
import Timeline from "./components/Timeline";
import SciencePage from "./components/SciencePage";
import ShadowDiagnosticsPage from "./components/ShadowDiagnosticsPage";
import ShadowPanel from "./components/ShadowPanel";
import VerifichePage from "./components/VerifichePage";
import { useForecastSchedule } from "./lib/forecast-schedule";
import { useBuyMeACoffee } from "./lib/buymeacoffee";
import { cellaDaHash } from "./lib/link-cella";
import { useHazard, useNomePericolo } from "./lib/hazard";
import { OVERLAYS, testoOverlay } from "./lib/overlays";

type Page =
  | "home"
  | "dashboard"
  | "guida"
  | "regioni"
  | "science"
  | "shadow"
  | "integrations"
  | "sensori"
  | "verifiche";

function pageFromHash(): Page {
  // La guida ha una sotto-rotta per sezione, quindi il confronto esatto non
  // basta. La vecchia documentazione in sei pagine è confluita nella guida:
  // i suoi link condivisi aprono quella.
  // La query dopo la rotta (`#/dashboard?cella=…`) non cambia la pagina.
  const hash = window.location.hash.split("?")[0] ?? "";
  if (hash.startsWith("#/come-funziona") || hash.startsWith("#/documentazione")) {
    return "guida";
  }
  if (hash.startsWith("#/regioni")) {
    return "regioni";
  }
  if (hash.startsWith("#/verifiche")) {
    return "verifiche";
  }
  if (hash.startsWith("#/integrazioni")) {
    return "integrations";
  }
  if (hash.startsWith("#/sensori")) {
    return "sensori";
  }
  switch (hash) {
    case "#/dashboard":
    case "#/italia": // vecchio deep-link: il quadro nazionale vive in dashboard
      return "dashboard";
    case "#/modello":
      return "science";
    case "#/diagnostica-ml":
      return "shadow";
    // Un hash sconosciuto — compresi i vecchi #/accedi, #/registrati,
    // #/verifica e #/admin — va sulla home: la mappa è pubblica e non c'è
    // più niente dietro cui mettere una porta.
    default:
      return "home";
  }
}

const T = testi(
  {
    livelloAttivo: "Livello attivo",
    tutti: "Tutti i pericoli",
    rischio: (nome: string) => `Rischio ${nome.toLowerCase()}`,
    fra: (h: number) => `fra ${h} h`,
    prossime72: "prossime 72 h",
    adesso: "adesso",
    notaFuturo: "pericolo stimato, non allerta · previsione per cella, solo sopra soglia, da zoom 7",
    notaLettera: " · la lettera dice quale pericolo (A, F, I)",
    nonCalcolata: (nomi: string) => ` · ${nomi}: previsione non calcolata`,
    notaMulti:
      "pericolo stimato, non allerta · il peggiore in ogni cella, la lettera dice quale (A allagamento, F frana, I incendio) · gli allagamenti guardano la pioggia delle prossime 72 h",
    notaFlood: "calcolata sulla pioggia prevista, non su quella che cade ora",
    previsto: (h: number, quando: string) => `Previsto a +${h} h · ${quando}`,
    valoriAdesso: "Qui sotto i valori di adesso.",
    pannello: "Pannello laterale",
    soloSoglia: "Solo sopra soglia",
    livelliContesto: "Livelli di contesto",
    livelli: "Livelli",
    nessuno: "nessuno",
    evidenziato: "evidenziato",
    togliEvidenziazione: "Togli l'evidenziazione del comune",
    navigazione: "Navigazione",
    tag: "soglia",
    navRegioni: "Regioni da monitorare",
    navVerifiche: "Verifiche",
    navGuida: "Come funziona",
    navIntegrazioni: "Integrazioni",
    navSensori: "Sensori",
    lingua: "Lingua",
    nomeLingua: { it: "Italiano", en: "English" },
    soloItaliano: "",
  },
  {
    livelloAttivo: "Active layer",
    tutti: "All hazards",
    rischio: (nome: string) => `${nome} risk`,
    fra: (h: number) => `in ${h} h`,
    prossime72: "next 72 h",
    adesso: "now",
    notaFuturo: "estimated hazard, not a warning · per-cell forecast, above threshold only, from zoom 7",
    notaLettera: " · the letter tells which hazard (F, L, W)",
    nonCalcolata: (nomi: string) => ` · ${nomi}: forecast not computed`,
    notaMulti:
      "estimated hazard, not a warning · the worst in each cell, the letter tells which (F flood, L landslide, W wildfire) · floods look at the rain of the next 72 h",
    notaFlood: "computed on the forecast rain, not on the rain falling now",
    previsto: (h: number, quando: string) => `Forecast at +${h} h · ${quando}`,
    valoriAdesso: "Below, the values for now.",
    pannello: "Side panel",
    soloSoglia: "Above threshold only",
    livelliContesto: "Context layers",
    livelli: "Layers",
    nessuno: "none",
    evidenziato: "highlighted",
    togliEvidenziazione: "Remove the municipality highlight",
    navigazione: "Navigation",
    tag: "threshold",
    navRegioni: "Regions to watch",
    navVerifiche: "Checks",
    navGuida: "How it works",
    navIntegrazioni: "Integrations",
    navSensori: "Sensors",
    lingua: "Language",
    nomeLingua: { it: "Italiano", en: "English" },
    soloItaliano:
      "This page is available in Italian only for now. The English version is on its way.",
  },
);

/** Le pagine lunghe non ancora tradotte: in inglese lo si dice in testa,
 *  invece di lasciare il lettore davanti a un muro d'italiano senza ragione. */
function SoloItaliano(): JSX.Element | null {
  const t = useTesti(T);
  return t.soloItaliano ? (
    <p className="nota-lingua" role="note" lang="en">
      {t.soloItaliano}
    </p>
  ) : null;
}

/** Il selettore della lingua in testata: due bottoni, la lingua attiva
 *  segnata. Due sole lingue non meritano un menu a tendina. */
function SelettoreLingua(): JSX.Element {
  const { lingua, imposta } = useLingua();
  const t = useTesti(T);
  return (
    <div className="lingua-switch" role="group" aria-label={t.lingua}>
      {LINGUE.map((l) => (
        <button
          key={l}
          type="button"
          lang={l}
          className={l === lingua ? "on" : ""}
          aria-pressed={l === lingua}
          aria-label={t.nomeLingua[l]}
          onClick={() => imposta(l)}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

/** Il riquadro «Livello attivo»: cosa colora la mappa, detto a parole. Con
 *  la vista d'insieme come default, senza questa riga non si saprebbe se il
 *  rosso di una cella è un incendio o una frana. */
function LivelloAttivo({ orizzonte }: { orizzonte: number }): JSX.Element {
  const { multi, selected, available } = useHazard();
  const t = useTesti(T);
  const nomePericolo = useNomePericolo();
  const corse = useForecastSchedule()?.cells.last_run_by_hazard ?? {};
  const nome = nomePericolo(selected);
  // Nella vista d'insieme al futuro mancano i pericoli senza una corsa
  // previsionale: va detto, o il loro silenzio si leggerebbe come «sotto
  // soglia».
  const senza = available
    .filter((h) => !(h.hazard in corse))
    .map((h) => nomePericolo(h.hazard).toLowerCase());
  return (
    <div className="map-testa" aria-live="polite">
      <span className="map-testa-occhiello">{t.livelloAttivo}</span>
      <span className="map-testa-titolo">
        {multi ? t.tutti : t.rischio(nome)} ·{" "}
        {orizzonte > 0
          ? t.fra(orizzonte)
          : !multi && selected === "flood"
            ? t.prossime72
            : t.adesso}
      </span>
      {orizzonte > 0 ? (
        <span className="map-testa-nota">
          {t.notaFuturo}
          {multi ? t.notaLettera : ""}
          {multi && senza.length > 0 ? t.nonCalcolata(senza.join(", ")) : ""}
        </span>
      ) : multi ? (
        <span className="map-testa-nota">{t.notaMulti}</span>
      ) : selected === "flood" ? (
        // L'alluvione si calcola sulla pioggia attesa, non su quella che
        // cade: «adesso» faceva leggere 0,80 su Trieste sotto il sole.
        <span className="map-testa-nota">{t.notaFlood}</span>
      ) : null}
    </div>
  );
}

/** Larghezza dell'ispettore: serve a decidere se aprirlo a destra o a
 *  sinistra della cella. Lo stesso valore sta in styles.css. */
const LARGHEZZA_ISPETTORE = 360;

/** Dove aprire l'ispettore, accanto alla cella e dentro la mappa. */
export function posizioneIspettore(
  punto: { x: number; y: number },
  mappa: { width: number; height: number },
): { left: number; top: number; maxHeight: number } {
  const margine = 16;
  const scarto = 28;
  // Almeno questo spazio sotto: il popup è lungo, e aprirlo a filo del
  // fondo lasciava fuori proprio le barre delle componenti.
  const spazioMinimo = 480;
  const aDestra = punto.x + scarto + LARGHEZZA_ISPETTORE + margine <= mappa.width;
  const left = aDestra
    ? punto.x + scarto
    : Math.max(margine, punto.x - scarto - LARGHEZZA_ISPETTORE);
  const top = Math.min(
    Math.max(margine, punto.y - 120),
    Math.max(margine, mappa.height - margine - spazioMinimo),
  );
  return { left, top, maxHeight: mappa.height - top - margine };
}

/** Ciò che la tile della previsione dice della cella cliccata. */
interface CellaPrevista {
  orizzonte: number;
  score: number;
  level: RiskLevel;
  hazard: string;
  target: string | null;
}

/** In testa all'ispettore quando si guarda il futuro: il valore previsto
 *  della cella, e la dichiarazione che il resto sotto è di adesso. Senza,
 *  una cella alta a +48 h apriva i numeri bassi di oggi senza dirlo. */
function TestaPrevista({ p }: { p: CellaPrevista }): JSX.Element {
  const t = useTesti(T);
  const loc = useLocale();
  const etichette = useEtichetteRischio();
  const nome = useNomePericolo()(p.hazard).toLowerCase();
  const quando = p.target
    ? new Date(p.target).toLocaleString(loc, { weekday: "short", hour: "2-digit", minute: "2-digit" })
    : `+${p.orizzonte} h`;
  return (
    <div className="ispettore-previsto" role="note">
      <span className="eyebrow">{t.previsto(p.orizzonte, quando)}</span>
      <span>
        <strong className="mono" style={{ color: RISK_TEXT_BY_LEVEL[p.level] }}>
          {p.score.toLocaleString(loc, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </strong>{" "}
        {etichette[p.level].toLowerCase()} · {nome}
      </span>
      <span className="ispettore-previsto-nota">{t.valoriAdesso}</span>
    </div>
  );
}

export function App(): JSX.Element {
  const { view } = useHazard();
  const t = useTesti(T);
  const { lingua } = useLingua();
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [selected, setSelected] = useState<(CellSelection & { previsto?: CellaPrevista }) | null>(
    null,
  );
  const [evidenziato, setEvidenziato] = useState<ComuneGeometry | null>(null);
  // Qui e non nel pannello: la mappa si ricostruisce a ogni cambio di
  // pericolo, e deve poter riaccendere i livelli che erano accesi.
  const [overlayAttivi, setOverlayAttivi] = useState<ReadonlySet<string>>(() => new Set());
  const toggleOverlay = useCallback((id: string) => {
    setOverlayAttivi((prima) => {
      const dopo = new Set(prima);
      if (dopo.has(id)) dopo.delete(id);
      else dopo.add(id);
      return dopo;
    });
  }, []);
  const [page, setPage] = useState<Page>(pageFromHash);
  const [cerca, setCerca] = useState("");
  // Acceso di default, come nel design: con un quarto d'Italia in classe
  // bassa la mappa era una coperta, e si cercava il moderato sotto di essa.
  const [soloSoglia, setSoloSoglia] = useState(true);
  const [orizzonte, setOrizzonte] = useState(0);
  const [puntoIspettore, setPuntoIspettore] = useState<{
    left: number;
    top: number;
    maxHeight: number;
  } | null>(null);

  useBuyMeACoffee(page !== "dashboard");

  const [cellaLink, setCellaLink] = useState(() => cellaDaHash(window.location.hash));

  useEffect(() => {
    const onHash = (): void => {
      setPage(pageFromHash());
      setCellaLink(cellaDaHash(window.location.hash));
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const onMapClick = useCallback(
    (cellId: string, lngLat?: { lng: number; lat: number }, p?: Record<string, unknown>) => {
      // Il punto cliccato, non il centro della cella: l'ispettore si apre lì
      // accanto, dove l'occhio già sta.
      const previsto: CellaPrevista | undefined =
        orizzonte > 0 && p && typeof p["risk_score"] === "number"
          ? {
              orizzonte,
              score: p["risk_score"],
              level: p["risk_level"] as RiskLevel,
              hazard: String(p["worst_hazard"] ?? ""),
              target: typeof p["target_at"] === "string" ? p["target_at"] : null,
            }
          : undefined;
      setSelected({ cellId, lon: lngLat?.lng ?? null, lat: lngLat?.lat ?? null, previsto });
    },
    [orizzonte],
  );

  // L'ispettore segue la cella mentre la mappa si muove: aperto in un
  // angolo fisso, il numero restava lontano dal posto di cui parlava.
  useEffect(() => {
    const map = mapRef.current;
    const lon = selected?.lon;
    const lat = selected?.lat;
    if (!map || lon == null || lat == null) {
      setPuntoIspettore(null);
      return;
    }
    const aggiorna = (): void => {
      const p = map.project([lon, lat]);
      const c = map.getContainer();
      setPuntoIspettore(posizioneIspettore(p, { width: c.clientWidth, height: c.clientHeight }));
    };
    aggiorna();
    map.on("move", aggiorna);
    return () => {
      map.off("move", aggiorna);
    };
    // `view`: la mappa si ricostruisce a ogni cambio di pericolo, e
    // l'ascoltatore resterebbe attaccato a quella vecchia. L'effetto della
    // mappa, che è un figlio, gira prima di questo: mapRef è già la nuova.
  }, [selected?.lon, selected?.lat, view, orizzonte]);


  // Dalla colonna alla mappa. Una classifica geografica su cui si clicca e
  // non succede niente è una lista di nomi: il posto è metà dell'informazione.
  const vaiAlComune = useCallback((c: ComuneRisk) => {
    // La cella aperta prima resta di un altro posto: con il popup di una
    // cella del Friuli aperto su Montegiordano, il numero non era di qui.
    setSelected(null);
    // Subito verso il centro, poi il confine vero quando arriva: senza, il
    // clic aspetterebbe la rete prima di muovere la mappa.
    mapRef.current?.flyTo({ center: [c.lon, c.lat], zoom: 11, duration: 700 });
    defaultApiClient
      .getComuneGeometry(c.istat_code)
      .then((g) => {
        setEvidenziato(g);
        // Il comune intero, non uno zoom fisso: a 11 Roma non ci stava e
        // Atrani era un puntino. Il bordo con la griglia a 1 km è ciò che
        // dice dove finisce un comune e comincia il vicino.
        mapRef.current?.fitBounds(
          [
            [g.bbox[0], g.bbox[1]],
            [g.bbox[2], g.bbox[3]],
          ],
          { padding: 60, maxZoom: 14, duration: 900 },
        );
      })
      .catch(() => {
        // Senza confine resta il volo verso il centro: meno chiaro, non rotto.
      });
  }, []);

  // Invio nella ricerca: la mappa va sul primo comune trovato.
  const cercaEVai = useCallback(
    (termine: string) => {
      if (page !== "dashboard") window.location.hash = "#/dashboard";
      defaultApiClient
        .getTopComuni(undefined, 1, undefined, termine)
        .then((r) => {
          const primo = r.comuni[0];
          if (primo) vaiAlComune(primo);
        })
        .catch(() => {
          // Senza risposta resta la lista filtrata: si sceglie a mano.
        });
    },
    [page, vaiAlComune],
  );

  const vaiAllaCella = useCallback((c: ComuneCell) => {
    mapRef.current?.flyTo({ center: [c.lon, c.lat], zoom: 13, duration: 700 });
    setSelected({ cellId: c.cell_id, lon: c.lon, lat: c.lat });
  }, []);

  useEffect(() => {
    if (page !== "dashboard" || !cellaLink) return;
    mapRef.current?.flyTo({ center: [cellaLink.lon, cellaLink.lat], zoom: 13, duration: 700 });
    setSelected({ cellId: cellaLink.cellId, lon: cellaLink.lon, lat: cellaLink.lat });
  }, [page, cellaLink]);

  const attiviNomi = OVERLAYS.filter((o) => overlayAttivi.has(o.id)).map(
    (o) => testoOverlay(o, lingua).label,
  );

  const dashboard = (
    <>
      <aside className="sidebar" aria-label={t.pannello}>
        <NationalStrip />
        <PrevisioneTesta />
        <ComuniBoard onComune={vaiAlComune} onCella={vaiAllaCella} cerca={cerca} />
        <ShadowPanel />
      </aside>
      <div className="map-area">
        <RiskMap
          mapRef={mapRef}
          onCellClick={onMapClick}
          selectedCellId={selected?.cellId ?? null}
          comuneEvidenziato={evidenziato}
          overlayAttivi={overlayAttivi}
          soloSopraSoglia={soloSoglia}
          orizzonte={orizzonte}
          geolocalizza={!cellaLink}
        />
        <LivelloAttivo orizzonte={orizzonte} />
        <Timeline orizzonte={orizzonte} onCambia={setOrizzonte} />
        <div className="map-strumenti">
          <UnstyledButton
            className="map-bottone"
            onClick={() => setSoloSoglia((v) => !v)}
            aria-pressed={soloSoglia}
          >
            <Switch
              size="xs"
              checked={soloSoglia}
              readOnly
              tabIndex={-1}
              aria-hidden
              styles={{ root: { pointerEvents: "none" } }}
            />
            {t.soloSoglia}
          </UnstyledButton>
          <Popover position="bottom-end" width={300} shadow="md" withinPortal={false}>
            <Popover.Target>
              <UnstyledButton className="map-bottone" aria-label={t.livelliContesto}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path d="M12 3l9 5-9 5-9-5 9-5z" stroke="currentColor" strokeWidth="2" />
                  <path d="M3 13l9 5 9-5" stroke="currentColor" strokeWidth="2" />
                </svg>
                {t.livelli}
                <span className="map-conta mono">
                  {attiviNomi.length === 0 ? t.nessuno : attiviNomi.length}
                </span>
              </UnstyledButton>
            </Popover.Target>
            <Popover.Dropdown className="map-livelli">
              <OverlayControl attivi={overlayAttivi} onToggle={toggleOverlay} />
            </Popover.Dropdown>
          </Popover>
        </div>
        {evidenziato ? (
          <div className="comune-chip" role="status">
            <span>
              <strong>{String(evidenziato.properties?.["name"] ?? "")}</strong> {t.evidenziato}
            </span>
            <button
              type="button"
              aria-label={t.togliEvidenziazione}
              onClick={() => setEvidenziato(null)}
            >
              ✕
            </button>
          </div>
        ) : null}
        <div className="map-legenda">
          <LegendPanel />
        </div>
        {selected ? (
          <div
            className={`ispettore ${puntoIspettore ? "" : "is-angolo"}`}
            style={puntoIspettore ?? undefined}
          >
            {selected.previsto ? <TestaPrevista p={selected.previsto} /> : null}
            <CellPopup
              cellId={selected.cellId}
              lon={selected.lon}
              lat={selected.lat}
              priority={selected.priority}
              exposure={selected.exposure}
              place={selected.place}
              onDismiss={() => setSelected(null)}
            />
          </div>
        ) : null}
      </div>
    </>
  );

  return (
    <div className={`app-shell ${page === "home" ? "is-home" : ""}`}>
      <header className="app-header">
        <a className="brand" href="#/">
          <img src="/logo.png" alt="" className="app-logo" height={36} />
          <span className="brand-name">Limen</span>
          <span className="brand-tag">{t.tag}</span>
        </a>
        <nav className="app-nav" aria-label={t.navigazione}>
          <a href="#/" className={page === "home" ? "on" : ""}>
            Home
          </a>
          <a href="#/dashboard" className={page === "dashboard" ? "on" : ""}>
            Dashboard
          </a>
          <a href="#/regioni" className={page === "regioni" ? "on" : ""}>
            {t.navRegioni}
          </a>
          <a href="#/verifiche" className={page === "verifiche" ? "on" : ""}>
            {t.navVerifiche}
          </a>
          <a
            href="#/come-funziona"
            className={page === "guida" || page === "science" || page === "shadow" ? "on" : ""}
          >
            {t.navGuida}
          </a>
          <a href="#/integrazioni" className={page === "integrations" ? "on" : ""}>
            {t.navIntegrazioni}
          </a>
          <a href="#/sensori" className={page === "sensori" ? "on" : ""}>
            {t.navSensori}
          </a>
        </nav>
        <div className="header-spazio" />
        <RicercaComune
          valore={cerca}
          onCambia={(v) => {
            setCerca(v);
            // Si cerca un comune per vederlo: la lista è sulla dashboard.
            if (v && page !== "dashboard") window.location.hash = "#/dashboard";
          }}
          onInvio={cercaEVai}
        />
        <FreshnessBadge />
        <SelettoreLingua />
      </header>

      <ErroreLocale chiave={page}>
        {page === "home" ? (
          <HomePage />
        ) : page === "regioni" ? (
          <div className="explainer-area">
            <RegioniPage />
          </div>
        ) : page === "verifiche" ? (
          <div className="explainer-area">
            <VerifichePage />
          </div>
        ) : page === "guida" ? (
          <div className="explainer-area">
            <SoloItaliano />
            <GuidaPage />
          </div>
        ) : page === "science" ? (
          <div className="explainer-area">
            <SoloItaliano />
            <SciencePage />
          </div>
        ) : page === "shadow" ? (
          <div className="explainer-area">
            <ShadowDiagnosticsPage />
          </div>
        ) : page === "integrations" ? (
          <div className="explainer-area">
            <SoloItaliano />
            <IntegrationsPage />
          </div>
        ) : page === "sensori" ? (
          <div className="explainer-area">
            <SensoriPage />
          </div>
        ) : (
          dashboard
        )}
      </ErroreLocale>
    </div>
  );
}

export default App;
