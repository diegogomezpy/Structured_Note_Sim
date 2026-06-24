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
import sys
import uuid
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
# app/ holds the reusable (Streamlit-free) chart + i18n + ticker modules, which
# import each other by bare name (e.g. `from translations import Translator`), so
# app/ must be on sys.path for those to resolve — same as when Streamlit runs.
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "app"))

from core.note import NoteTerms, price_note, replay_note          # noqa: E402
from core.calibrator import HestonCalibrator                      # noqa: E402
from core.simulator import HestonMultiSimulator                   # noqa: E402
from core.backtest import run_backtest                            # noqa: E402
from data.loader import (load_prices, load_dividends,             # noqa: E402
                          build_dividend_schedule, load_underlying_metrics)
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


# ── In-memory run store (bounded) ─────────────────────────────────────────────
# Keeps the compact per-path arrays for the explorer. LRU-evicted so a long-lived
# server can't grow without bound; a production multi-instance deploy would back
# this with Redis instead.
_RUNS: "OrderedDict[str, dict]" = OrderedDict()
_MAX_RUNS = 8


def _store_run(payload: dict) -> str:
    run_id = uuid.uuid4().hex[:12]
    _RUNS[run_id] = {"created": time.time(), **payload}
    while len(_RUNS) > _MAX_RUNS:
        _RUNS.popitem(last=False)
    return run_id


def get_run(run_id: str) -> dict | None:
    return _RUNS.get(run_id)


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
    ki  = note.get("knock_in_mask")
    irr = note.get("annualized_returns")

    wof_sel = np.asarray(perf[idx]).min(axis=2)   # (k, N+1) worst-of per asset
    paths = []
    for j, i in enumerate(idx):
        paths.append({
            "wof": [round(float(wof_sel[j, c]), 4) for c in tcols],
            "ap":  int(ap[i])  if ap  is not None else 0,
            "ki":  bool(ki[i]) if ki  is not None else False,
            "irr": _f(irr[i])  if irr is not None else None,
        })
    return {
        "t":        [round(float(t_grid[c]), 4) for c in tcols],
        "paths":    paths,
        "n_total":  int(P),
        "obs_times": run.get("obs_times", []),
        "barriers": {
            "knock_in": _f(terms.get("knock_in_barrier")),
            "autocall": _f(terms.get("autocall_barrier")),
            "coupon":   _f(terms.get("coupon_barrier")),
        },
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
    obs_steps = [min(int(grid.searchsorted(d)), N) for d in terms.obs_calendar_dates(anchor)]
    obs_times = [(grid[s] - grid[0]).days / 365.0 for s in obs_steps]

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
    }


def run_simulation(terms: NoteTerms, *, n_paths: int = 10000, seed: int = 42,
                   calib_years: float = 5.0, history_years: float | None = None,
                   engine: str = "numpy", lang: str = "en") -> dict:
    """Load → calibrate → simulate → price, then build the Monte Carlo figures.
    Mirrors the old Streamlit run block; returns summary stats + Plotly-JSON
    figures + a run_id (full paths cached server-side for the explorer)."""
    tr = translations.Translator(lang)
    sf = _simulate_full(terms, n_paths=n_paths, seed=seed, calib_years=calib_years,
                        history_years=history_years, engine=engine)
    cal_result, sim_results, note = sf["cal_result"], sf["sim_results"], sf["note"]
    perf_paths, wof_bands, asset_bands = sf["perf_paths"], sf["wof_bands"], sf["asset_bands"]
    t_grid, obs_steps, obs_times = sf["t_grid"], sf["obs_steps"], sf["obs_times"]
    obs_pairs, asset_names, eng_used = sf["obs_pairs"], sf["asset_names"], sf["eng_used"]

    figures = {
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

    summary = {k: _f(note.get(k)) for k in (
        "expected_irr", "expected_total_return", "expected_coupon",
        "prob_autocall", "prob_knock_in_total", "expected_nominal_payout",
        "loss_given_knock_in", "prob_maturity", "prob_rescued",
        "prob_barrier_event")}
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

    # Cache compact arrays for the path explorer (Phase 3).
    run_id = _store_run({
        "perf_paths": perf_paths.astype(np.float16),
        "wof_bands":  wof_bands.astype(np.float32),
        "obs_steps":  obs_steps,
        "obs_times":  obs_times,
        "t_grid":     t_grid,
        "asset_names": asset_names,
        "terms":      terms.to_dict(),
        "note":       {k: np.asarray(v) for k, v in note.items()
                       if isinstance(v, np.ndarray) and v.ndim <= 2},
    })
    return {"run_id": run_id, "summary": summary, "figures": figures}


# ── backtest flow ───────────────────────────────────────────────────────────────
def _lerp_hex(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3))


