# Reproducible single-image build for Cloud Run. Two stages:
#   1. node   — build the React/Vite front-end (web/) into web/dist
#   2. python — FastAPI (uvicorn) serves the API *and* the built bundle
#               same-origin, with chromium bundled so the PDF figure export
#               (kaleido) works. Pins the whole environment so
#               "works locally" == "works in prod".

# ── stage 1: build the front-end ──────────────────────────────────────────────
FROM node:22-slim AS web-build
WORKDIR /web
# Install deps first so this layer caches across source-only changes.
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build          # → /web/dist (tsc -b && vite build)

# ── stage 2: python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim

# System deps:
#  - chromium        : kaleido (v1) launches it headless to rasterise Plotly → PNG
#  - fonts-*         : glyphs for the rendered figures / PDF
#  - ca-certificates : HTTPS for yfinance / deep-translator
# (--no-install-recommends still pulls chromium's hard Depends.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        fonts-liberation \
        fonts-dejavu-core \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Point kaleido/choreographer at the system chromium.
ENV BROWSER_PATH=/usr/bin/chromium

WORKDIR /app

# Install Python deps first so the layer caches across source-only changes.
# All deps ship cp312 manylinux wheels, so no build toolchain is needed.
COPY requirements.txt ./requirements.txt
COPY api/requirements.txt ./api-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r api-requirements.txt

COPY . .
# Overlay the built front-end from stage 1 (web/dist is dockerignored from the
# build context, so the only copy present is this freshly-built one).
COPY --from=web-build /web/dist ./web/dist

# Run unprivileged — also lets chromium use its own sandbox (no --no-sandbox
# hacks) when rendering the PDF.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1

# Cloud Run injects $PORT (default 8080). Shell form so it expands. uvicorn binds
# 0.0.0.0 so the platform's startup probe can reach it.
EXPOSE 8080
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}
