import { useRef } from "react";
import type { JSX } from "react";
import maplibre from "maplibre-gl";
import type maplibregl from "maplibre-gl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LegendPanel from "../components/LegendPanel";
import RiskMap from "../components/RiskMap";
import SelettoreVista from "../components/SelettoreVista";
import { defaultApiClient } from "../lib/api-client";
import { HazardProvider } from "../lib/hazard";
import { MapStateProvider, pericoloDaHash } from "../lib/map-state";
import { DEM_SOURCE_ID, HILLSHADE_LAYER_ID, INCLINAZIONE_RILIEVO } from "../lib/rilievo";
import { COLORE_IGNOTO } from "../lib/risk-colors";
import { act, fireEvent, render, screen, waitFor } from "../test-utils";

// L'URL del DEM è una variabile di build: qui la si cambia per test.
const dem = vi.hoisted(() => ({ url: undefined as string | undefined }));
vi.mock("../lib/env", async (importOriginal) => {
  const orig = await importOriginal<typeof import("../lib/env")>();
  return {
    ...orig,
    config: new Proxy(orig.config, {
      get: (t, k) => (k === "demPmtilesUrl" ? dem.url : t[k as keyof typeof t]),
    }),
  };
});

function webgl2(presente: boolean): void {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    ((tipo: string) => (presente && tipo === "webgl2" ? {} : null)) as never,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  dem.url = undefined;
  vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue({
    items: [
      { hazard: "landslide", label_it: "Frana" },
      { hazard: "wildfire", label_it: "Incendio" },
    ],
    default: "landslide",
  });
  vi.spyOn(defaultApiClient, "getLegend").mockRejectedValue(new Error("offline"));
});

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

function monta(ui: JSX.Element): ReturnType<typeof render> {
  return render(
    <HazardProvider iniziale={pericoloDaHash(window.location.hash)}>
      <MapStateProvider>{ui}</MapStateProvider>
    </HazardProvider>,
  );
}

async function caricato(): Promise<void> {
  await waitFor(() => expect(defaultApiClient.getHazards).toHaveBeenCalled());
  await act(async () => {
    await new Promise((fatto) => setTimeout(fatto, 0));
  });
}

interface Stile {
  style: {
    sources: Record<string, Record<string, unknown>>;
    layers: { id: string; type: string; layout?: Record<string, unknown>; paint?: Record<string, unknown> }[];
    terrain?: unknown;
  };
  pitch: number;
  bearing: number;
}
const ultimoStile = (): Stile =>
  (maplibre.Map as unknown as { ultimeOpzioni: Stile }).ultimeOpzioni;

describe("SelettoreVista", () => {
  it("senza tile del terreno «Rilievo» è spento e dice perché", async () => {
    window.history.replaceState(null, "", "/#/dashboard");
    monta(<SelettoreVista />);
    await caricato();
    const rilievo = screen.getByRole("radio", { name: /Rilievo/ });
    expect(rilievo).toBeDisabled();
    expect(rilievo).toHaveAccessibleName(expect.stringContaining("VITE_DEM_PMTILES_URL"));
    expect(screen.getByRole("radio", { name: /3D/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /3D/ })).toHaveAccessibleName(
      expect.stringContaining("#321"),
    );
    expect(screen.getByRole("radio", { name: "2D" })).toBeChecked();
  });

  it("senza WebGL2 «Rilievo» è spento con quel motivo", async () => {
    dem.url = "https://dati.test/dem.pmtiles";
    webgl2(false);
    window.history.replaceState(null, "", "/#/dashboard");
    monta(<SelettoreVista />);
    await caricato();
    const rilievo = screen.getByRole("radio", { name: /Rilievo/ });
    expect(rilievo).toBeDisabled();
    expect(rilievo).toHaveAccessibleName(expect.stringContaining("WebGL2"));
  });

  it("scrive la vista nello stato e nell'URL, e la legenda dichiara l'esagerazione", async () => {
    dem.url = "https://dati.test/dem.pmtiles";
    webgl2(true);
    window.history.replaceState(null, "", "/#/dashboard");
    monta(
      <>
        <SelettoreVista />
        <LegendPanel />
      </>,
    );
    await caricato();
    expect(screen.queryByText(/Rilievo esagerato/)).toBeNull();
    fireEvent.click(screen.getByRole("radio", { name: "Rilievo" }));
    await waitFor(() => expect(window.location.hash).toBe("#/dashboard?vista=rilievo"));
    expect(screen.getByRole("radio", { name: "Rilievo" })).toBeChecked();
    expect(screen.getByText(/Rilievo esagerato ×1,5/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "2D" }));
    await waitFor(() => expect(window.location.hash).toBe("#/dashboard"));
  });

  it("un link a «Rilievo» dove non c'è mostra la mappa piatta", async () => {
    window.history.replaceState(null, "", "/#/mappa?vista=rilievo");
    monta(<SelettoreVista />);
    await caricato();
    expect(screen.getByRole("radio", { name: "2D" })).toBeChecked();
  });
});

