import { render } from "@testing-library/react";
import maplibregl from "maplibre-gl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RiskMap from "../components/RiskMap";
import { dentroItalia } from "../lib/posizione";

type Successo = (p: { coords: { longitude: number; latitude: number } }) => void;
type Errore = (e: { code: number }) => void;

let getCurrentPosition: ReturnType<typeof vi.fn>;

function rispondi(lon: number, lat: number): void {
  const ok = getCurrentPosition.mock.calls[0]?.[0] as Successo;
  ok({ coords: { longitude: lon, latitude: lat } });
}

beforeEach(() => {
  vi.restoreAllMocks();
  getCurrentPosition = vi.fn();
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: { getCurrentPosition },
  });
});

afterEach(() => {
  Reflect.deleteProperty(navigator, "geolocation");
});

describe("posizione all'apertura della mappa", () => {
  it("riconosce l'Italia, isole comprese, e non i vicini", () => {
    expect(dentroItalia(16.87, 41.12)).toBe(true); // Bari
    expect(dentroItalia(12.6, 35.5)).toBe(true); // Lampedusa
    expect(dentroItalia(2.35, 48.86)).toBe(false); // Parigi
    expect(dentroItalia(19.8, 41.3)).toBe(false); // Tirana
  });

  it("vola sulla posizione quando è in Italia", () => {
    const flyTo = vi.spyOn(maplibregl.Map.prototype, "flyTo");
    render(<RiskMap tileservUrl="http://tiles.test" geolocalizza />);
    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
    expect(flyTo).not.toHaveBeenCalled();
    rispondi(16.87, 41.12);
    expect(flyTo).toHaveBeenCalledWith({ center: [16.87, 41.12], zoom: 10 });
  });

  it("resta sulla vista di partenza se la posizione è all'estero", () => {
    const flyTo = vi.spyOn(maplibregl.Map.prototype, "flyTo");
    render(<RiskMap tileservUrl="http://tiles.test" geolocalizza />);
    rispondi(2.35, 48.86);
    expect(flyTo).not.toHaveBeenCalled();
  });

  it("resta sulla vista di partenza se il permesso è negato", () => {
    const flyTo = vi.spyOn(maplibregl.Map.prototype, "flyTo");
    render(<RiskMap tileservUrl="http://tiles.test" geolocalizza />);
    const ko = getCurrentPosition.mock.calls[0]?.[1] as Errore;
    ko({ code: 1 });
    expect(flyTo).not.toHaveBeenCalled();
  });

  it("non strappa la mappa a chi l'ha già spostata", () => {
    const flyTo = vi.spyOn(maplibregl.Map.prototype, "flyTo");
    const getCenter = vi.spyOn(maplibregl.Map.prototype, "getCenter");
    render(<RiskMap tileservUrl="http://tiles.test" geolocalizza />);
    getCenter.mockReturnValue({ lng: 15.8, lat: 40.6 } as maplibregl.LngLat);
    rispondi(16.87, 41.12);
    expect(flyTo).not.toHaveBeenCalled();
  });

  it("non chiede la posizione quando un link diretto ha già un posto", () => {
    render(<RiskMap tileservUrl="http://tiles.test" geolocalizza={false} />);
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  it("non la richiede di nuovo quando la mappa si ricostruisce", () => {
    const { rerender } = render(
      <RiskMap tileservUrl="http://tiles.test" tileLayer="public.v_risk_tiles" geolocalizza />,
    );
    rispondi(16.87, 41.12);
    rerender(<RiskMap tileservUrl="http://tiles.test" tileLayer="public.risk_at" geolocalizza />);
    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
  });

  it("una ricostruzione prima della risposta non perde la posizione", () => {
    // StrictMode monta la mappa due volte: la prima richiesta è annullata
    // dallo smontaggio, la seconda deve ancora portare la mappa sul posto.
    const flyTo = vi.spyOn(maplibregl.Map.prototype, "flyTo");
    const { rerender } = render(
      <RiskMap tileservUrl="http://tiles.test" tileLayer="public.v_risk_tiles" geolocalizza />,
    );
    rerender(<RiskMap tileservUrl="http://tiles.test" tileLayer="public.risk_at" geolocalizza />);
    expect(getCurrentPosition).toHaveBeenCalledTimes(2);
    rispondi(16.87, 41.12);
    expect(flyTo).not.toHaveBeenCalled();
    const ok = getCurrentPosition.mock.calls[1]?.[0] as Successo;
    ok({ coords: { longitude: 16.87, latitude: 41.12 } });
    expect(flyTo).toHaveBeenCalledTimes(1);
  });
});
