import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useBuyMeACoffee } from "../lib/buymeacoffee";

function Pagina({ attivo }: { attivo: boolean }) {
  useBuyMeACoffee(attivo);
  return null;
}

afterEach(() => {
  document.querySelectorAll('script[data-name="BMC-Widget"], #bmc-wbtn').forEach((n) => n.remove());
});

describe("Buy Me a Coffee", () => {
  it("fuori dalla dashboard carica il widget con il messaggio", () => {
    render(<Pagina attivo />);
    const s = document.querySelector<HTMLScriptElement>('script[data-name="BMC-Widget"]');
    expect(s?.src).toBe("https://cdnjs.buymeacoffee.com/1.0.0/widget.prod.min.js");
    expect(s?.dataset.id).toBe("f9t3zol");
    expect(s?.dataset.message).toContain("offrici un caffè");
  });

  it("sulla dashboard non lo carica, perché coprirebbe i comandi della mappa", () => {
    render(<Pagina attivo={false} />);
    expect(document.querySelector('script[data-name="BMC-Widget"]')).toBeNull();
  });

  it("se è già caricato, sulla dashboard nasconde il pulsante", () => {
    const b = document.createElement("div");
    b.id = "bmc-wbtn";
    document.body.appendChild(b);
    const { rerender } = render(<Pagina attivo />);
    rerender(<Pagina attivo={false} />);
    expect(b.style.display).toBe("none");
    rerender(<Pagina attivo />);
    expect(b.style.display).toBe("");
  });
});