describe("«Rilievo» sulla mappa", () => {
  function ConMappa({ onMappa }: { onMappa: (m: maplibregl.Map | null) => void }): JSX.Element {
    const mapRef = useRef<maplibregl.Map | null>(null);
    return (
      <>
        <SelettoreVista />
        <RiskMap tileservUrl="http://tiles.test" mapRef={mapRef} />
        <button type="button" onClick={() => onMappa(mapRef.current)}>
          leggi
        </button>
      </>
    );
  }

  it("aperto da un link: terreno, ombre sotto il rischio, «non misurato» grigio", async () => {
    dem.url = "https://dati.test/dem.pmtiles";
    webgl2(true);
    window.history.replaceState(null, "", "/#/mappa?vista=rilievo");
    monta(<ConMappa onMappa={() => {}} />);
    await caricato();
    const o = ultimoStile();
    expect(o.pitch).toBe(INCLINAZIONE_RILIEVO);
    expect(o.style.terrain).toMatchObject({ source: DEM_SOURCE_ID });
    expect(o.style.sources[DEM_SOURCE_ID]).toMatchObject({
      type: "raster-dem",
      url: "pmtiles://https://dati.test/dem.pmtiles",
      encoding: "mapbox",
      tileSize: 256,
      maxzoom: 11,
    });
    // Nessuna licenza scritta qui: l'attribuzione viene dai metadati
    // dell'archivio, attraverso la TileJSON del protocollo pmtiles.
    expect(o.style.sources[DEM_SOURCE_ID]).not.toHaveProperty("attribution");
    const ids = o.style.layers.map((l) => l.id);
    expect(ids.indexOf(HILLSHADE_LAYER_ID)).toBe(1);
    expect(ids.indexOf(HILLSHADE_LAYER_ID)).toBeLessThan(ids.indexOf("limen-risk-fill"));
    expect(o.style.layers[1]?.layout).toEqual({ visibility: "visible" });
    const celle = o.style.layers.find((l) => l.id === "limen-risk-fill");
    expect(JSON.stringify(celle?.paint?.["fill-color"])).toContain(COLORE_IGNOTO);
  });

  it("tornare a 2D spegne il terreno e raddrizza la camera, senza rimontare", async () => {
    dem.url = "https://dati.test/dem.pmtiles";
    webgl2(true);
    window.history.replaceState(null, "", "/#/dashboard");
    let mappa: maplibregl.Map | null = null;
    monta(<ConMappa onMappa={(m) => (mappa = m)} />);
    await caricato();
    expect(ultimoStile().style.layers[1]?.layout).toEqual({ visibility: "none" });
    expect(ultimoStile().style.terrain).toBeUndefined();
    fireEvent.click(screen.getByText("leggi"));
    const prima = mappa as unknown as maplibregl.Map;
    const contenitore = screen.getByTestId("risk-map");
    vi.spyOn(prima, "isStyleLoaded").mockReturnValue(true);
    vi.spyOn(prima, "getSource").mockReturnValue({} as never);
    vi.spyOn(prima, "getLayer").mockReturnValue({} as never);
    vi.spyOn(prima, "getBearing").mockReturnValue(35);
    const camera = vi.spyOn(prima, "easeTo");
    const terreno = vi.spyOn(prima, "setTerrain");
    const visibilita = vi.spyOn(prima, "setLayoutProperty");

    fireEvent.click(screen.getByRole("radio", { name: "Rilievo" }));
    expect(terreno).toHaveBeenLastCalledWith({ source: DEM_SOURCE_ID, exaggeration: 1.5 });
    expect(visibilita).toHaveBeenLastCalledWith(HILLSHADE_LAYER_ID, "visibility", "visible");
    expect(camera).toHaveBeenLastCalledWith(
      expect.objectContaining({ pitch: INCLINAZIONE_RILIEVO, bearing: 35 }),
    );

    fireEvent.click(screen.getByRole("radio", { name: "2D" }));
    expect(terreno).toHaveBeenLastCalledWith(null);
    expect(visibilita).toHaveBeenLastCalledWith(HILLSHADE_LAYER_ID, "visibility", "none");
    expect(camera).toHaveBeenLastCalledWith(expect.objectContaining({ pitch: 0, bearing: 0 }));

    fireEvent.click(screen.getByText("leggi"));
    expect(mappa).toBe(prima);
    expect(screen.getByTestId("risk-map")).toBe(contenitore);
  });
});
