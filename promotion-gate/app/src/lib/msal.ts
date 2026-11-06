import { InteractionRequiredAuthError, PublicClientApplication, type AccountInfo } from '@azure/msal-browser';
import { env } from './env';

/**
 * Tokens delegados del usuario para Fabric, Power BI y OneLake. Registro SPA propio (sin secreto, PKCE).
 * Separado de la sesión Rayfin, que solo da acceso a la base de datos de la app.
 * Consentimiento incremental: cada grupo de scopes se pide la primera vez que hace falta y siempre desde un clic.
 */
export const SCOPES = {
  fabricRead: [
    'https://api.fabric.microsoft.com/Workspace.Read.All',
    'https://api.fabric.microsoft.com/Item.Read.All',
  ],
  fabricRun: [
    'https://api.fabric.microsoft.com/Workspace.Read.All',
    'https://api.fabric.microsoft.com/Item.Read.All',
    'https://api.fabric.microsoft.com/Item.Execute.All',
  ],
  fabricDeploy: [
    'https://api.fabric.microsoft.com/Pipeline.Read.All',
    'https://api.fabric.microsoft.com/Pipeline.Deploy',
  ],
  powerbi: [
    'https://analysis.windows.net/powerbi/api/Report.Read.All',
    'https://analysis.windows.net/powerbi/api/Dataset.Read.All',
  ],
  onelake: ['https://storage.azure.com/user_impersonation'],
} as const;

export type ScopeSet = keyof typeof SCOPES;

export class SignInRequiredError extends Error {
  constructor(public readonly scopeSet: ScopeSet) {
    super('Hace falta iniciar sesión o dar consentimiento');
    this.name = 'SignInRequiredError';
  }
}

const msal = new PublicClientApplication({
  auth: {
    clientId: env.msalClientId || '00000000-0000-0000-0000-000000000000',
    authority: `https://login.microsoftonline.com/${env.msalTenantId}`,
    // Página en blanco: la renovación silenciosa en iframe no recarga la SPA (block_iframe_reload).
    redirectUri: `${window.location.origin}/blank.html`,
    // En el iframe del portal el almacenamiento está particionado: el popup devuelve la respuesta por esta página.
    popupRelayUri: window.top !== window.self ? `${window.location.origin}/popup-relay.html` : undefined,
  },
  cache: { cacheLocation: 'sessionStorage' },
});

let ready: Promise<void> | null = null;
function init(): Promise<void> {
  ready ??= msal.initialize().then(async () => {
    const r = await msal.handleRedirectPromise().catch(() => null);
    if (r?.account) msal.setActiveAccount(r.account);
  });
  return ready;
}

function account(): AccountInfo | null {
  return msal.getActiveAccount() ?? msal.getAllAccounts()[0] ?? null;
}

let loginHint: string | undefined;
export function setLoginHint(hint: string | undefined) {
  loginHint = hint;
}

export async function getToken(
  set: ScopeSet,
  opts: { interactive?: boolean; forceRefresh?: boolean; extraScopesToConsent?: string[] } = {},
): Promise<string> {
  await init();
  const scopes = [...SCOPES[set]];
  const acc = account();
  try {
    if (!acc) throw new InteractionRequiredAuthError('no_account', 'No hay cuenta en la caché de MSAL');
    const r = await msal.acquireTokenSilent({ scopes, account: acc, forceRefresh: opts.forceRefresh });
    return r.accessToken;
  } catch (err) {
    if (acc && !(err instanceof InteractionRequiredAuthError)) throw err;
    if (!opts.interactive) throw new SignInRequiredError(set);
    // Popup: desde un gesto del usuario es la única vía fiable dentro del iframe del portal de Fabric.
    const r = await msal.acquireTokenPopup({
      scopes, loginHint, prompt: acc ? undefined : 'select_account', extraScopesToConsent: opts.extraScopesToConsent,
    });
    msal.setActiveAccount(r.account);
    return r.accessToken;
  }
}

const EXTRA_CONSENT = [...SCOPES.fabricRun, ...SCOPES.powerbi, ...SCOPES.onelake]
  .filter((s) => !(SCOPES.fabricRead as readonly string[]).includes(s));

/**
 * Un solo popup: token de lectura de Fabric y consentimiento del resto (ejecución, Power BI, OneLake), para que después
 * todo se obtenga en silencio. Dentro del iframe del portal cada popup extra es fricción.
 */
export async function signIn(): Promise<AccountInfo | null> {
  await getToken('fabricRead', { interactive: true, extraScopesToConsent: EXTRA_CONSENT });
  return account();
}

/** Para sesiones abiertas antes de pedir todos los scopes: fuerza el popup de consentimiento (siempre desde un clic). */
export async function grantAccess(): Promise<void> {
  await init();
  const r = await msal.acquireTokenPopup({
    scopes: [...SCOPES.fabricRead], account: account() ?? undefined, extraScopesToConsent: EXTRA_CONSENT,
  });
  msal.setActiveAccount(r.account);
}

export async function currentAccount(): Promise<AccountInfo | null> {
  await init();
  return account();
}
