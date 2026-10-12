import type { JSX } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinguaProvider, linguaIniziale, testi, useLingua, useTesti } from "../lib/i18n";
import { fireEvent, render, screen } from "../test-utils";

const T = testi({ saluto: (n: string) => `Ciao ${n}` }, { saluto: (n: string) => `Hello ${n}` });

function Saluto(): JSX.Element {
  const t = useTesti(T);
  const { imposta } = useLingua();
  return (
    <>
      <p>{t.saluto("Limen")}</p>
      <button type="button" onClick={() => imposta("en")}>
        en
      </button>
    </>
  );
}

function imposta(url: string, lingue: string[]): void {
  window.history.replaceState(null, "", url);
  vi.spyOn(navigator, "languages", "get").mockReturnValue(lingue);
}

describe("linguaIniziale", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    window.history.replaceState(null, "", "/");
  });

  it("segue il browser: italiano solo a chi parla italiano", () => {
    imposta("/", ["it-IT", "en"]);
    expect(linguaIniziale()).toBe("it");
    imposta("/", ["de-DE", "fr"]);
    expect(linguaIniziale()).toBe("en");
  });

  it("un link con ?lang= vince sul browser, anche dentro la rotta", () => {
    imposta("/?lang=en", ["it-IT"]);
    expect(linguaIniziale()).toBe("en");
    imposta("/#/dashboard?lang=it", ["en-US"]);
    expect(linguaIniziale()).toBe("it");
  });

  it("la scelta ricordata vince sul browser", () => {
    imposta("/", ["it-IT"]);
    window.localStorage.setItem("limen.lingua", "en");
    expect(linguaIniziale()).toBe("en");
  });
});

describe("LinguaProvider", () => {
  afterEach(() => window.localStorage.clear());

  it("senza provider si parla italiano", () => {
    render(<Saluto />);
    expect(screen.getByText("Ciao Limen")).toBeInTheDocument();
  });

  it("cambiare lingua traduce, ricorda la scelta e aggiorna <html lang>", () => {
    render(
      <LinguaProvider iniziale="it">
        <Saluto />
      </LinguaProvider>,
    );
    fireEvent.click(screen.getByText("en"));
    expect(screen.getByText("Hello Limen")).toBeInTheDocument();
    expect(window.localStorage.getItem("limen.lingua")).toBe("en");
    expect(document.documentElement.lang).toBe("en");
  });

  it("render di test in inglese", () => {
    render(<Saluto />, { lingua: "en" });
    expect(screen.getByText("Hello Limen")).toBeInTheDocument();
  });
});
