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

from core.note import NoteTerms, price_note                       # noqa: E402
from core.calibrator import HestonCalibrator                      # noqa: E402
from core.simulator import HestonMultiSimulator                   # noqa: E402
from core.backtest import run_backtest                            # noqa: E402
from data.loader import (load_prices, load_dividends,             # noqa: E402
                          build_dividend_schedule)
import charts            # noqa: E402  (app/charts.py)
import translations      # noqa: E402  (app/translations.py)

_PCTS = [1, 5, 25, 50, 75, 95, 99]

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
def run_simulation(terms: NoteTerms, *, n_paths: int = 10000, seed: int = 42,
                   calib_years: float = 5.0, history_years: float | None = None,
                   engine: str = "numpy", lang: str = "en") -> dict:
    """Load → calibrate → simulate → price, then build the Monte Carlo figures.
    Mirrors the old Streamlit run block; returns summary stats + Plotly-JSON
    figures + a run_id (full paths cached server-side for the explorer)."""
    tickers = dict(terms.tickers)
    tr = translations.Translator(lang)

    # Calibrate on adjusted closes (total-return dynamics); barriers/S0/dividends
    # live in raw price space.
    prices_adj = load_prices(source="yfinance", tickers=tickers,
                             years=history_years, field="adj_close")
    prices_raw = load_prices(source="yfinance", tickers=tickers,
                             years=history_years, field="close")
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
    prices = load_prices(source="yfinance", tickers=dict(terms.tickers),
                         years=history_years, field="close")
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
