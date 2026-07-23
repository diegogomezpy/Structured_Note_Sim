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

MAX_PAGES = 40
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
            break
        bitmap = doc[i].render(scale=scale)
        import io
        buf = io.BytesIO()
        bitmap.to_pil().convert("RGB").save(buf, "PNG", optimize=False)
        out.append(base64.b64encode(buf.getvalue()).decode())
    return out


def render_proof(*, branding: dict | None = None, terms: dict | None = None,
                 sections: list[str] | None = None, lang: str = "en",
                 kind: str = "phoenix", scale: float = DEFAULT_SCALE,
                 pages: list[int] | None = None) -> dict:
    """Render a proof and return `{pages: [b64 png], page_count, cached}`.

    `terms` is the live note from the app when there is one; without it the
    fixture's note stands in, so the Studio works before anything is simulated.
    """
    scale = max(0.3, min(float(scale or DEFAULT_SCALE), MAX_SCALE))
    note = NoteTerms.from_dict(terms) if terms else fixture.note_terms(kind)
    key = _digest(branding, terms, sections, lang, kind, scale, pages)

    if key in _CACHE:
        _CACHE.move_to_end(key)
        return {"pages": _CACHE[key], "page_count": len(_CACHE[key]), "cached": True}

    results = fixture.results(note)
    opts_token = charts.set_chart_options(_chart_options_from_branding(branding))
    stub_token = pdf_report._FIG_STUB.set(fixture.stub_png)
    try:
        pdf_bytes = pdf_report._build_pdf_report(
            terms=note,
            results=results,
            asset_names=results["asset_names"],
            figures=fixture.figures(),
            lang=lang,
            branding=branding,
            include_sections=set(sections) if sections else None,
            logo_urls=None,
            issuer_logo_url=None,
            logo_tickers={name: sym for sym, name in note.tickers.items()},
        )
    finally:
        pdf_report._FIG_STUB.reset(stub_token)
        charts.reset_chart_options(opts_token)

    imgs = _rasterise(pdf_bytes, scale, pages)
    _CACHE[key] = imgs
    while len(_CACHE) > _MAX_CACHE:
        _CACHE.popitem(last=False)
    return {"pages": imgs, "page_count": len(imgs), "cached": False}
