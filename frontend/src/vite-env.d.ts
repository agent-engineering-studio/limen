/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_TILESERV_URL?: string;
  readonly VITE_ENABLE_TIMELINE?: string;
  readonly VITE_ENABLE_GRAPH?: string;
  readonly VITE_DEFAULT_LON?: string;
  readonly VITE_DEFAULT_LAT?: string;
  readonly VITE_DEFAULT_ZOOM?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
