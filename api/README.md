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

## Config
- **`ALLOWED_ORIGINS`** — comma-separated CORS origins. Defaults to `*` (dev).
  Set to your Pages origin in production.

## Notes
- The heavy calibrate+simulate step is memoised (`lru_cache`) per request signature.
- Charts render client-side from figure JSON, so **Chromium is only needed for
  `/pdf`** — `/simulate` works regardless. In a locked-down container, if PDF
  export fails the server logs print `[PDF figure] to_image failed (…)` and the
  rest of the API is unaffected.
- Free-tier hosts cold-start; the first `/simulate` after idle will be slow.
