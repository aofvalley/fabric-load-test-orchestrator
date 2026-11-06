/// <reference types="vite/client" />

interface ImportMetaEnv {
  // .env.local, generado por Rayfin
  readonly VITE_PORT?: string;
  readonly VITE_RAYFIN_API_URL?: string;
  readonly VITE_RAYFIN_PUBLISHABLE_KEY?: string;
  readonly VITE_FABRIC_WORKSPACE_ID?: string;
  readonly VITE_FABRIC_ITEM_ID?: string;
  readonly VITE_FABRIC_TENANT_ID?: string;
  readonly VITE_FABRIC_PORTAL_URL?: string;
  // .env, propio de la app
  readonly VITE_MSAL_CLIENT_ID?: string;
  readonly VITE_MSAL_TENANT_ID?: string;
  readonly VITE_GATE_WORKSPACE_ID?: string;
  readonly VITE_GATE_LAKEHOUSE_ID?: string;
  readonly VITE_CAPACITY_METRICS_WORKSPACE?: string;
  readonly VITE_DEMO_MODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
