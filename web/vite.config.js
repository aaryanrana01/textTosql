import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Codespaces serves the dev server through *.app.github.dev; Vite blocks unknown hosts by default.
    allowedHosts: ['.app.github.dev'],
    // In development, /api requests are forwarded to the Express API, so the browser talks to one origin only.
    proxy: { '/api': 'http://localhost:4000' },
  },
});