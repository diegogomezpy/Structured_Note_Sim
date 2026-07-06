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
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
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
_BRANDING_DIR = _REPO / "branding"


def _safe_child(base: Path, name: str) -> Path | None:
    """Resolve `base/name` and confirm it stays inside `base` — defence-in-depth
    against path traversal (encoded slashes etc.) on the file-serving routes.
    Returns the resolved path, or None if it escapes / isn't a .json file."""
    try:
        p = (base / name).resolve()
        if p.suffix == ".json" and p.is_file() and p.is_relative_to(base.resolve()):
            return p
    except (ValueError, OSError):
        pass
    return None

app = FastAPI(title="Structured Note Simulator API", version="1.0")

# Dev: the Vite React server runs on :5173. In the single-image prod build the
# front-end is served same-origin, so this is only needed for local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


# ── uniform error contract ──────────────────────────────────────────────────────
# Every API failure returns the same JSON shape — {ok: false, error: {status,
# message}} — instead of FastAPI's mix of {detail: "..."} (HTTPException),
# {detail: [...]} (validation) and a bare 500 (unhandled). The client's jget/jpost
# read this one shape and raise a typed ApiError. Success payloads are unchanged
# (no envelope) so no per-endpoint churn and no double serialization.
from fastapi.responses import JSONResponse                       # noqa: E402
from fastapi.exceptions import RequestValidationError            # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402


def _err_body(status: int, message: str) -> dict:
    return {"ok": False, "error": {"status": status, "message": message}}


@app.exception_handler(StarletteHTTPException)
async def _handle_http_exc(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content=_err_body(exc.status_code, str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def _handle_validation_exc(request: Request, exc: RequestValidationError):
    msg = "; ".join(f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}"
                    for e in exc.errors()) or "invalid request"
    return JSONResponse(status_code=422, content=_err_body(422, msg))


@app.exception_handler(Exception)
async def _handle_unhandled_exc(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content=_err_body(500, f"{type(exc).__name__}: {exc}"))


# ── request models ────────────────────────────────────────────────────────────
class SimulateRequest(BaseModel):
    terms: dict                                   # NoteTerms.from_dict payload
    n_paths: int = Field(10000, ge=1000, le=250000)
    seed: int = 42
    calib_years: float = 5.0
    history_years: float | None = None
    engine: str = "cpp"   # prefer C++; the engine falls back to numpy if unbuilt
    lang: str = "en"


class CompareRequest(BaseModel):
    terms_a: dict                                 # Note A (the primary note)
    terms_b: dict                                 # Note B (the variant)
    n_paths: int = Field(10000, ge=1000, le=250000)
    seed: int = 42
    calib_years: float = 5.0
    history_years: float | None = None
    engine: str = "cpp"
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


class QuotesRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)


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
    sections: list[str] = Field(default_factory=list)  # fine include keys; empty = all
    lang: str = "en"
    n_paths: int = Field(10000, ge=1000, le=250000)
    seed: int = 42
    calib_years: float = 5.0
    engine: str = "cpp"   # prefer C++; the engine falls back to numpy if unbuilt
    branding: dict | None = None
    compare_terms: dict | None = None   # Note B — adds an A/B comparison section


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


# Same-origin logo proxy. The client routes every remote logo through here so the
# images are (a) same-origin — letting the "download card as image" capture embed
# them without a cross-origin canvas-taint / fetch failure — and (b) resilient to
# CDNs that block hot-linking. Restricted to a host allowlist (no open SSRF), with
# a small in-memory byte cache. A miss returns 404 so the client's <img> onError
# advances to the next fallback source (and ultimately the monogram).
from collections import OrderedDict as _OD            # noqa: E402
import urllib.parse as _uparse                        # noqa: E402
import urllib.request as _ureq                        # noqa: E402

_LOGO_PROXY_CACHE: "_OD[str, tuple[bytes, str]]" = _OD()
_LOGO_PROXY_MAX = 512
_LOGO_ALLOW_HOSTS = {
    "assets.parqet.com", "www.google.com", "s2.googleusercontent.com",
    "financialmodelingprep.com", "logo.clearbit.com", "img.logo.dev",
}


