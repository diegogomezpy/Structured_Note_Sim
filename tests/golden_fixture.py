"""Brand fixtures for the PDF golden harness.

The analytics half of the fixture — the note, the results dict and the figure
stub — lives in ``api/preview_fixture.py``, because the proof endpoint renders
from exactly the same inputs. Sharing it is the point: the golden then guards
what the PDF Studio actually shows.

What stays here is the *branding* half, which is test-only. The real CADIEM
config and its brand fonts are gitignored licensed assets and must never enter
the repo, so these fixtures drive the same code paths — hexagon chamfers, hex
cluster, linear and radial gradients, watermark, cover art — using images
generated at test time.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np

from api.preview_fixture import (  # noqa: F401  (re-exported for the tests)
    SEED, N_PATHS, N_STEPS, note_terms, results, stub_png, figures, extras,
)

FIXTURES = Path(__file__).resolve().parent / "golden"


def branding(theme: str) -> dict:
    """Load a committed brand fixture and attach generated imagery.

    ``theme="hexcluster"`` is a synthetic variant of the hexagon/cadiem theme
    with NO uploaded watermark image and no filler-photo pool. It exercises the
    drawn hex-cluster fallback — CADIEM's real image-less production look — on
    the masthead / divider / empty-space surfaces. The other fixtures always
    attach a watermark image, so without this case the whole image-less mark
    path is unguarded and a refactor could silently break the deployed report.
    """
    hexcluster = theme == "hexcluster"
    photos = theme == "photos"
    _base = "hexagon" if hexcluster else ("mercator" if photos else theme)
    cfg = json.loads((FIXTURES / f"branding_{_base}.json").read_text())
    cfg["logo_base64"] = _swatch(320, 96, (18, 62, 64), "LOGO")
    cfg["cover_logo_base64"] = _swatch(560, 120, (255, 255, 255), "COVER")
    if photos:
        # The POSITIONAL image-slot path, which every other fixture bypasses by
        # setting an explicit cover AND back. Here the pool alone decides the
        # roles, and slot 0 is a deliberate BLANK — the picker's "No image" —
        # so the cover must fall back to the themed background while slot 1
        # still becomes the back page. Without this fixture three branches of
        # the slot algorithm render in no baseline at all.
        cfg["filler_images_base64"] = ["", _noise(900, 600, 67), _noise(700, 460, 71)]
        cfg["watermark_base64"] = _swatch(300, 300, (255, 255, 255), "WM")
        return cfg
    cfg["cover_image_base64"] = _noise(900, 600, 11)
    cfg["back_image_base64"] = _noise(900, 600, 29)
    if hexcluster:
        # No watermark image → the drawn hex cluster renders; no filler pool → the
        # empty-space band draws the cluster rather than a cover photo.
        cfg["filler_images_base64"] = []
    else:
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


def render_report(theme: str, kind: str = "phoenix", *, real_figures: bool = False,
                  lang: str = "en", include_sections: list[str] | None = None) -> bytes:
    """Build one report through the real ``_build_pdf_report`` entry point.

    The single render path for every PDF test — the golden's pixel diff and the
    structural layout invariants must be looking at the SAME document, or one of
    them is guarding a build nobody ships.
    """
    import pdf_report

    terms = note_terms(kind)
    res = results(terms)

    pdf_report._fetch_image_bytes = lambda *a, **k: None

    # The same ContextVar hook the proof endpoint uses, so tests exercise the
    # real interception path rather than a test-only monkeypatch.
    token = None if real_figures else pdf_report._FIG_HOOK.set(
        lambda fig, w, h, *colors: stub_png(w, h))
    try:
        return pdf_report._build_pdf_report(
            terms=terms,
            results=res,
            asset_names=res["asset_names"],
            figures=figures(terms),
            lang=lang,
            branding=branding(theme),
            # None ⇒ every section, which is what the golden pins. A list lets a
            # structural test render a report with chapters switched off — the
            # case where the contents list and the body headings have to agree
            # on a renumbering rather than on the full document.
            include_sections=include_sections,
            logo_urls=None,
            issuer_logo_url=None,
            logo_tickers={name: sym for sym, name in terms.tickers.items()},
            # The backtest / current-performance / comparison / underlying
            # sections draw their own chrome — metric bands, logo-row tables,
            # the A/B terms diff. They render only when handed data, so without
            # these the tests guard roughly half the document.
            **extras(terms, real=real_figures),
        )
    finally:
        if token is not None:
            pdf_report._FIG_HOOK.reset(token)
