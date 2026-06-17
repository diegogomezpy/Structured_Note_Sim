# Web frontend (static, GitHub Pages)

A zero-build static site (`index.html` + `app.js` + `styles.css`) that drives the
FastAPI backend in [`../api`](../api). Plotly.js (from CDN) renders the figure
JSON the API returns, so the charts match the Streamlit app and the PDF.

## Run locally

Start the backend and serve the static files:

```bash
# 1) backend
uvicorn api.main:app --reload --port 8000
# 2) frontend (any static server)
python -m http.server 8530 --directory web
```

Open http://localhost:8530. It auto-targets `http://localhost:8000` for the API.

## Pointing at a deployed backend

The API base URL resolves in this order:

1. `?api=https://your-backend` query parameter
2. saved value from the **API** box in the top-right (stored in `localStorage`)
3. same origin (if the API is reverse-proxied alongside the site)
4. `http://localhost:8000` (dev fallback)

On GitHub Pages, open the **API** panel once and paste your backend URL, or link
people with `?api=https://your-backend`.

## Deploy to GitHub Pages

`.github/workflows/pages.yml` publishes this folder on every push to `main`.
Enable it once: **Settings → Pages → Source: GitHub Actions**.

The backend must be hosted separately (it runs Python: calibration, Monte Carlo,
yfinance, PDF) — e.g. Render/Railway/Fly — and its CORS `ALLOWED_ORIGINS` must
include your Pages origin (e.g. `https://you.github.io`).
