// Gating per ruolo dell'area di diagnostica ML (#26). I ruoli arrivano ora
// dall'auth su database (GET /api/auth/me) via AuthContext, non da Clerk.
// `admin` è equivalente a ml-ops.

import { useAuth } from "./auth";

const ML_OPS_ROLES = new Set(["ml-ops", "admin"]);

/** True se la lista ruoli dell'utente contiene ml-ops (o admin). */
export function hasMlOpsRole(roles: readonly string[] | null | undefined): boolean {
  if (!roles) return false;
  return roles.some((r) => ML_OPS_ROLES.has(r));
}

export interface MlOpsGate {
  ready: boolean;
  allowed: boolean;
}

/** Hook: l'utente corrente ha il ruolo ml-ops? `ready` false finché /me carica. */
export function useMlOps(): MlOpsGate {
  const { ready, user } = useAuth();
  return { ready, allowed: hasMlOpsRole(user?.roles) };
}
