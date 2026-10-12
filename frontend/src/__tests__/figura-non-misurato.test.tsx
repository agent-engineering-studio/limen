import { screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import FiguraNonMisurato from "../components/figure/non-misurato";
import { letturaDi } from "../components/figure/non-misurato/model";
import { render } from "../test-utils";

describe("figura non misurato: zero non è zero", () => {
  it("una cella calma e una senza dato valgono entrambe zero", () => {
    expect(letturaDi({ segnale: 0 }).punteggio).toBe(0);
    expect(letturaDi({ segnale: null }).punteggio).toBe(0);
  });

  it("le distingue solo il segnale «misurato»", () => {
    expect(letturaDi({ segnale: 0 })).toMatchObject({ misurato: true, livello: "None" });
    expect(letturaDi({ segnale: null })).toMatchObject({ misurato: false, livello: null });
  });
});

describe("figura non misurato: si monta nelle due lingue", () => {
  beforeAll(() => {
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });

  it("in italiano", () => {
    render(<FiguraNonMisurato />, { lingua: "it" });
    expect(screen.getByText("Non misurato")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /bandierina grigia/ })).toBeInTheDocument();
    expect(screen.getByText("A 0,46 moderato · B 0,46 moderato")).toBeInTheDocument();
  });

  it("in inglese", () => {
    render(<FiguraNonMisurato />, { lingua: "en" });
    expect(screen.getByText("Not measured")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /grey flag/ })).toBeInTheDocument();
    expect(screen.getByText("A 0.46 moderate · B 0.46 moderate")).toBeInTheDocument();
  });
});
