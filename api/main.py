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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api import service
from api.schemas import PdfRequest, SimRequest

app = FastAPI(title="Structured Note Simulator API", version="0.1.0")

_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


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
def simulate(req: SimRequest) -> dict:
    return service.simulate(req)


@app.post("/pdf")
def pdf(req: PdfRequest) -> Response:
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
