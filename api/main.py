"""
api/main.py
-----------
FastAPI entry point. Run locally with:

    uvicorn api.main:app --reload --port 8000

Endpoints
  GET  /health     — liveness probe.
  GET  /universe   — selectable underlyings + logo URLs (for the frontend picker).
  POST /simulate   — calibrate+simulate+price; returns metrics + Plotly figure JSON.
  POST /pdf        — render the branded PDF (application/pdf bytes).

CORS: set ALLOWED_ORIGINS (comma-separated) in the environment to your GitHub
Pages origin in production, e.g. "https://you.github.io". Defaults to "*" for
local development.
"""
from __future__ import annotations

import os
import re
import threading

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api import service
from api.schemas import BacktestRequest, LiveRequest, PdfRequest, SimRequest

app = FastAPI(title="Structured Note Simulator API", version="0.1.0")

_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Concurrency guard ─────────────────────────────────────────────────────────
# The heavy endpoints (calibration + Monte Carlo) are memory- and CPU-bound.
# Bound how many run at once so a burst can't pile up and OOM a small instance;
# excess requests get a quick 503 + Retry-After instead. Tune with
# SNSIM_MAX_CONCURRENCY.
_MAX_CONCURRENCY = int(os.environ.get("SNSIM_MAX_CONCURRENCY", "1"))
# How long a request will WAIT for a free slot before giving up. Generous so
# overlapping requests queue and run sequentially (memory-safe) instead of
# erroring — only a genuine pile-up beyond this returns 503.
_BUSY_TIMEOUT = float(os.environ.get("SNSIM_BUSY_TIMEOUT", "45"))
_SEM = threading.BoundedSemaphore(_MAX_CONCURRENCY)


def _slot():
    if not _SEM.acquire(timeout=_BUSY_TIMEOUT):
        raise HTTPException(status_code=503, detail="Server busy — retry shortly.",
                            headers={"Retry-After": "10"})
    try:
        yield
    finally:
        _SEM.release()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/universe")
def universe() -> dict:
    """The selectable underlying universe + a logo URL per symbol, so the
    frontend can render the same picker the Streamlit app shows."""
    from underlyings import UNDERLYING_OPTIONS, TICKER_LOGOS, _LOGO_BASE
    return {
        "options": [
            {
                "label":  label,
                "symbol": sym,
                "logo":   TICKER_LOGOS.get(sym) or _LOGO_BASE.format(sym=sym),
            }
            for label, sym in UNDERLYING_OPTIONS.items()
        ]
    }


@app.post("/simulate")
def simulate(req: SimRequest, _=Depends(_slot)) -> dict:
    return service.simulate(req)


@app.post("/backtest")
def backtest(req: BacktestRequest, _=Depends(_slot)) -> dict:
    return service.backtest(req)


@app.post("/live")
def live(req: LiveRequest, _=Depends(_slot)) -> dict:
    return service.live(req)


@app.post("/pdf")
def pdf(req: PdfRequest, _=Depends(_slot)) -> Response:
    data = service.build_pdf(req)
    # Content-Disposition is latin-1 only — the note name may contain an em-dash,
    # slashes, etc. Reduce to a safe ASCII filename.
    raw  = req.terms.get("name") or "note"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("_") or "note"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}_report.pdf"'},
    )
