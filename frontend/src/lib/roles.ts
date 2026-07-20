// Ruoli Clerk per il gating dell'area di diagnostica ML (#26).
//
// Il ruolo va assegnato lato Clerk (dashboard): `publicMetadata.role = "ml-ops"`
// oppure `publicMetadata.roles = ["ml-ops"]`. `admin` è equivalente. Senza il
// ruolo l'operatore di campo non vede la diagnostica — solo il pannellino
// rassicurante nella dashboard.

import { useUser } from "@clerk/react";

const ML_OPS_ROLES = new Set(["ml-ops", "admin"]);

/** True se il metadata pubblico dell'utente porta un ruolo ml-ops/admin. */
export function hasMlOpsRole(publicMetadata: unknown): boolean {
  if (!publicMetadata || typeof publicMetadata !== "object") return false;
  const m = publicMetadata as Record<string, unknown>;
  const roles: string[] = [];
  if (typeof m.role === "string") roles.push(m.role);
  if (Array.isArray(m.roles)) roles.push(...m.roles.map(String));
  return roles.some((r) => ML_OPS_ROLES.has(r));
}

export interface MlOpsGate {
  ready: boolean;
  allowed: boolean;
}

/** Hook: l'utente corrente ha il ruolo ml-ops? `ready` false finché Clerk carica. */
export function useMlOps(): MlOpsGate {
  const { isLoaded, user } = useUser();
  return { ready: isLoaded, allowed: hasMlOpsRole(user?.publicMetadata) };
}
