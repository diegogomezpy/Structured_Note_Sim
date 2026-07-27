"""Render the REAL report as page images, for the PDF Studio's live proof.

The point of this module is that there is only ONE renderer. The Studio does not
approximate the document in the browser — it shows the pages `app/pdf_report.py`
actually produces, so "what you see is what the PDF will be" holds by
construction rather than by keeping a second implementation in sync.

Three things make that fast enough to type against:

* **Figures are stubbed.** Kaleido costs ~2s per figure regardless of resolution
  (it is Chrome IPC, not pixels), which would put a full document at 30s+. With
  the stub installed the whole build is ~0.3s. Every other surface — covers,
  mastheads, section heads, dividers, tables, typography, logos, watermark,
  gradients — is genuine. The stub is sized to the caller's exact request so
  pagination is identical to a real build.
* **Analytics come from a fixture** when the note has not been simulated, so a
  proof needs no yfinance call and no Monte Carlo run.
* **Rasterising is pypdfium2**, ~30ms per page.

Two rules this module must not break, both of which would corrupt a real
client's PDF rather than merely spoil a preview:

1. Never call `generate_pdf_report`. It starts and stops the shared Kaleido
   server in a `finally`, so a proof finishing mid-build would tear Chrome out
   from under a concurrent `/api/report`, whose figures would then silently come
   back empty — a complete-looking PDF with no charts in it.
2. Import `pdf_report` by bare name, exactly as `api/engine.py` does. `app/` is
   on sys.path, so `import app.pdf_report` would resolve to a SECOND module
   object with its own font registration and its own ContextVars — the stub
   would be set on one and read on the other.
"""
from __future__ import annotations

import base64
import hashlib
import sys
from collections import OrderedDict
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.note import NoteTerms                    # noqa: E402
import charts                                      # noqa: E402
import pdf_report                                  # noqa: E402  (bare name — see above)

from . import preview_fixture as fixture           # noqa: E402
from .engine import _chart_options_from_branding   # noqa: E402

# Page rasters are cached on a hash of (branding, terms, options). Editing one
# colour re-renders everything anyway, so the cache mostly serves scrolling and
# repeated identical requests. Small and FIFO-capped: the run store already owns
# this process's memory budget and a proof must not compete with it.
_CACHE: "OrderedDict[str, list[str]]" = OrderedDict()
_MAX_CACHE = 6

# Rasterised CHART pngs, keyed on everything that determines the pixels: the
# figure itself, the requested size and the three brand colours `_theme_figure`
# recolours with. This is what makes real charts affordable in a live preview.
# A chart costs ~2s of Chrome IPC no matter its resolution, so a 16-figure
# document is ~30s cold — but only chart-affecting edits invalidate these
# entries, so changing a chamfer, a logo or the cover art re-renders the whole
# document in ~0.3s with every chart served from here.
_FIG_CACHE: "OrderedDict[str, bytes]" = OrderedDict()
_MAX_FIG_CACHE = 96

# A full report with every section on, a long observation schedule and several
# underlyings runs past 40 pages; the cap silently truncated the tail, so the
# preview stopped where the document did not. Raised well clear of that, and the
# truncation is now reported instead of being invisible.
MAX_PAGES = 120
DEFAULT_SCALE = 1.4      # ~100 dpi — legible at the Studio's page width
MAX_SCALE = 3.0


def _digest(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode("utf-8", "replace"))
    return h.hexdigest()


