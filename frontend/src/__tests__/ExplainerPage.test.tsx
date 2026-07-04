import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ExplainerPage, {
  ALPINE,
  PLAIN,
  simulate,
} from "../components/ExplainerPage";

describe("ExplainerPage", () => {
  it("renders the lay explanation and the simulator", () => {
    render(<ExplainerPage />);
    expect(
      screen.getByText(/Come fa Limen a dire dove può franare/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Le due domande/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Pioggia nelle ultime 24 ore/)).toBeInTheDocument();
  });
});

describe("simulate (production formula)", () => {
  it("heavy rain raises risk on the susceptible slope", () => {
    const dry = simulate(ALPINE, 0, 60, 0.2, 0);
    const wet = simulate(ALPINE, 120, 200, 0.45, 0);
    expect(wet.risk).toBeGreaterThan(dry.risk);
    expect(wet.classIndex).toBeGreaterThanOrEqual(3); // Alto+
  });

  it("the same storm barely moves the flat plain", () => {
    const wet = simulate(PLAIN, 120, 200, 0.45, 0);
    expect(wet.risk).toBeLessThan(0.55); // mai Alto senza predisposizione
  });

  it("rain-on-snow adds to M, snow without rain does not", () => {
    const ros = simulate(ALPINE, 40, 120, 0.35, 0.5);
    const noSnow = simulate(ALPINE, 40, 120, 0.35, 0);
    const drySnow = simulate(ALPINE, 0, 120, 0.35, 0.5);
    expect(ros.m).toBeGreaterThan(noSnow.m);
    expect(drySnow.snow).toBe(0);
  });
});
