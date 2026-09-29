import React from "react";
import ReactDOM from "react-dom/client";

import { MantineProvider } from "@mantine/core";

import App from "./App";
import { HazardProvider } from "./lib/hazard";
import { theme } from "./lib/theme";
// L'ordine conta: gli stili di Mantine per primi, i nostri dopo, così una
// regola del progetto vince su quella del componente e non viceversa.
import "@mantine/core/styles.css";
import "./styles.css";

const root = document.getElementById("root");
if (!root) {
    throw new Error("root element not found");
}

ReactDOM.createRoot(root).render(
    <React.StrictMode>
        <MantineProvider theme={theme} defaultColorScheme="light">
            <HazardProvider>
                <App />
            </HazardProvider>
        </MantineProvider>
    </React.StrictMode>,
);
