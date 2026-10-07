import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ErroreLocale from "../components/ErroreLocale";

function Esplode(): never {
  throw new Error("guasto");
}

describe("ErroreLocale", () => {
  it("un guasto in una pagina mostra un avviso invece di svuotare l'app", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <div>
        <header>Limen</header>
        <ErroreLocale chiave="regioni">
          <Esplode />
        </ErroreLocale>
      </div>,
    );
    expect(screen.getByText("Limen")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("non si è caricata");
  });
});
