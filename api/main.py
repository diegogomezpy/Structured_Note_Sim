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
    engine: str = "cpp"   # prefer C++; the engine falls back to numpy if unbuilt
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
_SECTOR_QUERIES: "dict[str, list[str]]" = {
    "technology":         ["server room data center", "microchip processor macro", "circuit board electronics",
                           "robotic arm automation", "fiber optic network", "programmer coding screens",
                           "semiconductor clean room", "futuristic technology"],
    "energy":             ["oil refinery at night", "offshore wind turbines", "solar farm aerial",
                           "power plant cooling towers", "oil drilling rig", "hydroelectric dam",
                           "natural gas pipeline", "electricity pylons sunset"],
    "financials":         ["stock exchange trading floor", "financial district skyscrapers", "bank building columns",
                           "stock market charts screen", "gold bullion bars", "business handshake deal",
                           "wall street", "money currency finance"],
    "healthcare":         ["pharmaceutical research lab", "modern hospital corridor", "dna double helix",
                           "surgeons operating room", "medicine pills macro", "microscope laboratory",
                           "mri scanner machine", "scientist vaccine research"],
    "consumer_cyclical":  ["luxury retail boutique", "automobile assembly line", "shopping mall interior",
                           "fashion clothing store", "restaurant fine dining", "ecommerce delivery packages",
                           "car showroom", "travel resort hotel"],
    "consumer_defensive": ["supermarket shelves", "fresh produce market", "packaged food factory",
                           "beverage bottling line", "household cleaning products", "grocery checkout",
                           "agriculture farm field", "warehouse stocked goods"],
    "industrials":        ["factory robotic assembly", "heavy construction machinery", "cargo container port",
                           "aircraft manufacturing", "industrial warehouse", "welding sparks metal",
                           "freight train cargo", "construction crane skyline"],
    "materials":          ["steel mill molten metal", "open pit mine", "copper smelting plant",
                           "chemical plant pipes", "lumber timber yard", "gold mining",
                           "cement factory", "raw minerals ore"],
    "utilities":          ["high voltage power lines", "electric power plant", "water treatment facility",
                           "nuclear cooling towers", "solar utility farm", "electrical substation",
                           "wind energy turbines", "hydroelectric dam reservoir"],
    "real_estate":        ["modern office tower glass", "city skyline aerial", "luxury apartment building",
                           "construction site crane", "suburban residential houses", "commercial building facade",
                           "real estate keys home", "industrial warehouse property"],
    "communication":      ["telecom broadcast tower", "5g antenna mast", "fiber network servers",
                           "television broadcast studio", "satellite dish array", "social media smartphone",
                           "undersea cable network", "media newsroom"],
    "defense":            ["fighter jet aircraft", "naval warship ocean", "military radar defense",
                           "army tank field", "missile launch defense", "military drone uav",
                           "soldiers formation march", "aircraft carrier deck"],
    "aerospace":          ["commercial jet takeoff", "aircraft assembly hangar", "rocket launch space",
                           "satellite in orbit", "airplane cockpit controls", "jet engine turbine",
                           "airport runway planes", "spacecraft engineering lab"],
    "transportation":     ["cargo container ship port", "freight train railway", "logistics warehouse trucks",
                           "highway trucks aerial", "shipping port cranes", "delivery van fleet",
                           "railway station tracks", "air cargo loading"],
    "automotive":         ["car assembly line robots", "electric vehicle charging", "automobile showroom",
                           "sports car studio", "car manufacturing factory", "ev battery production",
                           "automotive engine macro", "highway traffic cars"],
    "semiconductors":     ["silicon wafer macro", "semiconductor clean room", "microchip fabrication",
                           "computer processor macro", "chip manufacturing robot", "circuit board closeup",
                           "nanotechnology lab", "electronics production line"],
    "infrastructure":     ["bridge construction engineering", "highway overpass aerial", "construction crane megaproject",
                           "tunnel infrastructure", "dam engineering concrete", "skyscraper construction",
                           "roadworks machinery", "power grid infrastructure"],
    "agriculture":        ["wheat field harvest", "tractor plowing field", "modern greenhouse farming",
                           "vineyard aerial rows", "combine harvester", "irrigation crops field",
                           "livestock cattle farm", "grain silos storage"],
    "luxury":             ["luxury boutique storefront", "designer handbags display", "fine jewelry diamonds",
                           "luxury watch macro", "champagne celebration toast", "yacht ocean luxury",
                           "haute couture fashion runway", "luxury car detail"],
    "retail":             ["shopping mall interior", "retail store shelves", "ecommerce fulfillment center",
                           "checkout counter store", "clothing retail display", "supermarket aisle",
                           "shopping crowd store", "online shopping delivery"],
    "insurance":          ["insurance office handshake", "family home protection concept", "car accident claim",
                           "umbrella protection concept", "financial advisor meeting", "health insurance care",
                           "property insurance house", "risk management documents"],
    "banking":            ["bank branch interior", "atm banking machine", "bank vault safe",
                           "mobile banking phone", "credit card payment", "bank building facade",
                           "banker client meeting", "digital banking network"],
    "travel":             ["luxury resort pool", "airport terminal travelers", "tropical beach vacation",
                           "hotel lobby modern", "cruise ship ocean", "city tourism landmark",
                           "airplane window view", "mountain travel adventure"],
    "mining":             ["open pit mine aerial", "mining excavator machinery", "gold ore extraction",
                           "coal mining site", "copper mine terraces", "underground mine tunnel",
                           "mining haul truck", "raw mineral ore"],
    "cybersecurity":      ["cybersecurity data center", "digital lock security", "network security servers",
                           "code screen security", "biometric security scan", "encrypted data network",
                           "security operations center", "firewall network protection"],
    "renewables":         ["solar panel farm aerial", "wind turbine field", "clean energy sunset",
                           "hydroelectric power dam", "green energy technology", "battery storage renewable",
                           "geothermal power plant", "sustainable energy grid"],
    "media":              ["television broadcast studio", "film production set", "streaming media concept",
                           "newsroom journalists", "music recording studio", "cinema movie theater",
                           "live concert stage", "content creator studio"],
    "pharmaceuticals":    ["pharmaceutical production line", "vaccine research lab", "pill manufacturing macro",
                           "biotech laboratory scientist", "drug discovery microscope", "medical research dna",
                           "pharmacy medicine shelves", "clinical trial laboratory"],
    "markets":            ["stock market display board", "world map global finance", "candlestick trading charts",
                           "business district skyline", "currency exchange money", "economic data screens",
                           "bull and bear market", "financial newspaper"],
}
_YAHOO_SECTOR_ALIAS = {
    "technology": "technology", "energy": "energy",
    "financial services": "financials", "financials": "financials", "financial": "financials",
    "healthcare": "healthcare", "health care": "healthcare",
    "consumer cyclical": "consumer_cyclical", "consumer discretionary": "consumer_cyclical",
    "consumer defensive": "consumer_defensive", "consumer staples": "consumer_defensive",
    "industrials": "industrials",
    "basic materials": "materials", "materials": "materials",
    "utilities": "utilities", "real estate": "real_estate",
    "communication services": "communication", "communication": "communication",
}
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
    path = _CONFIG_DIR / file
    if not path.is_file() or path.suffix != ".json":
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
    path = _BRANDING_DIR / file
    if not path.is_file() or path.suffix != ".json":
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
        return engine.run_underlying_metrics(req.tickers, lang=req.lang)
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


