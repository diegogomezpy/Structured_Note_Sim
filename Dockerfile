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

# ── stage 1b: build the optional C++ Heston engine (portable wheel) ───────────
# Clang is the intended compiler (the CMakeLists uses -fveclib=libmvec, a Clang
# flag). HESTON_NATIVE=OFF drops -march=native so the binary is portable across
# the Cloud Run CPUs. scikit-build-core pulls cmake/ninja/pybind11 in isolation.
FROM python:3.12-slim AS cpp-build
RUN apt-get update && apt-get install -y --no-install-recommends \
        clang build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY cpp ./cpp
RUN CC=clang CXX=clang++ CMAKE_ARGS="-DHESTON_NATIVE=OFF" \
        pip wheel --no-deps --no-cache-dir -w /wheels ./cpp

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

WORKDIR /app

# Install Python deps first so the layer caches across source-only changes.
# All deps ship cp312 manylinux wheels, so no build toolchain is needed.
COPY requirements.txt ./requirements.txt
COPY api/requirements.txt ./api-requirements.txt
# `git` is needed only to fetch reportkit from its tag, so it is installed and
# purged inside ONE layer — leaving it behind would ship a compiler-adjacent
# toolchain in a public-facing image for no runtime benefit. Without it the
# build fails outright at the reportkit line, which is how this was caught.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir -r requirements.txt -r api-requirements.txt \
    && apt-get purge -y git && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# The PDF figure export (kaleido) drives a headless browser. Debian's chromium
# package proved unusable for this: its version drifts on every image rebuild,
# and chromium 150.0.7871 crashes at launch (SIGTRAP) on Cloud Run — on both
# gen1 and gen2, sandbox on or off — which silently broke every PDF report
# (149.0.7827 worked). So instead of the apt chromium we bake in the
# Chrome-for-Testing build that kaleido/choreographer is actually tested
# against, fetched at build time by choreographer's own CLI. The apt chromium
# install above stays ONLY because it pulls in every shared library the
# browser needs (fonts, nss, gbm, …).
#
# The wrapper forces container-safe flags: --no-sandbox is acceptable because
# chromium only rasterises the app's own trusted Plotly JSON (never untrusted
# web content) and runs as the unprivileged appuser; --disable-dev-shm-usage
# avoids the tiny /dev/shm killing the renderer; --disable-gpu skips GPU init
# that doesn't exist on Cloud Run.
RUN choreo_get_chrome --path /opt/chrome --arch linux64 \
    && test -x /opt/chrome/chrome-linux64/chrome \
    && chmod -R a+rX /opt/chrome \
    && printf '#!/bin/sh\nexec /opt/chrome/chrome-linux64/chrome --no-sandbox --disable-gpu --disable-dev-shm-usage "$@"\n' \
        > /usr/local/bin/chromium-headless \
    && chmod +x /usr/local/bin/chromium-headless
ENV BROWSER_PATH=/usr/local/bin/chromium-headless

# Optional fast path: install the prebuilt heston_cpp wheel so engine="cpp" runs
# the compiled kernel. Built on the same python:3.12-slim base, so it's ABI-
# compatible; libstdc++6 / libmvec are present at runtime (chromium pulls the
# former, glibc the latter). If absent the simulator transparently uses numpy.
COPY --from=cpp-build /wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels

COPY . .
# Overlay the built front-end from stage 1 (web/dist is dockerignored from the
# build context, so the only copy present is this freshly-built one).
COPY --from=web-build /web/dist ./web/dist

# Run unprivileged. (chromium runs with --no-sandbox via the wrapper above —
# its own sandbox crashes on Cloud Run's runtime — so non-root matters more.)
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1

# Cloud Run injects $PORT (default 8080). Shell form so it expands. uvicorn binds
# 0.0.0.0 so the platform's startup probe can reach it.
EXPOSE 8080
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}