@app.get("/api/logo")
def logo_proxy(u: str):
    """Fetch a remote logo (allowlisted hosts only) and stream it back same-origin.
    Returns 404 on any failure so the client falls through to its next source."""
    try:
        parsed = _uparse.urlparse(u)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in _LOGO_ALLOW_HOSTS:
            raise ValueError("host not allowed")
    except Exception:
        raise HTTPException(status_code=400, detail="bad logo url")

    hit = _LOGO_PROXY_CACHE.get(u)
    if hit is not None:
        _LOGO_PROXY_CACHE.move_to_end(u)
        body, ctype = hit
        return Response(body, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})

    try:
        req = _ureq.Request(u, headers={"User-Agent": "Mozilla/5.0 (StructuredNoteSim logo proxy)"})
        with _ureq.urlopen(req, timeout=6) as resp:
            body = resp.read(2_000_000)                # cap at 2 MB
            ctype = resp.headers.get("Content-Type", "image/png").split(";")[0].strip() or "image/png"
    except Exception:
        raise HTTPException(status_code=404, detail="logo unavailable")

    if not body or not ctype.startswith("image/"):
        raise HTTPException(status_code=404, detail="not an image")

    _LOGO_PROXY_CACHE[u] = (body, ctype)
    if len(_LOGO_PROXY_CACHE) > _LOGO_PROXY_MAX:
        _LOGO_PROXY_CACHE.popitem(last=False)
    return Response(body, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})


# ── industry cover-photo library (Pexels) ──────────────────────────────────────
# A built-in library of professional cover photos, keyed by industry sector, so a
# tech note can take a server-rack / chip-wafer / fibre-optics shot, an energy note
# an oil-refinery / wind-farm one, etc. The frontend suggests the sector from the
# note's underlyings (overridable) and embeds the chosen photo into the branding.
# Powered by the Pexels API (free, commercial use) — set PEXELS_API_KEY on the
# deploy; without it the picker hides cleanly and manual upload still works.
# Several distinct subjects per sector (not variations of one) so the grid stays
# varied — e.g. tech spans server rooms, chip wafers, circuit boards, robotics,
# fibre optics, coding screens and clean-room fabs rather than only server racks.
from cover_photos import (                              # noqa: E402  (app/cover_photos.py)
    SECTOR_QUERIES as _SECTOR_QUERIES,
    YAHOO_SECTOR_ALIAS as _YAHOO_SECTOR_ALIAS,
    INDUSTRY_SECTOR_MAP as _INDUSTRY_SECTOR_MAP,
)
_COVER_CACHE: "dict[str, list]" = {}
_COVER_IMG_CACHE: "_OD[str, tuple[bytes, str]]" = _OD()


def _pexels_key() -> str:
    return os.environ.get("PEXELS_API_KEY", "").strip()


def _normalize_sector(s: str | None) -> str:
    if not s:
        return "markets"
    k = str(s).strip().lower()
    if k in _SECTOR_QUERIES:
        return k
    return _YAHOO_SECTOR_ALIAS.get(k, "markets")


def resolve_sector_key(sector: str | None, industry: str | None) -> str:
    """Best cover-photo sector key for an underlying: match the fine-grained Yahoo
    `industry` first (so a defense / semiconductor / luxury / bank name lands on
    its specific library sector), then fall back to the coarse `sector` alias,
    then 'markets'. Powers the picker's auto-suggestion."""
    ind = (industry or "").strip().lower()
    if ind:
        for needle, key in _INDUSTRY_SECTOR_MAP:
            if needle in ind:
                return key
    return _normalize_sector(sector)


def _pexels_search(query: str, per_page: int = 2, page: int = 1) -> list[dict]:
    key = _pexels_key()
    if not key:
        return []
    url = "https://api.pexels.com/v1/search?" + _uparse.urlencode(
        {"query": query, "per_page": per_page, "page": page,
         "orientation": "landscape", "size": "large"})
    try:
        req = _ureq.Request(url, headers={"Authorization": key, "User-Agent": "StructuredNoteSim/1.0"})
        with _ureq.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read(2_000_000))
    except Exception:
        return []
    out = []
    for p in data.get("photos", []):
        src = p.get("src", {})
        full = src.get("large") or src.get("large2x") or src.get("original")
        if not full:
            continue
        out.append({
            "id": p.get("id"),
            "thumb": src.get("medium") or src.get("small") or full,
            "src": full,
            "photographer": p.get("photographer"),
            "alt": p.get("alt") or query,
        })
    return out


