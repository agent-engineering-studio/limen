import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IntegrationsPage } from "../components/IntegrationsPage";
import { render as renderLingua } from "../test-utils";

describe("IntegrationsPage", () => {
  it("documents both MCP servers with their tools", () => {
    render(<IntegrationsPage />);
    expect(screen.getByText("Integrazioni: API, MCP & A2A")).toBeInTheDocument();
    // limen-ops read + admin tools
    expect(screen.getByText("tool_national_report()")).toBeInTheDocument();
    expect(screen.getByText("tool_build_report(admin_token)")).toBeInTheDocument();
    // ispra-geo geodata tools
    expect(screen.getByText("tool_hazard_at(lat, lon)")).toBeInTheDocument();
  });

  it("documents the A2A surface: agent card, endpoint, skills, streaming", () => {
    render(<IntegrationsPage />);
    expect(screen.getAllByText(/agent-card\.json/).length).toBeGreaterThan(0);
    // skills appear (national_report is both a skill and default)
    expect(screen.getAllByText(/national_report/).length).toBeGreaterThan(0);
    // JSON-RPC methods mentioned in the examples
    expect(screen.getAllByText(/message\/send/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/message\/stream/).length).toBeGreaterThan(0);
    expect(screen.getByText("comune_risk")).toBeInTheDocument();
  });

  it("documents the REST API and the vector tiles", () => {
    const { container } = render(<IntegrationsPage />);
    expect(screen.getByText("GET /api/comuni?hazard=&aoi=&q=&order=now&limit=50")).toBeInTheDocument();
    expect(screen.getByText("public.forecast_at")).toBeInTheDocument();
    expect(screen.getByText("tool_top_comuni(limit?, aoi_id?)")).toBeInTheDocument();
    const hrefs = [...container.querySelectorAll(".guida-indice a")].map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(
      expect.arrayContaining(["#/integrazioni/api-rest", "#/integrazioni/tile-vettoriali", "#/integrazioni/dati-aperti-e-licenze"]),
    );
  });

  it("in inglese tiene gli stessi strumenti e le stesse ancore", () => {
    const { container } = renderLingua(<IntegrationsPage />, { lingua: "en" });
    expect(screen.getByText("Integrations: API, MCP & A2A")).toBeInTheDocument();
    expect(screen.getByText("tool_national_report()")).toBeInTheDocument();
    const hrefs = [...container.querySelectorAll(".guida-indice a")].map((a) => a.getAttribute("href"));
    expect(hrefs).toContain("#/integrazioni/a2a-interoperabilita-tra-agent");
  });
});
