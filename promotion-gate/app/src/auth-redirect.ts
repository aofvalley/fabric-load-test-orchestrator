import { broadcastResponseToMainFrame } from '@azure/msal-browser/redirect-bridge';

broadcastResponseToMainFrame().catch((err: unknown) => {
  document.body.textContent = `No se pudo completar el inicio de sesión: ${err instanceof Error ? err.message : String(err)}`;
});
