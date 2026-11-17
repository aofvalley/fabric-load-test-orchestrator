import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Rayfin escribe VITE_PORT en .env.local y registra ese origen en el backend: el puerto no puede cambiar en silencio.
export default defineConfig(({ mode }) => {
  const port = Number(loadEnv(mode, process.cwd(), 'VITE_').VITE_PORT) || 5173;
  return {
    plugins: [react()],
    build: {
      outDir: 'dist',
      target: 'es2022',
      // blank.html: retorno del login de MSAL. popup-relay.html: login desde el iframe del portal de Fabric.
      rollupOptions: { input: { main: 'index.html', blank: 'blank.html', relay: 'popup-relay.html' } },
    },
    server: { port, strictPort: true, host: 'localhost' },
    preview: { port, strictPort: true, host: 'localhost' },
    test: { environment: 'jsdom', include: ['src/**/*.test.ts'] },
  };
});