@app.post("/api/report")
def report(req: ReportRequest, request: Request):
    """Build the institutional PDF report and return it as a downloadable file.
    `sections` selects which lenses to include (empty ⇒ everything available)."""
    try:
        terms = NoteTerms.from_dict(req.terms)
    except Exception as e:
        raise HTTPException(400, f"invalid note terms: {e}")
    # Server-side generation audit line (provenance: who generated what, when,
    # from where). Kept in the request log — visible ONLY to the service operator
    # — and deliberately NOT embedded in the PDF: the client IP is personal data
    # and the report is white-label / redistributable. For a commercial deploy,
    # mind IP-log retention (GDPR/CCPA).
    _audit(request, "report", note=terms.name, tickers=_tickers_of(req.terms),
           sections=len(req.sections or []), n_paths=req.n_paths, lang=req.lang, engine=req.engine)
    try:
        pdf = engine.build_report_pdf(
            terms, sections=req.sections, lang=req.lang, n_paths=req.n_paths,
            seed=req.seed, calib_years=req.calib_years, engine=req.engine,
            branding=req.branding)
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


# ── static front-end (single-image prod build) ───────────────────────────────
# In the container the React bundle is built to web/dist and served same-origin.
# Mounted LAST so the explicit /api/* routes above always take precedence;
# html=True serves index.html at "/" (and as the single-page fallback). Absent in
# local dev — Vite serves the front-end and proxies /api to uvicorn.
from fastapi.staticfiles import StaticFiles   # noqa: E402

_WEB_DIST = _REPO / "web" / "dist"
if _WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")
