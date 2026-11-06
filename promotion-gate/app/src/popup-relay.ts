import { runPopupRelay } from '@azure/msal-browser/popup-relay';

const button = document.getElementById('go') as HTMLButtonElement;
const msg = document.getElementById('msg') as HTMLParagraphElement;

// El popup del proveedor se abre desde un clic para que el navegador no lo bloquee.
button.addEventListener('click', () => {
  button.disabled = true;
  msg.textContent = 'Completa el inicio de sesión en la ventana de Microsoft.';
  try {
    runPopupRelay({ allowedAuthorityOrigins: ['https://login.microsoftonline.com'] });
  } catch (err) {
    button.disabled = false;
    msg.textContent = `No se pudo abrir el inicio de sesión: ${err instanceof Error ? err.message : String(err)}`;
  }
});
