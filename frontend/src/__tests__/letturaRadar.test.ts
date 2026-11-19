import { describe, expect, it } from "vitest";

import { letturaRadar } from "../components/CellPopup";
import type { RadarCella } from "../types";

const base: RadarCella = {
  affidabile: true,
  punteggio: 0.9,
  visibilita: 1,
  copertura: 0.9,
  accordo: 0.96,
  quota_fascio_m: 1100,
  radar_vicino: "Catania Fontanarossa",
  distanza_km: 81.7,
};

describe("letturaRadar (#643)", () => {
  it("dice dove il radar vede male, il caso di Lipari", () => {
    const [riga] =
      letturaRadar({ ...base, affidabile: false, quota_fascio_m: 3550 }) ?? [];
    expect(riga).toContain("vede male");
    expect(riga).toContain("non vuol dire che non piove");
  });

  it("dice quanto è rara la pioggia caduta, con il tetto dei 50 anni", () => {
    const righe = letturaRadar({
      ...base,
      pioggia_mm: 180,
      finestra_ore: 24,
      ritorno_anni: 50,
    });
    expect(righe?.[1]).toContain("meno di una volta ogni 50 anni");
    const altre = letturaRadar({
      ...base,
      pioggia_mm: 60,
      finestra_ore: 24,
      ritorno_anni: 7.4,
    });
    expect(altre?.[1]).toContain("una volta ogni 7 anni");
  });

  it("fuori dalla mappa e senza dati non inventa niente", () => {
    expect(letturaRadar(null)).toBeNull();
    expect(letturaRadar({ ...base, affidabile: null })).toEqual([
      "Questo punto è fuori dalla mappa del radar.",
    ]);
  });

  it("parla inglese", () => {
    expect(letturaRadar(base, "en")?.[0]).toContain("The radar sees well here");
  });
});
