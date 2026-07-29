"""Golden pixel-identity harness for the generated PDF report.

Why this exists
---------------
The report's look is spread across ``app/pdf_report.py`` (content) and
``reportkit/theme.py`` (visual identity), and both get edited constantly. A
theme refactor is only safe if we can prove the rendered pixels did not move,
and "I looked at it" does not scale to a 13-page document across three themes.

Design notes
------------
* **Hermetic.** No network and no Chrome. Inputs come from ``golden_fixture``'s
  seeded RNG; ``_fig_to_png`` is monkeypatched to a flat PNG at the exact pixel
  size the call site asked for, so figure aspect — and therefore every
  downstream page break — is identical to a real render. Network image loaders
  are stubbed out.
* **Synthetic branding.** The real CADIEM config and its brand fonts are
  gitignored licensed assets. The fixtures here drive the *same* code paths
  (hexagon chamfers, hex cluster, gradients, cover art) with
  generated images, so the harness runs on a clean checkout.
* **Hashes, not images.** The baseline is a JSON of per-page SHA-256 digests —
  a few KB instead of ~25 MB of PNGs. On failure the run writes both renders to
  a temp directory and prints the path so the diff can be eyeballed.

Usage
-----
    pytest tests/test_golden_pdf.py                 # check against the baseline
    GOLDEN_UPDATE=1 pytest tests/test_golden_pdf.py # re-baseline (review the diff!)

Deliberately skips when the PDF stack (fpdf2 / plotly / Pillow) or a rasteriser
is absent, so the lean CI job in .github/workflows/ci.yml stays green.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("fpdf", reason="fpdf2 not installed — PDF stack absent")
pytest.importorskip("plotly", reason="plotly not installed — PDF stack absent")
pytest.importorskip("PIL", reason="Pillow not installed — PDF stack absent")

import golden_fixture as gf  # noqa: E402  (after importorskip; tests/ is on sys.path)

BASELINE = Path(__file__).resolve().parent / "golden" / "hashes.json"
DPI = 110
THEMES = ["mercator", "hexagon", "custom", "hexcluster", "photos"]


# ── rasteriser ───────────────────────────────────────────────────────────────
def _rasterise(pdf_bytes: bytes, dpi: int = DPI):
    """PDF → list of (sha256, png_bytes), one per page.

    Prefers pypdfium2 (BSD/Apache, and the rasteriser the proof endpoint will
    ship with) and falls back to PyMuPDF, which requirements.txt keeps as an
    ad-hoc verification tool rather than a runtime dependency.
    """
    import io

    try:
        import pypdfium2 as pdfium
    except ImportError:
        pass
    else:
        out = []
        for page in pdfium.PdfDocument(pdf_bytes):
            pil = page.render(scale=dpi / 72.0).to_pil().convert("RGB")
            buf = io.BytesIO(); pil.save(buf, "PNG")
            out.append((hashlib.sha256(pil.tobytes()).hexdigest(), buf.getvalue()))
        return out

    fitz = pytest.importorskip(
        "fitz", reason="no rasteriser — install pypdfium2 or PyMuPDF")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        out.append((hashlib.sha256(pix.samples).hexdigest(), pix.tobytes("png")))
    doc.close()
    return out


# ── render ───────────────────────────────────────────────────────────────────
def _render(theme: str, kind: str = "autocall", *, real_figures: bool = False) -> bytes:
    """Build one report. Delegates to the shared fixture renderer so the golden
    and the structural layout test (tests/test_pdf_layout.py) cannot drift into
    guarding two different documents."""
    return gf.render_report(theme, kind, real_figures=real_figures)


def _load_baseline() -> dict:
    return json.loads(BASELINE.read_text()) if BASELINE.exists() else {}


# ── tests ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("theme", THEMES)
def test_report_is_pixel_identical(theme):
    """The rendered pages must match the committed baseline exactly."""
    pages = _rasterise(_render(theme))
    digests = [h for h, _ in pages]

    if os.environ.get("GOLDEN_UPDATE"):
        base = _load_baseline()
        base[theme] = digests
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(base, indent=2) + "\n")
        pytest.skip(f"baselined {theme}: {len(digests)} pages")

    base = _load_baseline()
    assert theme in base, (
        f"no baseline for '{theme}' — run: GOLDEN_UPDATE=1 pytest {__file__}")
    expected = base[theme]

    if digests != expected:
        out = Path(tempfile.mkdtemp(prefix=f"golden_{theme}_"))
        for i, (_, png) in enumerate(pages, 1):
            (out / f"p{i:02d}.png").write_bytes(png)
        if len(digests) != len(expected):
            pytest.fail(
                f"{theme}: page COUNT changed {len(expected)} → {len(digests)}. "
                f"Rendered pages written to {out}")
        bad = [i + 1 for i, (a, b) in enumerate(zip(digests, expected)) if a != b]
        pytest.fail(
            f"{theme}: {len(bad)} page(s) changed: {bad}. Rendered pages "
            f"written to {out}. If the change is intended, review it image by "
            f"image, then re-baseline with GOLDEN_UPDATE=1.")


@pytest.mark.parametrize("theme", THEMES)
def test_participation_report_renders(theme):
    """The participation payoff branch draws a different summary and profile."""
    pages = _rasterise(_render(theme, kind="participation"))
    assert len(pages) >= 3


def test_stub_figures_preserve_pagination():
    """A stubbed render must paginate exactly like a real one.

    This is the harness's own correctness check, and the reason ``stub_png``
    honours the caller's width/height rather than returning a fixed square:
    ``figure()`` derives placement height from image aspect and only then tests
    whether the block still fits the page. Get the aspect wrong and the golden
    silently stops guarding page breaks.

    Skipped unless GOLDEN_REAL_FIGURES=1, since a real render needs Kaleido and
    Chrome and costs ~2s per figure.
    """
    if not os.environ.get("GOLDEN_REAL_FIGURES"):
        pytest.skip("set GOLDEN_REAL_FIGURES=1 to check stub vs real pagination")

    stub_pages = len(_rasterise(_render("hexagon")))
    real_pages = len(_rasterise(_render("hexagon", real_figures=True)))
    assert stub_pages == real_pages, (
        f"stubbed render paginates differently: {stub_pages} vs {real_pages} "
        "pages — the figure stub's aspect ratio is wrong")
