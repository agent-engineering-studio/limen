-- Database-backed authentication (replaces Clerk — PA-compliant, self-hosted).
--
-- Three tables:
--   users        — identity (local password and/or SPID subject), roles, status.
--   auth_codes   — short-lived email verification / OTP codes (hashed).
--   sessions     — server-side sessions; the cookie carries an opaque token,
--                  `id` stores its SHA-256 so a DB leak can't mint sessions.
--
-- Email is case-insensitive (citext). Passwords are scrypt-hashed in app code
-- (never plaintext here). SPID wiring (spid_subject) lands in a later phase.
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE IF NOT EXISTS users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email          citext NOT NULL UNIQUE,
    first_name     text NOT NULL,
    last_name      text NOT NULL,
    password_hash  text,
    email_verified boolean NOT NULL DEFAULT false,
    status         text NOT NULL DEFAULT 'active',
    roles          text[] NOT NULL DEFAULT '{}',
    spid_subject   text UNIQUE,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_codes (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    code_hash   text NOT NULL,
    purpose     text NOT NULL,
    expires_at  timestamptz NOT NULL,
    consumed_at timestamptz,
    attempts    int NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS auth_codes_user_purpose_idx ON auth_codes (user_id, purpose);

CREATE TABLE IF NOT EXISTS sessions (
    id           text PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    user_agent   text,
    ip           inet
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);
