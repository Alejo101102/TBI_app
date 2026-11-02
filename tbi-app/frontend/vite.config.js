import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// En dev (npm run dev): proxy /api → backend en localhost:8000.
// En prod (Nginx en el contenedor frontend): el location /api de nginx.conf
// hace el mismo trabajo apuntando al servicio "backend" del compose.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
