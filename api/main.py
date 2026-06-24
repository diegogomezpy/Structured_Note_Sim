"""
api/main.py
-----------
FastAPI app for the Structured Note Simulator. Thin HTTP layer over api/engine.py
(which reuses the quant core + chart builders). Run locally:

    .venv/bin/uvicorn api.main:app --reload --port 8000

The React front-end (web/) calls these endpoints; figures come back as Plotly JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "app"))

from core.note import NoteTerms          # noqa: E402
import underlyings                       # noqa: E402  (app/underlyings.py)
from api import engine                   # noqa: E402

_CONFIG_DIR = _REPO / "note_configs"

app = FastAPI(title="Structured Note Simulator API", version="1.0")

# Dev: the Vite React server runs on :5173. In the single-image prod build the
# front-end is served same-origin, so this is only needed for local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


# ── request models ────────────────────────────────────────────────────────────
class SimulateRequest(BaseModel):
    terms: dict                                   # NoteTerms.from_dict payload
    n_paths: int = Field(10000, ge=1000, le=250000)
    seed: int = 42
    calib_years: float = 5.0
    history_years: float | None = None
    engine: str = "numpy"
    lang: str = "en"


class BacktestRequest(BaseModel):
    terms: dict
    history_years: float | None = None


# ── endpoints ─────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "cpp_engine": _cpp_available()}


@app.get("/api/underlyings")
def list_underlyings():
    """The selectable ticker universe (label + yfinance symbol + logo URL)."""
    return [{"label": label, "symbol": sym, "logo": underlyings.logo_for(sym)}
            for label, sym in underlyings.UNDERLYING_OPTIONS.items()]


@app.get("/api/logos")
def logos():
    """Curated symbol→logo-URL map plus the fallback URL template (so the client
    can resolve a logo for any ticker), and the issuer (bank) favicon map."""
    return {"map": underlyings.TICKER_LOGOS, "base": underlyings.LOGO_BASE,
            "issuers": underlyings.ISSUER_LOGOS}


@app.get("/api/configs")
def list_configs():
    """Bundled note term-sheet configs."""
    out = []
    for p in sorted(_CONFIG_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text())
            out.append({"file": p.name, "name": d.get("name", p.stem),
                        "issuer": d.get("issuer", "")})
        except Exception:
            continue
    return out


@app.get("/api/configs/{file}")
def get_config(file: str):
    """A single config, normalised through NoteTerms (legacy fields migrated)."""
    path = _CONFIG_DIR / file
    if not path.is_file() or path.suffix != ".json":
        raise HTTPException(404, f"config '{file}' not found")
    try:
        return NoteTerms.from_dict(json.loads(path.read_text())).to_dict()
    except Exception as e:
        raise HTTPException(400, f"could not parse config: {e}")


@app.post("/api/simulate")
def simulate(req: SimulateRequest):
    try:
        terms = NoteTerms.from_dict(req.terms)
    except Exception as e:
        raise HTTPException(400, f"invalid note terms: {e}")
    try:
        return engine.run_simulation(
            terms, n_paths=req.n_paths, seed=req.seed,
            calib_years=req.calib_years, history_years=req.history_years,
            engine=req.engine, lang=req.lang)
    except Exception as e:
        raise HTTPException(500, f"simulation failed: {e}")


@app.get("/api/runs/{run_id}/paths")
def run_paths(run_id: str, sample: int = 400):
    """Sampled worst-of trajectories for the path explorer (see engine.sample_paths)."""
    data = engine.sample_paths(run_id, sample=max(50, min(sample, 800)))
    if data is None:
        raise HTTPException(404, "run not found or expired — re-run the simulation")
    return data


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    try:
        terms = NoteTerms.from_dict(req.terms)
    except Exception as e:
        raise HTTPException(400, f"invalid note terms: {e}")
    try:
        return engine.run_backtest_api(terms, history_years=req.history_years)
    except Exception as e:
        raise HTTPException(500, f"backtest failed: {e}")


def _cpp_available() -> bool:
    try:
        import heston_cpp  # noqa: F401
        return True
    except Exception:
        return False