def run_backtest_api(terms: NoteTerms, *, history_years: float | None = None,
                     lang: str = "en") -> dict:
    """Historical backtest over realized prices — summary metrics, per-issue rows,
    and the outcome/scatter/pie/price figures (mirrors the Streamlit backtest)."""
    tr = translations.Translator(lang)
    prices = _prices(dict(terms.tickers), years=history_years, field="close")
    bt, summary = run_backtest(prices, terms)
    if bt.empty:
        return {"summary": {}, "issues": [], "figures": None}

    out_summary = {k: _f(v) for k, v in summary.items()
                   if not isinstance(v, (list, np.ndarray))}
    out_summary["n_issues"] = int(len(bt))

    # Outcome label per issue + a colour map (autocall periods on a blue ramp,
    # held-to-maturity slate, knock-in red) — the chart builders key off this.
    def _label(cq, ki):
        if int(cq) > 0:
            return f"Autocalled P{int(cq)}"
        return "Knock-in" if bool(ki) else "Held to maturity"
    bt = bt.copy()
    bt["Outcome"] = [_label(cq, ki) for cq, ki in zip(bt["Call Quarter"], bt["Knock-in"])]
    ac_periods = sorted({int(cq) for cq in bt["Call Quarter"] if int(cq) > 0})
    color_map = {"Held to maturity": "#334155", "Knock-in": "#dc2626"}
    for i, q in enumerate(ac_periods):
        t = i / max(1, len(ac_periods) - 1)
        color_map[f"Autocalled P{q}"] = _lerp_hex("#93c5fd", "#1e3a8a", t)

    figures = {
        "worst_asset_pie": _fig(charts.build_worst_asset_pie(bt, tr)),
        "irr_scatter":     _fig(charts.build_backtest_irr_scatter(bt, color_map, tr)),
        "prices":          _fig(charts.build_historical_prices(
            prices, bt["Issue Date"].min(), bt["Issue Date"].max(), tr)),
    }

    return {
        "summary": out_summary,
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


# ── live / current-performance flow ─────────────────────────────────────────────
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
        obs_markers.append({
            "date": snap, "label": label, "wof": obs_wof,
            "autocalled": bool(r["autocalled"]),
            "paid": bool(r["coupon_met"] or r["coupon_amount"] > 0),
            "amount": float(r["coupon_amount"]),
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
            "market_cap": _f(m.get("market_cap")),
            "iv_3m":      _f(m.get("iv_3m")),
            "iv_source":  m.get("iv_source"),
            "last_price": _f(m.get("last_price")),
            "rsi_14":     _f(m.get("rsi_14")),
            "business_summary": m.get("business_summary"),
            "figure":     fig,
        })
    return out


# ── PDF report flow ──────────────────────────────────────────────────────────────
def _expand_sections(groups: set[str], n_assets: int) -> set[str]:
    """Map coarse UI section groups to the fine-grained item keys the PDF gates on.
    Note terms + the observation schedule are always seeded — they are core to any
    term sheet, and the PDF defines its shared `usable` page width inside that
    block, so later sections (MC/calib/live) reference it expecting it present."""
    keys: set[str] = {"note_terms", "obs_schedule"}
    if "mc" in groups:
        keys |= {"mc_metrics", "mc_irr", "mc_autocall", "mc_wof"}
        keys |= {f"mc_fan_{i}" for i in range(n_assets)}
    if "calibration" in groups:
        keys |= {"calib_table", "calib_corr"}
    if "backtest" in groups:
        keys |= {"bt_metrics", "bt_outcome", "bt_pie", "bt_irr", "bt_prices"}
    if "live" in groups:
        keys |= {"live_metrics", "live_asset_table", "live_obs_table", "live_chart"}
    return keys


def _backtest_for_pdf(terms: NoteTerms, tr, history_years: float | None) -> tuple[dict | None, dict | None]:
    """(bt_summary, bt_figures) for the PDF, or (None, None) if no issues backtest.
    Builds the go.Figure objects (not JSON) the report embeds."""
    prices = _prices(dict(terms.tickers), years=history_years, field="close")
    bt, summary = run_backtest(prices, terms)
    if bt.empty:
        return None, None
    bt = bt.copy()

    def _label(cq, ki):
        if int(cq) > 0:
            return f"Autocalled P{int(cq)}"
        return "Knock-in" if bool(ki) else "Held to maturity"
    bt["Outcome"] = [_label(cq, ki) for cq, ki in zip(bt["Call Quarter"], bt["Knock-in"])]
    ac_periods = sorted({int(cq) for cq in bt["Call Quarter"] if int(cq) > 0})
    color_map = {"Held to maturity": "#334155", "Knock-in": "#dc2626"}
    for i, q in enumerate(ac_periods):
        color_map[f"Autocalled P{q}"] = _lerp_hex("#93c5fd", "#1e3a8a", i / max(1, len(ac_periods) - 1))

    bt_summary = dict(summary)
    ki_rows = bt[bt["Knock-in"]]
    if not ki_rows.empty:
        bt_summary["loss_given_ki"] = float(ki_rows["IRR"].mean())
    bt_figures = {
        "outcome":     charts.build_backtest_outcome_bar(bt, color_map, tr),
        "pie":         charts.build_worst_asset_pie(bt, tr),
        "irr_scatter": charts.build_backtest_irr_scatter(bt, color_map, tr),
        "prices":      charts.build_historical_prices(
            prices.resample("W-FRI").last().dropna(),
            bt["Issue Date"].min(), bt["Issue Date"].max(), tr),
    }
    return bt_summary, bt_figures


def build_report_pdf(terms: NoteTerms, *, sections: list[str] | None = None, lang: str = "en",
                     n_paths: int = 10000, seed: int = 42, calib_years: float = 5.0,
                     history_years: float | None = None, engine: str = "numpy") -> bytes:
    """Assemble the institutional PDF report (app/pdf_report.py). Runs only the
    flows whose sections were requested (empty/None ⇒ everything available), reusing
    the cached price pulls. Returns the PDF bytes."""
    from pdf_report import generate_pdf_report                     # heavy import, lazy

    tr = translations.Translator(lang)
    groups = set(sections or [])
    all_on = not groups
    want_mc   = all_on or {"mc", "calibration"} & groups
    want_bt   = all_on or "backtest" in groups
    want_live = all_on or "live" in groups

    tickers = dict(terms.tickers)
    asset_names = list(tickers.values())
    n_assets = len(tickers)
    include_sections = None if all_on else _expand_sections(groups, n_assets)

    results: dict = {}
    figures: dict = {}
    if want_mc:
        sf = _simulate_full(terms, n_paths=n_paths, seed=seed, calib_years=calib_years,
                            history_years=history_years, engine=engine)
        note, cal_result = sf["note"], sf["cal_result"]
        t_grid, obs_pairs = sf["t_grid"], sf["obs_pairs"]
        wof_bands, asset_bands = sf["wof_bands"], sf["asset_bands"]
        results = {**note, "params": cal_result.params, "corr_SS": cal_result.corr_SS}
        figures = {
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

    logo_urls     = {nm: underlyings.logo_for(sym) for sym, nm in tickers.items()}
    logo_tickers  = {nm: sym for sym, nm in tickers.items()}
    issuer_logo   = underlyings.issuer_logo_for(getattr(terms, "issuer", "") or "")

    return generate_pdf_report(
        terms=terms, results=results, asset_names=asset_names, figures=figures,
        lang=lang, bt_summary=bt_summary, bt_figures=bt_figures,
        live_data=live_data, live_figure=live_figure,
        logo_urls=logo_urls, issuer_logo_url=issuer_logo, logo_tickers=logo_tickers,
        include_sections=include_sections)
