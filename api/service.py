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
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── Resource limits (env-overridable) ─────────────────────────────────────────
# Each cached result holds the full simulated price array, so the cache is the
# main memory risk on a small instance — keep it tiny. n_paths is capped because
# peak memory scales with paths × steps × assets (antithetic doubles the input).
# Tune up on a larger host: SNSIM_MAX_PATHS, SNSIM_CACHE_SIZE.
_MAX_PATHS  = int(os.environ.get("SNSIM_MAX_PATHS", "8000"))
_CACHE_SIZE = int(os.environ.get("SNSIM_CACHE_SIZE", "3"))

# Make the repo root AND the app/ dir importable. app/charts.py and
# app/pdf_report.py use bare imports (`from translations import ...`), exactly
# as Streamlit runs them, so app/ must be on sys.path — same trick as
# scripts/verify_pdf.py.
_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_ROOT), str(_ROOT / "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import NoteTerms, price_note, replay_note          # noqa: E402
from core.calibrator import HestonCalibrator                 # noqa: E402
from core.simulator import HestonMultiSimulator              # noqa: E402
from core.backtest import run_backtest, snapped_obs_dates    # noqa: E402
from data.loader import (                                    # noqa: E402
    load_prices, load_dividends, build_dividend_schedule,
)
import datetime as _dt                                       # noqa: E402

import charts                                                # noqa: E402  (app/charts.py)
import pdf_report                                            # noqa: E402  (app/pdf_report.py)
from translations import Translator                          # noqa: E402
from underlyings import TICKER_LOGOS, _LOGO_BASE             # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Heavy pipeline (cached): calibrate → simulate → price_note
# ──────────────────────────────────────────────────────────────────────────────
@functools.lru_cache(maxsize=_CACHE_SIZE)
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
    n_paths = min(req.n_paths, _MAX_PATHS)
    R  = run_simulation(tj, n_paths, req.seed, req.calib_years, req.history_years)
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
    n_paths = min(req.n_paths, _MAX_PATHS)
    R  = run_simulation(tj, n_paths, req.seed, req.calib_years, req.history_years)
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


# ──────────────────────────────────────────────────────────────────────────────
# Historical backtest
# ──────────────────────────────────────────────────────────────────────────────
@functools.lru_cache(maxsize=_CACHE_SIZE)
def _run_backtest(terms_json: str, bt_start: str | None, bt_end: str | None,
                  history_years: float | None):
    terms = NoteTerms.from_json(terms_json)
    tickers_tuple = tuple(sorted(terms.tickers.items()))
    prices = load_prices("yfinance", dict(tickers_tuple), years=history_years, field="close")
    bt, summary = run_backtest(
        prices, terms,
        bt_start=pd.Timestamp(bt_start) if bt_start else None,
        bt_end=pd.Timestamp(bt_end) if bt_end else None,
    )
    return bt, summary, prices


def _bt_path_figure(prices, terms, issue_date: str, bt, tr):
    """Historical worst-of path for one issue date (mirrors app.py's explorer)."""
    anchor, obs_dates = snapped_obs_dates(prices, terms, pd.Timestamp(issue_date))
    sched = (list(zip(obs_dates, terms.autocall_barrier_schedule()))
             if terms.autocall_step_down else None)
    issue_loc = prices.index.searchsorted(anchor)
    s0 = prices.iloc[issue_loc].values.astype(float)
    perf_obs = []
    for d in obs_dates:
        loc = prices.index.searchsorted(d)
        if loc >= len(prices):
            break
        perf_obs.append(prices.iloc[loc].values.astype(float) / s0)
    flags = ([r["coupon_amount"] > 0 for r in replay_note(np.array(perf_obs), terms)["rows"]]
             if perf_obs else None)
    row = bt[bt["Issue Date"] == pd.Timestamp(issue_date)]
    call_q = int(row.iloc[0]["Call Quarter"]) if not row.empty else 0
    return charts.build_historical_wof_path(
        prices, issue_date=anchor, obs_dates=obs_dates,
        knock_in_barrier=terms.knock_in_barrier, autocall_barrier=terms.autocall_barrier,
        coupon_barrier=terms.coupon_barrier, call_quarter=call_q, tr=tr,
        autocall_schedule=sched, coupon_at_autocall_only=terms.coupon_at_autocall_only,
        coupon_flags=flags,
    )


def backtest(req) -> dict:
    terms = NoteTerms.from_dict(req.terms)
    tj = terms.to_json()
    bt, summary, prices = _run_backtest(tj, req.bt_start, req.bt_end, req.history_years)
    tr = Translator(req.lang)
    if bt is None or bt.empty:
        return {"summary": {}, "figures": {}, "issue_dates": [], "status": "no_results"}

    # Outcome labels + colour map — identical to app.py so the legend/palette
    # match (autocall blue gradient, maturity stark slate, knock-in red).
    bt = bt.copy()
    mat_lbl = tr("bt_outcome_maturity")
    ki_lbl  = tr("bt_outcome_knock_in")
    bt["Outcome"] = bt["Call Quarter"].map(
        {0: mat_lbl, **{i: tr("bt_outcome_autocalled_p", i=i) for i in range(1, terms.n_obs + 1)}})
    bt.loc[(bt["Call Quarter"] == 0) & bt["Knock-in"], "Outcome"] = ki_lbl
    n_ac = max(terms.n_obs - 1, 1)
    color_map = {
        mat_lbl: "#334155", ki_lbl: "#dc2626",
        **{tr("bt_outcome_autocalled_p", i=i): f"hsl(217,72%,{70 - ((i - 1) / n_ac) * 40:.0f}%)"
           for i in range(1, terms.n_obs + 1)},
    }

    ki_rows = bt[bt["Knock-in"]]
    summary = dict(summary)
    if not ki_rows.empty:
        summary["loss_given_ki"] = float(ki_rows["IRR"].mean())

    figures = {
        "outcome":     charts.build_backtest_outcome_bar(bt, color_map, tr).to_json(),
        "irr_scatter": charts.build_backtest_irr_scatter(bt, color_map, tr).to_json(),
        "pie":         charts.build_worst_asset_pie(bt, tr).to_json(),
    }
    try:
        weekly = prices.resample("W-FRI").last().dropna()
        figures["prices"] = charts.build_historical_prices(
            weekly, bt["Issue Date"].min(), bt["Issue Date"].max(), tr).to_json()
    except Exception:
        pass
    if req.issue_date:
        figures["path"] = _bt_path_figure(prices, terms, req.issue_date, bt, tr).to_json()

    issue_dates = [pd.Timestamp(d).date().isoformat() for d in sorted(bt["Issue Date"].unique())]
    return {"summary": summary, "figures": figures, "issue_dates": issue_dates, "status": "ok"}


# ──────────────────────────────────────────────────────────────────────────────
# Current performance (live tracking)
# ──────────────────────────────────────────────────────────────────────────────
def live(req) -> dict:
    terms = NoteTerms.from_dict(req.terms)
    if not terms.issue_date:
        raise ValueError("terms.issue_date is required for /live.")
    tr = Translator(req.lang)
    names = list(terms.tickers.values())
    obs_labels = [f"P{i+1}" for i in range(terms.n_obs)]
    disp_to_sym = {disp: sym for sym, disp in terms.tickers.items()}

    full = load_prices("yfinance", dict(tuple(sorted(terms.tickers.items()))), years=None, field="close")
    issue_ts = pd.Timestamp(terms.issue_date)
    today    = pd.Timestamp(_dt.date.today())
    mat_ts   = issue_ts + pd.DateOffset(months=round(terms.maturity * 12))
    if today < issue_ts:
        return {"status": "not_started", "issue_date": terms.issue_date}

    elapsed_years = (today - issue_ts).days / 365.25
    i0 = min(int(full.index.searchsorted(issue_ts)), len(full) - 1)
    anchor = full.index[i0]
    live_prices = full.iloc[i0:]
    if len(live_prices) < 2:
        return {"status": "not_enough_data"}

    s0 = full.iloc[i0].values.astype(float)
    today_slice = live_prices[live_prices.index <= today]
    perf_today  = today_slice.iloc[-1].values / s0
    wof_today   = float(perf_today.min())
    worst_asset = names[int(perf_today.argmin())]

    obs_cal  = terms.obs_calendar_dates(anchor)
    ac_sched = terms.autocall_barrier_schedule()
    next_idx = next((i for i, d in enumerate(obs_cal) if pd.Timestamp(d) > today), len(ac_sched) - 1)
    next_ac  = float(ac_sched[next_idx])

    # Snap observation dates that have already happened; replay coupons.
    obs_snapped = []
    for d in obs_cal:
        j = int(full.index.searchsorted(d))
        obs_snapped.append(full.index[j] if (j < len(full) and full.index[j] <= today) else None)
    past = [d for d in obs_snapped if d is not None]
    perf_obs = np.vstack([full.loc[d].values / s0 for d in past]) if past else np.empty((0, len(s0)))
    replay = replay_note(perf_obs, terms)

    rows, markers, running = [], [], 0.0
    for q, label in enumerate(obs_labels):
        snap = obs_snapped[q] if q < len(obs_snapped) else None
        if q >= len(replay["rows"]) or snap is None:
            if replay["autocall_period"] and q + 1 > replay["autocall_period"]:
                break
            est = obs_cal[q].date().isoformat() if q < len(obs_cal) else "—"
            rows.append({"period": label, "date": est, "status": "upcoming",
                         "worst_of": None, "coupon": None, "cumulative": None})
            continue
        r = replay["rows"][q]
        obs_wof = float(perf_obs[q].min())
        running += r["coupon_amount"]
        if r["autocalled"]:
            status = "autocalled"
        elif terms.coupon_at_autocall_only:
            status = "no_coupon"
        elif r["coupon_met"]:
            status = "coupon_paid"
        else:
            status = "coupon_missed"
        rows.append({"period": label, "date": snap.date().isoformat(), "status": status,
                     "worst_of": obs_wof, "coupon": float(r["coupon_amount"]) or None,
                     "cumulative": float(running)})
        markers.append({"date": snap, "label": label, "wof": obs_wof,
                        "autocalled": r["autocalled"],
                        "paid": bool(r["coupon_met"] or r["coupon_amount"] > 0),
                        "amount": r["coupon_amount"]})
        if r["autocalled"]:
            break

    total_coupons = replay["total_coupons"]
    irr_to_date   = total_coupons / max(elapsed_years, 1 / 252)

    future_obs = ([] if replay["autocall_period"]
                  else [(obs_labels[q], obs_cal[q]) for q in range(len(replay["rows"]), terms.n_obs)])
    live_sched = ([(d, ac_sched[q]) for q, d in enumerate(obs_cal)]
                  if terms.autocall_step_down else None)
    fig = charts.build_live_performance_chart(
        hist_prices=live_prices, issue_date=anchor, today=today, maturity_date=mat_ts,
        obs_markers=markers, future_obs=future_obs,
        knock_in_barrier=terms.knock_in_barrier, autocall_barrier=terms.autocall_barrier,
        coupon_barrier=terms.coupon_barrier, tr=tr, autocall_schedule=live_sched,
    )

    return {
        "status": "ok",
        "metrics": {
            "wof_today": wof_today,
            "worst_asset": worst_asset,
            "ki_buffer": wof_today - terms.knock_in_barrier,
            "ac_buffer": wof_today - next_ac,
            "next_autocall_barrier": next_ac,
            "irr_to_date": irr_to_date,
            "elapsed_years": elapsed_years,
            "remaining_years": max(terms.maturity - elapsed_years, 0.0),
            "pending_coupons": int(replay["pending_coupons"]),
        },
        "perf_today": {n: float(p) for n, p in zip(names, perf_today)},
        "obs_rows": rows,
        "figure": fig.to_json(),
        "meta": {"issue_date": anchor.date().isoformat(), "maturity_date": mat_ts.date().isoformat()},
    }
