import { describe, expect, it } from "vitest";

import { cellaDaHash } from "../lib/link-cella";

describe("cellaDaHash", () => {
  it("legge cella e coordinate del link della mail", () => {
    expect(cellaDaHash("#/dashboard?cella=it-basilicata%7C12%7C34&lon=16.10512&lat=40.10533")).toEqual({
      cellId: "it-basilicata|12|34",
      lon: 16.10512,
      lat: 40.10533,
    });
  });

  it("senza query, o con coordinate mancanti, non c'è cella", () => {
    expect(cellaDaHash("#/dashboard")).toBeNull();
    expect(cellaDaHash("#/dashboard?cella=it-x%7C1%7C1&lon=16.1")).toBeNull();
    expect(cellaDaHash("#/dashboard?cella=it-x%7C1%7C1&lon=abc&lat=40")).toBeNull();
  });
});
