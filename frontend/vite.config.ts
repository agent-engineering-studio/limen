import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dichiarazione locale invece di @types/node: `types` in tsconfig.json e'
// esplicito e non include i tipi di node, e vite.config.ts sta dentro
// `include`, quindi `tsc -b` non compilerebbe. Serve solo process.env.
declare const process: { env: Record<string, string | undefined> };

// Vite 5.4.12+ rifiuta le richieste con un Host che non riconosce (fix per
// il DNS rebinding). Dietro un reverse proxy l'Host e' il dominio pubblico,
// quindi senza questo elenco il dev server risponde "Blocked request. This
// host is not allowed." a ogni richiesta. Separati da virgola e presi
// dall'ambiente: il dominio non appartiene a un file versionato.
const allowedHosts = (process.env.VITE_ALLOWED_HOSTS ?? "")
  .split(",")
  .map((host) => host.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // Omesso quando la variabile e' vuota, per non cambiare il
    // comportamento dello sviluppo in locale.
    ...(allowedHosts.length > 0 ? { allowedHosts } : {}),
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
