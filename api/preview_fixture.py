"""Deterministic, network-free stand-in analytics for rendering a report.

Two callers share this:

* the **proof endpoint** (`api/proof.py`), so the PDF Studio can render a real
  report for a note that has never been simulated — no yfinance call, no Monte
  Carlo run, no waiting;
* the **golden harness** (`tests/test_golden_pdf.py`), so a change to the
  drawing code is diffed against fixed inputs and does not go red every time the
  quant library legitimately changes a number.

Sharing matters: it means the golden guards the exact inputs the proof renders.

Everything is drawn from one fixed seed. The shapes and dtypes mirror what
`api/engine.py` really stores; the values are synthetic and are never shown to a
client — the proof is stamped as a proof.
"""
from __future__ import annotations

import io

import numpy as np

SEED = 20240617
N_PATHS = 4000
N_STEPS = 394


def note_terms(kind: str = "phoenix"):
    """A representative note of each family the report can render."""
    from core.note import NoteTerms

    if kind == "participation":
        return NoteTerms.from_dict({
            "name": "Sample Participation Note",
            "maturity": 3.0, "payment_freq": "annual", "coupon_pa": 0.0,
            "coupon_barrier": 0.0, "autocall_barrier": 0.0,
            "autocall_start_period": 1, "knock_in_barrier": 0.0,
            "memory": False, "coupon_basket": "worst_of",
            "autocall_basket": "worst_of", "note_type": "participation",
            "participation_downside": "airbag", "participation_upside": "linear",
            "participation_rate": 1.4, "participation_strike": 1.0,
            "protection_level": 0.7, "upside_cap": 1.6,
            "tickers": {"AAA": "Alpha Corp", "BBB": "Beta SA"},
        })
    return NoteTerms.from_dict({
        "name": "Sample Phoenix Note XS0000000000",
        "maturity": 1.5, "payment_freq": "quarterly", "coupon_pa": 0.124,
        "coupon_barrier": 0.60, "autocall_barrier": 1.0,
        "autocall_start_period": 1, "knock_in_barrier": 0.50,
        "memory": True, "coupon_basket": "worst_of",
        "autocall_basket": "worst_of", "note_type": "phoenix",
        "tickers": {"AAA": "Alpha Corp", "BBB": "Beta SA", "CCC": "Gamma Inc"},
    })


def results(terms) -> dict:
    """A results dict shaped exactly like the one `api/engine.py` stores."""
    from core.simulator import HestonParams

    rng = np.random.default_rng(SEED)
    names = list(terms.tickers.values())
    n_obs = max(1, terms.n_obs)

    called = rng.random(N_PATHS) < 0.62
    period = np.where(called, rng.integers(1, n_obs + 1, N_PATHS), 0)
    ki = (~called) & (rng.random(N_PATHS) < 0.34)

    ann = rng.normal(0.09, 0.13, N_PATHS)
    ann[ki] -= 0.42
    total = ann * np.clip(period / max(1, n_obs) * terms.maturity, 0.25, None)

    return {
        "asset_names": names,
        "annualized_returns": ann,
        "total_returns": total,
        "autocall_events": called,
        "autocall_period": period,
        "knock_in_mask": ki,
        "knock_in_triggered": ki,
        "coupon_amounts": rng.random((N_PATHS, n_obs)) * terms.coupon_rate,
        "coupon_payoffs": rng.random(N_PATHS) * 0.2,
        "nominal_payoffs": 1.0 + total,
        "principal_payoffs": np.clip(1.0 + total, 0.0, 1.0),
        "worst_of_paths": np.cumprod(
            1 + rng.normal(0.0002, 0.011, (N_PATHS, N_STEPS)), axis=1),
        "t_grid_years": np.linspace(0, terms.maturity, N_STEPS),
        "obs_times": [terms.maturity * (i + 1) / n_obs for i in range(n_obs)],
        "prob_autocall": float(called.mean()),
        "prob_autocall_by_period": [
            float(x) for x in
            (np.bincount(period[called], minlength=n_obs + 1)[1:] / N_PATHS)],
        "prob_knock_in": float(ki.mean()),
        "prob_knock_in_total": float(ki.mean()),
        "prob_maturity": float((~called).mean()),
        "prob_barrier_event": float(ki.mean()),
        "prob_rescued": 0.031,
        "expected_irr": float(ann.mean()),
        "expected_total_return": float(total.mean()),
        "expected_coupon": 0.0931,
        "expected_nominal_payout": float((1 + total).mean()),
        "avg_time_to_autocall": 0.83,
        "loss_given_knock_in": -0.287,
        "corr_SS": np.eye(len(names)) * 0.55 + 0.45,
        "params": [
            HestonParams(name=n, S0=100.0 + 10 * i, kappa=1.8 + 0.1 * i,
                         theta=0.041 + 0.003 * i, xi=0.55, rho=-0.62,
                         V0=0.038, mu=0.061 + 0.004 * i)
            for i, n in enumerate(names)
        ],
    }


