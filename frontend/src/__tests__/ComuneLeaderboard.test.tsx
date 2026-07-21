import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { getTopComuni } = vi.hoisted(() => ({ getTopComuni: vi.fn() }));
vi.mock("../lib/api-client", () => ({ defaultApiClient: { getTopComuni } }));

import ComuneLeaderboard from "../components/ComuneLeaderboard";

describe("ComuneLeaderboard", () => {
  it("renders comuni ranked with alert counts", async () => {
    getTopComuni.mockResolvedValue({
      comuni: [
        {
          istat_code: "C1",
          name: "Testville",
          aoi_id: "it-test",
          worst_class: "High",
          max_score: 0.8,
          n_cells: 2,
          n_alert: 3,
          counts: {},
          exposure_rank: 0.9,
        },
      ],
    });
    render(<ComuneLeaderboard />);
    await waitFor(() => expect(screen.getByText("Testville")).toBeInTheDocument());
    expect(screen.getByText(/3 in allerta/)).toBeInTheDocument();
  });

  it("renders nothing when there are no alerting comuni", async () => {
    getTopComuni.mockResolvedValue({ comuni: [] });
    const { container } = render(<ComuneLeaderboard />);
    await waitFor(() => expect(getTopComuni).toHaveBeenCalled());
    expect(container.querySelector(".comuni-board")).toBeNull();
  });
});
