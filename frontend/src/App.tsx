import { useCallback, useEffect, useRef, useState } from "react";
import type { JSX } from "react";
import type maplibregl from "maplibre-gl";

import CellPopup from "./components/CellPopup";
import ComuniBoard from "./components/ComuniBoard";
import DocsPage from "./components/DocsPage";
import ExplainerPage from "./components/ExplainerPage";
import { defaultApiClient } from "./lib/api-client";
import type { CellSelection, ComuneCell, ComuneGeometry, ComuneRisk } from "./types";
import FreshnessBadge from "./components/FreshnessBadge";
import HomePage from "./components/HomePage";
import IntegrationsPage from "./components/IntegrationsPage";
import HazardSelector from "./components/HazardSelector";
import LegendPanel from "./components/LegendPanel";
import NationalStrip from "./components/NationalStrip";
import OverlayControl from "./components/OverlayControl";
import RiskMap from "./components/RiskMap";
import SciencePage from "./components/SciencePage";
import ShadowDiagnosticsPage from "./components/ShadowDiagnosticsPage";
import ShadowPanel from "./components/ShadowPanel";

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

export function App(): JSX.Element {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [selected, setSelected] = useState<CellSelection | null>(null);
  const [evidenziato, setEvidenziato] = useState<ComuneGeometry | null>(null);
  const [page, setPage] = useState<Page>(pageFromHash);

  useEffect(() => {
    const onHash = (): void => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const onMapClick = useCallback((cellId: string) => {
    // Le coordinate non servono: la cella è già inquadrata dall'utente.
    setSelected({ cellId, lon: null, lat: null });
  }, []);

  // Dalla colonna alla mappa. Una classifica geografica su cui si clicca e
  // non succede niente è una lista di nomi: il posto è metà dell'informazione.
  const vaiAlComune = useCallback((c: ComuneRisk) => {
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

  const vaiAllaCella = useCallback((c: ComuneCell) => {
    mapRef.current?.flyTo({ center: [c.lon, c.lat], zoom: 13, duration: 700 });
    setSelected({ cellId: c.cell_id, lon: c.lon, lat: c.lat });
  }, []);

  const dashboard = (
    <>
      <aside className="sidebar" aria-label="Pannello laterale">
        <NationalStrip />
        <ComuniBoard onComune={vaiAlComune} onCella={vaiAllaCella} />
        <LegendPanel />
        <ShadowPanel />
      </aside>
      <div className="map-area">
        <RiskMap
          mapRef={mapRef}
          onCellClick={onMapClick}
          selectedCellId={selected?.cellId ?? null}
          comuneEvidenziato={evidenziato}
        />
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
        <HazardSelector />
        <OverlayControl mapRef={mapRef} />
        <CellPopup
          cellId={selected?.cellId ?? null}
          lon={selected?.lon}
          lat={selected?.lat}
          priority={selected?.priority}
          exposure={selected?.exposure}
          place={selected?.place}
          onDismiss={() => setSelected(null)}
        />
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