@app.get("/api/cover/sectors")
def cover_sectors():
    """Industry sector keys for the cover-photo picker dropdown (the client maps
    each to a localized label). `available` reflects whether a Pexels key is set."""
    return {"available": bool(_pexels_key()), "sectors": list(_SECTOR_QUERIES.keys())}


def _cover_pool(resolved: str) -> list[dict]:
    """Full per-sector photo pool (cached). Fetched a few deep per subject term
    so there's a well to draw varied random samples from on each refresh without
    re-hitting Pexels every time."""
    pool = _COVER_CACHE.get(resolved)
    if pool is not None:
        return pool
    pool, seen = [], set()
    for term in _SECTOR_QUERIES.get(resolved, _SECTOR_QUERIES["markets"]):
        # 6 per subject term × ~8 terms → a ~40-50 deep pool, so 16-per-refresh
        # has plenty of room to rotate without repeating the same shots.
        for ph in _pexels_search(term, per_page=6):
            if ph["id"] in seen:
                continue
            seen.add(ph["id"])
            ph["term"] = term
            pool.append(ph)
    if pool:
        _COVER_CACHE[resolved] = pool
    return pool


@app.get("/api/cover/photos")
def cover_photos(sector: str = "markets", n: int = 16, exclude: str = ""):
    """A varied set of professional cover photos for the given sector (or the
    Yahoo sector string, normalized). Returns a RANDOM sample of `n` from the
    cached per-sector pool, so each (re)load — i.e. the refresh button — shows
    different photos. `exclude` is a comma-separated list of photo ids the client
    already shows/has selected; they're held out of the sample (relaxed only if
    too few would remain). Returns the resolved sector key for highlighting."""
    import random as _rnd
    resolved = _normalize_sector(sector)
    if not _pexels_key():
        return {"available": False, "sector": resolved, "photos": []}
    pool = _cover_pool(resolved)
    ex = {x.strip() for x in exclude.split(",") if x.strip()}
    k = min(max(1, n), len(pool))
    fresh = [p for p in pool if str(p["id"]) not in ex]
    if len(fresh) >= k:
        photos = _rnd.sample(fresh, k)
    else:
        # Not enough unseen left — show all the fresh ones and top up randomly
        # from the rest, so the grid stays full instead of shrinking on refresh.
        rest = [p for p in pool if str(p["id"]) in ex]
        photos = list(fresh) + _rnd.sample(rest, k - len(fresh))
        _rnd.shuffle(photos)
    return {"available": True, "sector": resolved, "photos": photos}


