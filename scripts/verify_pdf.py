"""
Standalone verification harness for app/pdf_report.py.

Runs a minimal calibration -> simulation -> price_note pipeline (replicating
app.py's run block) on the PUENTE Bonus Certificate config, builds a few
Plotly figures directly (so we don't depend on app/charts.py or
app/translations.py, which another agent owns), loads the CADIEM branding
dict, and renders the report once in English and once in Spanish.

Outputs /tmp/report_en.pdf and /tmp/report_es.pdf, then rasterises every page
to PNG via PyMuPDF so the pages can be eyeballed.

Run:
    .venv/bin/python scripts/verify_pdf.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from core import NoteTerms, price_note                      # noqa: E402
from core.calibrator import HestonCalibrator                # noqa: E402
from core.simulator import HestonMultiSimulator             # noqa: E402
from data.loader import load_prices, load_dividends, build_dividend_schedule  # noqa: E402

import pdf_report                                            # noqa: E402


# ── Build the simulation results dict (mirrors app.py's run block) ───────────
def run_pipeline(terms: NoteTerms, n_paths: int = 2000, seed: int = 7) -> dict:
    tickers = dict(terms.tickers)
    tickers_tuple = tuple(sorted(tickers.items()))

    prices_adj = load_prices(source="yfinance", tickers=dict(tickers_tuple),
                             years=5.0, field="adj_close")
    prices_raw = load_prices(source="yfinance", tickers=dict(tickers_tuple),
                             years=5.0, field="close")

    cal = HestonCalibrator(prices_df=prices_adj, calib_years=5.0)
    cal_result = cal.calibrate()

    raw_last = prices_raw.iloc[-1]
    for p in cal_result.params:
        if p.name in raw_last.index:
            p.S0 = float(raw_last[p.name])

    anchor = prices_raw.index[-1]
    mat_date = pd.offsets.BDay().rollforward(
        anchor + pd.DateOffset(months=round(terms.maturity * 12)))
    grid = pd.bdate_range(anchor, mat_date)
    dt_grid = np.diff(grid.values).astype("timedelta64[D]").astype(float) / 365.0
    n_steps = len(grid) - 1
    obs_steps = [min(int(grid.searchsorted(d)), n_steps)
                 for d in terms.obs_calendar_dates(anchor)]
    obs_times = [(grid[s] - grid[0]).days / 365.0 for s in obs_steps]

    try:
        divs = load_dividends(tickers=dict(tickers_tuple))
    except Exception:
        divs = {}
    div_sched = build_dividend_schedule(
        [divs.get(p.name, pd.Series(dtype=float)) for p in cal_result.params],
        [p.S0 for p in cal_result.params],
        grid,
    )

    sim = HestonMultiSimulator(
        params=cal_result.params,
        corr_SS=cal_result.corr_SS,
        corr_VV=cal_result.corr_VV,
        corr_SV=cal_result.corr_SV,
        n_paths=n_paths,
        seed=seed,
        t_dof=cal_result.t_dof,
        dt_grid=dt_grid,
        div_schedule=div_sched,
    )
    sim_results = sim.run()

    n_assets = len(cal_result.params)
    sim_prices = np.stack(sim_results["S_paths"], axis=2)
    S0_vec = np.array([p.S0 for p in cal_result.params]).reshape(1, 1, n_assets)
    perf_paths = sim_prices / S0_vec
    wof_paths = perf_paths.min(axis=2)

    note_results = price_note(perf_paths, terms, seed=seed + 1,
                              obs_steps=obs_steps, obs_times=obs_times)

    results = {
        **note_results,
        "worst_of_paths": wof_paths,
        "asset_names": list(tickers.values()),
        "params": cal_result.params,
        "corr_SS": cal_result.corr_SS,
        "obs_times": obs_times,
        "t_grid_years": np.concatenate([[0.0], np.cumsum(dt_grid)]),
    }
    return results


# ── Real charts.py figures (exercises the actual palette + aspect ratios) ─────
def build_figures(results: dict, terms: NoteTerms, lang: str = "en") -> dict:
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "app"))
    import charts
    from translations import Translator

    tr = Translator(lang)
    obs_times = list(results.get("obs_times", []))
    obs_pairs = [(f"P{i+1}", float(t)) for i, t in enumerate(obs_times)]

    f_irr = charts.build_irr_distribution(
        results["annualized_returns"], results["autocall_events"],
        results["expected_irr"], terms.coupon_pa, tr)
    f_wof = charts.build_wof_fan(
        results["worst_of_paths"], results["t_grid_years"],
        terms.knock_in_barrier, obs_pairs, tr,
        autocall_barrier=terms.autocall_barrier)
    f_corr = charts.build_corr_heatmap(
        results["corr_SS"], results["asset_names"], tr("corr_input"))

    return {"irr_dist": f_irr, "wof_fan": f_wof, "corr": f_corr}


def render_pages(pdf_path: str, out_prefix: str, dpi: int = 120) -> list[str]:
    import fitz
    doc = fitz.open(pdf_path)
    paths = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        out = f"{out_prefix}_p{i+1}.png"
        pix.save(out)
        paths.append(out)
    doc.close()
    return paths


def main():
    cfg_path = ROOT / "note_configs" / "puente_mayo_bonus_meli_orcl_meta.json"
    terms = NoteTerms.from_json(cfg_path.read_text())

    branding = json.loads((ROOT / "branding" / "branding_cadiem.json").read_text())

    print("== Running pipeline ==")
    results = run_pipeline(terms, n_paths=2000)

    asset_names = results["asset_names"]
    logo_urls = {name: f"https://assets.parqet.com/logos/symbol/{sym}?format=png"
                 for sym, name in terms.tickers.items()}
    logo_tickers = {name: sym for sym, name in terms.tickers.items()}
    issuer_logo_url = None  # PUENTE favicon 404s; exercise the missing-logo path

    for lang, out in [("en", "/tmp/report_en.pdf"), ("es", "/tmp/report_es.pdf")]:
        print(f"== Generating {lang} -> {out} ==")
        figures = build_figures(results, terms, lang)
        pdf_bytes = pdf_report.generate_pdf_report(
            terms=terms,
            results=results,
            asset_names=asset_names,
            figures=figures,
            lang=lang,
            logo_urls=logo_urls,
            issuer_logo_url=issuer_logo_url,
            branding=branding,
            logo_tickers=logo_tickers,
        )
        Path(out).write_bytes(pdf_bytes)
        pages = render_pages(out, f"/tmp/render_{lang}")
        print(f"   {len(pdf_bytes):,} bytes, {len(pages)} pages -> {pages}")


if __name__ == "__main__":
    main()