def stub_png(width: int, height: int) -> bytes:
    """A flat grey PNG at EXACTLY the requested pixel size.

    Size fidelity is the whole point — see the note in `_fig_to_png`, which
    installs this. Getting the aspect wrong silently changes where pages break.
    """
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (max(1, int(width)), max(1, int(height))),
              (208, 213, 219)).save(buf, "PNG")
    return buf.getvalue()


# Figure keys the report may read. Values are opaque sentinels: with the stub
# installed nothing ever inspects them, they only need to be PRESENT so each
# figure-bearing block renders its card, caption and page break.
FIGURE_KEYS = ("irr_dist", "wof_fan", "outcome", "sample",
               "corr", "corr_input", "corr_realized", "corr_diff")


def figures(terms=None) -> dict:
    """Placeholder figure set.

    `terms` matters: the report draws one per-asset fan chart per underlying, so
    without them a stubbed proof paginates one page shorter than the real
    document and the fast preview quietly stops predicting page breaks.
    """
    d: dict = {k: object() for k in FIGURE_KEYS}
    d["asset_fans"] = []
    names = list(terms.tickers.values()) if terms is not None else []
    d["individual"] = [(n, object()) for n in names]
    return d


def real_figures(terms, results: dict, lang: str = "en") -> dict:
    """Genuine Plotly figures built from the fixture, mirroring what
    `api/engine.py` assembles for a real report.

    Used by the proof's real-chart mode. Deliberately the same builders the
    report calls, so the brand's chart options apply exactly as they will in the
    delivered PDF — the whole point being that nothing about the proof is a
    separate implementation.
    """
    import charts
    import translations

    tr = translations.Translator(lang)
    names = results["asset_names"]
    t_grid = results["t_grid_years"]
    wof = results["worst_of_paths"]
    obs = [(f"{i + 1}", t) for i, t in enumerate(results["obs_times"])]
    participation = getattr(terms, "note_type", "") == "participation"

    figs: dict = {
        "outcome": (charts.build_redemption_distribution(results["nominal_payoffs"], terms, tr)
                    if participation else
                    charts.build_outcome_breakdown(
                        results["prob_autocall_by_period"], results["prob_maturity"],
                        results["prob_knock_in_total"], tr)),
        "irr_dist": charts.build_irr_distribution(
            results["annualized_returns"], results["total_returns"],
            results["autocall_events"], results["expected_irr"], terms.coupon_pa, tr),
        "wof_fan": charts.build_wof_fan(
            wof, t_grid, terms.knock_in_barrier, obs, tr,
            autocall_barrier=terms.autocall_barrier, participation=participation),
        "sample": charts.build_sample_paths(
            wof, t_grid, results["autocall_period"], results["knock_in_mask"],
            terms.knock_in_barrier, terms.autocall_barrier, obs, tr),
        "corr": charts.build_corr_heatmap(results["corr_SS"], names, tr("corr_input")),
        "individual": [(n, charts.build_fan_chart(
            np.asarray(wof) * (1.0 + 0.02 * i), n, t_grid, obs, tr))
            for i, n in enumerate(names)],
    }
    figs["asset_fans"] = []
    return figs
