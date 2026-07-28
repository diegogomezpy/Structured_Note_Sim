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
    # The path-explorer selection ("Selected path(s)"). In the real report these
    # are PNGs the client captured; here one panel stands in so the section is
    # previewed rather than silently skipped.
    d["panels"] = [{"title": None, "wof": object(), "num": 1}]
    d["single_path_num"] = 1
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
    figs["panels"] = [{"title": None, "wof": figs["wof_fan"], "num": 1}]
    figs["single_path_num"] = 1
    return figs


# ---------------------------------------------------------------------------
# Sections beyond the Monte Carlo lens
# ---------------------------------------------------------------------------
# The proof used to hand `_build_pdf_report` only the MC results + figure set, so
# every section gated on OTHER data — the historical backtest, current
# performance, the A/B comparison, the underlying breakdown, the captured path
# panels — was silently dropped. Selecting everything in the Report panel then
# produced a preview with several sections missing, which reads as "the preview
# is broken" rather than "the preview has no data for those".
#
# These build the same SHAPES `api/engine.py` passes, from the same fixed seed.

def bt_summary(terms) -> dict:
    """Backtest summary shaped like `_backtest_for_pdf`'s first return value."""
    rng = np.random.default_rng(SEED + 1)
    irr = rng.normal(0.075, 0.10, 240)
    return {
        "n_issues": 240,
        "mean_irr": float(irr.mean()),
        "median_irr": float(np.median(irr)),
        "expected_total_return": 0.118,
        "expected_nominal_payout": 1.036,
        "prob_called": 0.74,
        "prob_knock_in": 0.11,
        "prob_knock_in_total": 0.11,
        "prob_above_par": 0.81,
        "prob_below_par": 0.19,
        "loss_given_ki": -0.263,
        "avg_time_to_autocall": 0.71,
    }


def live_data(terms) -> dict:
    """Current-performance block shaped like `run_live_api(..., for_pdf=True)`.

    `obs_rows` is a list of uniform dicts — the report turns its keys straight
    into table headers, and picks a 6-column width profile, so the fixture keeps
    six columns to paginate like the real thing.
    """
    names = list(terms.tickers.values())
    rng = np.random.default_rng(SEED + 2)
    perf = {nm: float(v) for nm, v in zip(names, rng.normal(0.04, 0.11, len(names)))}
    worst = min(perf, key=perf.get) if perf else ""
    n_obs = min(6, max(1, terms.n_obs))
    rows = [{
        "#": str(i + 1),
        "Date": f"2025-{(i % 12) + 1:02d}-15",
        "Worst-of": f"{0.98 - 0.01 * i:.2%}",
        "Coupon": "Paid" if i % 3 else "Missed",
        "Autocall": "No",
        "Cumulative": f"{terms.coupon_rate * (i + 1):.2%}",
    } for i in range(n_obs)]
    return {
        "wof_today": 0.943,
        "worst_asset": worst,
        "irr_to_date": 0.081,
        "elapsed_years": 0.58,
        "perf_today": perf,
        "obs_rows": rows,
    }


def compare_data(terms) -> dict:
    """A/B comparison block shaped like `_compare_for_pdf`'s first return value.

    Note B is the same note with a wider coupon barrier and a richer coupon, so
    the differing-terms table has rows to draw.
    """
    from core.note import NoteTerms

    b = NoteTerms.from_dict({**terms.to_dict(), "name": f"{terms.name} (B)",
                             "coupon_pa": float(terms.coupon_pa) * 1.25,
                             "coupon_barrier": min(0.95, float(terms.coupon_barrier) + 0.15)})
    rows = [
        {"key": "expected_irr", "a": 0.084, "b": 0.101, "delta": 0.017, "se": 0.0021},
        {"key": "expected_total_return", "a": 0.061, "b": 0.052, "delta": -0.009, "se": 0.0018},
        {"key": "expected_coupon", "a": 0.093, "b": 0.081, "delta": -0.012, "se": 0.0009},
        {"key": "prob_autocall", "a": 0.742, "b": 0.798, "delta": 0.056, "se": 0.0044},
        {"key": "prob_knock_in_total", "a": 0.081, "b": 0.104, "delta": 0.023, "se": 0.0027},
    ]
    return {
        "shared_paths": True,
        "diff": {"rows": rows},
        "paired": {"win_rate": 0.44, "loss_rate": 0.56, "tie_rate": 0.0,
                   "mean_edge": -0.009, "median_edge": -0.004, "se_edge": 0.0018,
                   "edge_p5": -0.121, "edge_p95": 0.046},
        "name_a": terms.name, "name_b": b.name, "terms_b": b,
    }


def _panels(n: int = 1) -> list[dict]:
    """Captured path-explorer panels (MC and backtest use the same shape)."""
    return [{"title": "", "issue": "2019-04-01", "path": object(), "price": object()}
            for _ in range(n)]


def underlying_closes(terms) -> dict:
    """A trailing-12M daily close series per underlying.

    The breakdown page shows a price chart and, above it, the last price — so
    one series feeds both and the two agree. VALUES are seeded; only the index
    dates track today, because a proof chart labelled with a stale year reads as
    a broken preview. Nothing pinned by the golden depends on the dates: in stub
    mode `_FIG_HOOK` intercepts the figure before it is ever rendered.
    """
    import pandas as pd

    rng = np.random.default_rng(SEED + 4)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=252)
    out = {}
    for i, nm in enumerate(terms.tickers.values()):
        steps = rng.normal(0.0004, 0.0135, len(idx))
        out[nm] = pd.Series((60.0 + 30 * i) * np.cumprod(1.0 + steps), index=idx)
    return out


