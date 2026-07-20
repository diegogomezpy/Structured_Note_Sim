"""
api/engine.py
-------------
The compute flows behind the API, factored out of the old Streamlit run block.
Reuses the pure-quant core (core/, data/) and the Streamlit-free chart builders
(app/charts.py) — nothing numeric is reimplemented. Each flow returns plain,
JSON-serialisable dicts (figures as Plotly JSON via go.Figure.to_json()).

Full run results are kept in an in-memory store keyed by run_id so the path
explorer can fetch/filter individual paths later without re-simulating.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
# app/ holds the reusable (Streamlit-free) chart + i18n + ticker modules, which
# import each other by bare name (e.g. `from translations import Translator`), so
# app/ must be on sys.path for those to resolve — same as when Streamlit runs.
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "app"))

from core.note import (NoteTerms, price_note, replay_note,        # noqa: E402
                       _basket, _participation_redemption,
                       _participation_breakeven, participation_barrier_levels,
                       participation_period_income)
from core.calibrator import HestonCalibrator                      # noqa: E402
from core.simulator import HestonMultiSimulator                   # noqa: E402
from core.backtest import run_backtest, snapped_obs_dates         # noqa: E402
from data.loader import (load_prices, load_dividends,             # noqa: E402
                          build_dividend_schedule, load_underlying_metrics,
                          fetch_business_summary, resolve_issuer_summary,
                          translate_text)
import charts            # noqa: E402  (app/charts.py)
import translations      # noqa: E402  (app/translations.py)
import underlyings       # noqa: E402  (app/underlyings.py)

_PCTS = [1, 5, 25, 50, 75, 95, 99]

# ── Price cache (TTL) ─────────────────────────────────────────────────────────
# yfinance pulls are the slow part of every flow (calibrate / backtest / live all
# re-fetch the same daily closes). The Streamlit app memoised these via
# st.cache_data(ttl=…); the API has no such layer, so the live tab in particular
# re-pulled full history on every open. Cache by (tickers, years, field) with a
# 1-hour TTL — matching the Streamlit refresh cadence — so a single warm-up pull
# serves simulate + backtest + live. DataFrames are treated as read-only.
import threading                                                # noqa: E402

_PRICE_CACHE: "dict[tuple, tuple[float, pd.DataFrame]]" = {}
_PRICE_TTL = 3600.0
_PRICE_MAX = 32
_PRICE_LOCK = threading.Lock()


def _prices(tickers: dict, *, years: float | None, field: str = "close") -> pd.DataFrame:
    """Cached load_prices: reuse a recent pull for the same tickers/window/field."""
    key = (tuple(sorted(tickers.items())), years, field)
    now = time.time()
    with _PRICE_LOCK:
        hit = _PRICE_CACHE.get(key)
        if hit is not None and now - hit[0] < _PRICE_TTL:
            return hit[1]
    df = load_prices(source="yfinance", tickers=dict(tickers), years=years, field=field)
    with _PRICE_LOCK:
        _PRICE_CACHE[key] = (now, df)
        if len(_PRICE_CACHE) > _PRICE_MAX:
            oldest = min(_PRICE_CACHE.items(), key=lambda kv: kv[1][0])[0]
            _PRICE_CACHE.pop(oldest, None)
    return df


# ── Translation cache ─────────────────────────────────────────────────────────
# Machine translation (translate_text) is a network round-trip; the underlying
# cards re-fetch metrics on every language switch, so cache by (text, lang) to
# avoid re-translating the same Yahoo summary repeatedly.
_TR_CACHE: "OrderedDict[tuple, str]" = OrderedDict()
_TR_MAX = 256
_TR_LOCK = threading.Lock()


def _translated(text: str | None, lang: str) -> str | None:
    """Cached translate_text. Returns text unchanged for English/blank input."""
    if not text or not text.strip() or lang in (None, "", "en"):
        return text
    key = (text, lang)
    with _TR_LOCK:
        if key in _TR_CACHE:
            _TR_CACHE.move_to_end(key)
            return _TR_CACHE[key]
    out = translate_text(text, lang) or text
    with _TR_LOCK:
        _TR_CACHE[key] = out
        if len(_TR_CACHE) > _TR_MAX:
            _TR_CACHE.popitem(last=False)
    return out


# ── In-memory run store (bounded) ─────────────────────────────────────────────
# Keeps the compact per-path arrays for the explorer. LRU-evicted so a long-lived
# server can't grow without bound; a production multi-instance deploy would back
# this with Redis instead.
# ── run store (pluggable: in-memory default, Redis when REDIS_URL is set) ────────
# The store keeps the compact per-run arrays the path explorer / inspector / report
# re-read. In-memory it's LRU-bounded and lock-guarded (FastAPI runs sync endpoints
# in a threadpool). A multi-instance Cloud Run deploy needs a SHARED store, or a
# follow-up call load-balanced to a different instance 404s "run not found" — set
# REDIS_URL to a Memorystore/Redis and runs persist across instances. Redis is
# opt-in and best-effort: if it's unset or unreachable we fall back to in-memory.
_MAX_RUNS = 8
_RUN_TTL = 3600.0


class _InMemoryRunStore:
    """LRU + lock-guarded dict. `get` promotes so an actively-explored run isn't
    FIFO-evicted out from under the path explorer."""
    def __init__(self, max_runs: int = _MAX_RUNS):
        self._runs: "OrderedDict[str, dict]" = OrderedDict()
        self._max = max_runs
        self._lock = threading.Lock()

    def put(self, run_id: str, payload: dict) -> None:
        with self._lock:
            self._runs[run_id] = payload
            while len(self._runs) > self._max:
                self._runs.popitem(last=False)

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                self._runs.move_to_end(run_id)
            return run


class _RedisRunStore:
    """Shared cross-instance store. Payloads (numpy cubes + dicts) are pickled under
    a per-run key with a TTL; larger over the wire than in-memory, but the only way
    a path-explorer call that lands on a different instance can find its run."""
    def __init__(self, url: str, ttl: float = _RUN_TTL):
        import pickle
        import redis
        self._r = redis.from_url(url, socket_timeout=3, socket_connect_timeout=3)
        self._r.ping()                                   # fail fast → caller falls back
        self._ttl = int(ttl)
        self._pickle = pickle

    def put(self, run_id: str, payload: dict) -> None:
        self._r.set(f"snsim:run:{run_id}", self._pickle.dumps(payload), ex=self._ttl)

    def get(self, run_id: str) -> dict | None:
        raw = self._r.get(f"snsim:run:{run_id}")
        return self._pickle.loads(raw) if raw is not None else None


def _make_run_store():
    url = os.environ.get("REDIS_URL", "").strip()
    if url:
        try:
            store = _RedisRunStore(url)
            print(f"[engine] run store: Redis @ {url.rsplit('@', 1)[-1]}", flush=True)
            return store
        except Exception as e:                           # unreachable / redis not installed
            print(f"[engine] REDIS_URL set but Redis unavailable ({e}); using in-memory run store", flush=True)
    return _InMemoryRunStore()


_run_store = _make_run_store()

# Backtest results cache (keyed on tickers + terms) so the backtest inspector's
# filter/nav clicks reuse one run instead of re-backtesting every issue each time.
_BT_CACHE: "OrderedDict[tuple, tuple[float, object, dict]]" = OrderedDict()
_BT_TTL = 1800.0
_BT_MAX = 6
_BT_LOCK = threading.Lock()


def _store_run(payload: dict) -> str:
    run_id = uuid.uuid4().hex[:12]
    _run_store.put(run_id, {"created": time.time(), **payload})
    return run_id


def get_run(run_id: str) -> dict | None:
    return _run_store.get(run_id)


def sample_paths(run_id: str, *, sample: int = 400, seed: int = 7) -> dict | None:
    """A bounded, time-downsampled sample of worst-of trajectories for the path
    explorer, each tagged with its outcome (autocall period / knock-in / IRR) so
    the client can filter, colour, and zoom without re-simulating. Returns None
    if the run has been evicted from the in-memory store."""
    run = get_run(run_id)
    if run is None:
        return None
    perf   = run["perf_paths"]          # (P, N+1, A) float16
    t_grid = run["t_grid"]
    note   = run.get("note", {})
    terms  = run["terms"]

    P, N1 = perf.shape[0], perf.shape[1]
    rng = np.random.default_rng(seed)
    k = min(int(sample), P)
    idx = np.sort(rng.choice(P, size=k, replace=False))

    # Downsample the time axis to ~100 points (keep first + last).
    step  = max(1, N1 // 100)
    tcols = list(range(0, N1, step))
    if tcols[-1] != N1 - 1:
        tcols.append(N1 - 1)

    ap  = note.get("autocall_period")
    ki  = note.get("knock_in_triggered")   # price_note's key (was wrongly "knock_in_mask")
    irr = note.get("annualized_returns")
    red = note.get("nominal_payoffs")      # per-path redemption (participation)

    _note_type = terms.get("note_type", "phoenix")
    _is_part = _note_type == "participation"
    # For a Participation note the payoff references the participation BASKET, not the
    # worst-of — reduce along assets with the note's basket type so the fan matches.
    _sel = np.asarray(perf[idx], dtype=np.float32)
    if _is_part and terms.get("participation_basket") == "best_of":
        line_sel = _sel.max(axis=2)
    elif _is_part and terms.get("participation_basket") == "average":
        line_sel = _sel.mean(axis=2)
    else:
        line_sel = _sel.min(axis=2)               # (k, N+1) worst-of / worst-of basket
    paths = []
    for j, i in enumerate(idx):
        row = {
            "wof": [round(float(line_sel[j, c]), 4) for c in tcols],
            "ap":  int(ap[i])  if ap  is not None else 0,
            "ki":  bool(ki[i]) if ki  is not None else False,
            "irr": _f(irr[i])  if irr is not None else None,
        }
        if _is_part and red is not None:
            row["red"] = _f(red[i])               # realised redemption (fraction of par)
        paths.append(row)

    if _is_part:
        periodic = bool(terms.get("participation_periodic"))
        _lv = participation_barrier_levels(terms)
        barriers = {"participation": {"strike": _f(terms.get("participation_strike")),
                                      "floor": _f(_lv["floor"]), "cap": _f(_lv["cap"]), "periodic": periodic}}
    else:
        barriers = {"knock_in": _f(terms.get("knock_in_barrier")),
                    "autocall": _f(terms.get("autocall_barrier")),
                    "coupon":   _f(terms.get("coupon_barrier"))}
    return {
        "t":        [round(float(t_grid[c]), 4) for c in tcols],
        "paths":    paths,
        "n_total":  int(P),
        "note_type": _note_type,
        "obs_times": run.get("obs_times", []),
        "barriers": barriers,
    }


# ── single-path inspector (Monte Carlo & backtest share this) ───────────────────
def _path_filter_matches(autocall_events, knock_in, total_returns, coupon_amounts,
                         *, outcome="any", ac_periods=None, ki_choice="any",
                         ret_lo=None, ret_hi=None, coupon_periods=None):
    """Sorted indices of paths matching the explorer query (AND-combined). Pure —
    operates on the per-path arrays price_note returns, so it serves both the MC
    and backtest inspectors. Ported verbatim from app.py:_path_filter_matches."""
    ac   = np.asarray(autocall_events)
    ki   = np.asarray(knock_in, dtype=bool)
    ret  = np.asarray(total_returns, dtype=float)
    mask = np.ones(ac.shape[0], dtype=bool)

    if outcome == "autocalled":
        mask &= ac > 0
        if ac_periods:
            mask &= np.isin(ac, list(ac_periods))
    elif outcome == "maturity":
        mask &= ac == 0
    elif outcome == "loss":
        mask &= (ac == 0) & ki
    # Participation outcomes (no autocall) — filter on the redemption sign, i.e. the
    # per-path total return: gain above par, flat at par, loss below par.
    elif outcome == "part_gain":
        mask &= ret > 1e-9
    elif outcome == "part_par":
        mask &= np.abs(ret) <= 1e-9
    elif outcome == "part_loss":
        mask &= ret < -1e-9

    if ki_choice == "yes":
        mask &= ki
    elif ki_choice == "no":
        mask &= ~ki

    if ret_lo is not None:
        mask &= ret >= ret_lo
    if ret_hi is not None:
        mask &= ret <= ret_hi

    if coupon_periods and coupon_amounts is not None:
        ca = np.asarray(coupon_amounts)
        for p in coupon_periods:
            if 1 <= int(p) <= ca.shape[1]:
                mask &= ca[:, int(p) - 1] > 0

    return np.nonzero(mask)[0]


def _build_path_marker_info(rows, autocall_q, n_obs, wof_levels, knock_in, terms, tr):
    """Per-observation legend entries for the inspector's worst-of chart (ported
    from app.py:_build_path_marker_info). Each entry: {text, kind}."""
    info = []
    n_live = autocall_q if autocall_q > 0 else n_obs
    rate = terms.coupon_rate
    for i in range(n_live):
        period      = i + 1
        row         = rows[i] if i < len(rows) else None
        amt         = float(row["coupon_amount"]) if row else 0.0
        pending     = int(row["pending_after"]) if row else 0
        called      = (autocall_q == period)
        reached_mat = (autocall_q == 0 and period == n_obs)

        parts = [f"P{period}", tr("leg_wof", v=f"{wof_levels[i]:.0%}")]
        if called:
            parts.append(tr("leg_called"))
        elif reached_mat:
            parts.append(tr("leg_maturity"))

        if terms.coupon_at_autocall_only:
            if amt > 0:
                parts.append(tr("leg_premium", v=f"{amt:.2%}", k=period))
            elif not called and not reached_mat:
                parts.append(tr("leg_accruing"))
        elif amt > 0:
            released = round(amt / rate) if rate else 1
            if terms.memory and released > 1:
                parts.append(tr("leg_coupon_memory", v=f"{amt:.2%}", k=released))
            else:
                parts.append(tr("leg_coupon", v=f"{amt:.2%}"))
        else:
            if terms.memory and pending > 0:
                parts.append(tr("leg_no_coupon_pending", k=pending))
            else:
                parts.append(tr("leg_no_coupon"))

        if reached_mat:
            parts.append(tr("leg_knock_in") if knock_in else tr("leg_redeemed_par"))

        # Number of coupons released at this observation (>1 when memory pays out
        # accrued coupons in a lump) — drives the stacked-dot marker on the client.
        released = round(amt / rate) if (rate and amt > 0) else (1 if amt > 0 else 0)

        if reached_mat and knock_in:
            kind = "knock_in"
        elif reached_mat:
            kind = "redeem"                       # matured at par, not knocked in
        elif called:
            kind = "call_coupon" if amt > 0 else "call"
        else:
            kind = "coupon" if amt > 0 else "missed"
        info.append({"text": " · ".join(parts), "kind": kind, "n": int(released)})
    return info


def _participation_line_and_markers(asset_paths, obs_steps, terms, tr):
    """For a Participation note the payoff references the participation BASKET (not
    the worst-of), and there are no coupons / autocall / knock-in events. Return
    ``(basket_line, marker_info)``:

    - ``basket_line`` — the participation-basket trajectory over the full path (drawn
      as the hero line in place of the worst-of).
    - single-shot: a muted basket dot at each intermediate observation, and a final
      redemption marker (green when redeemed ≥ par, red on a capital loss) reading
      the realised redemption vs the final basket.
    - cliquet: one marker per reset period showing that period's basket move and the
      locked-in participation P&L (which can be negative under buffer/airbag/bear).
    """
    basket_line = _basket(np.asarray(asset_paths, dtype=float), terms.participation_basket)  # (N+1,)
    B = np.asarray([float(basket_line[int(s)]) for s in obs_steps])                            # basket at each obs
    info: list[dict] = []
    if getattr(terms, "participation_periodic", False):
        prev = 1.0
        for j, b in enumerate(B):
            level = b / prev if prev else 1.0
            inc = float(participation_period_income([level], terms)[0])
            prev = b
            kind = "part_gain" if inc > 1e-9 else ("part_loss" if inc < -1e-9 else "part_flat")
            info.append({"text": tr("leg_part_reset", k=j + 1,
                                    move=f"{level - 1:+.1%}", inc=f"{inc:+.2%}"),
                         "kind": kind, "n": 1})
    else:
        for j, b in enumerate(B):
            if j < len(B) - 1:
                info.append({"text": tr("leg_part_hold", k=j + 1, b=f"{b:.0%}"),
                             "kind": "part_hold", "n": 1})
            else:
                R = float(_participation_redemption(np.array([b]), terms)[0])
                kind = "part_loss" if R < 1.0 - 1e-9 else "part_redeem"
                info.append({"text": tr("leg_part_redeem", b=f"{b:.0%}", r=f"{R:.1%}"),
                             "kind": kind, "n": 1})
    return basket_line, info


def _path_payload(worst_path, asset_paths, asset_names, obs_steps, autocall_q,
                  marker_info, terms, note_type="phoenix") -> dict:
    """Raw single-path data for the React inspector chart — per-asset + worst-of
    trajectories (truncated at the call, time-downsampled) plus observation markers
    and barriers. The client renders it in the app's own chart aesthetic, so the
    inspector matches the rest of the UI instead of the Streamlit chart palette.

    For a Participation note the ``worst_path`` passed in is actually the
    participation-basket line, and the barriers carry the payoff reference levels
    (strike / protection floor / cap) instead of knock-in / autocall."""
    worst_path  = np.asarray(worst_path)
    asset_paths = np.asarray(asset_paths)
    N1  = len(worst_path)
    cut = int(obs_steps[autocall_q - 1]) if autocall_q > 0 else N1 - 1
    step = max(1, (cut + 1) // 150)
    cols = list(range(0, cut + 1, step))
    if cols[-1] != cut:
        cols.append(cut)
    # Force every observation step onto the sampled grid so each event marker lands
    # exactly on a plotted vertex. This matters for the cliquet per-period view: the
    # front-end renormalises each period by the basket level *at its reset*, and if a
    # reset falls between sampled columns it would pick a stale/ahead neighbour and
    # smear a level offset across the whole next period.
    obs_cols = [int(s) for s in obs_steps if 0 <= int(s) <= cut]
    if obs_cols:
        cols = sorted(set(cols) | set(obs_cols))

    series = [{"name": nm, "perf": [round(float(asset_paths[c, i]), 4) for c in cols]}
              for i, nm in enumerate(asset_names)]
    wof = [round(float(worst_path[c]), 4) for c in cols]

    markers = []
    n_live = autocall_q if autocall_q > 0 else len(obs_steps)
    for i in range(min(n_live, len(marker_info))):
        s = int(obs_steps[i])
        if s > cut:
            break
        markers.append({"x": s, "y": round(float(worst_path[s]), 4),
                        "text": marker_info[i]["text"], "kind": marker_info[i]["kind"],
                        "n": int(marker_info[i].get("n", 1))})

    if note_type == "participation":
        periodic = bool(getattr(terms, "participation_periodic", False))
        # The floor / cap reference the whole-basket redemption of a single-maturity
        # note; a cliquet's per-period profile resets each period, so a single floor/
        # cap over the cumulative basket would mislead — the helper omits them there.
        _lv = participation_barrier_levels(terms)
        barriers = {"knock_in": None, "autocall": None, "autocall_schedule": None,
                    "participation": {"strike": _f(terms.participation_strike),
                                      "floor": _f(_lv["floor"]), "cap": _f(_lv["cap"]),
                                      "periodic": periodic}}
    else:
        ac_sched = ([[int(s), float(lv)]
                     for s, lv in zip(obs_steps, terms.autocall_barrier_schedule())]
                    if terms.autocall_step_down else None)
        barriers = {"knock_in": _f(terms.knock_in_barrier),
                    "autocall": _f(terms.autocall_barrier),
                    "autocall_schedule": ac_sched}
    return {
        "t": cols, "series": series, "wof": wof, "markers": markers, "x_max": cut,
        "barriers": barriers,
    }


def inspect_run(run_id: str, *, lang: str = "en", filters: dict | None = None,
                position: int = 0, randomize: bool = False, title: str | None = None) -> dict | None:
    """One Monte-Carlo path in full detail for the single-path inspector: the
    worst-of + per-asset trajectories with per-observation event markers (via
    replay_note), plus filter/match metadata so the client can step through the
    paths matching its query. Returns None if the run has expired."""
    run = get_run(run_id)
    if run is None:
        return None
    tr     = translations.Translator(lang)
    perf   = run["perf_paths"]                       # (P, N+1, A) float16
    note   = run.get("note", {})
    terms  = NoteTerms.from_dict(run["terms"])
    obs_steps = list(run["obs_steps"])
    obs_times = list(run["obs_times"])
    asset_names = run["asset_names"]
    n_obs   = terms.n_obs
    obs_labels = [f"P{i + 1}" for i in range(n_obs)]

    ac       = np.asarray(note["autocall_period"])
    ki_arr   = np.asarray(note["knock_in_triggered"], dtype=bool)
    total    = np.asarray(note["total_returns"], dtype=float)
    coupon_m = note.get("coupon_amounts")
    P = perf.shape[0]
    ret_range = [float(total.min()), float(total.max())]

    f = filters or {}
    matches = _path_filter_matches(
        ac, ki_arr, total, coupon_m,
        outcome=f.get("outcome", "any"), ac_periods=f.get("ac_periods"),
        ki_choice=f.get("ki_choice", "any"),
        ret_lo=f.get("ret_lo"), ret_hi=f.get("ret_hi"),
        coupon_periods=f.get("coupon_periods"))
    M = int(len(matches))

    _note_type = getattr(terms, "note_type", "phoenix")
    _is_part = _note_type == "participation"
    base = {"n_total": int(P), "n_matched": M, "ret_range": ret_range,
            "n_obs": int(n_obs), "coupon_available": (coupon_m is not None) and not _is_part,
            "note_type": _note_type,
            "participation_periodic": bool(getattr(terms, "participation_periodic", False))}
    if M == 0:
        return {**base, "position": 0, "path_index": None, "figure": None}

    if randomize:
        position = int(np.random.default_rng().integers(0, M))
    position = max(0, min(int(position), M - 1))
    pn = int(matches[position])

    asset_paths = np.asarray(perf[pn], dtype=np.float64)   # (N+1, A)
    worst_path  = asset_paths.min(axis=1)
    autocall_q  = int(ac[pn])
    ki_pn       = bool(ki_arr[pn])

    if _is_part:
        line_path, marker_info = _participation_line_and_markers(asset_paths, obs_steps, terms, tr)
        B_final = float(line_path[-1])
        R_final = float(_participation_redemption(np.array([B_final]), terms)[0])
        outcome = {"autocall_q": 0, "call_time": None,
                   "knock_in": R_final < 1.0 - 1e-9, "worst_final": _f(B_final),
                   "redemption": _f(R_final), "final_basket": _f(B_final),
                   "is_loss": R_final < 1.0 - 1e-9}
    else:
        line_path = worst_path
        perf_obs    = asset_paths[obs_steps, :]
        rows        = replay_note(perf_obs, terms)["rows"]
        wof_levels  = [float(worst_path[s]) for s in obs_steps]
        marker_info = _build_path_marker_info(rows, autocall_q, n_obs, wof_levels, ki_pn, terms, tr)
        outcome = {"autocall_q": autocall_q,
                   "call_time": _f(obs_times[autocall_q - 1]) if autocall_q > 0 else None,
                   "knock_in": ki_pn, "worst_final": _f(float(worst_path[-1]))}

    return {
        **base,
        "position":   position,
        "path_index": pn,
        "path":       _path_payload(line_path, asset_paths, asset_names,
                                    obs_steps, autocall_q, marker_info, terms, _note_type),
        "outcome": outcome,
        "metrics": {
            "principal":    _f(note["principal_payoffs"][pn]),
            "coupons":      _f(note["coupon_payoffs"][pn]),
            "irr":          _f(note["annualized_returns"][pn]),
            "total_return": _f(total[pn]),
        },
        "assets": [{"name": nm, "final": _f(float(asset_paths[-1, i]))}
                   for i, nm in enumerate(asset_names)],
    }


# ── helpers ───────────────────────────────────────────────────────────────────
def _fig(fig) -> dict:
    """Plotly figure → plain dict (numpy-safe via Plotly's own JSON encoder)."""
    return json.loads(fig.to_json())


def _f(x) -> float | None:
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


# ── simulation flow ────────────────────────────────────────────────────────────
def _snap_obs(grid, anchor, N: int, terms: NoteTerms) -> tuple[list[int], list[float]]:
    """Snap a note's observation calendar onto the trading-day `grid` → (step index
    per observation, capped at N; time-in-years per observation). Shared by the
    initial simulation and the A/B reprice so the two stay identical."""
    obs_steps = [min(int(grid.searchsorted(d)), N) for d in terms.obs_calendar_dates(anchor)]
    obs_times = [(grid[s] - grid[0]).days / 365.0 for s in obs_steps]
    return obs_steps, obs_times


def _simulate_full(terms: NoteTerms, *, n_paths: int, seed: int, calib_years: float,
                   history_years: float | None, engine: str) -> dict:
    """Load → calibrate → simulate → price. The shared compute core behind both
    the JSON simulate endpoint and the PDF report builder; returns the raw numpy
    objects (full price_note dict, perf cubes, percentile bands, calibration) so
    each caller can serialise or render as it needs. price_note stays the single
    payoff engine."""
    tickers = dict(terms.tickers)

    # Calibrate on adjusted closes (total-return dynamics); barriers/S0/dividends
    # live in raw price space.
    prices_adj = _prices(tickers, years=history_years, field="adj_close")
    prices_raw = _prices(tickers, years=history_years, field="close")
    cal_result = HestonCalibrator(prices_df=prices_adj, calib_years=calib_years).calibrate()

    raw_last = prices_raw.iloc[-1]
    for p in cal_result.params:
        if p.name in raw_last.index:
            p.S0 = float(raw_last[p.name])

    # Trading-day grid to maturity.
    anchor   = prices_raw.index[-1]
    mat_date = pd.offsets.BDay().rollforward(
        anchor + pd.DateOffset(months=round(terms.maturity * 12)))
    grid     = pd.bdate_range(anchor, mat_date)
    dt_grid  = np.diff(grid.values).astype("timedelta64[D]").astype(float) / 365.0
    N        = len(grid) - 1
    obs_steps, obs_times = _snap_obs(grid, anchor, N, terms)

    # Pre-programmed dividend jumps (graceful if the pull fails).
    try:
        divs = load_dividends(tickers)
    except Exception:
        divs = {}
    div_sched = build_dividend_schedule(
        [divs.get(p.name, pd.Series(dtype=float)) for p in cal_result.params],
        [p.S0 for p in cal_result.params], grid)

    sim = HestonMultiSimulator(
        params=cal_result.params, corr_SS=cal_result.corr_SS,
        corr_VV=cal_result.corr_VV, corr_SV=cal_result.corr_SV,
        n_paths=n_paths, seed=seed, t_dof=cal_result.t_dof,
        dt_grid=dt_grid, div_schedule=div_sched)
    eng_used = engine
    try:
        sim_results = sim.run(engine=engine)
    except ImportError:
        eng_used = "numpy"
        sim_results = sim.run(engine="numpy")

    n_assets   = len(cal_result.params)
    sim_prices = np.stack(sim_results["S_paths"], axis=2)
    S0_vec     = np.array([p.S0 for p in cal_result.params]).reshape(1, 1, n_assets)
    perf_paths = sim_prices / S0_vec
    wof_paths  = perf_paths.min(axis=2)

    note = price_note(perf_paths, terms, seed=seed + 1,
                      obs_steps=obs_steps, obs_times=obs_times)

    wof_bands   = np.percentile(wof_paths, _PCTS, axis=0)
    asset_bands = np.stack([np.percentile(sim_prices[:, :, i], _PCTS, axis=0)
                            for i in range(n_assets)])
    t_grid      = np.concatenate([[0.0], np.cumsum(dt_grid)])
    obs_pairs   = [(f"P{i+1}", t) for i, t in enumerate(obs_times)]
    asset_names = list(tickers.values())

    return {
        "cal_result": cal_result, "sim_results": sim_results, "note": note,
        "perf_paths": perf_paths, "wof_paths": wof_paths, "sim_prices": sim_prices,
        "wof_bands": wof_bands, "asset_bands": asset_bands, "t_grid": t_grid,
        "obs_steps": obs_steps, "obs_times": obs_times, "obs_pairs": obs_pairs,
        "asset_names": asset_names, "eng_used": eng_used,
        # Grid internals so a second note (A/B compare) can be RE-PRICED on the very
        # same simulated paths — recomputing only its own observation schedule.
        "grid": grid, "anchor": anchor, "N": N, "seed": seed,
    }


def _mc_figures(sf: dict, note: dict, terms: NoteTerms, tr) -> dict:
    """Monte Carlo figures for ONE note off a simulation context `sf`. The
    underlying figures (worst-of fan, per-asset fans, correlations) depend only on
    the shared simulated paths; the note figures (outcome, IRR) depend on the
    priced note — so an A/B compare that shares paths rebuilds these cheaply."""
    cal_result, sim_results = sf["cal_result"], sf["sim_results"]
    wof_bands, asset_bands = sf["wof_bands"], sf["asset_bands"]
    t_grid, obs_pairs, asset_names = sf["t_grid"], sf["obs_pairs"], sf["asset_names"]

    _is_part = getattr(terms, "note_type", "") == "participation"
    # Participation never autocalls → the autocall outcome breakdown is meaningless;
    # show the redemption distribution instead. Phoenix path unchanged.
    _outcome_fig = (charts.build_redemption_distribution(note["nominal_payoffs"], terms, tr)
                    if _is_part else
                    charts.build_outcome_breakdown(
                        note.get("prob_autocall_by_period"), note.get("prob_maturity"),
                        note.get("prob_knock_in_total"), tr))
    return {
        "outcome": _fig(_outcome_fig),
        "irr_dist": _fig(charts.build_irr_distribution(
            note["annualized_returns"], note.get("total_returns"),
            note["autocall_events"], note["expected_irr"], terms.coupon_pa, tr)),
        "wof_fan": _fig(charts.build_wof_fan(
            None, t_grid, terms.knock_in_barrier, obs_pairs, tr,
            autocall_barrier=terms.autocall_barrier, bands=wof_bands)),
        "asset_fans": [
            {"name": nm, "fig": _fig(charts.build_fan_chart(
                None, nm, t_grid, obs_pairs, tr, bands=asset_bands[i]))}
            for i, nm in enumerate(asset_names)
        ],
        "corr_input":    _fig(charts.build_corr_heatmap(
            cal_result.corr_SS, asset_names, tr("corr_input"))),
        "corr_realized": _fig(charts.build_corr_heatmap(
            sim_results["realized_corr"], asset_names, tr("corr_realized"))),
        "corr_diff": _fig(charts.build_corr_heatmap(
            np.asarray(cal_result.corr_SS) - np.asarray(sim_results["realized_corr"]),
            asset_names, "Δ  input − realized", zmin=-0.1, zmax=0.1)),
    }


def _mc_summary(sf: dict, note: dict, terms: NoteTerms) -> dict:
    """Assemble the JSON summary (payoff stats + calibration) for ONE note."""
    cal_result, obs_times = sf["cal_result"], sf["obs_times"]
    asset_names, eng_used = sf["asset_names"], sf["eng_used"]
    summary = {k: _f(note.get(k)) for k in (
        "expected_irr", "expected_total_return", "expected_coupon",
        "prob_autocall", "prob_knock_in_total", "expected_nominal_payout",
        "loss_given_knock_in", "prob_maturity", "prob_rescued",
        "prob_barrier_event", "avg_time_to_autocall",
        # participation-only (None on Phoenix → the client ignores them)
        "prob_above_par", "prob_below_par", "prob_at_cap", "prob_knocked_out",
        "expected_gain", "expected_redemption", "p5_redemption", "p95_redemption",
        "cvar5_redemption", "breakeven_level", "up_capture", "dn_capture")}
    summary["note_type"] = getattr(terms, "note_type", "phoenix")
    # For a Participation run, send a downsample of the final-basket levels so the
    # client can redraw the payoff-profile distribution overlay and recompute the
    # what-if table (rate/cap/protection) instantly via the TS redemption mirror —
    # no re-simulation. ~2000 points (stride subsample; paths are already unordered).
    _fb = note.get("final_basket")
    if _fb is not None:
        _fb = np.asarray(_fb, dtype=float)
        stride = max(1, len(_fb) // 4000)
        summary["final_basket_sample"] = [round(float(x), 5) for x in _fb[::stride][:4000]]
    # Cliquet per-period stats — power the per-reset small-multiples.
    if getattr(terms, "participation_periodic", False):
        for k in ("period_move_mean", "period_income_mean", "period_move_p25", "period_move_p75"):
            v = note.get(k)
            if v is not None:
                summary[k] = [round(float(x), 5) for x in np.asarray(v)]
    summary["n_paths"] = int(len(note["annualized_returns"]))   # 2×n_paths (antithetic)
    summary["engine"]  = eng_used
    summary["assets"]  = asset_names
    summary["coupon_pa"] = _f(terms.coupon_pa)
    summary["n_obs"]     = int(terms.n_obs)
    # Per-period autocall fractions — powers the outcome waterfall on the client.
    summary["autocall_by_period"] = [float(x) for x in
                                     note.get("prob_autocall_by_period", [])]
    summary["obs_times"] = [float(x) for x in obs_times]
    # Calibrated Heston parameters per asset (+ Feller margin) for the calibration
    # table, and the Student-t copula dof.
    summary["t_dof"] = _f(cal_result.t_dof)
    summary["calibration"] = [
        {"name": p.name, "S0": _f(p.S0), "mu": _f(p.mu), "V0": _f(p.V0),
         "theta": _f(p.theta), "kappa": _f(p.kappa), "xi": _f(p.xi), "rho": _f(p.rho),
         "feller": _f(2 * p.kappa * p.theta - p.xi ** 2)}
        for p in cal_result.params
    ]
    return summary


def _store_mc_run(sf: dict, note: dict, terms: NoteTerms) -> str:
    """Cache the compact per-note arrays for the path explorer (Phase 3)."""
    return _store_run({
        "perf_paths": sf["perf_paths"].astype(np.float16),
        "wof_bands":  sf["wof_bands"].astype(np.float32),
        "obs_steps":  sf["obs_steps"],
        "obs_times":  sf["obs_times"],
        "t_grid":     sf["t_grid"],
        "asset_names": sf["asset_names"],
        "terms":      terms.to_dict(),
        "note":       {k: np.asarray(v) for k, v in note.items()
                       if isinstance(v, np.ndarray) and v.ndim <= 2},
    })


def run_simulation(terms: NoteTerms, *, n_paths: int = 10000, seed: int = 42,
                   calib_years: float = 5.0, history_years: float | None = None,
                   engine: str = "cpp", lang: str = "en") -> dict:
    """Load → calibrate → simulate → price, then build the Monte Carlo figures.
    Mirrors the old Streamlit run block; returns summary stats + Plotly-JSON
    figures + a run_id (full paths cached server-side for the explorer)."""
    tr = translations.Translator(lang)
    sf = _simulate_full(terms, n_paths=n_paths, seed=seed, calib_years=calib_years,
                        history_years=history_years, engine=engine)
    note = sf["note"]
    figures = _mc_figures(sf, note, terms, tr)
    summary = _mc_summary(sf, note, terms)
    run_id = _store_mc_run(sf, note, terms)
    return {"run_id": run_id, "summary": summary, "figures": figures}


def _reprice_on_paths(sf: dict, terms: NoteTerms, *, seed: int) -> dict:
    """Re-price a DIFFERENT note on an existing simulation context `sf` (same
    underlying paths). Recomputes only the note's own observation schedule against
    the shared trading-day grid, then returns a fresh `sf`-shaped dict whose `note`
    and obs metadata are for `terms` but whose paths/bands/calibration are shared."""
    grid, anchor, N = sf["grid"], sf["anchor"], sf["N"]
    obs_steps, obs_times = _snap_obs(grid, anchor, N, terms)
    note = price_note(sf["perf_paths"], terms, seed=seed + 1,
                      obs_steps=obs_steps, obs_times=obs_times)
    return {**sf, "note": note, "obs_steps": obs_steps, "obs_times": obs_times,
            "obs_pairs": [(f"P{i+1}", t) for i, t in enumerate(obs_times)]}


def run_compare(terms_a: NoteTerms, terms_b: NoteTerms, *, n_paths: int = 10000,
                seed: int = 42, calib_years: float = 5.0,
                history_years: float | None = None, engine: str = "cpp",
                lang: str = "en") -> dict:
    """Price two notes head-to-head. When they share the SAME underlyings and
    maturity the underlying is simulated ONCE and both notes are priced on the
    identical paths — so every difference is attributable to the terms, not RNG
    noise. Otherwise B is simulated independently. Returns each side's run/summary/
    figures plus overlay figures and a metrics diff."""
    tr = translations.Translator(lang)
    sf_a = _simulate_full(terms_a, n_paths=n_paths, seed=seed, calib_years=calib_years,
                          history_years=history_years, engine=engine)
    shared = (dict(terms_a.tickers) == dict(terms_b.tickers)
              and abs(float(terms_a.maturity) - float(terms_b.maturity)) < 1e-9)
    if shared:
        sf_b = _reprice_on_paths(sf_a, terms_b, seed=seed)
    else:
        sf_b = _simulate_full(terms_b, n_paths=n_paths, seed=seed, calib_years=calib_years,
                              history_years=history_years, engine=engine)
    note_a, note_b = sf_a["note"], sf_b["note"]

    side_a = {"run_id": _store_mc_run(sf_a, note_a, terms_a),
              "summary": _mc_summary(sf_a, note_a, terms_a),
              "figures": _mc_figures(sf_a, note_a, terms_a, tr)}
    side_b = {"run_id": _store_mc_run(sf_b, note_b, terms_b),
              "summary": _mc_summary(sf_b, note_b, terms_b),
              "figures": _mc_figures(sf_b, note_b, terms_b, tr)}

    compare = {
        "shared_paths": shared,
        "diff": _compare_diff(side_a["summary"], side_b["summary"], terms_a, terms_b),
        "figures": {
            "irr": _fig(charts.build_irr_compare(
                note_a["annualized_returns"], note_b["annualized_returns"],
                note_a["expected_irr"], note_b["expected_irr"], tr)),
            "outcome": _fig(charts.build_outcome_compare(note_a, note_b, terms_a, terms_b, tr)),
        },
    }
    return {"a": side_a, "b": side_b, "compare": compare}


def _compare_diff(sum_a: dict, sum_b: dict, terms_a: NoteTerms, terms_b: NoteTerms) -> dict:
    """Metric-by-metric A · B · Δ table data. Only metrics meaningful for BOTH
    note types are surfaced; the client renders/formats per metric."""
    both_part = sum_a.get("note_type") == "participation" and sum_b.get("note_type") == "participation"
    # NB: for a Phoenix note `expected_nominal_payout` is just `expected_total_return
    # + 100%` (it folds coupons into "redemption"), so it's deliberately omitted here
    # — it's redundant with total return and its "redemption" label misleads. It's
    # kept for Participation, where there are no coupons and it IS the redemption.
    keys = (["expected_irr", "expected_total_return", "expected_gain", "prob_above_par",
             "prob_at_cap", "prob_knocked_out", "p5_redemption"] if both_part else
            ["expected_irr", "expected_total_return", "expected_coupon", "prob_autocall",
             "prob_knock_in_total", "avg_time_to_autocall"])
    rows = []
    for k in keys:
        a, b = sum_a.get(k), sum_b.get(k)
        if a is None and b is None:
            continue
        d = (b - a) if (isinstance(a, (int, float)) and isinstance(b, (int, float))) else None
        rows.append({"key": k, "a": a, "b": b, "delta": d})
    return {"rows": rows, "both_participation": both_part}


# ── backtest flow ───────────────────────────────────────────────────────────────
def _lerp_hex(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3))


def _backtest_outcome_labels(bt) -> "tuple[list[str], dict[str, str]]":
    """Per-issue outcome label + a matching colour map for the backtest charts.
    Autocall periods ride a light-emerald→ink-green ramp, held-to-maturity teal,
    knock-in amber (no red — survives the PDF rebrand). The single source shared by
    the web backtest and the PDF backtest so their legends and colours stay identical."""
    def _label(cq, ki):
        if int(cq) > 0:
            return f"Autocalled P{int(cq)}"
        return "Knock-in" if bool(ki) else "Held to maturity"
    outcome = [_label(cq, ki) for cq, ki in zip(bt["Call Quarter"], bt["Knock-in"])]
    ac_periods = sorted({int(cq) for cq in bt["Call Quarter"] if int(cq) > 0})
    color_map = {"Held to maturity": "#2e7e8c", "Knock-in": "#c9772d"}
    for i, q in enumerate(ac_periods):
        color_map[f"Autocalled P{q}"] = _lerp_hex("#9bd8b4", "#0b3d2e", i / max(1, len(ac_periods) - 1))
    return outcome, color_map


def _ts(s: str | None):
    return pd.Timestamp(s) if s else None


def run_backtest_api(terms: NoteTerms, *, history_years: float | None = None,
                     lang: str = "en", bt_start: str | None = None,
                     bt_end: str | None = None) -> dict:
    """Historical backtest over realized prices — summary metrics, per-issue rows,
    and the outcome/scatter/pie/price figures (mirrors the Streamlit backtest).
    bt_start/bt_end restrict the issue-date window (ISO strings)."""
    tr = translations.Translator(lang)
    prices = _prices(dict(terms.tickers), years=history_years, field="close")
    bt, summary = run_backtest(prices, terms, bt_start=_ts(bt_start), bt_end=_ts(bt_end))
    if bt.empty:
        return {"summary": {}, "issues": [], "figures": None}

    _note_type = getattr(terms, "note_type", "phoenix")
    _is_part = _note_type == "participation"
    _periodic = bool(getattr(terms, "participation_periodic", False))
    out_summary = {k: _f(v) for k, v in summary.items()
                   if not isinstance(v, (list, np.ndarray))}
    out_summary["n_issues"] = int(len(bt))
    out_summary["note_type"] = _note_type
    out_summary["participation_periodic"] = _periodic
    bt = bt.copy()

    if _is_part:
        # Participation: realised redemption per issue is the "Payout". Summarise the
        # redemption distribution (prob above/below par, median/best/worst, CVaR,
        # capture ratios) and label each issue by which redemption BAND it landed in
        # — there is no autocall period to bucket on.
        R = bt["Payout"].to_numpy(dtype=float)
        asset_cols = [f"{nm} Perf" for nm in terms.tickers.values() if f"{nm} Perf" in bt.columns]
        B = (_basket(bt[asset_cols].to_numpy(dtype=float), terms.participation_basket)
             if asset_cols else bt["Worst Final Perf"].to_numpy(dtype=float))
        from core.note import _participation_stats
        out_summary.update({k: _f(v) for k, v in _participation_stats(R, terms, B).items()})
        out_summary["median_redemption"] = _f(float(np.median(R)))
        out_summary["best_redemption"]   = _f(float(R.max()))
        out_summary["worst_redemption"]  = _f(float(R.min()))

        cap_lv = (1.0 + terms.upside_cap) if terms.upside_cap is not None else None
        L_loss, L_par = tr("bt_band_loss"), tr("bt_band_par")
        L_gain, L_cap = tr("bt_band_gain"), tr("bt_band_capped")
        def _band(r):
            if r < 1.0 - 1e-9:                              return L_loss
            if abs(r - 1.0) <= 5e-3:                        return L_par
            if cap_lv is not None and r >= cap_lv - 1e-6:   return L_cap
            return L_gain
        bt["Outcome"] = [_band(r) for r in R]
        color_map = {L_loss: "#c9772d", L_par: "#2e7e8c", L_gain: "#3f8a6f", L_cap: "#0b3d2e"}

        figures = {
            "worst_asset_pie": _fig(charts.build_worst_asset_pie(bt, tr)),
            "redemption_dist": _fig(charts.build_redemption_distribution(R, terms, tr)),
            "irr_scatter":     _fig(charts.build_backtest_irr_scatter(bt, color_map, tr)),
            "prices":          _fig(charts.build_historical_prices(
                prices, bt["Issue Date"].min(), bt["Issue Date"].max(), tr)),
        }
        issues = [
            {"issue_date": d.strftime("%Y-%m-%d"),
             "redemption": _f(r), "income": _f(inc), "irr": _f(irr),
             "worst_asset": str(wa), "worst_perf": _f(wp), "band": band}
            for d, r, inc, irr, wa, wp, band in zip(
                bt["Issue Date"], R, bt["Total Coupons"], bt["IRR"],
                bt["Worst Asset"], bt["Worst Final Perf"], bt["Outcome"])
        ]
        return {"summary": out_summary, "issues": issues, "figures": figures,
                "note_type": _note_type}

    # Outcome label per issue + a matching colour map — the chart builders key off
    # this (shared with the PDF backtest so legends/colours stay identical).
    bt["Outcome"], color_map = _backtest_outcome_labels(bt)

    figures = {
        "worst_asset_pie": _fig(charts.build_worst_asset_pie(bt, tr)),
        "irr_scatter":     _fig(charts.build_backtest_irr_scatter(bt, color_map, tr)),
        "prices":          _fig(charts.build_historical_prices(
            prices, bt["Issue Date"].min(), bt["Issue Date"].max(), tr)),
    }

    return {
        "summary": out_summary,
        "note_type": _note_type,
        "issues": [
            {"issue_date": d.strftime("%Y-%m-%d"),
             "call_quarter": int(cq), "knock_in": bool(ki),
             "irr": _f(irr), "worst_asset": str(wa), "worst_perf": _f(wp)}
            for d, cq, ki, irr, wa, wp in zip(
                bt["Issue Date"], bt["Call Quarter"], bt["Knock-in"],
                bt["IRR"], bt["Worst Asset"], bt["Worst Final Perf"])
        ],
        "figures": figures,
    }


def backtest_paths(terms: NoteTerms, *, history_years: float | None = None,
                   sample: int = 400, seed: int = 7, bt_start: str | None = None,
                   bt_end: str | None = None) -> dict:
    """Per-issue worst-of trajectories for the backtest path explorer — the same
    ExplorerData shape as the Monte Carlo sample_paths, but the "paths" are real
    historical issues (worst-of at each observation, in note-relative time) tagged
    with their outcome (autocall period / knock-in / IRR). Lets the client overlay
    and filter them exactly like the MC fan."""
    prices = _prices(dict(terms.tickers), years=history_years, field="close")
    bt, summary = run_backtest(prices, terms, bt_start=_ts(bt_start), bt_end=_ts(bt_end))
    _note_type = getattr(terms, "note_type", "phoenix")
    _is_part = _note_type == "participation"
    if _is_part:
        periodic = bool(getattr(terms, "participation_periodic", False))
        _lv = participation_barrier_levels(terms)
        barriers = {"participation": {"strike": _f(terms.participation_strike),
                                      "floor": _f(_lv["floor"]), "cap": _f(_lv["cap"]), "periodic": periodic}}
    else:
        barriers = {"knock_in": _f(terms.knock_in_barrier),
                    "autocall": _f(terms.autocall_barrier),
                    "coupon":   _f(terms.coupon_barrier)}
    if bt.empty or "wof_obs" not in summary:
        return {"t": [], "paths": [], "n_total": 0, "obs_times": [],
                "note_type": _note_type, "barriers": barriers}

    wof = np.asarray(summary["wof_obs"])            # (n_issues, n_obs+1)
    t   = [float(x) for x in summary["obs_times_rel"]]
    ap  = bt["Call Quarter"].to_numpy()
    ki  = bt["Knock-in"].to_numpy()
    irr = bt["IRR"].to_numpy()
    payout = bt["Payout"].to_numpy()                # per-issue redemption (participation)
    dates = bt["Issue Date"]

    P = wof.shape[0]
    rng = np.random.default_rng(seed)
    k = min(int(sample), P)
    idx = np.sort(rng.choice(P, size=k, replace=False))

    paths = []
    for i in idx:
        row = {
            "wof": [round(float(wof[i, c]), 4) for c in range(wof.shape[1])],
            "ap":  int(ap[i]), "ki": bool(ki[i]), "irr": _f(irr[i]),
            "issue_date": dates.iloc[i].strftime("%Y-%m-%d"),
        }
        if _is_part:
            row["red"] = _f(payout[i])
        paths.append(row)

    return {
        "t":         [round(x, 4) for x in t],
        "paths":     paths,
        "n_total":   int(P),
        "note_type": _note_type,
        "obs_times": [round(x, 4) for x in t[1:]],
        "barriers":  barriers,
    }


def _cached_backtest(terms: NoteTerms, history_years: float | None,
                     bt_start: str | None = None, bt_end: str | None = None):
    """(prices, bt, summary) for the backtest inspector, memoised so filter/nav
    reuse one backtest run. prices come from the shared price cache; bt is cached
    here keyed on tickers + terms + issue-date window."""
    prices = _prices(dict(terms.tickers), years=history_years, field="close")
    key = (tuple(sorted(terms.tickers.items())), terms.to_json(), history_years, bt_start, bt_end)
    now = time.time()
    with _BT_LOCK:
        hit = _BT_CACHE.get(key)
        if hit is not None and now - hit[0] < _BT_TTL:
            return prices, hit[1], hit[2]
    bt, summary = run_backtest(prices, terms, bt_start=_ts(bt_start), bt_end=_ts(bt_end))
    with _BT_LOCK:
        _BT_CACHE[key] = (now, bt, summary)
        while len(_BT_CACHE) > _BT_MAX:
            _BT_CACHE.popitem(last=False)
    return prices, bt, summary


def backtest_inspect(terms: NoteTerms, *, lang: str = "en", filters: dict | None = None,
                     position: int = 0, randomize: bool = False,
                     history_years: float | None = None,
                     bt_start: str | None = None, bt_end: str | None = None) -> dict:
    """One historical issue in full detail for the backtest single-path inspector —
    the same InspectResult shape as inspect_run, so the React <PathInspector> is
    shared. Builds the issue's daily worst-of + per-asset window and replays its
    observations (replay_note) for the event markers."""
    tr = translations.Translator(lang)
    prices, bt, summary = _cached_backtest(terms, history_years, bt_start, bt_end)
    tickers = dict(terms.tickers)
    asset_names = list(tickers.values())
    n_obs = terms.n_obs
    obs_times_rel = [0.0] + list(terms.obs_times())

    _note_type = getattr(terms, "note_type", "phoenix")
    _is_part = _note_type == "participation"
    base = {"n_total": int(len(bt)), "n_matched": 0, "ret_range": [0.0, 0.0],
            "n_obs": int(n_obs), "coupon_available": False, "note_type": _note_type,
            "participation_periodic": bool(getattr(terms, "participation_periodic", False))}
    if bt.empty:
        return {**base, "position": 0, "path_index": None, "path": None}

    ac    = bt["Call Quarter"].to_numpy()
    ki    = bt["Knock-in"].to_numpy()
    irr   = bt["IRR"].to_numpy()              # backtest return band uses IRR (per app.py)
    coupon_m = summary.get("coupon_amounts")  # (n_issues, n_obs), row-aligned with bt
    base["ret_range"] = [float(np.min(irr)), float(np.max(irr))]
    base["coupon_available"] = (coupon_m is not None) and not _is_part

    f = filters or {}
    matches = _path_filter_matches(
        ac, ki, irr, coupon_m,
        outcome=f.get("outcome", "any"), ac_periods=f.get("ac_periods"),
        ki_choice=f.get("ki_choice", "any"),
        ret_lo=f.get("ret_lo"), ret_hi=f.get("ret_hi"),
        coupon_periods=f.get("coupon_periods"))
    M = int(len(matches))
    base["n_matched"] = M
    if M == 0:
        return {**base, "position": 0, "path_index": None, "path": None}

    if randomize:
        position = int(np.random.default_rng().integers(0, M))
    position = max(0, min(int(position), M - 1))
    row_i = int(matches[position])
    row = bt.iloc[row_i]
    issue_date = row["Issue Date"]
    autocall_q = int(row["Call Quarter"])
    ki_pn = bool(row["Knock-in"])

    # Daily worst-of window: issue → maturity, snapped to trading days.
    anchor, obs_dates = snapped_obs_dates(prices, terms, issue_date)
    a_loc   = int(prices.index.searchsorted(anchor))
    mat_loc = int(prices.index.searchsorted(obs_dates[-1]))
    window  = prices.iloc[a_loc:mat_loc + 1]
    S0      = window.iloc[0].values.astype(float)
    perf_daily = window.values.astype(float) / S0
    worst_path = perf_daily.min(axis=1)
    obs_steps  = [int(window.index.searchsorted(d)) for d in obs_dates]
    obs_steps  = [min(s, len(window) - 1) for s in obs_steps]

    if _is_part:
        line_path, marker_info = _participation_line_and_markers(perf_daily, obs_steps, terms, tr)
        B_final = float(line_path[-1])
        R_final = float(_participation_redemption(np.array([B_final]), terms)[0])
        outcome = {"autocall_q": 0, "call_time": None,
                   "knock_in": R_final < 1.0 - 1e-9, "worst_final": _f(B_final),
                   "redemption": _f(R_final), "final_basket": _f(B_final),
                   "is_loss": R_final < 1.0 - 1e-9}
    else:
        line_path = worst_path
        perf_obs    = perf_daily[obs_steps, :]
        rows        = replay_note(perf_obs, terms)["rows"]
        wof_levels  = [float(worst_path[s]) for s in obs_steps]
        marker_info = _build_path_marker_info(rows, autocall_q, n_obs, wof_levels, ki_pn, terms, tr)
        outcome = {"autocall_q": autocall_q,
                   "call_time": _f(obs_times_rel[autocall_q]) if autocall_q > 0 else None,
                   "knock_in": ki_pn, "worst_final": _f(float(worst_path[-1]))}

    return {
        **base,
        "position":   position,
        "path_index": row_i,
        "path":       _path_payload(line_path, perf_daily, asset_names,
                                    obs_steps, autocall_q, marker_info, terms, _note_type),
        "outcome": outcome,
        "metrics": {
            "principal":    _f(row["Principal"]),
            "coupons":      _f(row["Total Coupons"]),
            "irr":          _f(row["IRR"]),
            "total_return": _f(row["IRR"]),
        },
        "assets": [{"name": nm, "final": _f(float(perf_daily[-1, i]))}
                   for i, nm in enumerate(asset_names)],
    }


# ── live / current-performance flow ─────────────────────────────────────────────
def _participation_live_result(terms, tr, asset_names, disp_to_sym, obs_labels,
                               live_prices, full_prices, S0, perf_today, worst_asset,
                               perf_obs, past_dates, obs_cal, obs_snapped, anchor_live,
                               issue_ts, today_ts, mat_ts, elapsed_years, remaining_years,
                               pct_elapsed, history_gap_days, for_pdf):
    """Current-performance for a Participation note — see run_live_api. Reports the
    note against its own maturity payoff (basket today → redemption if settled now,
    distance to breakeven / floor / cap). Cliquet notes also accrue the per-period
    locked-in P&L over the elapsed resets, mark the running period to today, and list
    each reset in the observation table."""
    pk = terms.participation_basket
    periodic = bool(getattr(terms, "participation_periodic", False))
    basket_today = float(_basket(perf_today[None, :], pk)[0])
    proj_now = float(_participation_redemption(np.array([basket_today]), terms)[0])
    breakeven = _participation_breakeven(terms)
    _lv = participation_barrier_levels(terms)
    floor, cap = _lv["floor"], _lv["cap"]

    n_past = len(past_dates)
    reset_markers: list[dict] = []
    obs_rows: list[dict] = []
    accrued = 0.0
    current_income = 0.0
    if periodic:
        B_reset = _basket(perf_obs, pk) if n_past else np.empty(0)
        prev = 1.0
        running = 0.0
        for j in range(n_past):
            level = float(B_reset[j]) / prev if prev else 1.0
            inc = float(participation_period_income([level], terms)[0])
            prev = float(B_reset[j])
            accrued += inc
            running += inc
            status = "part_gain" if inc > 1e-9 else ("part_loss" if inc < -1e-9 else "part_flat")
            reset_markers.append({"date": past_dates[j], "label": obs_labels[j],
                                  "move": level - 1.0, "income": inc})
            obs_rows.append({"period": obs_labels[j],
                             "date": past_dates[j].date().isoformat(),
                             "status": status, "move": round(level - 1.0, 6),
                             "income": round(inc, 6), "cumulative": round(running, 6),
                             "upcoming": False})
        # Running (unsettled) period, marked to today off the last reset basket.
        if n_past < terms.n_obs:
            cur_level = basket_today / prev if prev else 1.0
            current_income = float(participation_period_income([cur_level], terms)[0])
            obs_rows.append({"period": obs_labels[n_past],
                             "date": (obs_cal[n_past].date().isoformat() if n_past < len(obs_cal) else None),
                             "status": "running", "move": round(cur_level - 1.0, 6),
                             "income": round(current_income, 6),
                             "cumulative": round(running + current_income, 6), "upcoming": False})
            for q in range(n_past + 1, terms.n_obs):
                obs_rows.append({"period": obs_labels[q],
                                 "date": (obs_cal[q].date().isoformat() if q < len(obs_cal) else None),
                                 "status": "upcoming", "move": None, "income": None,
                                 "cumulative": None, "upcoming": True})
        projected_redemption = max(1.0 + accrued + current_income, 0.0)
    else:
        projected_redemption = proj_now

    future_resets = ([(obs_labels[q], obs_cal[q]) for q in range(n_past, terms.n_obs)]
                     if periodic else [])
    fig = charts.build_participation_live_chart(
        live_prices, anchor_live, today_ts, mat_ts, pk, tr,
        floor=floor, cap=cap, breakeven=(breakeven if not periodic else None),
        reset_markers=reset_markers or None, future_resets=future_resets or None)

    if for_pdf:
        # The PDF current-performance section is still phoenix-shaped; skip it for a
        # participation note rather than render coupon columns that don't apply.
        return {"available": False, "reason": "participation_pdf_unsupported"}

    summary = {
        "note_type":       "participation",
        "participation_periodic": periodic,
        "participation_basket": pk,
        "issue_date":      issue_ts.date().isoformat(),
        "anchor_date":     anchor_live.date().isoformat(),
        "maturity_date":   mat_ts.date().isoformat(),
        "today":           today_ts.date().isoformat(),
        "history_gap_days": history_gap_days,
        "elapsed_years":   _f(elapsed_years),
        "remaining_years": _f(remaining_years),
        "pct_elapsed":     _f(pct_elapsed),
        "basket_today":    _f(basket_today),
        "worst_asset":     worst_asset,
        "worst_symbol":    disp_to_sym.get(worst_asset, ""),
        "projected_redemption": _f(projected_redemption),
        "projected_gain":  _f(projected_redemption - 1.0),
        "redeem_now":      _f(proj_now),
        "strike":          _f(terms.participation_strike),
        "breakeven_level": _f(breakeven),
        "dist_breakeven":  _f(basket_today - breakeven) if breakeven is not None else None,
        "protection_level": _f(floor),
        "dist_protection": _f(basket_today - floor) if floor is not None else None,
        "cap_level":       _f(cap),
        "dist_cap":        _f(cap - basket_today) if cap is not None else None,
        # cliquet accrual
        "accrued_income":  _f(accrued) if periodic else None,
        "current_income":  _f(current_income) if periodic else None,
        "n_reset_done":    n_past if periodic else None,
        "n_reset_total":   int(terms.n_obs) if periodic else None,
        "period_cap":      _f(terms.period_cap) if periodic else None,
        "alive":           True,
    }
    return {
        "available": True,
        "summary": summary,
        "assets": [
            {"name": nm, "symbol": disp_to_sym.get(nm, ""), "perf": _f(perf_today[i])}
            for i, nm in enumerate(asset_names)
        ],
        "obs_rows": obs_rows,
        "figure": _fig(fig),
    }


def run_live_api(terms: NoteTerms, *, lang: str = "en", for_pdf: bool = False) -> dict:
    """Current-performance replay of a partially-elapsed note (the Streamlit
    "Current Performance" tab). Loads live prices from the issue date, replays the
    observation calendar through today via core.note.replay_note (the single
    source of truth for past-observation status), and returns summary metrics,
    per-asset performance, the per-observation table, and the live chart figure.

    With ``for_pdf=True`` returns ``{"available", "live_data", "live_figure"}``
    shaped for app/pdf_report.py instead of the web JSON.

    Returns ``{"available": False, "reason": ...}`` when the note has no usable
    live data (no issue date, not yet issued, or too little price history)."""
    tr = translations.Translator(lang)
    tickers = dict(terms.tickers)
    asset_names = list(tickers.values())
    disp_to_sym = {disp: sym for sym, disp in tickers.items()}
    obs_labels = [f"P{i + 1}" for i in range(terms.n_obs)]

    if not terms.issue_date:
        return {"available": False, "reason": "no_issue_date"}

    issue_ts = pd.Timestamp(terms.issue_date)
    today_ts = pd.Timestamp(pd.Timestamp.today().date())
    if issue_ts > today_ts:
        return {"available": False, "reason": "not_issued"}

    mat_ts = issue_ts + pd.DateOffset(months=round(terms.maturity * 12))
    elapsed_years   = (today_ts - issue_ts).days / 365.25
    remaining_years = max(terms.maturity - elapsed_years, 0.0)
    pct_elapsed     = min(elapsed_years / terms.maturity, 1.0) if terms.maturity else 1.0

    full_prices = _prices(tickers, years=None, field="close")
    issue_idx = int(full_prices.index.searchsorted(issue_ts))
    if issue_idx >= len(full_prices):
        issue_idx = len(full_prices) - 1
    anchor_live = full_prices.index[issue_idx]
    live_prices = full_prices.iloc[issue_idx:]
    if len(live_prices) < 2:
        return {"available": False, "reason": "not_enough_data"}

    history_gap_days = int((anchor_live - issue_ts).days)

    S0 = full_prices.iloc[issue_idx].values.astype(float)
    today_slice = live_prices[live_prices.index <= today_ts]
    perf_today  = today_slice.iloc[-1].values / S0
    wof_today   = float(perf_today.min())
    worst_i     = int(perf_today.argmin())
    worst_asset = asset_names[worst_i]

    obs_cal  = terms.obs_calendar_dates(anchor_live)
    ac_sched = terms.autocall_barrier_schedule()
    next_obs_idx = next((i for i, d in enumerate(obs_cal)
                         if pd.Timestamp(d) > today_ts), len(ac_sched) - 1)
    next_ac_barrier = float(ac_sched[next_obs_idx])
    ki_buffer = wof_today - terms.knock_in_barrier
    ac_buffer = wof_today - next_ac_barrier

    # Snap each calendar observation date to the trading calendar; an obs is in
    # the past only if its snapped trading day has already occurred.
    obs_snapped: list = []
    for d in obs_cal:
        j = int(full_prices.index.searchsorted(d))
        if j < len(full_prices) and full_prices.index[j] <= today_ts:
            obs_snapped.append(full_prices.index[j])
        else:
            obs_snapped.append(None)

    past_dates = [d for d in obs_snapped if d is not None]
    if past_dates:
        perf_obs = np.vstack([full_prices.loc[d].values / S0 for d in past_dates])
    else:
        perf_obs = np.empty((0, len(S0)))

    # ── Participation branch — a maturity-payoff note has no coupons / autocall /
    # knock-in, so the phoenix replay below doesn't apply. Report where the note
    # stands against its OWN payoff: the participation basket today, the redemption
    # it would pay if it settled now, and the distance to breakeven / floor / cap.
    if getattr(terms, "note_type", "phoenix") == "participation":
        return _participation_live_result(
            terms, tr, asset_names, disp_to_sym, obs_labels, live_prices, full_prices,
            S0, perf_today, worst_asset, perf_obs, past_dates, obs_cal, obs_snapped,
            anchor_live, issue_ts, today_ts, mat_ts, elapsed_years, remaining_years,
            pct_elapsed, history_gap_days, for_pdf)

    replay = replay_note(perf_obs, terms)

    obs_rows: list[dict] = []
    obs_markers: list[dict] = []
    running_total = 0.0
    for q, label in enumerate(obs_labels):
        snap = obs_snapped[q] if q < len(obs_snapped) else None
        if q >= len(replay["rows"]) or snap is None:
            # Upcoming — unless an autocall already terminated the note.
            if replay["autocall_period"] and q + 1 > replay["autocall_period"]:
                break
            est = obs_cal[q].date().isoformat() if q < len(obs_cal) else None
            obs_rows.append({
                "period": label, "date": est, "status": "upcoming",
                "wof": None, "coupon": None, "cumulative": None, "upcoming": True,
            })
            continue

        r = replay["rows"][q]
        obs_wof = float(perf_obs[q].min())
        running_total += r["coupon_amount"]
        if r["autocalled"]:
            status = "autocalled"
        elif terms.coupon_at_autocall_only:
            status = "no_coupon"
        elif r["coupon_met"]:
            status = "coupon_paid"
        else:
            status = "coupon_missed"
        obs_rows.append({
            "period": label, "date": snap.date().isoformat(), "status": status,
            "wof": round(obs_wof, 6),
            "coupon": _f(r["coupon_amount"]) if r["coupon_amount"] > 0 else None,
            "cumulative": round(running_total, 6), "upcoming": False,
        })
        _amt = float(r["coupon_amount"])
        _released = round(_amt / terms.coupon_rate) if (terms.coupon_rate and _amt > 0) else (1 if _amt > 0 else 0)
        obs_markers.append({
            "date": snap, "label": label, "wof": obs_wof,
            "autocalled": bool(r["autocalled"]),
            "paid": bool(r["coupon_met"] or r["coupon_amount"] > 0),
            "amount": _amt, "released": int(_released),
        })
        if r["autocalled"]:
            break

    pending_coupons = int(replay["pending_coupons"])
    total_coupons   = float(replay["total_coupons"])
    irr_to_date     = total_coupons / max(elapsed_years, 1 / 252)
    n_replayed      = len(replay["rows"])

    # Future observation reference lines (calendar dates) — only while alive.
    if replay["autocall_period"]:
        future_obs = []
    else:
        future_obs = [(obs_labels[q], obs_cal[q])
                      for q in range(n_replayed, terms.n_obs)]
    live_sched = ([(d, ac_sched[q]) for q, d in enumerate(obs_cal)]
                  if terms.autocall_step_down else None)

    fig = charts.build_live_performance_chart(
        hist_prices=live_prices, issue_date=anchor_live, today=today_ts,
        maturity_date=mat_ts, obs_markers=obs_markers, future_obs=future_obs,
        knock_in_barrier=terms.knock_in_barrier,
        autocall_barrier=terms.autocall_barrier,
        coupon_barrier=terms.coupon_barrier, tr=tr,
        autocall_schedule=live_sched)

    if for_pdf:
        # PDF shapes (app/pdf_report.py): translated obs-table headers/values +
        # the raw go.Figure. The obs table uses the row dict keys as headers.
        _dash = tr("live_obs_dash")
        _status_key = {"autocalled": "live_status_autocalled",
                       "coupon_paid": "live_status_coupon_paid",
                       "coupon_missed": "live_status_coupon_missed",
                       "no_coupon": "live_status_no_coupon",
                       "upcoming": "live_status_upcoming"}
        pdf_rows = [{
            tr("live_col_period"):     r["period"],
            tr("live_col_date"):       r["date"] or _dash,
            tr("live_col_status"):     tr(_status_key[r["status"]]),
            tr("live_col_wof"):        f"{r['wof']:.1%}" if r["wof"] is not None else _dash,
            tr("live_col_coupon"):     f"{r['coupon']:.4%}" if r["coupon"] else _dash,
            tr("live_col_cumulative"): f"{r['cumulative']:.4%}" if r["cumulative"] is not None else _dash,
        } for r in obs_rows]
        return {
            "available": True,
            "live_data": {
                "wof_today":     wof_today,
                "worst_asset":   worst_asset,
                "perf_today":    {nm: float(perf_today[i]) for i, nm in enumerate(asset_names)},
                "irr_to_date":   irr_to_date,
                "elapsed_years": elapsed_years,
                "obs_rows":      pdf_rows,
            },
            "live_figure": fig,
        }

    return {
        "available": True,
        "summary": {
            "issue_date":      issue_ts.date().isoformat(),
            "anchor_date":     anchor_live.date().isoformat(),
            "maturity_date":   mat_ts.date().isoformat(),
            "today":           today_ts.date().isoformat(),
            "history_gap_days": history_gap_days,
            "elapsed_years":   _f(elapsed_years),
            "remaining_years": _f(remaining_years),
            "pct_elapsed":     _f(pct_elapsed),
            "wof_today":       _f(wof_today),
            "worst_asset":     worst_asset,
            "worst_symbol":    disp_to_sym.get(worst_asset, ""),
            "ki_buffer":       _f(ki_buffer),
            "ac_buffer":       _f(ac_buffer),
            "next_ac_barrier": _f(next_ac_barrier),
            "knock_in_barrier": _f(terms.knock_in_barrier),
            "coupon_barrier":  _f(terms.coupon_barrier),
            "coupon_rate":     _f(terms.coupon_rate),
            "coupon_pa":       _f(terms.coupon_pa),
            "total_coupons":   _f(total_coupons),
            "pending_coupons": pending_coupons,
            "pending_value":   _f(pending_coupons * terms.coupon_rate),
            "irr_to_date":     _f(irr_to_date),
            "autocall_period": int(replay["autocall_period"]),
            "alive":           not bool(replay["autocall_period"]),
            "coupon_at_autocall_only": bool(terms.coupon_at_autocall_only),
            "next_premium":    _f(terms.coupon_rate * (n_replayed + 1)),
        },
        "assets": [
            {"name": nm, "symbol": disp_to_sym.get(nm, ""), "perf": _f(perf_today[i])}
            for i, nm in enumerate(asset_names)
        ],
        "obs_rows": obs_rows,
        "figure": _fig(fig),
    }


def history_span(tickers: dict) -> dict:
    """How much overlapping price history these underlyings actually have — the
    ceiling on a useful calibration window. Reads the SAME cached max-history pull
    the backtest/live flows use, so it's usually free; the basket is only as long
    as its shortest member (load_prices aligns to common trading days).

    Returns ``{"years", "start", "end", "n_days"}``; years is floored to 0.0 when
    nothing resolves, which the client reads as "no cap known"."""
    if not tickers:
        return {"years": 0.0, "start": None, "end": None, "n_days": 0}
    df = _prices(dict(tickers), years=None, field="close")
    if df.empty:
        return {"years": 0.0, "start": None, "end": None, "n_days": 0}
    start, end = df.index[0], df.index[-1]
    return {
        "years":   round((end - start).days / 365.25, 2),
        "start":   start.date().isoformat(),
        "end":     end.date().isoformat(),
        "n_days":  int(len(df)),
    }


# ── underlying breakdown flow ────────────────────────────────────────────────────
def run_underlying_metrics(tickers: dict, *, lang: str = "en") -> list[dict]:
    """Per-underlying breakdown for the note-structure cards: long name, type/sector,
    market cap, 3-month implied (or realized) vol, last price, Wilder RSI, business
    summary, and a trailing-12-month price-chart figure. Best-effort — a ticker that
    fails to resolve still returns its row (with the fields it has) so the panel
    degrades cleanly."""
    tr = translations.Translator(lang)
    tickers = dict(tickers)
    try:
        prices_1y = _prices(tickers, years=1.0, field="close")
        closes = {name: prices_1y[name] for name in prices_1y.columns}
    except Exception as e:
        print(f"[underlyings] 1Y price pull failed: {e}")
        prices_1y, closes = None, None

    try:
        metrics = load_underlying_metrics(tickers, closes=closes)
    except Exception as e:
        print(f"[underlyings] metrics pull failed: {e}")
        metrics = {}

    out = []
    for sym, name in tickers.items():
        m = metrics.get(name, {}) or {}
        fig = None
        if prices_1y is not None and name in getattr(prices_1y, "columns", []):
            try:
                fig = _fig(charts.build_underlying_price_chart(prices_1y[name], name, tr))
            except Exception as e:
                print(f"[underlyings] price chart for {name} failed: {e}")
        out.append({
            "name": name, "symbol": sym,
            "long_name":  m.get("long_name") or name,
            "type":       m.get("type"),
            "sector":     m.get("sector"),
            "industry":   m.get("industry"),
            "market_cap": _f(m.get("market_cap")),
            "iv_3m":      _f(m.get("iv_3m")),
            "iv_source":  m.get("iv_source"),
            "last_price": _f(m.get("last_price")),
            "day_change": _f(m.get("day_change")),
            "rsi_14":     _f(m.get("rsi_14")),
            "business_summary": _translated(m.get("business_summary"), lang),
            "figure":     fig,
        })
    return out


# Per-symbol quote cache. The live ticker tape polls /api/quotes constantly, so a
# short TTL turns a burst of identical polls into one Yahoo hit per symbol.
_QUOTE_CACHE: "dict[str, tuple[float, dict]]" = {}
_QUOTE_TTL = 20.0
_QUOTE_MAX = 256
_QUOTE_LOCK = threading.Lock()


def _empty_quote() -> dict:
    return {"price": None, "change": None, "open": None, "prev_close": None,
            "day_low": None, "day_high": None, "year_low": None, "year_high": None,
            "volume": None, "market_cap": None, "currency": None}


def _quote_one(sym: str) -> dict:
    """One symbol's fast_info snapshot (best-effort; nulls on any failure)."""
    import yfinance as yf

    rec = _empty_quote()
    try:
        fi = yf.Ticker(sym).fast_info

        def g(*names):
            """First non-None of several fast_info keys (attribute + dict styles
            vary across yfinance versions)."""
            for n in names:
                v = getattr(fi, n, None)
                if v is None and hasattr(fi, "get"):
                    v = fi.get(n)
                if v is not None:
                    return v
            return None

        last = _f(g("last_price", "lastPrice"))
        prev = _f(g("previous_close", "previousClose"))
        rec["price"] = last
        rec["prev_close"] = prev
        if last is not None and prev:
            rec["change"] = last / prev - 1.0
        rec["open"] = _f(g("open"))
        rec["day_low"] = _f(g("day_low", "dayLow"))
        rec["day_high"] = _f(g("day_high", "dayHigh"))
        rec["year_low"] = _f(g("year_low", "yearLow"))
        rec["year_high"] = _f(g("year_high", "yearHigh"))
        rec["volume"] = _f(g("last_volume", "lastVolume", "regularMarketVolume"))
        rec["market_cap"] = _f(g("market_cap", "marketCap"))
        cur = g("currency")
        rec["currency"] = str(cur) if cur else None
    except Exception as e:
        print(f"[quotes] {sym} failed: {e}")
    return rec


def run_quotes(symbols: list[str]) -> dict:
    """Fast quote snapshot per symbol for the live ticker tape and its hover detail
    card (Yahoo fast_info only). Served from a short-TTL cache; cache-miss symbols
    are fetched CONCURRENTLY (Yahoo I/O is the bottleneck, so threads parallelize
    despite the GIL). Best-effort — a failed symbol/field returns null."""
    now = time.time()
    out: dict[str, dict] = {}
    todo: list[str] = []
    with _QUOTE_LOCK:
        for sym in symbols:
            hit = _QUOTE_CACHE.get(sym)
            if hit is not None and now - hit[0] < _QUOTE_TTL:
                out[sym] = hit[1]
            else:
                todo.append(sym)
    if todo:
        with ThreadPoolExecutor(max_workers=min(8, len(todo))) as ex:
            fetched = dict(zip(todo, ex.map(_quote_one, todo)))
        with _QUOTE_LOCK:
            for sym, rec in fetched.items():
                _QUOTE_CACHE[sym] = (now, rec)
            if len(_QUOTE_CACHE) > _QUOTE_MAX:
                for k in sorted(_QUOTE_CACHE, key=lambda k: _QUOTE_CACHE[k][0])[:len(_QUOTE_CACHE) - _QUOTE_MAX]:
                    _QUOTE_CACHE.pop(k, None)
        out.update(fetched)
    # Preserve the caller's symbol order.
    return {sym: out.get(sym, _empty_quote()) for sym in symbols}


# ── description prefill (Yahoo business summaries) ───────────────────────────────
def run_describe(*, issuer: str | None = None, symbols: list[str] | None = None,
                 lang: str = "en") -> dict:
    """Business-summary prefill for the issuer and/or underlyings (Yahoo). Returns
    {issuer_description, underlyings: {symbol: description}}; any lookup that fails
    yields None for that entry. In Spanish mode the summaries are machine-translated."""
    out: dict = {"issuer_description": None, "underlyings": {}}
    if issuer:
        try:
            out["issuer_description"] = resolve_issuer_summary(issuer)
        except Exception as e:
            print(f"[describe] issuer summary failed: {e}")
    def _safe_summary(sym: str):
        try:
            return fetch_business_summary(sym)
        except Exception as e:
            print(f"[describe] summary for {sym} failed: {e}")
            return None

    syms = list(symbols or [])
    if syms:
        # Fetch the per-underlying summaries concurrently (each is a Yahoo round-trip).
        with ThreadPoolExecutor(max_workers=min(8, len(syms))) as ex:
            for sym, summ in zip(syms, ex.map(_safe_summary, syms)):
                out["underlyings"][sym] = summ
    if lang and lang != "en":
        try:
            out["issuer_description"] = _translated(out["issuer_description"], lang)
            for k, v in list(out["underlyings"].items()):
                out["underlyings"][k] = _translated(v, lang)
        except Exception as e:
            print(f"[describe] translation skipped: {e}")
    return out


# ── PDF report flow ──────────────────────────────────────────────────────────────
def _backtest_for_pdf(terms: NoteTerms, tr, history_years: float | None) -> tuple[dict | None, dict | None]:
    """(bt_summary, bt_figures) for the PDF, or (None, None) if no issues backtest.
    Builds the go.Figure objects (not JSON) the report embeds."""
    prices = _prices(dict(terms.tickers), years=history_years, field="close")
    bt, summary = run_backtest(prices, terms)
    if bt.empty:
        return None, None
    bt = bt.copy()

    bt["Outcome"], color_map = _backtest_outcome_labels(bt)

    bt_summary = dict(summary)
    ki_rows = bt[bt["Knock-in"]]
    if not ki_rows.empty:
        bt_summary["loss_given_ki"] = float(ki_rows["IRR"].mean())

    _is_part = getattr(terms, "note_type", "") == "participation"
    if _is_part:
        # Participation: the realised outcome is the redemption (bt["Payout"]), not
        # an autocall/knock-in classification. Derive above/below-par probabilities
        # for the metric band and swap the outcome bar for a redemption distribution.
        _payout = bt["Payout"].to_numpy(dtype=float)
        bt_summary["prob_above_par"] = float((_payout > 1.0 + 1e-9).mean())
        bt_summary["prob_below_par"] = float((_payout < 1.0 - 1e-9).mean())
        _outcome_fig = charts.build_redemption_distribution(_payout, terms, tr)
    else:
        _outcome_fig = charts.build_backtest_outcome_bar(bt, color_map, tr)
    bt_figures = {
        "outcome":     _outcome_fig,
        "pie":         charts.build_worst_asset_pie(bt, tr),
        "irr_scatter": charts.build_backtest_irr_scatter(bt, color_map, tr),
        "prices":      charts.build_historical_prices(
            prices.resample("W-FRI").last().dropna(),
            bt["Issue Date"].min(), bt["Issue Date"].max(), tr),
    }
    return bt_summary, bt_figures


def _decode_data_url(s: str | None) -> bytes | None:
    """Decode a base64 data-URL (custom logo upload) to raw bytes."""
    if not s or "," not in s:
        return None
    import base64
    try:
        return base64.b64decode(s.split(",", 1)[1])
    except Exception:
        return None


def _compare_for_pdf(sf_a: dict, terms_a: NoteTerms, terms_b: NoteTerms, tr, *,
                     n_paths: int, seed: int, calib_years: float,
                     history_years: float | None, engine: str) -> tuple[dict, dict]:
    """Compute the A/B comparison payload for the PDF: metrics diff + raw go.Figure
    overlays (kaleido renders these to PNG downstream). Reuses A's simulation `sf`
    and reprices B on the same paths when they share underlyings + maturity."""
    shared = (dict(terms_a.tickers) == dict(terms_b.tickers)
              and abs(float(terms_a.maturity) - float(terms_b.maturity)) < 1e-9)
    sf_b = (_reprice_on_paths(sf_a, terms_b, seed=seed) if shared else
            _simulate_full(terms_b, n_paths=n_paths, seed=seed, calib_years=calib_years,
                           history_years=history_years, engine=engine))
    note_a, note_b = sf_a["note"], sf_b["note"]
    summary_a = _mc_summary(sf_a, note_a, terms_a)
    summary_b = _mc_summary(sf_b, note_b, terms_b)
    data = {
        "shared_paths": shared,
        "diff": _compare_diff(summary_a, summary_b, terms_a, terms_b),
        "name_a": terms_a.name, "name_b": terms_b.name,
        "terms_b": terms_b,   # NoteTerms object (in-process) for the side-by-side terms table
    }
    figs = {
        "irr": charts.build_irr_compare(
            note_a["annualized_returns"], note_b["annualized_returns"],
            note_a["expected_irr"], note_b["expected_irr"], tr),
        "outcome": charts.build_outcome_compare(note_a, note_b, terms_a, terms_b, tr),
    }
    return data, figs


def build_report_pdf(terms: NoteTerms, *, sections: list[str] | None = None, lang: str = "en",
                     n_paths: int = 10000, seed: int = 42, calib_years: float = 5.0,
                     history_years: float | None = None, engine: str = "cpp",
                     branding: dict | None = None,
                     compare_terms: NoteTerms | None = None,
                     report_kind: str | None = None) -> bytes:
    """Assemble the institutional PDF report (app/pdf_report.py). `sections` is the
    set of fine-grained item keys to include (empty/None ⇒ everything available);
    only the flows those keys touch are run. `branding` is an optional firm-branding
    dict. `compare_terms` (Note B) adds an A/B comparison section. `report_kind` is
    the audience preset it was built for — stamped on the cover as the report-type
    subtitle. Returns PDF bytes."""
    from pdf_report import generate_pdf_report                     # heavy import, lazy

    tr = translations.Translator(lang)
    tickers = dict(terms.tickers)
    asset_names = list(tickers.values())
    n_assets = len(tickers)

    keys = set(sections or [])
    all_on = not keys
    if "mc_fans" in keys:                                           # per-underlying fans pseudo-key
        keys |= {f"mc_fan_{i}" for i in range(n_assets)}
        keys.discard("mc_fans")
    include_sections = None if all_on else keys

    want_mc   = all_on or any(k.startswith("mc_") for k in keys)
    want_cal  = all_on or bool({"calib_table", "calib_corr"} & keys)
    want_bt   = all_on or any(k.startswith("bt_") for k in keys)
    want_live = all_on or any(k.startswith("live_") for k in keys)
    want_ul   = all_on or "underlying_breakdown" in keys
    # Supplying a Note B is itself the opt-in — the comparison isn't a fine-grained
    # section toggle, so it renders whenever compare_terms is provided.
    want_compare = compare_terms is not None

    results: dict = {}
    figures: dict = {}
    sf = None
    if want_mc or want_cal or want_compare:
        sf = _simulate_full(terms, n_paths=n_paths, seed=seed, calib_years=calib_years,
                            history_years=history_years, engine=engine)
    if want_mc or want_cal:
        note, cal_result = sf["note"], sf["cal_result"]
        t_grid, obs_pairs = sf["t_grid"], sf["obs_pairs"]
        wof_bands, asset_bands = sf["wof_bands"], sf["asset_bands"]
        results = {**note, "params": cal_result.params, "corr_SS": cal_result.corr_SS}
        _rep_part = getattr(terms, "note_type", "") == "participation"
        figures = {
            "outcome": (charts.build_redemption_distribution(note["nominal_payoffs"], terms, tr)
                        if _rep_part else
                        charts.build_outcome_breakdown(
                            note.get("prob_autocall_by_period"), note.get("prob_maturity"),
                            note.get("prob_knock_in_total"), tr)),
            "sample": charts.build_sample_paths(
                sf["wof_paths"], t_grid, note.get("autocall_period"),
                note.get("knock_in_mask"), terms.knock_in_barrier,
                terms.autocall_barrier, obs_pairs, tr),
            "irr_dist": charts.build_irr_distribution(
                note["annualized_returns"], note.get("total_returns"),
                note["autocall_events"], note["expected_irr"], terms.coupon_pa, tr),
            "wof_fan": charts.build_wof_fan(
                None, t_grid, terms.knock_in_barrier, obs_pairs, tr,
                autocall_barrier=terms.autocall_barrier, bands=wof_bands),
            "individual": [(nm, charts.build_fan_chart(None, nm, t_grid, obs_pairs, tr,
                                                       bands=asset_bands[i]))
                           for i, nm in enumerate(asset_names)],
            "corr": charts.build_corr_heatmap(cal_result.corr_SS, asset_names, tr("corr_input")),
        }

    bt_summary = bt_figures = None
    if want_bt:
        try:
            bt_summary, bt_figures = _backtest_for_pdf(terms, tr, history_years)
        except Exception as e:                                     # backtest is best-effort
            print(f"[report] backtest section skipped: {e}")

    live_data = live_figure = None
    if want_live and terms.issue_date:
        live = run_live_api(terms, lang=lang, for_pdf=True)
        if live.get("available"):
            live_data, live_figure = live["live_data"], live["live_figure"]

    # A/B comparison section (only when a Note B was supplied).
    compare_data = compare_figures = None
    if want_compare and sf is not None:
        try:
            compare_data, compare_figures = _compare_for_pdf(
                sf, terms, compare_terms, tr, n_paths=n_paths, seed=seed,
                calib_years=calib_years, history_years=history_years, engine=engine)
        except Exception as e:                                     # comparison is best-effort
            print(f"[report] comparison section skipped: {e}")

    # Underlying breakdown: per-asset metrics + a 1Y price chart (raw go.Figures).
    underlying_metrics = underlying_price_figs = None
    if want_ul:
        try:
            px_1y = _prices(tickers, years=1.0, field="close")
            closes = {nm: px_1y[nm] for nm in px_1y.columns}
            underlying_metrics = load_underlying_metrics(tickers, closes=closes)
            # The web card shows `business_summary` as the description even when the
            # user never saved a per-underlying override; mirror that in the PDF by
            # translating the auto-pulled blurb so the fallback there is localized.
            if lang != "en" and underlying_metrics:
                for _rec in underlying_metrics.values():
                    if _rec.get("business_summary"):
                        _rec["business_summary"] = _translated(_rec["business_summary"], lang)
            underlying_price_figs = {nm: charts.build_underlying_price_chart(px_1y[nm], nm, tr)
                                     for nm in asset_names if nm in px_1y.columns}
        except Exception as e:
            print(f"[report] underlying breakdown skipped: {e}")

    logo_urls     = {nm: underlyings.logo_for(sym) for sym, nm in tickers.items()}
    logo_tickers  = {nm: sym for sym, nm in tickers.items()}
    issuer_logo   = underlyings.issuer_logo_for(getattr(terms, "issuer", "") or "")
    # User-uploaded custom underlying logos (terms.underlyings[name].logo data-URLs).
    logo_overrides = {nm: b for nm, ov in (terms.underlyings or {}).items()
                      if isinstance(ov, dict) and (b := _decode_data_url(ov.get("logo")))}

    # Issuer blurb: mirror the underlying business-summary fallback — when the note
    # has no curated issuer_description, fetch one so a preloaded issuer still shows
    # in the report (translated for non-EN).
    issuer_desc = getattr(terms, "issuer_description", "") or ""
    want_issuer = all_on or "issuer_info" in keys
    if want_issuer and not issuer_desc and (getattr(terms, "issuer", "") or ""):
        try:
            _s = resolve_issuer_summary(terms.issuer)
            if _s:
                issuer_desc = _translated(_s, lang)
        except Exception as e:
            print(f"[report] issuer summary fallback skipped: {e}")

    return generate_pdf_report(
        terms=terms, results=results, asset_names=asset_names, figures=figures,
        lang=lang, bt_summary=bt_summary, bt_figures=bt_figures,
        live_data=live_data, live_figure=live_figure,
        logo_urls=logo_urls, issuer_logo_url=issuer_logo, logo_tickers=logo_tickers,
        logo_overrides=logo_overrides or None, branding=branding,
        underlying_metrics=underlying_metrics, underlying_price_figs=underlying_price_figs,
        issuer_description=issuer_desc or None, include_sections=include_sections,
        compare_data=compare_data, compare_figures=compare_figures,
        report_kind=report_kind)
