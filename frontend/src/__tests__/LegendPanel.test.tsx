import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LegendPanel from "../components/LegendPanel";

describe("LegendPanel", () => {
  it("renders five class labels with score ranges (not colour-only)", () => {
    render(<LegendPanel />);
    expect(screen.getByText("Nessuno")).toBeInTheDocument();
    expect(screen.getByText("Basso")).toBeInTheDocument();
    expect(screen.getByText("Moderato")).toBeInTheDocument();
    expect(screen.getByText("Alto")).toBeInTheDocument();
    expect(screen.getByText("Molto alto")).toBeInTheDocument();
    expect(screen.getByText("0.00-0.15")).toBeInTheDocument();
    expect(screen.getByText("0.75-1.00")).toBeInTheDocument();
  });
});
