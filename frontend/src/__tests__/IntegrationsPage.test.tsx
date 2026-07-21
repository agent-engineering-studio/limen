import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IntegrationsPage } from "../components/IntegrationsPage";

describe("IntegrationsPage", () => {
  it("documents both MCP servers with their tools", () => {
    render(<IntegrationsPage />);
    expect(screen.getByText("Integrazioni: MCP & A2A")).toBeInTheDocument();
    // limen-ops read + admin tools
    expect(screen.getByText("tool_national_report()")).toBeInTheDocument();
    expect(screen.getByText("tool_build_report(admin_token)")).toBeInTheDocument();
    // ispra-geo geodata tools
    expect(screen.getByText("tool_hazard_at(lat, lon)")).toBeInTheDocument();
  });

  it("documents the A2A surface: agent card, endpoint, skills, streaming", () => {
    render(<IntegrationsPage />);
    expect(screen.getByText(/agent-card\.json/)).toBeInTheDocument();
    // skills appear (national_report is both a skill and default)
    expect(screen.getAllByText(/national_report/).length).toBeGreaterThan(0);
    // JSON-RPC methods mentioned in the examples
    expect(screen.getAllByText(/message\/send/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/message\/stream/).length).toBeGreaterThan(0);
  });
});
