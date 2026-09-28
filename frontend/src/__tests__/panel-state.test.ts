import { describe, expect, it } from "vitest";

import { ApiClientError } from "../lib/api-client";
import { describeFailure, isStale, relativeTime } from "../lib/panel-state";

describe("describeFailure", () => {
  it("un 500 dice che non sappiamo, non che non c'è rischio", () => {
    const f = describeFailure(new ApiClientError("request to /x failed with 500", 500, null));
    expect(f.title).toBe("Il servizio non risponde");
    expect(f.detail).toContain("non lo sappiamo");
    expect(f.retryable).toBe(true);
  });

  it("non lascia mai uscire il messaggio tecnico", () => {
    const f = describeFailure(
      new ApiClientError("request to /api/report/national failed with 500", 500, null),
    );
    expect(`${f.title} ${f.detail}`).not.toContain("/api/");
    expect(`${f.title} ${f.detail}`).not.toContain("500");
  });

  it("su una richiesta sbagliata non propone di riprovare", () => {
    expect(describeFailure(new ApiClientError("x", 422, null)).retryable).toBe(false);
    expect(describeFailure(new ApiClientError("x", 404, null)).retryable).toBe(false);
  });

  it("un guasto di rete non è un errore del servizio", () => {
    expect(describeFailure(new TypeError("Failed to fetch")).title).toBe("Connessione assente");
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-09-28T12:00:00Z");
  it("sotto il minuto dice adesso", () => {
    expect(relativeTime("2026-09-28T11:59:30Z", now)).toBe("adesso");
  });
  it("accorda il singolare", () => {
    expect(relativeTime("2026-09-28T11:59:00Z", now)).toBe("1 minuto fa");
    expect(relativeTime("2026-09-28T11:00:00Z", now)).toBe("1 ora fa");
  });
  it("passa a ore e giorni", () => {
    expect(relativeTime("2026-09-28T09:00:00Z", now)).toBe("3 ore fa");
    expect(relativeTime("2026-09-26T12:00:00Z", now)).toBe("2 giorni fa");
  });
});

describe("isStale", () => {
  const now = new Date("2026-09-28T12:00:00Z");
  it("due ore non sono vecchie, quattro sì", () => {
    expect(isStale("2026-09-28T10:00:00Z", now)).toBe(false);
    expect(isStale("2026-09-28T08:00:00Z", now)).toBe(true);
  });
});
