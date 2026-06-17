# Backend API image — FastAPI + the quant engine.
#
# Chromium is installed for server-side PDF rendering (Plotly → PNG via kaleido).
# NOTE: the static frontend renders all charts client-side with Plotly.js, so
# Chromium is only needed for the /pdf endpoint. If PDF export misbehaves in a
# particular host's container, /simulate (the core feature) still works without it.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Chromium for kaleido + CA certificates. The IBM Plex fonts ship in fonts/.
RUN apt-get update \
 && apt-get install -y --no-install-recommends chromium ca-certificates \
 && rm -rf /var/lib/apt/lists/*
# Let kaleido/choreographer find the system browser.
ENV BROWSER_PATH=/usr/bin/chromium

WORKDIR /app

COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

# Application code. app/ is copied for charts.py / pdf_report.py / translations.py
# / underlyings.py (imported via sys.path in api/service.py); app.py itself is
# never imported, so Streamlit is not required at runtime.
COPY core/        core/
COPY data/        data/
COPY app/         app/
COPY api/         api/
COPY fonts/       fonts/
COPY branding/    branding/
COPY note_configs/ note_configs/

# Drop privileges. HOME must be writable — kaleido/Chromium and the runtime
# get_chrome fallback cache under it. (Hugging Face Spaces run the image's USER.)
RUN useradd --create-home --uid 1000 appuser
ENV HOME=/home/appuser
USER appuser

# Hosts (Render/Railway/Fly) inject $PORT; default to 8000 locally.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
