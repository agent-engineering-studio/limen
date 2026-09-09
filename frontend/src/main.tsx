import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { HazardProvider } from "./lib/hazard";
import "./styles.css";

const root = document.getElementById("root");
if (!root) {
    throw new Error("root element not found");
}

ReactDOM.createRoot(root).render(
    <React.StrictMode>
        <HazardProvider>
            <App />
        </HazardProvider>
    </React.StrictMode>,
);
