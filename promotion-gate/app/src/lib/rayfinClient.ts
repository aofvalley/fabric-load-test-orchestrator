import { RayfinClient } from '@microsoft/rayfin-client';
import { initEmbeddedAuth, ensureSignedInWithFabric, type FabricAuthOptions } from '@microsoft/rayfin-auth-provider-fabric';
import type { PromotionGateSchema } from '../../rayfin/data/schema.js';
import { env } from './env';

/** Cliente de la base de datos de la app (historial de runs). No toca Fabric: eso va con el token MSAL. */
export const client = new RayfinClient<PromotionGateSchema>({
  baseUrl: env.rayfinApiUrl || window.location.origin,
  publishableKey: env.rayfinPublishableKey,
  authStorage: true,
});

const fabricOptions: FabricAuthOptions = {
  workspaceId: env.fabricWorkspaceId,
  projectId: env.fabricItemId,
  fabricPortalUrl: env.fabricPortalUrl,
  returnOrigin: window.location.origin,
};

/** Sesión sin popup: viva, refrescable o por el handoff del iframe de Fabric. */
export async function ensureRayfinSession(): Promise<boolean> {
  if (!env.fabricItemId || !env.rayfinApiUrl) return false;
  try {
    const s = await initEmbeddedAuth(client.auth, fabricOptions);
    if (s?.isAuthenticated) return true;
  } catch { /* fuera de Fabric o sin sesión refrescable */ }
  return client.auth.getSession()?.isAuthenticated ?? false;
}

/** Inicio de sesión interactivo en Rayfin (desde un clic). */
export async function signInRayfin(): Promise<boolean> {
  const s = await ensureSignedInWithFabric(client.auth, fabricOptions);
  return s?.isAuthenticated ?? false;
}

export function rayfinUser(): { id?: string; email?: string } {
  try {
    const u = client.auth.getSession()?.user;
    return { id: u?.id ?? undefined, email: u?.email ?? undefined };
  } catch {
    return {};
  }
}
