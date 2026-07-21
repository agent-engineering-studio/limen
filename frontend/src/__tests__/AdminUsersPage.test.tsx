import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { adminListUsers, adminUpdateUser, adminCreateUser } = vi.hoisted(() => ({
  adminListUsers: vi.fn(),
  adminUpdateUser: vi.fn(),
  adminCreateUser: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../lib/api-client", () => ({
  ApiClientError: class extends Error {},
  defaultApiClient: { adminListUsers, adminUpdateUser, adminCreateUser },
}));

import { AdminUsersPage } from "../components/AdminUsersPage";

const USER = {
  id: "u1",
  email: "op@limen.test",
  first_name: "Ada",
  last_name: "Op",
  email_verified: true,
  status: "active",
  roles: ["operatore"],
};

describe("AdminUsersPage", () => {
  it("lists users and saves a role change", async () => {
    adminListUsers.mockResolvedValue({ users: [USER] });
    adminUpdateUser.mockResolvedValue({ ...USER, roles: ["operatore", "ml-ops"] });
    render(<AdminUsersPage />);

    await waitFor(() => expect(screen.getByText("op@limen.test")).toBeInTheDocument());

    // Save is disabled until something changes.
    const save = screen.getByRole("button", { name: "Salva" });
    expect(save).toBeDisabled();

    // Toggle the ml-ops role for the row (last checkbox; the create form has
    // its own ml-ops checkbox rendered first) → Save enables → click saves.
    const rowMlOps = screen.getAllByLabelText("ml-ops").at(-1);
    if (!rowMlOps) throw new Error("row ml-ops checkbox not found");
    fireEvent.click(rowMlOps);
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() =>
      expect(adminUpdateUser).toHaveBeenCalledWith("u1", ["operatore", "ml-ops"], "active"),
    );
  });

  it("renders the create-user form", async () => {
    adminListUsers.mockResolvedValue({ users: [] });
    render(<AdminUsersPage />);
    expect(screen.getByRole("heading", { name: "Nuovo utente" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Password/)).toBeInTheDocument();
  });
});
