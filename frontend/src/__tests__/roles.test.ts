import { describe, expect, it } from "vitest";

import { hasMlOpsRole } from "../lib/roles";

describe("hasMlOpsRole", () => {
  it("accepts ml-ops and admin", () => {
    expect(hasMlOpsRole(["ml-ops"])).toBe(true);
    expect(hasMlOpsRole(["viewer", "admin"])).toBe(true);
  });
  it("rejects other or missing roles", () => {
    expect(hasMlOpsRole(["operatore", "viewer"])).toBe(false);
    expect(hasMlOpsRole([])).toBe(false);
    expect(hasMlOpsRole(null)).toBe(false);
    expect(hasMlOpsRole(undefined)).toBe(false);
  });
});
