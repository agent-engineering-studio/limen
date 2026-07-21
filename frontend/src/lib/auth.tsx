// Auth su database (sostituisce Clerk). Context che risolve la sessione via
// GET /api/auth/me (cookie httpOnly), ed espone login/logout + il check ruoli.
// `admin` implica ogni ruolo (come lato server).

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { AuthUser } from "../types";
import { defaultApiClient } from "./api-client";

interface AuthContextValue {
  user: AuthUser | null;
  ready: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (role: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const me = await defaultApiClient.getMe();
      setUser(me.user);
    } catch {
      setUser(null); // 401 (no session) or backend down ⇒ signed out
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      const me = await defaultApiClient.login(email, password);
      setUser(me.user);
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await defaultApiClient.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const hasRole = useCallback(
    (role: string) => {
      const roles = user?.roles ?? [];
      return roles.includes(role) || roles.includes("admin");
    },
    [user],
  );

  const value = useMemo(
    () => ({ user, ready, refresh, login, logout, hasRole }),
    [user, ready, refresh, login, logout, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within <AuthProvider>");
  }
  return ctx;
}
