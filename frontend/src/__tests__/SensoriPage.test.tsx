import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SensoriPage } from "../components/SensoriPage";
import { render as renderLingua } from "../test-utils";

describe("SensoriPage", () => {
  it("avvisa che la rete dei sensori non accetta ancora misure", () => {
    render(<SensoriPage />);
    expect(screen.getByText("Sensori e MQTT")).toBeInTheDocument();
    expect(screen.getByText(/Lavori in corso/)).toBeInTheDocument();
  });

  it("descrive entrambi i broker con i loro topic", () => {
    render(<SensoriPage />);
    expect(screen.getAllByText("limen-mosquitto").length).toBeGreaterThan(0);
    expect(screen.getAllByText("limen-mosquitto-sensori").length).toBeGreaterThan(0);
    expect(screen.getAllByText("limen/alerts").length).toBeGreaterThan(0);
  });

  it("in inglese tiene l'avviso e le stesse ancore", () => {
    const { container } = renderLingua(<SensoriPage />, { lingua: "en" });
    expect(screen.getByText("Sensors and MQTT")).toBeInTheDocument();
    expect(screen.getByText(/Work in progress/)).toBeInTheDocument();
    const hrefs = [...container.querySelectorAll(".guida-indice a")].map((a) => a.getAttribute("href"));
    expect(hrefs).toContain("#/sensori/il-broker-delle-allerte");
    expect(hrefs).toContain("#/sensori/sicurezza-dove-non-installare");
  });
});
