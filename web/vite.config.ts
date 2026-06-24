import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api → the FastAPI backend (uvicorn on :8000), so the
// browser talks same-origin and we don't depend on CORS in development.
// In the Phase ⑤ single-image build, FastAPI serves the built bundle instead.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
      },
    },
  },
})
