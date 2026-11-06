const e = import.meta.env;

/**
 * Configuración en dos ficheros:
 * - `.env.local`: lo genera Rayfin (`rayfin up`, `rayfin dev` o `rayfin env`) a partir de `rayfin/.env`. Backend de la app.
 * - `.env`: lo escribe `deploy/deploy.ps1` (o a mano desde `.env.example`). MSAL y el workspace del gate.
 */
export const env = {
  rayfinApiUrl: e.VITE_RAYFIN_API_URL ?? '',
  rayfinPublishableKey: e.VITE_RAYFIN_PUBLISHABLE_KEY ?? '',
  fabricWorkspaceId: e.VITE_FABRIC_WORKSPACE_ID ?? '',
  fabricItemId: e.VITE_FABRIC_ITEM_ID ?? '',
  fabricPortalUrl: e.VITE_FABRIC_PORTAL_URL || 'https://app.fabric.microsoft.com',
  msalClientId: e.VITE_MSAL_CLIENT_ID ?? '',
  msalTenantId: e.VITE_MSAL_TENANT_ID || e.VITE_FABRIC_TENANT_ID || 'organizations',
  gateWorkspaceId: e.VITE_GATE_WORKSPACE_ID ?? '',
  gateLakehouseId: e.VITE_GATE_LAKEHOUSE_ID ?? '',
  capacityMetricsWorkspace: e.VITE_CAPACITY_METRICS_WORKSPACE ?? '',
  demo: (e.VITE_DEMO_MODE ?? '').toLowerCase() === 'true',
};

/** Qué falta para trabajar contra Fabric real. Vacío = listo. Sin backend Rayfin el historial va al navegador. */
export function missingConfig(): string[] {
  if (env.demo) return [];
  const missing: string[] = [];
  if (!env.msalClientId) missing.push('VITE_MSAL_CLIENT_ID');
  if (!env.gateWorkspaceId) missing.push('VITE_GATE_WORKSPACE_ID');
  if (!env.gateLakehouseId) missing.push('VITE_GATE_LAKEHOUSE_ID');
  return missing;
}
