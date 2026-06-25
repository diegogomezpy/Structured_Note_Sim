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
from fastapi.responses import Response
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
    lang: str = "en"
    bt_start: str | None = None   # ISO date — restrict issue-date window
    bt_end: str | None = None


class LiveRequest(BaseModel):
    terms: dict
    lang: str = "en"


class MetricsRequest(BaseModel):
    tickers: dict          # {yfinance_symbol: display_name}
    lang: str = "en"


class DescribeRequest(BaseModel):
    issuer: str | None = None
    symbols: list[str] = Field(default_factory=list)
    lang: str = "en"


class InspectRequest(BaseModel):
    filters: dict = Field(default_factory=dict)   # outcome/ac_periods/ki_choice/ret_lo/ret_hi/coupon_periods
    position: int = 0
    randomize: bool = False
    title: str | None = None
    lang: str = "en"


class BacktestInspectRequest(BaseModel):
    terms: dict
    filters: dict = Field(default_factory=dict)
    position: int = 0
    randomize: bool = False
    history_years: float | None = None
    lang: str = "en"
    bt_start: str | None = None
    bt_end: str | None = None


class ReportRequest(BaseModel):
    terms: dict
    sections: list[str] = Field(default_factory=list)  # mc/calibration/backtest/live; empty = all
    lang: str = "en"
    n_paths: int = Field(10000, ge=1000, le=250000)
    seed: int = 42
    calib_years: float = 5.0
    engine: str = "numpy"


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


class ParseConfigRequest(BaseModel):
    config: dict


@app.post("/api/configs/parse")
def parse_config(req: ParseConfigRequest):
    """Normalise an uploaded term-sheet JSON through NoteTerms (legacy fields
    migrated). Auto-corrects an inverted ``tickers`` map ({name: symbol}) — a
    yfinance symbol is short, uppercase and space-free, a display name isn't."""
    d = dict(req.config)
    tk = d.get("tickers")
    if isinstance(tk, dict) and tk:
        def _sym(s: object) -> bool:
            return isinstance(s, str) and len(s) <= 6 and s == s.upper() and " " not in s
        if all(_sym(v) for v in tk.values()) and not all(_sym(k) for k in tk.keys()):
            d["tickers"] = {v: k for k, v in tk.items()}
    try:
        return NoteTerms.from_dict(d).to_dict()
    except Exception as e:
        raise HTTPException(400, f"could not parse config: {e}")


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
        return engine.run_backtest_api(terms, history_years=req.history_years, lang=req.lang,
                                       bt_start=req.bt_start, bt_end=req.bt_end)
    except Exception as e:
        raise HTTPException(500, f"backtest failed: {e}")


@app.post("/api/live")
def live(req: LiveRequest):
    """Current-performance replay for a partially-elapsed note (see
    engine.run_live_api). Returns {available: false, reason} when the note has no
    usable live data (no issue date, not yet issued, or too little history)."""
    try:
        terms = NoteTerms.from_dict(req.terms)
    except Exception as e:
        raise HTTPException(400, f"invalid note terms: {e}")
    try:
        return engine.run_live_api(terms, lang=req.lang)
    except Exception as e:
        raise HTTPException(500, f"current performance failed: {e}")


@app.post("/api/runs/{run_id}/inspect")
def inspect(run_id: str, req: InspectRequest):
    """One Monte-Carlo path in full detail for the single-path inspector
    (see engine.inspect_run)."""
    data = engine.inspect_run(run_id, lang=req.lang, filters=req.filters,
                              position=req.position, randomize=req.randomize, title=req.title)
    if data is None:
        raise HTTPException(404, "run not found or expired — re-run the simulation")
    return data


@app.post("/api/backtest/paths")
def backtest_path_explorer(req: BacktestRequest, sample: int = 400, seed: int = 7):
    """Per-issue worst-of trajectories for the backtest path explorer (same shape
    as the MC explorer; see engine.backtest_paths)."""
    try:
        terms = NoteTerms.from_dict(req.terms)
    except Exception as e:
        raise HTTPException(400, f"invalid note terms: {e}")
    try:
        return engine.backtest_paths(terms, history_years=req.history_years,
                                     sample=max(50, min(sample, 800)), seed=seed,
                                     bt_start=req.bt_start, bt_end=req.bt_end)
    except Exception as e:
        raise HTTPException(500, f"backtest paths failed: {e}")


@app.post("/api/backtest/inspect")
def backtest_inspect(req: BacktestInspectRequest):
    """One historical issue in detail for the backtest single-path inspector
    (same shape as /runs/{id}/inspect; see engine.backtest_inspect)."""
    try:
        terms = NoteTerms.from_dict(req.terms)
    except Exception as e:
        raise HTTPException(400, f"invalid note terms: {e}")
    try:
        return engine.backtest_inspect(terms, lang=req.lang, filters=req.filters,
                                       position=req.position, randomize=req.randomize,
                                       history_years=req.history_years,
                                       bt_start=req.bt_start, bt_end=req.bt_end)
    except Exception as e:
        raise HTTPException(500, f"backtest inspect failed: {e}")


@app.post("/api/describe")
def describe(req: DescribeRequest):
    """Prefill issuer / underlying descriptions from Yahoo business summaries
    (see engine.run_describe)."""
    try:
        return engine.run_describe(issuer=req.issuer, symbols=req.symbols, lang=req.lang)
    except Exception as e:
        raise HTTPException(500, f"describe failed: {e}")


@app.post("/api/underlyings/metrics")
def underlying_metrics(req: MetricsRequest):
    """Per-underlying breakdown cards (market cap, IV/vol, last price, RSI, summary,
    1Y price chart). Slow (Yahoo .info + options per ticker) — the client fetches it
    lazily when the breakdown section is opened."""
    try:
        return engine.run_underlying_metrics(req.tickers, lang=req.lang)
    except Exception as e:
        raise HTTPException(500, f"underlying metrics failed: {e}")


@app.post("/api/report")
def report(req: ReportRequest):
    """Build the institutional PDF report and return it as a downloadable file.
    `sections` selects which lenses to include (empty ⇒ everything available)."""
    try:
        terms = NoteTerms.from_dict(req.terms)
    except Exception as e:
        raise HTTPException(400, f"invalid note terms: {e}")
    try:
        pdf = engine.build_report_pdf(
            terms, sections=req.sections, lang=req.lang, n_paths=req.n_paths,
            seed=req.seed, calib_years=req.calib_years, engine=req.engine)
    except Exception as e:
        raise HTTPException(500, f"report generation failed: {e}")
    # Content-Disposition is latin-1 only, so strip the filename to safe ASCII
    # (note names carry em-dashes / accents that would crash header encoding).
    import re
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", terms.name or "structured_note").strip("_")[:60]
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{safe or "note"}_report.pdf"'})


def _cpp_available() -> bool:
    try:
        import heston_cpp  # noqa: F401
        return True
    except Exception:
        return False
