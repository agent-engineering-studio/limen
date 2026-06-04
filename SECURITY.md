# Security policy

## Reporting a vulnerability

If you find a security issue in Limen, **please do not open a public
GitHub issue**. Instead, write to **security@hevolus.it** with:

* a description of the issue and its impact;
* a minimal reproducer or PoC;
* the affected version(s) (commit SHA or tag).

We aim to acknowledge within **48 hours**, propose a remediation plan
within **5 working days**, and ship a fix as part of a normal patch
release. Credit is offered (and welcomed) unless you prefer
anonymity.

## Supported versions

Limen is in V1 (pre-1.0) — only the latest `main` is supported for
security fixes. Tagged releases get fixes on a best-effort basis.

## Scope

In scope:

* The Limen backend (FastAPI + workflow + scoring engine + DB layer).
* The Limen frontend SPA (`frontend/`).
* The container images we publish (`ghcr.io/agent-engineering-studio/limen-api`).
* The CI workflows under `.github/workflows/`.

Out of scope:

* Vulnerabilities in unmodified third-party dependencies — please
  report them upstream. We monitor Dependabot / GHSA advisories and
  bump promptly.
* DoS by sending the public API absurd payloads beyond the documented
  size/rate limits — that's a deployment concern, not an application
  bug.
* Issues in deprecated branches.

## Secrets handling

Limen never logs secret values:

* `pydantic.SecretStr` everywhere for API keys and passwords.
* `_redact_dsn` strips passwords from any DSN before structured
  logging.
* `LLM__PROVIDER` precedence is decided at startup; the chosen client
  prints only the provider label, never the key.

If a secret is leaked into a log, that *is* a security issue — please
report it via the channel above.

## Threat model snapshot

* The API is **unauthenticated by design in V1** (public map, §1.6
  defers auth). Treat any deployment as anonymously accessible.
* Clerk-based auth lands when the operator-protected area arrives; see
  the `production-stack` memory for the planned shape (Vite +
  `@clerk/clerk-react` on the frontend, JWT validation on the backend).
* Database access is via asyncpg with parameterised queries only — no
  string-interpolated SQL.
* Notifications run server-side; alert payloads contain only
  deterministically-derived numbers from the assessment — no PII, no
  free-text user input.
