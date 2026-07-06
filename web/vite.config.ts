import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api → the FastAPI backend (uvicorn on :8000), so the
// browser talks same-origin and we don't depend on CORS in development.
// In the Phase ⑤ single-image build, FastAPI serves the built bundle instead.
export default defineConfig({
  plugins: [react()],
  // The custom modular Plotly bundle (src/lib/plotly.ts) deep-imports plotly.js's
  // CJS entrypoints; Vite's dev optimizer must pre-bundle them or the huge source
  // tree fails to load in dev. (The production rolldown build handles it already.)
  optimizeDeps: {
    include: [
      'plotly.js/lib/core',
      'plotly.js/lib/bar',
      'plotly.js/lib/histogram',
      'plotly.js/lib/scatter',
      'plotly.js/lib/pie',
      'plotly.js/lib/heatmap',
    ],
  },
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
