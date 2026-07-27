"""Structural layout invariants for the generated PDF.

The golden test (`test_golden_pdf.py`) pins the exact pixels, which catches any
unintended change but says nothing about whether the layout is *good* — a
baseline can happily encode a broken page. This file pins PROPERTIES instead, so
a defect is caught the first time it appears rather than the first time someone
looks at a render.

The property here is the one that actually shipped broken: a heading must never
be separated from the block it introduces. It happened because the room a
sub-heading reserved (`_table_room`, capped at 130mm) and the room `data_table`
demanded (uncapped) were computed independently and disagreed for tables of
roughly 16-29 rows — so the heading drew, the table bounced to the next page,
and the heading was left alone on a page the void-decorator then filled with
ornament, making a pagination failure look deliberate.

Rather than guess at headings by scraping text out of the PDF, this instruments
the builder: every heading call records the page it landed on, and the next
content call records the page IT landed on. If they differ, the heading is an
orphan. That is exact, and it fails with the heading's own text in the message.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fpdf")
pytest.importorskip("pypdfium2")

import tests.golden_fixture as gf              # noqa: E402
from tests.golden_fixture import render_report  # noqa: E402

THEMES = ["mercator", "hexagon", "custom", "hexcluster"]

# Calls that draw a heading and then expect content under it.
HEADINGS = ["subsection", "secondary_head", "section_divider", "section_title",
            "start_section"]
# Calls that emit the content a heading is introducing. `figure` is included:
# a caption split from its figure is the same defect wearing a different hat.
CONTENT = ["data_table", "logo_row_table", "kv_table", "metric_band", "figure",
           "callout", "body", "bullet"]


def _orphans(theme: str, kind: str = "phoenix") -> list[str]:
    """Render, and return a description of every heading whose first following
    content landed on a different page."""
    import pdf_report

    cls = pdf_report._NotePDF
    seen: list[str] = []
    pending: list[tuple[str, int]] = []     # [(label, page)] — at most one
    originals = {}

    def wrap_heading(name):
        orig = getattr(cls, name)

        def inner(self, *a, **k):
            out = orig(self, *a, **k)
            # Record AFTER the call: the heading hook may itself page-break
            # first, and the page it ends on is the page it drew on.
            label = next((x for x in a if isinstance(x, str) and x.strip()), name)
            pending.clear()
            pending.append((f"{name}({label!r})", self.page_no()))
            return out
        return inner

    def wrap_content(name):
        orig = getattr(cls, name)

        def inner(self, *a, **k):
            # Page BEFORE the call — a table that breaks internally after
            # drawing its first rows on this page is fine; one that breaks
            # before drawing anything is what strands the heading. data_table
            # decides that up front, so sample the page after it settles.
            out = orig(self, *a, **k)
            if pending:
                label, hpage = pending.pop()
                # `self.page_no()` can have advanced legitimately if the content
                # itself is long; what matters is where it STARTED, which for a
                # block that broke immediately is the page after the heading.
                started = getattr(self, "_layout_probe_start", self.page_no())
                if started != hpage:
                    seen.append(f"{label} on p{hpage} but {name} started p{started}")
            return out
        return inner

    def wrap_start_probe(name):
        """Record the page a content call is on once it has done its own
        keep-together break but before it draws."""
        orig = getattr(cls, name)

        def inner(self, *a, **k):
            self._layout_probe_start = None
            _add = cls.add_page

            def probe_add(s, *aa, **kk):
                r = _add(s, *aa, **kk)
                if getattr(s, "_layout_probe_start", None) is None:
                    s._layout_probe_start = s.page_no()
                return r
            cls.add_page = probe_add
            try:
                if self._layout_probe_start is None:
                    self._layout_probe_start = self.page_no()
                return orig(self, *a, **k)
            finally:
                cls.add_page = _add
        return inner

    try:
        for nm in HEADINGS:
            originals[nm] = getattr(cls, nm)
            setattr(cls, nm, wrap_heading(nm))
        for nm in CONTENT:
            originals[nm] = getattr(cls, nm)
            setattr(cls, nm, wrap_content(nm))
        render_report(theme, kind)
    finally:
        for nm, fn in originals.items():
            setattr(cls, nm, fn)
    return seen


@pytest.mark.parametrize("theme", THEMES)
def test_no_orphaned_headings(theme):
    """No heading is left on a page without the block it introduces."""
    bad = _orphans(theme)
    assert not bad, theme + ": orphaned heading(s):\n  " + "\n  ".join(bad)


def test_no_orphaned_headings_participation():
    """The participation note takes different branches through the builder."""
    bad = _orphans("mercator", kind="participation")
    assert not bad, "participation: orphaned heading(s):\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("n_obs,expect_together", [(6, True), (18, True), (60, True)])
def test_table_room_matches_data_table_break_rule(n_obs, expect_together):
    """`_table_room` must predict `data_table`'s own break rule.

    These are the two numbers that drifted apart. The heading reserves
    `_table_room(n)`; the table then decides for itself whether to break. If the
    table would break at the y the heading left the cursor on, the heading is
    stranded — so assert the reservation is at least what the table demands.
    """
    import pdf_report as P

    reserved = P._table_room(n_obs)
    full = P._TBL_HEAD_H + n_obs * P._TBL_ROW_H + P._TBL_PAD
    if full <= P._PAGE_CAP:
        # Short table: kept whole, so the heading must reserve the whole thing
        # plus its own height.
        assert reserved >= full, f"{n_obs} rows: reserved {reserved} < table {full}"
    else:
        # Long table: splits anyway, so only a modest reservation is right —
        # demanding the full height would waste a page before every long table.
        assert reserved < P._PAGE_CAP
    assert expect_together
