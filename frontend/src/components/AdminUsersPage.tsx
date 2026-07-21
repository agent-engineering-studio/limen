// Dashboard admin (solo ruolo admin): elenco utenti con modifica ruoli/stato e
// creazione di nuovi account. Chiama /api/admin/*. Gating lato server (403 se
// non admin) — questa pagina è comunque montata dietro RequireRole("admin").

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ApiClientError, defaultApiClient } from "../lib/api-client";
import { ALL_ROLES, type AdminUser } from "../types";

function errorMessage(err: unknown): string {
  if (err instanceof ApiClientError) {
    const body = err.body as { detail?: unknown } | null;
    if (body && typeof body.detail === "string") return body.detail;
  }
  return "Operazione non riuscita.";
}

function RolePicker({
  roles,
  onToggle,
}: {
  roles: string[];
  onToggle: (role: string) => void;
}): JSX.Element {
  return (
    <div className="admin-roles">
      {ALL_ROLES.map((r) => (
        <label key={r} className="admin-role">
          <input type="checkbox" checked={roles.includes(r)} onChange={() => onToggle(r)} />
          {r}
        </label>
      ))}
    </div>
  );
}

function UserRow({ user, onSaved }: { user: AdminUser; onSaved: (u: AdminUser) => void }): JSX.Element {
  const [roles, setRoles] = useState<string[]>(user.roles);
  const [status, setStatus] = useState(user.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty = status !== user.status || roles.slice().sort().join() !== user.roles.slice().sort().join();

  const toggle = (r: string): void =>
    setRoles((cur) => (cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r]));

  const save = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const updated = await defaultApiClient.adminUpdateUser(user.id, roles, status);
      onSaved(updated);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <tr className={status === "disabled" ? "admin-disabled" : ""}>
      <td>
        <strong>
          {user.first_name} {user.last_name}
        </strong>
        <br />
        <span className="admin-email">{user.email}</span>
        {!user.email_verified && <span className="admin-badge">non verificato</span>}
      </td>
      <td>
        <RolePicker roles={roles} onToggle={toggle} />
      </td>
      <td>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="active">attivo</option>
          <option value="disabled">disabilitato</option>
        </select>
      </td>
      <td>
        <button type="button" className="btn-signin" disabled={!dirty || busy} onClick={save}>
          {busy ? "…" : "Salva"}
        </button>
        {error && <span className="auth-error"> {error}</span>}
      </td>
    </tr>
  );
}

function CreateForm({ onCreated }: { onCreated: () => void }): JSX.Element {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [roles, setRoles] = useState<string[]>(["viewer"]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const toggle = (r: string): void =>
    setRoles((cur) => (cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r]));

  const onSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await defaultApiClient.adminCreateUser({
        first_name: firstName,
        last_name: lastName,
        email,
        password,
        roles,
      });
      setFirstName("");
      setLastName("");
      setEmail("");
      setPassword("");
      setRoles(["viewer"]);
      onCreated();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="admin-create" onSubmit={onSubmit} aria-label="Crea utente">
      <h3>Nuovo utente</h3>
      <div className="admin-create-grid">
        <input placeholder="Nome" value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
        <input placeholder="Cognome" value={lastName} onChange={(e) => setLastName(e.target.value)} required />
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input
          type="password"
          placeholder="Password (min 8)"
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      <RolePicker roles={roles} onToggle={toggle} />
      {error && <p className="auth-error" role="alert">{error}</p>}
      <button type="submit" className="btn-primary" disabled={busy}>
        {busy ? "Creazione…" : "Crea account"}
      </button>
    </form>
  );
}

export function AdminUsersPage(): JSX.Element {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (q: string): Promise<void> => {
    setError(null);
    try {
      const res = await defaultApiClient.adminListUsers(q || undefined);
      setUsers(res.users);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => void load(query), 250);
    return () => clearTimeout(t);
  }, [query, load]);

  const onSaved = (u: AdminUser): void =>
    setUsers((cur) => cur.map((x) => (x.id === u.id ? u : x)));

  return (
    <div className="explainer admin-page" aria-label="Gestione utenti">
      <article>
        <p className="exp-eyebrow">Amministrazione</p>
        <h2>Gestione utenti</h2>
        <CreateForm onCreated={() => void load(query)} />
        <div className="admin-search">
          <input
            type="search"
            placeholder="Cerca per nome o email…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Cerca utenti"
          />
        </div>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <table className="int-table admin-table">
          <thead>
            <tr>
              <th>Utente</th>
              <th>Ruoli</th>
              <th>Stato</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <UserRow key={u.id} user={u} onSaved={onSaved} />
            ))}
          </tbody>
        </table>
        {users.length === 0 && <p className="exp-note">Nessun utente.</p>}
      </article>
    </div>
  );
}

export default AdminUsersPage;
