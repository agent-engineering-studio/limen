import { render, screen } from "../test-utils";
import { describe, expect, it } from "vitest";

import { RigaPredisposizione } from "../components/ComuniBoard";

const REGOLA = "none 0% · low <5% · medium 5-15% · high 15-30% · very high >=30%";

describe("RigaPredisposizione", () => {
  it("dice le due classi con la quota, e che non è un'allerta", () => {
    render(
      <RigaPredisposizione
        predisposizione={{
          frana: { classe: "medium", quota_pct: 6.726 },
          alluvione: { classe: "very high", quota_pct: 57.704 },
          regola: REGOLA,
        }}
      />,
    );
    expect(screen.getByText(/frana media \(6,7 % del territorio in P3\+P4\)/)).toBeInTheDocument();
    expect(screen.getByText(/alluvione molto alta \(57,7 % in scenario P2\)/)).toBeInTheDocument();
    expect(screen.getByText(/non è un'allerta/)).toBeInTheDocument();
  });

  it("una classe non disponibile non si mostra come «nessuna»", () => {
    render(
      <RigaPredisposizione
        predisposizione={{
          frana: { classe: "none", quota_pct: 0 },
          alluvione: { classe: null, quota_pct: null },
          regola: REGOLA,
        }}
      />,
    );
    expect(screen.getByText(/frana nessuna/)).toBeInTheDocument();
    expect(screen.queryByText(/alluvione/)).toBeNull();
  });

  it("senza predisposizione non disegna niente", () => {
    const { container } = render(<RigaPredisposizione predisposizione={null} />);
    expect(container.querySelector(".cb-predisposizione")).toBeNull();
  });
});
