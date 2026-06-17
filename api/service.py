"""
api/service.py
--------------
Orchestration for the API: calibrate → simulate → price, plus figure and PDF
assembly. This mirrors the run block in app/app.py exactly (adjusted closes for
calibration; raw closes for S0 and dividend jumps; a real trading-day grid),
but with no Streamlit dependency.

The heavy calibrate+simulate step is memoised with functools.lru_cache, keyed on
the request parameters — the API equivalent of app.py's @st.cache_data.
"""
from __future__ import annotations

import functools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Make the repo root AND the app/ dir importable. app/charts.py and
# app/pdf_report.py use bare imports (`from translations import ...`), exactly
# as Streamlit runs them, so app/ must be on sys.path — same trick as
# scripts/verify_pdf.py.
_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_ROOT), str(_ROOT / "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import NoteTerms, price_note                       # noqa: E402
from core.calibrator import HestonCalibrator                 # noqa: E402
from core.simulator import HestonMultiSimulator              # noqa: E402
from data.loader import (                                    # noqa: E402
    load_prices, load_dividends, build_dividend_schedule,
)

import charts                                                # noqa: E402  (app/charts.py)
import pdf_report                                            # noqa: E402  (app/pdf_report.py)
from translations import Translator                          # noqa: E402
from underlyings import TICKER_LOGOS, _LOGO_BASE             # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Heavy pipeline (cached): calibrate → simulate → price_note
# ──────────────────────────────────────────────────────────────────────────────
@functools.lru_cache(maxsize=64)
def run_simulation(terms_json: str, n_paths: int, seed: int,
                   calib_years: float, history_years: float | None) -> dict:
    """Full Monte Carlo pipeline for one note. Cached on the exact arguments so
    repeated /simulate and /pdf calls for the same configuration are free."""
    terms = NoteTerms.from_json(terms_json)
    tickers_tuple = tuple(sorted(terms.tickers.items()))

    # Calibrate on dividend-adjusted (total-return) closes; observe barriers,
    # S0 and dividend jumps in raw price space.
    prices_adj = load_prices("yfinance", dict(tickers_tuple), years=history_years, field="adj_close")
    prices_raw = load_prices("yfinance", dict(tickers_tuple), years=history_years, field="close")

    cal = HestonCalibrator(prices_df=prices_adj, calib_years=calib_years).calibrate()
    raw_last = prices_raw.iloc[-1]
    for p in cal.params:
        if p.name in raw_last.index:
            p.S0 = float(raw_last[p.name])

    # Trading-day grid from the last close to maturity.
    anchor   = prices_raw.index[-1]
    mat_date = pd.offsets.BDay().rollforward(anchor + pd.DateOffset(months=round(terms.maturity * 12)))
    grid     = pd.bdate_range(anchor, mat_date)
    dt_grid  = np.diff(grid.values).astype("timedelta64[D]").astype(float) / 365.0
    n_steps  = len(grid) - 1
    obs_steps = [min(int(grid.searchsorted(d)), n_steps) for d in terms.obs_calendar_dates(anchor)]
    obs_times = [(grid[s] - grid[0]).days / 365.0 for s in obs_steps]

    try:
        divs = load_dividends(dict(tickers_tuple))
    except Exception:
        divs = {}
    div_sched = build_dividend_schedule(
        [divs.get(p.name, pd.Series(dtype=float)) for p in cal.params],
        [p.S0 for p in cal.params], grid,
    )

    sim = HestonMultiSimulator(
        params=cal.params, corr_SS=cal.corr_SS, corr_VV=cal.corr_VV,
        corr_SV=cal.corr_SV, n_paths=n_paths, seed=seed, t_dof=cal.t_dof,
        dt_grid=dt_grid, div_schedule=div_sched,
    ).run()

    n_assets   = len(cal.params)
    sim_prices = np.stack(sim["S_paths"], axis=2)
    s0_vec     = np.array([p.S0 for p in cal.params]).reshape(1, 1, n_assets)
    perf_paths = sim_prices / s0_vec
    wof_paths  = perf_paths.min(axis=2)

    note = price_note(perf_paths, terms, seed=seed + 1, obs_steps=obs_steps, obs_times=obs_times)

    return {
        **note,
        "worst_of_paths": wof_paths,
        "sim_prices":     sim_prices,
        "asset_names":    list(terms.tickers.values()),
        "s0_values":      [p.S0 for p in cal.params],
        "params":         cal.params,
        "corr_SS":        cal.corr_SS,
        "realized_corr":  sim["realized_corr"],
        "effective_corr": sim.get("effective_corr"),
        "t_dof":          cal.t_dof,
        "terms":          terms,
        "t_grid_years":   np.concatenate([[0.0], np.cumsum(dt_grid)]),
        "obs_steps":      obs_steps,
        "obs_times":      obs_times,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Figure assembly (reuses app/charts.py — returns go.Figure objects)
# ──────────────────────────────────────────────────────────────────────────────
def build_mc_figures(R: dict, lang: str) -> dict:
    """Build the Monte Carlo figures as Plotly go.Figure objects (the same
    builders the Streamlit app uses). Keyed so the PDF and the JSON API agree."""
    tr     = Translator(lang)
    terms  = R["terms"]
    names  = R["asset_names"]
    t_grid = R["t_grid_years"]
    obs_pairs = [(f"P{i+1}", float(t)) for i, t in enumerate(R["obs_times"])]
    ac_sched = (list(zip(R["obs_times"], terms.autocall_barrier_schedule()))
                if terms.autocall_step_down else None)

    figs = {
        "irr_dist": charts.build_irr_distribution(
            R["annualized_returns"], R["autocall_events"], R["expected_irr"], terms.coupon_pa, tr),
        "wof_fan": charts.build_wof_fan(
            R["worst_of_paths"], t_grid, terms.knock_in_barrier, obs_pairs, tr,
            autocall_barrier=terms.autocall_barrier, autocall_schedule=ac_sched),
        "corr": charts.build_corr_heatmap(R["corr_SS"], names, tr("corr_input")),
    }
    figs["individual"] = [
        (nm, charts.build_fan_chart(R["sim_prices"][:, :, i], nm, t_grid, obs_pairs, tr))
        for i, nm in enumerate(names)
    ]
    return figs


# ──────────────────────────────────────────────────────────────────────────────
# High-level entry points used by the routes
# ──────────────────────────────────────────────────────────────────────────────
_METRIC_KEYS = (
    "expected_irr", "expected_total_return", "expected_coupon",
    "prob_autocall", "prob_barrier_event", "prob_knock_in_total",
    "prob_rescued", "loss_given_knock_in",
)


def _terms_json(terms_dict: dict) -> str:
    # Normalise through NoteTerms so legacy/loose configs validate and the cache
    # key is canonical.
    return NoteTerms.from_dict(terms_dict).to_json()


def simulate(req) -> dict:
    """Run the pipeline and return JSON-safe metrics + Plotly figure JSON."""
    tj = _terms_json(req.terms)
    R  = run_simulation(tj, req.n_paths, req.seed, req.calib_years, req.history_years)
    figs = build_mc_figures(R, req.lang)

    figures_json = {
        "irr_dist": figs["irr_dist"].to_json(),
        "wof_fan":  figs["wof_fan"].to_json(),
        "corr":     figs["corr"].to_json(),
        "individual": [{"name": nm, "figure": f.to_json()} for nm, f in figs["individual"]],
    }
    metrics = {k: (None if (v := R.get(k)) is None or v != v else float(v))  # nan -> None
               for k in _METRIC_KEYS}
    n_paths_eff = int(np.asarray(R["annualized_returns"]).shape[0])
    return {
        "metrics": metrics,
        "figures": figures_json,
        "meta": {
            "asset_names": R["asset_names"],
            "n_paths": n_paths_eff,
            "obs_times": [float(t) for t in R["obs_times"]],
        },
    }


def build_pdf(req) -> bytes:
    """Render the branded PDF, reusing app/pdf_report.py unchanged."""
    tj = _terms_json(req.terms)
    R  = run_simulation(tj, req.n_paths, req.seed, req.calib_years, req.history_years)
    figs = build_mc_figures(R, req.lang)
    terms = R["terms"]

    logo_urls = {name: (TICKER_LOGOS.get(sym) or _LOGO_BASE.format(sym=sym))
                 for sym, name in terms.tickers.items()}
    logo_tickers = {name: sym for sym, name in terms.tickers.items()}

    include = set(req.include_sections) if req.include_sections is not None else None
    return pdf_report.generate_pdf_report(
        terms=terms, results=R, asset_names=R["asset_names"],
        figures=figs, lang=req.lang,
        logo_urls=logo_urls, logo_tickers=logo_tickers,
        branding=req.branding, include_sections=include,
    )
