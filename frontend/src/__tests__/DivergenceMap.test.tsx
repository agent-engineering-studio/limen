import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DivergenceMap from "../components/DivergenceMap";

describe("DivergenceMap", () => {
  it("renders the diagnostic map with the divergence tile layer + plain legend", () => {
    render(<DivergenceMap tileservUrl="http://tiles.test" />);
    const node = screen.getByTestId("divergence-map");
    expect(node.dataset["tileUrl"]).toBe(
      "http://tiles.test/public.v_shadow_divergence_tiles/{z}/{x}/{y}.pbf",
    );
    // legend is words, not colour-only (meno / più = two "vede" entries)
    expect(screen.getAllByText(/vede/).length).toBe(2);
    expect(screen.getByText("d'accordo")).toBeInTheDocument();
  });
});
