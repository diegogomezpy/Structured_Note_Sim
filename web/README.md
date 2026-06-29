# Web front-end

The React + TypeScript (Vite) single-page app for the Structured Note Simulator.
It talks to the FastAPI backend over `/api`; in dev, Vite proxies `/api` to
`http://localhost:8010` (see `vite.config.ts`).

## Develop

```bash
npm install
npm run dev        # http://localhost:5173 — start the FastAPI backend separately:
                   #   uvicorn api.main:app --reload --port 8010   (from the repo root)
```

## Scripts

| Command | What it does |
|---------|--------------|
| `npm run dev` | Vite dev server with HMR |
| `npm run build` | `tsc -b && vite build` → `dist/` (type-check + production bundle) |
| `npm run preview` | Serve the built `dist/` locally |
| `npm run lint` | Oxlint |

## Layout

- `src/App.tsx` — top-level page (setup → results tabs)
- `src/components/` — UI (charts, panels, report builder, path explorer, tour, …)
- `src/api/` — typed client + response shapes (`client.ts`, `types.ts`)
- `src/lib/` — helpers (local folders, metrics cache, …)
- `src/i18n/` — EN/ES string registry
- `src/theme/` — palette/tokens

The production image builds this bundle in a dedicated Docker stage; FastAPI then
serves `dist/` same-origin alongside the API (see the repo-root `Dockerfile`).