def _rasterise(pdf_bytes: bytes, scale: float, pages: list[int] | None) -> list[str]:
    """PDF bytes → base64 PNG per page."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_bytes)
    want = range(len(doc)) if not pages else [i for i in pages if 0 <= i < len(doc)]
    out = []
    for i in want:
        if len(out) >= MAX_PAGES:
            print(f"[proof] page cap hit: showing {MAX_PAGES} of {len(doc)} pages")
            break
        bitmap = doc[i].render(scale=scale)
        import io
        buf = io.BytesIO()
        bitmap.to_pil().convert("RGB").save(buf, "PNG", optimize=False)
        out.append(base64.b64encode(buf.getvalue()).decode())
    return out


def _placeholder_hook(fig, width, height, *_colors):
    """Fast mode: a flat block at the requested size, no Plotly, no Chrome."""
    return fixture.stub_png(width, height)


def _memoised_hook(fig, width, height, *colors):
    """Real mode: the genuine rasteriser, but each distinct chart drawn once.

    The key covers everything that changes the pixels — the figure's own JSON
    (which already carries the brand's chart options, since every builder ends
    in `charts._apply_theme`) plus the size and the three colours
    `_theme_figure` recolours with. So editing anything that is not a chart
    setting leaves every entry valid.
    """
    import plotly.graph_objects as go

    try:
        key = _digest(go.Figure(fig).to_json(), width, height, colors)
    except Exception:
        return None                      # unhashable figure → just render it

    hit = _FIG_CACHE.get(key)
    if hit is not None:
        _FIG_CACHE.move_to_end(key)
        return hit

    # Re-enter the real rasteriser with the hook lifted, or this recurses.
    token = pdf_report._FIG_HOOK.set(None)
    try:
        png = pdf_report._fig_to_png(fig, width, height, *colors)
    finally:
        pdf_report._FIG_HOOK.reset(token)

    if png:
        _FIG_CACHE[key] = png
        while len(_FIG_CACHE) > _MAX_FIG_CACHE:
            _FIG_CACHE.popitem(last=False)
    return png


def render_proof(*, branding: dict | None = None, terms: dict | None = None,
                 sections: list[str] | None = None, lang: str = "en",
                 kind: str = "phoenix", scale: float = DEFAULT_SCALE,
                 pages: list[int] | None = None,
                 figures: str = "stub") -> dict:
    """Render a proof and return `{pages: [b64 png], page_count, cached, figures}`.

    `terms` is the live note from the app when there is one; without it the
    fixture's note stands in, so the Studio works before anything is simulated.

    `figures='real'` draws the actual charts. They are the slow part — ~2s each
    — so the caller is expected to show a stubbed render first and upgrade to
    this one when it lands. Repeat renders are fast because the chart cache
    survives any edit that is not a chart setting.
    """
    scale = max(0.3, min(float(scale or DEFAULT_SCALE), MAX_SCALE))
    real = figures == "real"
    note = NoteTerms.from_dict(terms) if terms else fixture.note_terms(kind)
    key = _digest(branding, terms, sections, lang, kind, scale, pages, figures)

    if key in _CACHE:
        _CACHE.move_to_end(key)
        return {"pages": _CACHE[key], "page_count": len(_CACHE[key]),
                "cached": True, "figures": figures}

    results = fixture.results(note)
    opts_token = charts.set_chart_options(_chart_options_from_branding(branding))
    # Chart options must be installed BEFORE the figures are built: every
    # builder ends in charts._apply_theme(), which reads them.
    figs = fixture.real_figures(note, results, lang) if real else fixture.figures(note)
    hook_token = pdf_report._FIG_HOOK.set(_memoised_hook if real else _placeholder_hook)
    try:
        pdf_bytes = pdf_report._build_pdf_report(
            terms=note,
            results=results,
            asset_names=results["asset_names"],
            figures=figs,
            lang=lang,
            branding=branding,
            include_sections=set(sections) if sections else None,
            logo_urls=None,
            issuer_logo_url=None,
            logo_tickers={name: sym for sym, name in note.tickers.items()},
            # Stand-in data for every section gated on something other than the
            # Monte Carlo run — backtest, current performance, A/B comparison,
            # underlying breakdown. Without these the proof silently dropped
            # them, so "select everything" previewed a partial document.
            **fixture.extras(note, real=real, lang=lang, sections=sections),
        )
    finally:
        pdf_report._FIG_HOOK.reset(hook_token)
        charts.reset_chart_options(opts_token)

    imgs = _rasterise(pdf_bytes, scale, pages)
    _CACHE[key] = imgs
    while len(_CACHE) > _MAX_CACHE:
        _CACHE.popitem(last=False)
    return {"pages": imgs, "page_count": len(imgs), "cached": False, "figures": figures}
