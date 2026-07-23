"""Deterministic, network-free inputs for the PDF golden harness.

Everything here is synthesised from a fixed RNG seed rather than loaded from
yfinance or produced by the simulator. That is deliberate: the golden guards the
*drawing* code in ``app/pdf_report.py`` and ``reportkit/theme.py``, so it must
not go red every time the quant library legitimately changes a number. The
shapes and dtypes mirror what ``api/engine.py`` really stores; only the values
are made up.

Used by ``tests/test_golden_pdf.py`` and (from Slice 3) by the proof endpoint's
fixture path, so a designer preview needs neither a simulation nor a network.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np

FIXTURES = Path(__file__).resolve().parent / "golden"

# One seed for the whole fixture: same numbers on every machine, every run.
SEED = 20240617
N_PATHS = 4000
N_STEPS = 394


def note_terms(kind: str = "phoenix"):
    """A representative note of each family the report can render."""
    from core.note import NoteTerms

    if kind == "participation":
        return NoteTerms.from_dict({
            "name": "Golden Participation Note",
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
        "name": "Golden Phoenix Note XS0000000000",
        "maturity": 1.5, "payment_freq": "quarterly", "coupon_pa": 0.124,
        "coupon_barrier": 0.60, "autocall_barrier": 1.0,
        "autocall_start_period": 1, "knock_in_barrier": 0.50,
        "memory": True, "coupon_basket": "worst_of",
        "autocall_basket": "worst_of", "note_type": "phoenix",
        "tickers": {"AAA": "Alpha Corp", "BBB": "Beta SA", "CCC": "Gamma Inc"},
    })


def results(terms) -> dict:
    """A results dict shaped exactly like the one `api/engine.py` stores.

    Every array is drawn from the seeded RNG, so the numbers are stable but
    meaningless — the report only has to lay them out.
    """
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
        "prob_autocall_by_period": [float(x) for x in
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

    Size fidelity is the whole point. ``_NotePDF.figure`` derives its placement
    height from the image's true aspect (``h = w * ih / iw``) and only then
    decides whether the figure still fits on the page, so a stub with the wrong
    aspect silently shifts every downstream page break and the golden stops
    guarding pagination. Returning ``None`` instead is worse still: ``figure()``
    early-returns, emitting no card, no caption and no page break at all.
    """
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (max(1, int(width)), max(1, int(height))), (208, 213, 219)).save(buf, "PNG")
    return buf.getvalue()


def branding(theme: str) -> dict:
    """Load a committed brand fixture.

    These are synthetic on purpose — the real CADIEM config and its brand fonts
    are gitignored licensed assets that must never enter the repo. The fixtures
    exercise the same code paths (chamfer geometry, hex cluster, gradients,
    watermark, cover art) using generated images.
    """
    cfg = json.loads((FIXTURES / f"branding_{theme}.json").read_text())
    cfg["logo_base64"] = _swatch(320, 96, (18, 62, 64), "LOGO")
    cfg["cover_logo_base64"] = _swatch(560, 120, (255, 255, 255), "COVER")
    cfg["cover_image_base64"] = _noise(900, 600, 11)
    cfg["back_image_base64"] = _noise(900, 600, 29)
    cfg["filler_images_base64"] = [_noise(700, 460, 41), _noise(700, 460, 53)]
    cfg["watermark_base64"] = _swatch(300, 300, (255, 255, 255), "WM")
    return cfg


def _swatch(w: int, h: int, rgb: tuple, label: str) -> str:
    """A deterministic labelled block — stands in for a logo/wordmark."""
    import base64
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), rgb)
    d = ImageDraw.Draw(im)
    inv = tuple(255 - c for c in rgb)
    d.rectangle([2, 2, w - 3, h - 3], outline=inv, width=3)
    d.text((10, h // 2 - 6), label, fill=inv)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _noise(w: int, h: int, seed: int) -> str:
    """A deterministic soft gradient — stands in for a cover photograph."""
    import base64
    from PIL import Image

    rng = np.random.default_rng(seed)
    base = np.linspace(0, 255, w, dtype=np.float64)[None, :, None] * np.ones((h, 1, 3))
    base += rng.normal(0, 6, (h, w, 3))
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    buf = io.BytesIO(); im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()
