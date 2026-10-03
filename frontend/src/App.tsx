import { useCallback, useEffect, useRef, useState } from "react";
import type { JSX } from "react";
import type maplibregl from "maplibre-gl";
import { Popover, Switch, UnstyledButton } from "@mantine/core";

import CellPopup from "./components/CellPopup";
import ComuniBoard from "./components/ComuniBoard";
import DocsPage from "./components/DocsPage";
import ExplainerPage from "./components/ExplainerPage";
import { defaultApiClient } from "./lib/api-client";
import type { CellSelection, ComuneCell, ComuneGeometry, ComuneRisk } from "./types";
import FreshnessBadge from "./components/FreshnessBadge";
import HomePage from "./components/HomePage";
import IntegrationsPage from "./components/IntegrationsPage";
import LegendPanel from "./components/LegendPanel";
import NationalStrip from "./components/NationalStrip";
import OverlayControl from "./components/OverlayControl";
import PrevisioneTesta from "./components/PrevisioneTesta";
import RicercaComune from "./components/RicercaComune";
import RiskMap from "./components/RiskMap";
import SciencePage from "./components/SciencePage";
import ShadowDiagnosticsPage from "./components/ShadowDiagnosticsPage";
import ShadowPanel from "./components/ShadowPanel";
import { useHazard } from "./lib/hazard";
import { OVERLAYS } from "./lib/overlays";

type Page =
  | "home"
  | "dashboard"
  | "explainer"
  | "docs"
  | "science"
  | "shadow"
  | "integrations";

function pageFromHash(): Page {
  // La documentazione ha una sotto-rotta per pagina, quindi il confronto
  // esatto non basta: `#/documentazione/glossario` è la stessa sezione.
  if (window.location.hash.startsWith("#/documentazione")) {
    return "docs";
  }
  switch (window.location.hash) {
    case "#/dashboard":
    case "#/italia": // vecchio deep-link: il quadro nazionale vive in dashboard
      return "dashboard";
    case "#/come-funziona":
      return "explainer";
    case "#/modello":
      return "science";
    case "#/diagnostica-ml":
      return "shadow";
    case "#/integrazioni":
      return "integrations";
    // Un hash sconosciuto — compresi i vecchi #/accedi, #/registrati,
    // #/verifica e #/admin — va sulla home: la mappa è pubblica e non c'è
    // più niente dietro cui mettere una porta.
    default:
      return "home";
  }
}

/** Il riquadro «Livello attivo»: cosa colora la mappa, detto a parole. Con
 *  la vista d'insieme come default, senza questa riga non si saprebbe se il
 *  rosso di una cella è un incendio o una frana. */
function LivelloAttivo(): JSX.Element {
  const { multi, selected, available } = useHazard();
  const nome = available.find((h) => h.hazard === selected)?.label_it ?? selected;
  return (
    <div className="map-testa" aria-live="polite">
      <span className="map-testa-occhiello">Livello attivo</span>
      <span className="map-testa-titolo">
        {multi ? "Tutti i pericoli" : `Rischio ${nome.toLowerCase()}`} · adesso
      </span>
      {multi ? (
        <span className="map-testa-nota">il peggiore in ogni cella</span>
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

export function App(): JSX.Element {
  const { view } = useHazard();
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [selected, setSelected] = useState<CellSelection | null>(null);
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
  const [puntoIspettore, setPuntoIspettore] = useState<{
    left: number;
    top: number;
    maxHeight: number;
  } | null>(null);

  useEffect(() => {
    const onHash = (): void => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const onMapClick = useCallback((cellId: string, lngLat?: { lng: number; lat: number }) => {
    // Il punto cliccato, non il centro della cella: l'ispettore si apre lì
    // accanto, dove l'occhio già sta.
    setSelected({ cellId, lon: lngLat?.lng ?? null, lat: lngLat?.lat ?? null });
  }, []);

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
  }, [selected?.lon, selected?.lat, view]);


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

  const attiviNomi = OVERLAYS.filter((o) => overlayAttivi.has(o.id)).map((o) => o.label);

  const dashboard = (
    <>
      <aside className="sidebar" aria-label="Pannello laterale">
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
        />
        <LivelloAttivo />
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
            Solo sopra soglia
          </UnstyledButton>
          <Popover position="bottom-end" width={300} shadow="md" withinPortal={false}>
            <Popover.Target>
              <UnstyledButton className="map-bottone" aria-label="Livelli di contesto">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path d="M12 3l9 5-9 5-9-5 9-5z" stroke="currentColor" strokeWidth="2" />
                  <path d="M3 13l9 5 9-5" stroke="currentColor" strokeWidth="2" />
                </svg>
                Livelli
                <span className="map-conta mono">
                  {attiviNomi.length === 0 ? "nessuno" : attiviNomi.length}
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
              <strong>{String(evidenziato.properties?.["name"] ?? "")}</strong> evidenziato
            </span>
            <button
              type="button"
              aria-label="Togli l'evidenziazione del comune"
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
          <span className="brand-tag">soglia</span>
        </a>
        <nav className="app-nav" aria-label="Navigazione">
          <a href="#/" className={page === "home" ? "on" : ""}>
            Home
          </a>
          <a href="#/dashboard" className={page === "dashboard" ? "on" : ""}>
            Dashboard
          </a>
          <a
            href="#/come-funziona"
            className={
              page === "explainer" || page === "science" || page === "shadow" ? "on" : ""
            }
          >
            Cos&apos;è Limen
          </a>
          <a href="#/documentazione" className={page === "docs" ? "on" : ""}>
            Documentazione
          </a>
          <a href="#/integrazioni" className={page === "integrations" ? "on" : ""}>
            Integrazioni
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
      </header>

      {page === "home" ? (
        <HomePage />
      ) : page === "explainer" ? (
        <div className="explainer-area">
          <ExplainerPage />
        </div>
      ) : page === "docs" ? (
        <div className="explainer-area">
          <DocsPage />
        </div>
      ) : page === "science" ? (
        <div className="explainer-area">
          <SciencePage />
        </div>
      ) : page === "shadow" ? (
        <div className="explainer-area">
          <ShadowDiagnosticsPage />
        </div>
      ) : page === "integrations" ? (
        <div className="explainer-area">
          <IntegrationsPage />
        </div>
      ) : (
        dashboard
      )}
    </div>
  );
}

export default App;
