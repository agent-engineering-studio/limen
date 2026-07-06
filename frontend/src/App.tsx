import { Show, SignInButton, UserButton } from "@clerk/react";
import { useCallback, useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";

import AlertList from "./components/AlertList";
import CellPopup from "./components/CellPopup";
import ExplainerPage from "./components/ExplainerPage";
import HomePage from "./components/HomePage";
import LegendPanel from "./components/LegendPanel";
import NationalReportPanel from "./components/NationalReportPanel";
import RiskMap from "./components/RiskMap";
import TimelineSlider from "./components/TimelineSlider";
import { config } from "./lib/env";
import type { AlertItem } from "./types";

type Page = "home" | "dashboard" | "national" | "explainer";

function pageFromHash(): Page {
  switch (window.location.hash) {
    case "#/dashboard":
      return "dashboard";
    case "#/italia":
      return "national";
    case "#/come-funziona":
      return "explainer";
    default:
      return "home";
  }
}

/** Auth wall for the operational pages: dashboard + national picture. */
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
  const [selectedCell, setSelectedCell] = useState<string | null>(null);
  const [page, setPage] = useState<Page>(pageFromHash);

  useEffect(() => {
    const onHash = (): void => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const flyToAlert = useCallback((alert: AlertItem) => {
    // We don't have per-cell coordinates from /api/alerts; fly to the
    // map's overall extent instead. The map click handler picks up
    // cell geometry from the vector tile when an analyst zooms in.
    setSelectedCell(alert.cell_id);
    mapRef.current?.flyTo({
      center: [config.defaultLon, config.defaultLat],
      zoom: 9,
      essential: true,
    });
  }, []);

  const dashboard = (
    <>
      <aside className="sidebar" aria-label="Pannello laterale">
        <LegendPanel />
        {config.enableTimeline ? <TimelineSlider /> : null}
        <AlertList onAlertClick={flyToAlert} />
        <CellPopup cellId={selectedCell} onDismiss={() => setSelectedCell(null)} />
      </aside>
      <RiskMap mapRef={mapRef} onCellClick={setSelectedCell} />
    </>
  );

  return (
    <div className={`app-shell ${page === "home" ? "is-home" : ""}`}>
      <header className="app-header">
        <a className="brand" href="#/">
          <img src="/logo.png" alt="" className="app-logo" height={36} />
          <span className="brand-name">Limen</span>
        </a>
        <nav className="app-nav" aria-label="Navigazione">
          <a href="#/" className={page === "home" ? "on" : ""}>
            Home
          </a>
          <a href="#/dashboard" className={page === "dashboard" ? "on" : ""}>
            Dashboard
          </a>
          <a href="#/italia" className={page === "national" ? "on" : ""}>
            Situazione Italia
          </a>
          <a href="#/come-funziona" className={page === "explainer" ? "on" : ""}>
            Come funziona
          </a>
        </nav>
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
      ) : page === "national" ? (
        <RequireAuth>
          <div className="explainer-area">
            <NationalReportPanel />
          </div>
        </RequireAuth>
      ) : (
        <RequireAuth>{dashboard}</RequireAuth>
      )}
    </div>
  );
}

export default App;
