import React from "react";
import ReactDOM from "react-dom/client";

import { MantineProvider } from "@mantine/core";
import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

import App from "./App";
import { HazardProvider } from "./lib/hazard";
import { LinguaProvider } from "./lib/i18n";
import { MapStateProvider, pericoloDaHash } from "./lib/map-state";
import { trovaRilievo } from "./lib/rilievo";
import { theme } from "./lib/theme";
// L'ordine conta: gli stili di Mantine per primi, i nostri dopo, così una
// regola del progetto vince su quella del componente e non viceversa.
import "@mantine/core/styles.css";
import "./styles.css";

// MapLibre 6 cerca il worker accanto al proprio modulo: nel bundle quel file
// non esiste, e senza questo la mappa resta vuota solo nella build.
setWorkerUrl(workerUrl);

const root = document.getElementById("root");
if (!root) {
    throw new Error("root element not found");
}

// Prima del primo disegno: la mappa legge l'URL del rilievo una volta sola.
void trovaRilievo().finally(() => ReactDOM.createRoot(root).render(
    <React.StrictMode>
        <LinguaProvider>
            <MantineProvider theme={theme} forceColorScheme="dark">
                <HazardProvider iniziale={pericoloDaHash(window.location.hash)}>
                    <MapStateProvider>
                        <App />
                    </MapStateProvider>
                </HazardProvider>
            </MantineProvider>
        </LinguaProvider>
    </React.StrictMode>,
));
