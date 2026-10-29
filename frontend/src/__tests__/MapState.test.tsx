import { useRef } from "react";
import type { JSX } from "react";
import type maplibregl from "maplibre-gl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HazardSelector from "../components/HazardSelector";
import RiskMap from "../components/RiskMap";
import { defaultApiClient } from "../lib/api-client";
import { HazardProvider } from "../lib/hazard";
import {
  hashDaStato,
  MapStateProvider,
  pericoloDaHash,
  STATO_INIZIALE,
  statoDaHash,
  useMapState,
  type StatoMappa,
} from "../lib/map-state";
import { act, fireEvent, render, screen, waitFor } from "../test-utils";
import type { HazardsResponse } from "../types";

const TRE: HazardsResponse = {
  items: [
    { hazard: "landslide", label_it: "Frana" },
    { hazard: "flood", label_it: "Allagamento" },
    { hazard: "wildfire", label_it: "Incendio" },
  ],
  default: "landslide",
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(defaultApiClient, "getHazards").mockResolvedValue(TRE);
});

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

/** Mostra lo stato e lo cambia: il posto di un pannello qualunque. */
function Sonda(): JSX.Element {
  const s = useMapState();
  return (
    <div>
      <output data-testid="stato">
        {JSON.stringify({
          vista: s.vista,
          pericolo: s.pericolo,
          orizzonte: s.orizzonte,
          soloSoglia: s.soloSoglia,
          livelli: [...s.overlayAttivi],
          area: s.area,
          cella: s.cella?.cellId ?? null,
          geolocalizza: s.geolocalizza,
        })}
      </output>
      <button type="button" onClick={() => s.impostaVista("3d")}>vista</button>
      <button type="button" onClick={() => s.impostaOrizzonte(72)}>orizzonte</button>
      <button type="button" onClick={() => s.impostaSoloSoglia(!s.soloSoglia)}>soglia</button>
      <button type="button" onClick={() => s.commutaOverlay("bruciate")}>livello</button>
      <button type="button" onClick={() => s.cliccaCella("c-1", { lng: 16, lat: 40 })}>cella</button>
      <button type="button" onClick={() => s.impostaArea({ lon: 9.19, lat: 45.46, zoom: 11 })}>area</button>
      <button type="button" onClick={() => s.impostaPericolo("flood")}>pericolo</button>
    </div>
  );
}

function letto(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId("stato").textContent ?? "{}") as Record<string, unknown>;
}

/** `/api/hazards` ha risposto: dopo, il default del backend non sovrascrive
 *  più la scelta. */
async function pericoliCaricati(): Promise<void> {
  await waitFor(() => expect(defaultApiClient.getHazards).toHaveBeenCalled());
  await act(async () => {
    await new Promise((fatto) => setTimeout(fatto, 0));
  });
}

function monta(ui: JSX.Element): ReturnType<typeof render> {
  return render(
    <HazardProvider iniziale={pericoloDaHash(window.location.hash)}>
      <MapStateProvider>{ui}</MapStateProvider>
    </HazardProvider>,
  );
}

describe("hash ↔ stato", () => {
  it("fa il giro senza perdere niente", () => {
    const stato: StatoMappa = {
      ...STATO_INIZIALE,
      vista: "rilievo",
      orizzonte: 48,
      soloSoglia: false,
      overlayAttivi: new Set(["dpc", "bruciate"]),
      area: { lon: 15.8, lat: 40.6, zoom: 9.5 },
    };
    const hash = hashDaStato("#/mappa", stato, "wildfire");
    expect(hash).toBe(
      "#/mappa?vista=rilievo&hazard=wildfire&h=48&soglia=0&livelli=dpc,bruciate&centro=15.8000,40.6000&z=9.50",
    );
    const letto = statoDaHash(hash);
    expect(letto).toEqual({
      vista: "rilievo",
      pericolo: "wildfire",
      orizzonte: 48,
      soloSoglia: false,
      overlayAttivi: new Set(["dpc", "bruciate"]),
      area: { lon: 15.8, lat: 40.6, zoom: 9.5 },
    });
    expect(pericoloDaHash(hash)).toBe("wildfire");
  });

  it("lascia `#/dashboard` com'è a stato di default, e non tocca cella e lingua", () => {
    expect(hashDaStato("#/dashboard", STATO_INIZIALE, "multi")).toBe("#/dashboard");
    const link = "#/dashboard?cella=c-9&lon=16.1&lat=40.2&lang=en";
    expect(hashDaStato(link, STATO_INIZIALE, "multi")).toBe(link);
    expect(hashDaStato(link, { ...STATO_INIZIALE, orizzonte: 24 }, "multi")).toBe(`${link}&h=24`);
  });

  it("scarta i valori che non conosce", () => {
    expect(statoDaHash("#/mappa?vista=4d&hazard=meteorite&h=13&soglia=forse&livelli=boh,dpc")).toEqual({
      overlayAttivi: new Set(["dpc"]),
      area: null,
    });
    expect(pericoloDaHash("#/regioni?hazard=flood")).toBeUndefined();
  });
});