def underlying_metrics(terms) -> dict:
    """Per-underlying metric records for the breakdown pages.

    The KEYS are the contract with `data.loader.load_underlying_metrics`, whose
    record `underlying_block` reads — `market_cap` / `last_price` / `rsi_14` /
    `iv_3m`. They were once named `u_*` here, which nothing reads, so every
    metric tile in the proof rendered "—" while the real report filled them.
    """
    rng = np.random.default_rng(SEED + 3)
    closes = underlying_closes(terms)
    out = {}
    for i, nm in enumerate(terms.tickers.values()):
        px = closes[nm]
        out[nm] = {
            "long_name": nm,
            "type": "EQUITY",
            "industry": ("Aerospace & Defense", "Specialty Retail", "Software")[i % 3],
            "sector": "Industrials",
            "currency": "USD",
            "market_cap": float(8.0e10 * (i + 1) + rng.normal(0, 4e9)),
            "last_price": float(px.iloc[-1]),
            "day_change": float(px.iloc[-1] / px.iloc[-2] - 1.0),
            "rsi_14": float(np.clip(rng.normal(52.0, 9.0), 5.0, 95.0)),
            "iv_3m": float(abs(rng.normal(0.28, 0.05))),
            "iv_source": "implied",
            "business_summary": (
                "A representative issuer profile used by the PDF Studio proof. "
                "The real report shows the description pulled for this underlying, "
                "or the one written for it in the note's own settings."),
            "analyst": {"buy": 58.0, "hold": 36.0, "sell": 6.0},
        }
    return out


def underlying_price_figs(terms, *, real: bool = False, lang: str = "en") -> dict:
    """The trailing-12M price chart per underlying.

    Absent, `underlying_block` draws its metric tiles and description and then
    simply stops — leaving the bottom two thirds of the page to the void
    decoration. That is what the proof showed: not a chart that failed to load,
    a chart that was never handed over.
    """
    if not real:
        return {nm: object() for nm in terms.tickers.values()}
    import charts
    import translations

    tr = translations.Translator(lang)
    return {nm: charts.build_underlying_price_chart(px, nm, tr)
            for nm, px in underlying_closes(terms).items()}


# The A/B comparison is not a tree item in the Report panel — it is its own
# toggle — so the front end mirrors it into the active-section list under this
# synthetic key (see web/src/lib/reportSections.ts:COMPARE_KEY). The section is
# data-gated in the report, so without this the proof would show a comparison
# whether or not the user asked for one.
COMPARE_KEY = "compare_ab"


def extras(terms, *, real: bool = False, lang: str = "en",
           sections: list[str] | None = None) -> dict:
    """Everything `_build_pdf_report` needs beyond `results` + `figures`.

    Splat into the call: `_build_pdf_report(..., **fixture.extras(note))`. In
    stub mode every figure is an opaque sentinel — `_fig_to_png` is intercepted,
    so nothing inspects them; they only need to be PRESENT for their block to be
    written and the pagination to match.
    """
    stub = (lambda: object())
    figs = {"outcome": stub(), "pie": stub(), "irr_scatter": stub(),
            "prices": stub(), "panels": _panels()}
    cmp_figs = {"irr": stub(), "outcome": stub()}
    if real:
        figs, cmp_figs = _real_side_figures(terms, lang)
    want_cmp = sections is None or COMPARE_KEY in sections
    return {
        "bt_summary": bt_summary(terms),
        "bt_figures": figs,
        "live_data": live_data(terms),
        "live_figure": (figs.get("prices") if real else stub()),
        "compare_data": compare_data(terms) if want_cmp else None,
        "compare_figures": cmp_figs if want_cmp else None,
        "underlying_metrics": underlying_metrics(terms),
        "underlying_price_figs": underlying_price_figs(terms, real=real, lang=lang),
        "issuer_description": (
            "A representative issuer profile used by the PDF Studio proof. The "
            "real report shows the issuer description saved on the note, or the "
            "one pulled for it automatically."),
    }


def _real_side_figures(terms, lang: str) -> tuple[dict, dict]:
    """Genuine Plotly figures for the backtest / live / compare blocks.

    A backtest figure wants a realised-issue DataFrame, which the fixture does
    not have — rather than fake one badly, these reuse builders that take plain
    arrays, so the proof's real-chart mode shows a real chart of the right kind
    in each slot instead of a grey block.
    """
    import charts
    import translations

    tr = translations.Translator(lang)
    res = results(terms)
    t_grid = res["t_grid_years"]
    obs = [(f"{i + 1}", t) for i, t in enumerate(res["obs_times"])]
    fan = charts.build_wof_fan(res["worst_of_paths"], t_grid, terms.knock_in_barrier,
                               obs, tr, autocall_barrier=terms.autocall_barrier)
    irr = charts.build_irr_distribution(
        res["annualized_returns"], res["total_returns"], res["autocall_events"],
        res["expected_irr"], terms.coupon_pa, tr)
    outcome = charts.build_outcome_breakdown(
        res["prob_autocall_by_period"], res["prob_maturity"],
        res["prob_knock_in_total"], tr)
    # Distinct chart per slot — two identical figures on consecutive pages read
    # as a rendering bug rather than as two different measures.
    pie = charts.build_redemption_distribution(res["nominal_payoffs"], terms, tr)
    figs = {"outcome": outcome, "pie": pie, "irr_scatter": irr,
            "prices": fan, "panels": [{"title": "", "issue": "2019-04-01",
                                       "path": fan, "price": fan}]}
    return figs, {"irr": irr, "outcome": outcome}
