import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/react";
import { useCallback, useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";

import AlertList from "./components/AlertList";
import CellPopup from "./components/CellPopup";
import ExplainerPage from "./components/ExplainerPage";
import NationalReportPanel from "./components/NationalReportPanel";
import LegendPanel from "./components/LegendPanel";
import RiskMap from "./components/RiskMap";
import TimelineSlider from "./components/TimelineSlider";
import { config } from "./lib/env";
import type { AlertItem } from "./types";

export function App(): JSX.Element {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [selectedCell, setSelectedCell] = useState<string | null>(null);
  const pageFromHash = (): string => {
    if (window.location.hash === "#/come-funziona") return "explainer";
    if (window.location.hash === "#/italia") return "national";
    return "map";
  };
  const [page, setPage] = useState(pageFromHash);

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

  return (
    <div className="app-shell">
      <header className="app-header">
        <img src="/logo.png" alt="Limen" className="app-logo" height={40} />
        <h1>Limen</h1>
        <span className="subtitle">
          Mappa pubblica del rischio frane — copertura nazionale
        </span>
        <nav className="app-nav" aria-label="Navigazione">
          <a href="#/" className={page === "map" ? "on" : ""}>
            Mappa
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
            <SignInButton />
            <SignUpButton />
          </Show>
          <Show when="signed-in">
            <UserButton />
          </Show>
        </div>
      </header>

      {page === "explainer" ? (
        <div className="explainer-area">
          <ExplainerPage />
        </div>
      ) : page === "national" ? (
        <div className="explainer-area">
          <NationalReportPanel />
        </div>
      ) : (
        <>
      <aside className="sidebar" aria-label="Pannello laterale">
        <LegendPanel />
        {config.enableTimeline ? <TimelineSlider /> : null}
        <AlertList onAlertClick={flyToAlert} />
        <CellPopup
          cellId={selectedCell}
          onDismiss={() => setSelectedCell(null)}
        />
      </aside>

      <RiskMap mapRef={mapRef} onCellClick={setSelectedCell} />
        </>
      )}
    </div>
  );
}

export default App;
