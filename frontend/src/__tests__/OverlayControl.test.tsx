// I livelli di contesto per pericolo. C'erano solo quelli delle frane, mentre
// i dati di alluvione e incendio stavano già nel database e pg_tileserv li
// pubblicava già; e lo stato acceso/spento viveva nel pannello, così una
// mappa ricostruita al cambio di pericolo li spegneva lasciando la casella
// spuntata.

import { fireEvent, render, screen } from "../test-utils";
import { describe, expect, it, vi } from "vitest";

import OverlayControl from "../components/OverlayControl";
import { OVERLAYS } from "../lib/overlays";

describe("livelli di contesto", () => {
  it("ci sono per tutti e tre i pericoli, non solo per le frane", () => {
    render(<OverlayControl attivi={new Set()} onToggle={() => undefined} />);
    expect(screen.getByText("Frane")).toBeInTheDocument();
    expect(screen.getByText("Alluvioni")).toBeInTheDocument();
    expect(screen.getByText("Incendi")).toBeInTheDocument();
    expect(screen.getByText(/Pericolosità idraulica/)).toBeInTheDocument();
    expect(screen.getByText(/Aree bruciate/)).toBeInTheDocument();
  });

  it("è controllato: la casella dice ciò che App dice alla mappa", () => {
    // Nessuno stato proprio. È ciò che impedisce alla casella di restare
    // spuntata mentre la mappa, appena ricostruita, ha spento il livello.
    const onToggle = vi.fn();
    const { rerender } = render(<OverlayControl attivi={new Set()} onToggle={onToggle} />);
    const casella = screen.getByLabelText(/Aree bruciate/) as HTMLInputElement;
    expect(casella.checked).toBe(false);
    fireEvent.click(casella);
    expect(onToggle).toHaveBeenCalledWith("bruciate");
    rerender(<OverlayControl attivi={new Set(["bruciate"])} onToggle={onToggle} />);
    expect((screen.getByLabelText(/Aree bruciate/) as HTMLInputElement).checked).toBe(true);
  });

  it("dice da che zoom compare un livello pesante", () => {
    // Sotto zoom 10 la pericolosità idraulica non arriva: senza dirlo, una
    // casella accesa su una mappa che non cambia sembrerebbe rotta.
    render(<OverlayControl attivi={new Set()} onToggle={() => undefined} />);
    expect(screen.getByText(/da zoom 10/)).toBeInTheDocument();
  });

  it("la pericolosità idraulica, accesa, mostra le sue classi", () => {
    render(<OverlayControl attivi={new Set(["idraulica"])} onToggle={() => undefined} />);
    expect(screen.getByText(/P3 alta/)).toBeInTheDocument();
    expect(screen.getByText(/P1 bassa/)).toBeInTheDocument();
  });

  it("ogni livello accende almeno un livello della mappa", () => {
    for (const o of OVERLAYS) expect(o.layerIds.length).toBeGreaterThan(0);
  });
});
