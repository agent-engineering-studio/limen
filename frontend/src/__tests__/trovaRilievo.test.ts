import { afterEach, describe, expect, it, vi } from "vitest";

import { config, impostaRilievo } from "../lib/env";
import { trovaRilievo } from "../lib/rilievo";

const URL_TILE = "http://localhost/rilievo/rilievo-italia.pmtiles";

function risposta(status: number, tipo: string): Response {
  return new Response(null, { status, headers: { "content-type": tipo } });
}

afterEach(() => {
  vi.restoreAllMocks();
  impostaRilievo(undefined);
});

describe("trovaRilievo (#318)", () => {
  it("con le tile al percorso predefinito il rilievo si accende", async () => {
    const chiamata = vi.spyOn(globalThis, "fetch").mockResolvedValue(risposta(200, "application/octet-stream"));
    await trovaRilievo(URL_TILE, 100, undefined);
    expect(config.demPmtilesUrl).toBe(URL_TILE);
    expect(chiamata).toHaveBeenCalledWith(URL_TILE, expect.objectContaining({ method: "HEAD" }));
  });

  it("un 404 lo lascia spento", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(risposta(404, "text/html"));
    await trovaRilievo(URL_TILE, 100, undefined);
    expect(config.demPmtilesUrl).toBeUndefined();
  });

  it("l'index.html del ripiego della SPA non è un PMTiles", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(risposta(200, "text/html; charset=utf-8"));
    await trovaRilievo(URL_TILE, 100, undefined);
    expect(config.demPmtilesUrl).toBeUndefined();
  });

  it("senza rete resta spento e non lancia", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));
    await expect(trovaRilievo(URL_TILE, 100, undefined)).resolves.toBeUndefined();
    expect(config.demPmtilesUrl).toBeUndefined();
  });

  it("un URL di build o «off» non chiedono niente", async () => {
    const chiamata = vi.spyOn(globalThis, "fetch");
    await trovaRilievo(URL_TILE, 100, "off");
    impostaRilievo("https://tile.example/rilievo.pmtiles");
    await trovaRilievo(URL_TILE, 100, undefined);
    expect(chiamata).not.toHaveBeenCalled();
    expect(config.demPmtilesUrl).toBe("https://tile.example/rilievo.pmtiles");
  });
});
