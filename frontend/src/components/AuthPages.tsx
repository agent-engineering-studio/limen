// Pagine di autenticazione (auth su DB, no Clerk): accesso, registrazione,
// verifica email tramite codice. Form controllati, messaggi in italiano.
// SPID: bottone presente ma disabilitato (arriva nella fase D, seam OIDC).

import { useState, type FormEvent } from "react";

import { ApiClientError, defaultApiClient } from "../lib/api-client";
import { useAuth } from "../lib/auth";

function errorMessage(err: unknown): string {
  if (err instanceof ApiClientError) {
    const body = err.body as { detail?: unknown } | null;
    if (body && typeof body.detail === "string") return body.detail;
    if (err.status === 422) return "Dati non validi: controlla i campi.";
  }
  return "Qualcosa è andato storto. Riprova.";
}

function SpidButton(): JSX.Element {
  return (
    <button type="button" className="btn-ghost auth-spid" disabled title="Disponibile a breve">
      Entra con SPID <span className="auth-soon">(in arrivo)</span>
    </button>
  );
}

export function LoginPage(): JSX.Element {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      window.location.hash = "#/dashboard";
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-form" aria-label="Accedi">
      <h2>Accedi</h2>
      <form onSubmit={onSubmit}>
        <label htmlFor="login-email">Email</label>
        <input
          id="login-email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <label htmlFor="login-password">Password</label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Accesso…" : "Accedi"}
        </button>
      </form>
      <div className="auth-alt">
        <SpidButton />
      </div>
      <p className="auth-links">
        Non hai un account? <a href="#/registrati">Registrati</a>
      </p>
    </div>
  );
}

export function RegisterPage(): JSX.Element {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await defaultApiClient.register({
        first_name: firstName,
        last_name: lastName,
        email,
        password,
      });
      sessionStorage.setItem("limen_verify_email", email);
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div className="auth-form" aria-label="Registrazione">
        <h2>Controlla la tua email</h2>
        <p>
          Se l&rsquo;indirizzo è valido riceverai un codice di verifica. Inseriscilo
          nella pagina di conferma per attivare l&rsquo;account.
        </p>
        <a className="btn-primary" href="#/verifica">
          Inserisci il codice
        </a>
      </div>
    );
  }

  return (
    <div className="auth-form" aria-label="Registrazione">
      <h2>Registrati</h2>
      <form onSubmit={onSubmit}>
        <label htmlFor="reg-first">Nome</label>
        <input id="reg-first" value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
        <label htmlFor="reg-last">Cognome</label>
        <input id="reg-last" value={lastName} onChange={(e) => setLastName(e.target.value)} required />
        <label htmlFor="reg-email">Email</label>
        <input
          id="reg-email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <label htmlFor="reg-password">Password (min 8 caratteri)</label>
        <input
          id="reg-password"
          type="password"
          autoComplete="new-password"
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Invio…" : "Crea account"}
        </button>
      </form>
      <div className="auth-alt">
        <SpidButton />
      </div>
      <p className="auth-links">
        Hai già un account? <a href="#/accedi">Accedi</a>
      </p>
    </div>
  );
}

export function VerifyEmailPage(): JSX.Element {
  const [email, setEmail] = useState(() => sessionStorage.getItem("limen_verify_email") ?? "");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await defaultApiClient.verifyEmail(email, code);
      sessionStorage.removeItem("limen_verify_email");
      window.location.hash = "#/accedi";
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const resend = async (): Promise<void> => {
    setError(null);
    setNotice(null);
    try {
      await defaultApiClient.resendCode(email);
      setNotice("Se l'indirizzo è valido, ti abbiamo inviato un nuovo codice.");
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div className="auth-form" aria-label="Verifica email">
      <h2>Verifica email</h2>
      <p>Inserisci il codice ricevuto via email.</p>
      <form onSubmit={onSubmit}>
        <label htmlFor="ver-email">Email</label>
        <input
          id="ver-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <label htmlFor="ver-code">Codice</label>
        <input
          id="ver-code"
          inputMode="numeric"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          required
        />
        {error && <p className="auth-error" role="alert">{error}</p>}
        {notice && <p className="auth-notice">{notice}</p>}
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Verifica…" : "Verifica"}
        </button>
      </form>
      <p className="auth-links">
        <button type="button" className="auth-linkbtn" onClick={resend}>
          Reinvia il codice
        </button>
      </p>
    </div>
  );
}
