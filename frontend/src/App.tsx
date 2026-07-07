import { Show, SignInButton, UserButton } from "@clerk/react";
import { useCallback, useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";

import CellPopup from "./components/CellPopup";
import ExplainerPage from "./components/ExplainerPage";
import ForecastList from "./components/ForecastList";
import HomePage from "./components/HomePage";
import LegendPanel from "./components/LegendPanel";
import NationalStrip from "./components/NationalStrip";
import RegionAccordion from "./components/RegionAccordion";
import type { CellSelection } from "./components/RegionAccordion";
import RiskMap from "./components/RiskMap";
import TimelineSlider from "./components/TimelineSlider";
import { config } from "./lib/env";

type Page = "home" | "dashboard" | "explainer";

function pageFromHash(): Page {
  switch (window.location.hash) {
    case "#/dashboard":
    case "#/italia": // vecchio deep-link: il quadro nazionale vive in dashboard
      return "dashboard";
    case "#/come-funziona":
      return "explainer";
    default:
      return "home";
  }
}

/** Auth wall for the operational dashboard. */
function RequireAuth({ children }: { children: JSX.Element }): JSX.Element {
  return (
    <>
      <Show when="signed-in">{children}</Show>
      <Show when="signed-out">
        <div className="auth-wall">
          <h2>Area riservata</h2>
          <p>
            La dashboard operativa è accessibile agli utenti registrati.
            Accedi per consultare la mappa del rischio, il quadro nazionale e
            le allerte.
          </p>
          <div className="auth-wall-actions">
            <SignInButton mode="modal">
              <button type="button" className="btn-primary">
                Accedi
              </button>
            </SignInButton>
            <a className="btn-ghost" href="#/">
              ← Torna alla home
            </a>
          </div>
        </div>
      </Show>
    </>
  );
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
        <LegendPanel />
        {config.enableTimeline ? <TimelineSlider /> : null}
      </aside>
      <div className="map-area">
        <RiskMap
          mapRef={mapRef}
          onCellClick={onMapClick}
          selectedCellId={selected?.cellId ?? null}
        />
        <CellPopup
          cellId={selected?.cellId ?? null}
          lon={selected?.lon}
          lat={selected?.lat}
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
          <a href="#/come-funziona" className={page === "explainer" ? "on" : ""}>
            Come funziona
          </a>
        </nav>
        <span className="header-meta">agg. 1h · 20 regioni</span>
        <div className="auth-controls">
          <Show when="signed-out">
            <SignInButton mode="modal">
              <button type="button" className="btn-signin">
                Accedi
              </button>
            </SignInButton>
          </Show>
          <Show when="signed-in">
            <UserButton />
          </Show>
        </div>
      </header>

      {page === "home" ? (
        <HomePage />
      ) : page === "explainer" ? (
        <div className="explainer-area">
          <ExplainerPage />
        </div>
      ) : (
        <RequireAuth>{dashboard}</RequireAuth>
      )}
    </div>
  );
}

export default App;
