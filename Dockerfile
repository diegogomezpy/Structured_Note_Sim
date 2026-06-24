# Reproducible image for Cloud Run (or any container host). Bundles chromium so
# the PDF figure export (kaleido) works, and pins the whole environment so
# "works locally" == "works in prod" — unlike the opaque Streamlit Cloud builder.
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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run unprivileged — also lets chromium use its own sandbox (no --no-sandbox
# hacks) when rendering the PDF.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# Headless overrides the repo's config.toml (which has headless=false for local).
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Cloud Run injects $PORT (default 8080). Shell form so it expands.
EXPOSE 8080
CMD streamlit run app/app.py \
    --server.port=${PORT:-8080} \
    --server.address=0.0.0.0 \
    --server.headless=true
