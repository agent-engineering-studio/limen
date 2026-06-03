import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiClientError } from "../lib/api-client";
import type { AoiListResponse } from "../types";

describe("ApiClient", () => {
  it("composes the URL and parses the JSON body", async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          items: [{ id: "it-puglia", name: "Puglia", kind: "region" }],
        } satisfies AoiListResponse),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const client = new ApiClient({ baseUrl: "http://api", fetchImpl });
    const out = await client.getAoiList();
    expect(out.items[0]?.id).toBe("it-puglia");
    expect(fetchImpl).toHaveBeenCalledOnce();
    const url = fetchImpl.mock.calls[0]?.[0];
    expect(url).toBe("http://api/api/aoi");
  });

  it("propagates the abort signal", async () => {
    const fetchImpl = vi.fn().mockImplementation(async (_, init: RequestInit) => {
      // emulate fetch: throw if signal is already aborted
      if (init.signal?.aborted) {
        const err = new Error("aborted");
        err.name = "AbortError";
        throw err;
      }
      return new Response("{}", { status: 200 });
    });
    const client = new ApiClient({ baseUrl: "http://api", fetchImpl });
    const ctrl = new AbortController();
    ctrl.abort();
    await expect(client.getAoiList(ctrl.signal)).rejects.toThrow();
  });

  it("throws ApiClientError on non-2xx", async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "not found" }), { status: 404 }),
    );
    const client = new ApiClient({ baseUrl: "http://api", fetchImpl });
    await expect(client.getLatestRisk("missing")).rejects.toThrow(
      ApiClientError,
    );
  });

  it("encodes path parameters", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(new Response("{}", { status: 200 }));
    const client = new ApiClient({ baseUrl: "http://api", fetchImpl });
    await client.getCellBreakdown("aoi|0|0");
    const url = fetchImpl.mock.calls[0]?.[0];
    expect(url).toBe("http://api/api/cell/aoi%7C0%7C0/breakdown");
  });

  it("serialises alerts query params", async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [] }), { status: 200 }),
    );
    const client = new ApiClient({ baseUrl: "http://api", fetchImpl });
    await client.getAlerts({ threshold: "VeryHigh", sinceHours: 24, limit: 50 });
    const url = fetchImpl.mock.calls[0]?.[0] as string;
    expect(url).toContain("threshold=VeryHigh");
    expect(url).toContain("since_hours=24");
    expect(url).toContain("limit=50");
  });
});
