import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Local dev: `npm run dev` on :5173 proxies API calls to a locally
    // running `uvicorn api:app` on :8000, so the app works identically
    // in dev and in the production build (where FastAPI serves this
    // same origin and no proxy/CORS is needed at all).
    proxy: {
      '/health': 'http://localhost:8000',
      '/agents': 'http://localhost:8000',
      '/run': 'http://localhost:8000',
      '/execute': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
