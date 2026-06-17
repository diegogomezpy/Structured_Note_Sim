# Backend API

FastAPI service that wraps the quant engine (`core/`, `data/`) and the chart/PDF
builders (`app/charts.py`, `app/pdf_report.py`). The Streamlit app is unaffected —
this layer only imports shared code.

## Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/health`   | liveness probe |
| GET  | `/universe` | selectable underlyings + logo URLs |
| POST | `/simulate` | calibrate+simulate+price → metrics + Plotly figure JSON |
| POST | `/pdf`      | branded PDF (`application/pdf`) |

`/simulate` and `/pdf` bodies are `{ terms: <NoteTerms config>, n_paths, seed, calib_years, history_years, lang }`
(`/pdf` also takes `include_sections`, `branding`). `terms` is the same JSON shape as `note_configs/*.json`.

## Run locally
```bash
pip install -r requirements-api.txt          # or the full requirements.txt
uvicorn api.main:app --reload --port 8000
```

## Deploy with Docker
```bash
docker build -t snote-api .
docker run -p 8000:8000 -e ALLOWED_ORIGINS="https://you.github.io" snote-api
```
The image installs Chromium for kaleido (server-side PDF rasterisation). Hosts
that inject `$PORT` (Render/Railway/Fly) are handled by the `CMD`.

### Render (one click)
`render.yaml` defines the service. New → Blueprint → this repo; then set
`ALLOWED_ORIGINS` in the dashboard to your GitHub Pages origin.

## Config (env vars)
- **`ALLOWED_ORIGINS`** — comma-separated CORS origins. Defaults to `*` (dev).
  Set to your Pages origin in production.
- **`SNSIM_MAX_PATHS`** (default `8000`) — hard cap on `n_paths`; requests above
  it are clamped. Peak memory ≈ paths × steps × assets (antithetic doubles the
  input), so keep low on small instances; raise on a bigger host.
- **`SNSIM_CACHE_SIZE`** (default `3`) — how many full simulation/backtest
  results are memoised. Each holds large arrays — the main memory driver.
- **`SNSIM_MAX_CONCURRENCY`** (default `1`) — how many heavy requests run at
  once; excess get a quick `503` + `Retry-After` instead of piling up.

Rough sizing: defaults (8k paths, cache 3, concurrency 1) target a ~512 MB
free tier. On a 2 GB instance, `SNSIM_MAX_PATHS=20000`, `SNSIM_CACHE_SIZE=8`,
`SNSIM_MAX_CONCURRENCY=2` is comfortable.

## Notes
- The heavy calibrate+simulate step is memoised (`lru_cache`) per request signature.
- Charts render client-side from figure JSON, so **Chromium is only needed for
  `/pdf`** — `/simulate` works regardless. In a locked-down container, if PDF
  export fails the server logs print `[PDF figure] to_image failed (…)` and the
  rest of the API is unaffected.
- Free-tier hosts cold-start; the first `/simulate` after idle will be slow.
