import { useCallback, useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";

import CellPopup from "./components/CellPopup";
import ComuneLeaderboard from "./components/ComuneLeaderboard";
import ExplainerPage from "./components/ExplainerPage";
import ForecastList from "./components/ForecastList";
import FreshnessBadge from "./components/FreshnessBadge";
import HomePage from "./components/HomePage";
import IntegrationsPage from "./components/IntegrationsPage";
import HazardSelector from "./components/HazardSelector";
import LegendPanel from "./components/LegendPanel";
import NationalStrip from "./components/NationalStrip";
import OverlayControl from "./components/OverlayControl";
import RegionAccordion from "./components/RegionAccordion";
import type { CellSelection } from "./components/RegionAccordion";
import RiskMap from "./components/RiskMap";
import SciencePage from "./components/SciencePage";
import ShadowDiagnosticsPage from "./components/ShadowDiagnosticsPage";
import ShadowPanel from "./components/ShadowPanel";

type Page =
  | "home"
  | "dashboard"
  | "explainer"
  | "science"
  | "shadow"
  | "integrations";

function pageFromHash(): Page {
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
  const [page, setPage] = useState<Page>(pageFromHash);

  useEffect(() => {
    const onHash = (): void => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const selectCell = useCallback((sel: CellSelection) => {
    setSelected(sel);
    if (sel.lon != null && sel.lat != null && mapRef.current) {
      mapRef.current.flyTo({
        center: [sel.lon, sel.lat],
        zoom: Math.max(mapRef.current.getZoom(), 11),
        essential: true,
      });
    }
  }, []);

  const onMapClick = useCallback((cellId: string) => {
    // Le coordinate non servono: la cella è già inquadrata dall'utente.
    setSelected({ cellId, lon: null, lat: null });
  }, []);

  const dashboard = (
    <>
      <aside className="sidebar" aria-label="Pannello laterale">
        <NationalStrip />
        <ForecastList />
        <RegionAccordion
          onCellSelect={selectCell}
          selectedCellId={selected?.cellId ?? null}
        />
        <ComuneLeaderboard />
        <LegendPanel />
        <ShadowPanel />
      </aside>
      <div className="map-area">
        <RiskMap
          mapRef={mapRef}
          onCellClick={onMapClick}
          selectedCellId={selected?.cellId ?? null}
        />
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
          <a href="#/integrazioni" className={page === "integrations" ? "on" : ""}>
            Integrazioni
          </a>
        </nav>
        <HazardSelector />
        <FreshnessBadge />
      </header>

      {page === "home" ? (
        <HomePage />
      ) : page === "explainer" ? (
        <div className="explainer-area">
          <ExplainerPage />
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