@app.get("/api/cover/photo")
def cover_photo_proxy(u: str):
    """Stream a Pexels image same-origin (images.pexels.com only) so the client can
    embed it into the branding config without a cross-origin canvas taint."""
    try:
        parsed = _uparse.urlparse(u)
        if parsed.scheme != "https" or parsed.hostname != "images.pexels.com":
            raise ValueError("host not allowed")
    except Exception:
        raise HTTPException(status_code=400, detail="bad photo url")
    hit = _COVER_IMG_CACHE.get(u)
    if hit is not None:
        _COVER_IMG_CACHE.move_to_end(u)
        body, ctype = hit
        return Response(body, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})
    try:
        req = _ureq.Request(u, headers={"User-Agent": "StructuredNoteSim/1.0"})
        with _ureq.urlopen(req, timeout=10) as resp:
            body = resp.read(8_000_000)                 # cap at 8 MB
            ctype = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip() or "image/jpeg"
    except Exception:
        raise HTTPException(status_code=404, detail="photo unavailable")
    if not body or not ctype.startswith("image/"):
        raise HTTPException(status_code=404, detail="not an image")
    _COVER_IMG_CACHE[u] = (body, ctype)
    if len(_COVER_IMG_CACHE) > 128:
        _COVER_IMG_CACHE.popitem(last=False)
    return Response(body, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/configs")
def list_configs():
    """Note term-sheet configs are intentionally NOT auto-discovered from the
    repo — the app starts on a blank note and users load their own via the folder
    picker or the upload button. The example JSONs stay in note_configs/ for
    reference only, so this returns an empty list."""
    return []


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
    path = _safe_child(_CONFIG_DIR, file)
    if path is None:
        raise HTTPException(404, f"config '{file}' not found")
    try:
        return NoteTerms.from_dict(json.loads(path.read_text())).to_dict()
    except Exception as e:
        raise HTTPException(400, f"could not parse config: {e}")


@app.post("/api/simulate")
def simulate(req: SimulateRequest, request: Request):
    try:
        terms = NoteTerms.from_dict(req.terms)
    except Exception as e:
        raise HTTPException(400, f"invalid note terms: {e}")
    # Generation audit (who ran a simulation, when, from where) — server-log only.
    _audit(request, "simulate", note=terms.name, tickers=_tickers_of(req.terms),
           n_paths=req.n_paths, seed=req.seed, lang=req.lang, engine=req.engine)
    try:
        return engine.run_simulation(
            terms, n_paths=req.n_paths, seed=req.seed,
            calib_years=req.calib_years, history_years=req.history_years,
            engine=req.engine, lang=req.lang)
    except Exception as e:
        raise HTTPException(500, f"simulation failed: {e}")


@app.post("/api/compare")
def compare(req: CompareRequest, request: Request):
    """Price two notes (A vs B) head-to-head. Same underlyings + maturity → both
    priced on ONE shared simulation; otherwise B is simulated independently."""
    try:
        terms_a = NoteTerms.from_dict(req.terms_a)
        terms_b = NoteTerms.from_dict(req.terms_b)
    except Exception as e:
        raise HTTPException(400, f"invalid note terms: {e}")
    _audit(request, "compare", note=f"{terms_a.name} vs {terms_b.name}",
           tickers=_tickers_of(req.terms_a), n_paths=req.n_paths, seed=req.seed,
           lang=req.lang, engine=req.engine)
    try:
        return engine.run_compare(
            terms_a, terms_b, n_paths=req.n_paths, seed=req.seed,
            calib_years=req.calib_years, history_years=req.history_years,
            engine=req.engine, lang=req.lang)
    except Exception as e:
        raise HTTPException(500, f"comparison failed: {e}")


@app.get("/api/runs/{run_id}/paths")
def run_paths(run_id: str, sample: int = 400):
    """Sampled worst-of trajectories for the path explorer (see engine.sample_paths)."""
    data = engine.sample_paths(run_id, sample=max(50, min(sample, 2000)))
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
                                     sample=max(50, min(sample, 2000)), seed=seed,
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


@app.get("/api/branding")
def list_branding():
    """Branding presets are intentionally NOT auto-discovered from the repo —
    users load branding via the folder picker or the upload button. The example
    JSON stays in branding/ for reference only, so this returns an empty list."""
    return []


@app.get("/api/branding/{file}")
def get_branding(file: str):
    """A single branding preset dict (passed straight to the PDF as `branding`)."""
    path = _safe_child(_BRANDING_DIR, file)
    if path is None:
        raise HTTPException(404, f"branding '{file}' not found")
    try:
        return json.loads(path.read_text())
    except Exception as e:
        raise HTTPException(400, f"could not parse branding: {e}")


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
        rows = engine.run_underlying_metrics(req.tickers, lang=req.lang)
        # Resolve each underlying's fine-grained cover-photo sector (industry-first)
        # so the picker can auto-suggest the granular sectors, not just Yahoo's
        # coarse ~11. Cheap, string-only — done here beside the sector tables.
        for r in rows:
            r["sector_key"] = resolve_sector_key(r.get("sector"), r.get("industry"))
        return rows
    except Exception as e:
        raise HTTPException(500, f"underlying metrics failed: {e}")


@app.post("/api/quotes")
def quotes(req: QuotesRequest):
    """Fast last-price + day-change per symbol for the live ticker tape — Yahoo
    fast_info only (no .info / options / history). Best-effort; a symbol that
    fails returns nulls so the tape degrades cleanly."""
    try:
        return engine.run_quotes(req.symbols)
    except Exception as e:
        raise HTTPException(500, f"quotes failed: {e}")


_GEO_CACHE: "_OD[str, str]" = _OD()


def _geo(ip: str) -> str:
    """Best-effort IP → coarse location + network, for the generation audit log
    (tracing who might be using the tool without permission). Cached per IP;
    skips private/blank addresses; never raises (returns '' on any failure).

    Uses ip-api.com's keyless endpoint, whose FREE tier is NON-COMMERCIAL only —
    fine for personal audit use, but for a commercial deploy swap in a licensed
    provider (ipinfo/ipgeolocation with a key) or a self-hosted MaxMind GeoLite2
    database. Set SNSIM_GEOIP=off to disable geolocation entirely."""
    if not ip or ip == "?" or os.environ.get("SNSIM_GEOIP", "on").lower() == "off":
        return ""
    if ip.startswith(("10.", "127.", "192.168.", "172.16.", "::1", "fc", "fd", "169.254.")):
        return "private"
    hit = _GEO_CACHE.get(ip)
    if hit is not None:
        _GEO_CACHE.move_to_end(ip)
        return hit
    out = ""
    try:
        url = ("http://ip-api.com/json/" + _uparse.quote(ip)
               + "?fields=status,country,regionName,city,isp,as")
        r = _ureq.Request(url, headers={"User-Agent": "StructuredNoteSim/1.0"})
        with _ureq.urlopen(r, timeout=2.0) as resp:
            d = json.loads(resp.read(50_000))
        if isinstance(d, dict) and d.get("status") == "success":
            loc = ", ".join(x for x in (d.get("city"), d.get("regionName"), d.get("country")) if x)
            net = " · ".join(x for x in (d.get("isp"), d.get("as")) if x)
            out = f"{loc}{(' · ' + net) if net else ''}".strip(" ·,")
    except Exception:
        out = ""
    _GEO_CACHE[ip] = out
    while len(_GEO_CACHE) > 512:
        _GEO_CACHE.popitem(last=False)
    return out


def _audit(request: Request, tag: str, **fields) -> None:
    """One server-side provenance line: UTC timestamp + geotagged client IP + the
    given fields + user-agent, e.g. `[simulate] ts=… ip=… geo=… note=… …`. Never
    raises. The IP/geo stay in the request log (operator-only) and are never
    embedded in any output document."""
    try:
        import datetime as _dt
        xff = request.headers.get("x-forwarded-for", "")
        ip = (xff.split(",")[0].strip() if xff
              else (request.client.host if request.client else "?"))
        extra = " ".join(f"{k}={v!r}" if isinstance(v, str) else f"{k}={v}"
                         for k, v in fields.items())
        print(f"[{tag}] ts={_dt.datetime.now(_dt.timezone.utc).isoformat()} ip={ip} "
              f"geo={_geo(ip)!r} {extra} ua={request.headers.get('user-agent', '?')!r}",
              flush=True)
    except Exception:
        pass


def _tickers_of(terms_dict) -> str:
    return "/".join((terms_dict.get("tickers") or {}).keys()) if isinstance(terms_dict, dict) else ""


def _prepare_report(req: ReportRequest, request: Request):
    """Validate a report request → (terms, compare_terms, filename); raise on bad
    terms and emit the generation audit line. Shared by the sync + async routes.

    The audit line is provenance (who generated what, when, from where), kept in the
    request log — operator-only — and deliberately NOT embedded in the PDF (the
    client IP is personal data and the report is white-label / redistributable)."""
    try:
        terms = NoteTerms.from_dict(req.terms)
    except Exception as e:
        raise HTTPException(400, f"invalid note terms: {e}")
    compare_terms = None
    if req.compare_terms:
        try:
            compare_terms = NoteTerms.from_dict(req.compare_terms)
        except Exception as e:
            raise HTTPException(400, f"invalid comparison terms: {e}")
    _audit(request, "report", note=terms.name, tickers=_tickers_of(req.terms),
           sections=len(req.sections or []), n_paths=req.n_paths, lang=req.lang, engine=req.engine,
           compare=bool(compare_terms))
    # Content-Disposition is latin-1 only, so strip the filename to safe ASCII
    # (note names carry em-dashes / accents that would crash header encoding).
    import re
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", terms.name or "structured_note").strip("_")[:60]
    return terms, compare_terms, f"{safe or 'note'}_report.pdf"


def _build_report_bytes(terms, compare_terms, req: ReportRequest) -> bytes:
    return engine.build_report_pdf(
        terms, sections=req.sections, lang=req.lang, n_paths=req.n_paths,
        seed=req.seed, calib_years=req.calib_years, engine=req.engine,
        branding=req.branding, compare_terms=compare_terms)


@app.post("/api/report")
def report(req: ReportRequest, request: Request):
    """Build the PDF synchronously and return it. This is the endpoint the web
    client uses: on Cloud Run, CPU is only allocated while a request is in
    flight, so the async /api/report/start job flow below starves and never
    finishes there. Keep the async flow only for always-allocated-CPU deploys."""
    terms, compare_terms, filename = _prepare_report(req, request)
    try:
        pdf = _build_report_bytes(terms, compare_terms, req)
    except Exception as e:
        raise HTTPException(500, f"report generation failed: {e}")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── async report jobs ─────────────────────────────────────────────────────────
# PDF generation boots Chromium/kaleido and renders many figures (~5-40s), holding
# a worker the whole time so the rest of the API (the live tape polls constantly)
# stalls. /api/report/start renders in a dedicated background pool and returns a
# job_id the client polls, then downloads the result. Jobs are in-memory with a TTL
# (fine for single-instance); a multi-instance deploy would share them via Redis.
_REPORT_POOL = ThreadPoolExecutor(max_workers=2)
_REPORT_JOBS: "dict[str, dict]" = {}
_REPORT_JOBS_LOCK = threading.Lock()
_REPORT_JOB_TTL = 900.0
_REPORT_JOB_MAX = 16


def _reap_report_jobs() -> None:
    now = time.time()
    for k in [k for k, v in _REPORT_JOBS.items() if now - v["created"] > _REPORT_JOB_TTL]:
        _REPORT_JOBS.pop(k, None)
    while len(_REPORT_JOBS) > _REPORT_JOB_MAX:
        _REPORT_JOBS.pop(min(_REPORT_JOBS, key=lambda k: _REPORT_JOBS[k]["created"]), None)


def _run_report_job(job_id: str, terms, compare_terms, req: ReportRequest) -> None:
    try:
        pdf = _build_report_bytes(terms, compare_terms, req)
        with _REPORT_JOBS_LOCK:
            if job_id in _REPORT_JOBS:
                _REPORT_JOBS[job_id].update(status="done", pdf=pdf)
    except Exception as e:
        with _REPORT_JOBS_LOCK:
            if job_id in _REPORT_JOBS:
                _REPORT_JOBS[job_id].update(status="error", error=f"{type(e).__name__}: {e}")


@app.post("/api/report/start")
def report_start(req: ReportRequest, request: Request):
    """Kick off async PDF generation in the background; returns a job_id to poll."""
    terms, compare_terms, filename = _prepare_report(req, request)
    job_id = uuid.uuid4().hex[:12]
    with _REPORT_JOBS_LOCK:
        _reap_report_jobs()
        _REPORT_JOBS[job_id] = {"status": "pending", "created": time.time(), "filename": filename}
    _REPORT_POOL.submit(_run_report_job, job_id, terms, compare_terms, req)
    return {"job_id": job_id}


@app.get("/api/report/status/{job_id}")
def report_status(job_id: str):
    with _REPORT_JOBS_LOCK:
        j = _REPORT_JOBS.get(job_id)
    if j is None:
        raise HTTPException(404, "report job not found or expired")
    return {"status": j["status"], "error": j.get("error")}


@app.get("/api/report/result/{job_id}")
def report_result(job_id: str):
    with _REPORT_JOBS_LOCK:
        j = _REPORT_JOBS.get(job_id)
    if j is None:
        raise HTTPException(404, "report job not found or expired")
    if j["status"] == "pending":
        raise HTTPException(409, "report not ready yet")
    if j["status"] == "error":
        raise HTTPException(500, j.get("error") or "report generation failed")
    return Response(content=j["pdf"], media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{j["filename"]}"'})


def _cpp_available() -> bool:
    try:
        import heston_cpp  # noqa: F401
        return True
    except Exception:
        return False


# ── static front-end (single-image prod build) ───────────────────────────────
# In the container the React bundle is built to web/dist and served same-origin.
# Mounted LAST so the explicit /api/* routes above always take precedence;
# html=True serves index.html at "/" (and as the single-page fallback). Absent in
# local dev — Vite serves the front-end and proxies /api to uvicorn.
from fastapi.staticfiles import StaticFiles   # noqa: E402

_WEB_DIST = _REPO / "web" / "dist"
if _WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")
