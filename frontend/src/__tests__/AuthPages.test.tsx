import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { login, register } = vi.hoisted(() => ({
  login: vi.fn(() => Promise.resolve()),
  register: vi.fn(() => Promise.resolve({ message: "ok" })),
}));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ login }) }));
vi.mock("../lib/api-client", () => ({
  ApiClientError: class extends Error {},
  defaultApiClient: { register },
}));

import { LoginPage, RegisterPage, VerifyEmailPage } from "../components/AuthPages";

describe("LoginPage", () => {
  it("submits email + password and links to registration", async () => {
    render(<LoginPage />);
    expect(screen.getByRole("link", { name: /Registrati/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.it" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "Accedi" }));
    await waitFor(() => expect(login).toHaveBeenCalledWith("a@b.it", "password123"));
  });

  it("shows a disabled SPID button", () => {
    render(<LoginPage />);
    expect(screen.getByRole("button", { name: /Entra con SPID/ })).toBeDisabled();
  });
});

describe("RegisterPage", () => {
  it("registers then shows the check-your-email screen", async () => {
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Mario" } });
    fireEvent.change(screen.getByLabelText("Cognome"), { target: { value: "Rossi" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "m@r.it" } });
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "Crea account" }));
    await waitFor(() =>
      expect(screen.getByText(/Controlla la tua email/)).toBeInTheDocument(),
    );
    expect(register).toHaveBeenCalledWith({
      first_name: "Mario",
      last_name: "Rossi",
      email: "m@r.it",
      password: "password123",
    });
  });
});

describe("VerifyEmailPage", () => {
  it("renders the code field", () => {
    render(<VerifyEmailPage />);
    expect(screen.getByLabelText("Codice")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verifica" })).toBeInTheDocument();
  });
});
