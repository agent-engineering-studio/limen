// Le stazioni dei sensori sulla mappa (#255): il popup dice quanto conta una
// stazione, e il simbolo non si confonde con una classe di rischio.

import { describe, expect, it } from "vitest";

import { render, screen } from "../test-utils";
import OverlayControl from "../components/OverlayControl";
import { OVERLAYS } from "../lib/overlays";
import { HAZARD_HUE, RISK_COLOR_BY_LEVEL } from "../lib/risk-colors";
import { COLORE_LIVELLO, popupStazione, righeStazione } from "../lib/stazioni";
import type { ProprietaStazione } from "../lib/stazioni";

const BASE: ProprietaStazione = {
  id: "pluvio-matera-01",
  tipo: "pluviometro",
  livello: 0,
  stato: "online",
  arrotondata: true,
  ultima_grandezza: "rainfall",
  ultimo_valore: 0.4,
  ultima_unita: "mm",
  ultimo_istante: "2026-10-16T10:05:00+00:00",
  valide_24h: 280,
  segnalate_24h: 3,
};

describe("stazioni dei cittadini", () => {
  it("un osservatore dice che non fa scattare allerte", () => {
    const righe = righeStazione(BASE, "it");
    expect(righe[0]).toContain("Osservatore");
    expect(righe.join(" ")).toMatch(/non fa scattare allerte/);
    expect(righe.join(" ")).toMatch(/280 misure valide, 3 segnalate/);
    expect(righe.join(" ")).toMatch(/arrotondata a circa un chilometro/);
  });

  it("una verificata dice che conta insieme ad altre", () => {
    const righe = righeStazione({ ...BASE, livello: 1 }, "it").join(" ");
    expect(righe).toMatch(/insieme ad altre stazioni/);
    expect(righe).toMatch(/Verificata/);
  });

  it("parla inglese", () => {
    const righe = righeStazione(BASE, "en").join(" ");
    expect(righe).toMatch(/does not trigger alerts/);
    expect(righe).toMatch(/Last reading: rain/);
  });

  it("senza dati lo dice, anche se MapLibre ha tolto i null", () => {
    const senza = { ...BASE } as Partial<ProprietaStazione>;
    delete senza.ultimo_valore;
    delete senza.ultimo_istante;
    const righe = righeStazione(
      { ...(senza as ProprietaStazione), valide_24h: 0, segnalate_24h: 0 },
      "it",
    ).join(" ");
    expect(righe).toMatch(/Nessun dato negli ultimi 30 giorni/);
    expect(righe).toMatch(/Nessuna misura nelle ultime 24 ore/);
  });

  it("il popup è testo, non HTML: l'id lo sceglie chi registra", () => {
    const el = popupStazione({ ...BASE, id: "<img src=x onerror=alert(1)>" }, "it");
    expect(el.querySelector("img")).toBeNull();
    expect(el.textContent).toContain("<img src=x");
  });

  it("i simboli non usano la rampa del rischio né le tinte dei pericoli", () => {
    const rampa = new Set(
      [...Object.values(RISK_COLOR_BY_LEVEL), ...Object.values(HAZARD_HUE)].map((c) =>
        c.toLowerCase(),
      ),
    );
    for (const c of Object.values(COLORE_LIVELLO)) expect(rampa.has(c.toLowerCase())).toBe(false);
  });

  it("è un livello di contesto spento di default, nel suo gruppo", () => {
    const stazioni = OVERLAYS.find((o) => o.id === "stazioni");
    expect(stazioni?.gruppo).toBe("cittadini");
    render(<OverlayControl attivi={new Set()} onToggle={() => undefined} />);
    expect(screen.getByText("Rete dei sensori")).toBeInTheDocument();
    expect((screen.getByLabelText(/Stazioni dei cittadini/) as HTMLInputElement).checked).toBe(
      false,
    );
  });
});
