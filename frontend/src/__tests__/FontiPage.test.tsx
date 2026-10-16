// La pagina delle fonti (#277): tutte le fonti, per ruolo, e il logo solo
// dove il titolare lo concede.

import { describe, expect, it } from "vitest";

import { render, screen } from "../test-utils";
import FontiPage from "../components/FontiPage";
import { FONTI, ORDINE_RUOLI } from "../lib/fonti";

describe("fonti dei dati", () => {
  it("ogni fonte ha un id unico, un ruolo noto, licenza e link", () => {
    const ids = FONTI.map((f) => f.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const f of FONTI) {
      expect(ORDINE_RUOLI).toContain(f.ruolo);
      expect(f.licenza.length).toBeGreaterThan(0);
      expect(f.url).toMatch(/^(https:\/\/|#\/)/);
      expect(f.dataset.it.length).toBeGreaterThan(0);
      expect(f.dataset.en.length).toBeGreaterThan(0);
    }
  });

  it("un logo porta sempre le regole che ne permettono l'uso e la nota richiesta", () => {
    for (const f of FONTI.filter((x) => x.logo)) {
      expect(f.logo?.regole).toMatch(/^https:\/\//);
      expect(f.logo?.nota.it).toMatch(/non è approvato/);
    }
  });

  it("i loghi vietati senza autorizzazione non ci sono", () => {
    // DPC per legge (art. 30 D.Lgs. 1/2018); ISTAT, NASA, ECMWF, EEA, EFFIS
    // per le loro regole. Aggiungerne uno richiede di cambiare questo test.
    const conLogo = FONTI.filter((f) => f.logo).map((f) => f.id);
    expect(conLogo).toEqual(["osm-mappa"]);
  });

  it("la dicitura Copernicus del GloFAS c'è", () => {
    const glofas = FONTI.find((f) => f.id === "glofas");
    expect(glofas?.attribuzione?.it).toMatch(/Copernicus Emergency Management Service/);
  });

  it("mostra i gruppi e dice che Limen non è affiliato", () => {
    render(<FontiPage />);
    expect(screen.getByRole("heading", { name: "Entrano nel calcolo" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Servono a verificare" })).toBeInTheDocument();
    expect(screen.getByText(/non vuol dire che l'ente approvi Limen/)).toBeInTheDocument();
    expect(screen.getByAltText("OpenStreetMap")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(FONTI.length);
  });
});
