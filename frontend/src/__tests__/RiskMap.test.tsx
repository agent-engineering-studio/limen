import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RiskMap from "../components/RiskMap";

describe("RiskMap", () => {
  it("renders the map container with the composed tile URL", () => {
    render(
      <RiskMap
        tileservUrl="http://tiles.test"
        tileLayer="public.mv_latest_risk"
      />,
    );
    const node = screen.getByTestId("risk-map");
    expect(node).toBeInTheDocument();
    expect(node.dataset["tileUrl"]).toBe(
      "http://tiles.test/public.mv_latest_risk/{z}/{x}/{y}.pbf",
    );
    expect(node).toHaveAttribute(
      "aria-label",
      "Mappa interattiva del rischio frane",
    );
  });
});