describe("MapStateProvider", () => {
  it("URL → contesto → URL", async () => {
    window.history.replaceState(
      null,
      "",
      "/#/mappa?vista=rilievo&hazard=wildfire&h=48&soglia=0&livelli=dpc&centro=15.8000,40.6000&z=9.50&lang=en",
    );
    monta(<Sonda />);
    expect(letto()).toEqual({
      vista: "rilievo",
      pericolo: "wildfire",
      orizzonte: 48,
      soloSoglia: false,
      livelli: ["dpc"],
      area: { lon: 15.8, lat: 40.6, zoom: 9.5 },
      cella: null,
      geolocalizza: false,
    });
    // Il default del backend (frane) non vince sul pericolo del link.
    await pericoliCaricati();
    expect(letto()["pericolo"]).toBe("wildfire");

    fireEvent.click(screen.getByText("vista"));
    fireEvent.click(screen.getByText("orizzonte"));
    fireEvent.click(screen.getByText("soglia"));
    fireEvent.click(screen.getByText("livello"));
    fireEvent.click(screen.getByText("area"));
    fireEvent.click(screen.getByText("pericolo"));
    await waitFor(() =>
      expect(window.location.hash).toBe(
        "#/mappa?lang=en&vista=3d&hazard=flood&h=72&livelli=dpc,bruciate&centro=9.1900,45.4600&z=11.00",
      ),
    );
    expect(statoDaHash(window.location.hash)).toEqual({
      vista: "3d",
      pericolo: "flood",
      orizzonte: 72,
      overlayAttivi: new Set(["dpc", "bruciate"]),
      area: { lon: 9.19, lat: 45.46, zoom: 11 },
    });
  });

  it("un link incollato cambia ciò che nomina e lascia il resto", async () => {
    window.history.replaceState(null, "", "/#/dashboard");
    monta(<Sonda />);
    await pericoliCaricati();
    fireEvent.click(screen.getByText("livello"));
    await act(async () => {
      window.history.replaceState(null, "", "/#/mappa?h=24&hazard=flood");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(letto()).toMatchObject({ orizzonte: 24, pericolo: "flood", livelli: ["bruciate"] });
    expect(window.location.hash).toBe("#/mappa?hazard=flood&h=24&livelli=bruciate");
  });

  it("fuori dalla mappa non riscrive l'URL", async () => {
    window.history.replaceState(null, "", "/#/regioni");
    monta(<Sonda />);
    await pericoliCaricati();
    fireEvent.click(screen.getByText("orizzonte"));
    expect(window.location.hash).toBe("#/regioni");
  });
});

describe("RiskMap dentro MapStateProvider", () => {
  function ConMappa({ onMappa }: { onMappa: (m: maplibregl.Map | null) => void }): JSX.Element {
    const mapRef = useRef<maplibregl.Map | null>(null);
    return (
      <>
        <Sonda />
        <HazardSelector />
        <RiskMap tileservUrl="http://tiles.test" mapRef={mapRef} />
        <button type="button" onClick={() => onMappa(mapRef.current)}>
          leggi
        </button>
      </>
    );
  }

  it("cambiare un campo non rimonta la mappa", async () => {
    // Si parte dal futuro: fra adesso e previsione cambia la sorgente, e la
    // mappa si ricostruiva già prima di #317; fra due scadenze no.
    window.history.replaceState(null, "", "/#/dashboard?h=24");
    let mappa: maplibregl.Map | null = null;
    monta(<ConMappa onMappa={(m) => (mappa = m)} />);
    await screen.findByRole("button", { name: "Incendio" });
    const contenitore = screen.getByTestId("risk-map");
    fireEvent.click(screen.getByText("leggi"));
    const prima = mappa;
    expect(prima).not.toBeNull();

    for (const campo of ["vista", "orizzonte", "soglia", "livello", "cella", "area"]) {
      fireEvent.click(screen.getByText(campo));
      fireEvent.click(screen.getByText("leggi"));
      expect(mappa, campo).toBe(prima);
      expect(screen.getByTestId("risk-map"), campo).toBe(contenitore);
    }
    // L'orizzonte passa dallo stato alla mappa: la tile è quella del futuro.
    expect(screen.getByTestId("risk-map").dataset["tileUrl"]).toBe(
      "http://tiles.test/public.forecast_at/{z}/{x}/{y}.pbf?p_horizon=72",
    );

    // Il pericolo cambia sorgente e MapLibre ricostruisce lo stile, come
    // prima di #317; il componente però resta lo stesso.
    fireEvent.click(screen.getByRole("button", { name: "Incendio" }));
    await waitFor(() =>
      expect(screen.getByTestId("risk-map").dataset["tileUrl"]).toContain("p_hazard=wildfire"),
    );
    expect(screen.getByTestId("risk-map")).toBe(contenitore);
  });
});
