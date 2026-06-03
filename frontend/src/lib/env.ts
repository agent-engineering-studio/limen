// Lightweight env-var accessor. Vite exposes variables prefixed VITE_
// at build time via `import.meta.env`; we centralise defaults here so
// components don't reimplement fallback logic.

interface ViteEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_TILESERV_URL?: string;
  readonly VITE_ENABLE_TIMELINE?: string;
  readonly VITE_ENABLE_GRAPH?: string;
  readonly VITE_DEFAULT_LON?: string;
  readonly VITE_DEFAULT_LAT?: string;
  readonly VITE_DEFAULT_ZOOM?: string;
}

const env: ViteEnv =
  typeof import.meta !== "undefined" && import.meta.env
    ? (import.meta.env as ViteEnv)
    : {};

const num = (raw: string | undefined, fallback: number): number => {
  if (raw === undefined) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const bool = (raw: string | undefined, fallback: boolean): boolean => {
  if (raw === undefined) return fallback;
  return ["1", "true", "yes", "on"].includes(raw.toLowerCase());
};

export const config = {
  apiUrl: env.VITE_API_URL ?? "http://localhost:8080",
  tileservUrl: env.VITE_TILESERV_URL ?? "http://localhost:7800",
  enableTimeline: bool(env.VITE_ENABLE_TIMELINE, true),
  enableGraph: bool(env.VITE_ENABLE_GRAPH, false),
  defaultLon: num(env.VITE_DEFAULT_LON, 16.6),
  defaultLat: num(env.VITE_DEFAULT_LAT, 40.5),
  defaultZoom: num(env.VITE_DEFAULT_ZOOM, 7),
} as const;
