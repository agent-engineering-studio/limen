import { ClerkProvider } from "@clerk/react";
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) {
    throw new Error("root element not found");
}

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
if (!publishableKey) {
    throw new Error("VITE_CLERK_PUBLISHABLE_KEY is not set");
}

ReactDOM.createRoot(root).render(
    <React.StrictMode>
        <ClerkProvider publishableKey={publishableKey} afterSignOutUrl="/">
            <App />
        </ClerkProvider>
    </React.StrictMode>,
);
