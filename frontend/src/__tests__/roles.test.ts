import { describe, expect, it } from "vitest";

import { hasMlOpsRole } from "../lib/roles";

describe("hasMlOpsRole", () => {
  it("accepts a single role string", () => {
    expect(hasMlOpsRole({ role: "ml-ops" })).toBe(true);
    expect(hasMlOpsRole({ role: "admin" })).toBe(true);
  });
  it("accepts a roles array", () => {
    expect(hasMlOpsRole({ roles: ["viewer", "ml-ops"] })).toBe(true);
  });
  it("rejects other or missing roles", () => {
    expect(hasMlOpsRole({ role: "operator" })).toBe(false);
    expect(hasMlOpsRole({})).toBe(false);
    expect(hasMlOpsRole(null)).toBe(false);
    expect(hasMlOpsRole(undefined)).toBe(false);
  });
});
