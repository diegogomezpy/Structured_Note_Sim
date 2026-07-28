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
        """Record the page the block's FIRST INK lands on.

        Not the page it finishes on: a long table legitimately spans several
        pages, and comparing the heading against the LAST page turns every
        multi-page table into a false orphan. Not the page it starts the call on
        either: the block may break before drawing anything, which is exactly
        the defect. So instrument the drawing primitives and take the page of
        the first one that fires — ignoring ink from the running header/footer
        and the void decorator, which are not the block's own content.
        """
        orig = getattr(cls, name)
        INK = ("cell", "multi_cell", "rect", "image", "line")

        def inner(self, *a, **k):
            if not pending:
                return orig(self, *a, **k)
            first = []
            saved = {m: getattr(cls, m) for m in INK if hasattr(cls, m)}

            def probe(m, fn):
                def p(s, *aa, **kk):
                    if not first and not getattr(s, "_in_chrome", False):
                        first.append(s.page_no())
                    return fn(s, *aa, **kk)
                return p

            # The header/footer/void hooks fire mid-block via add_page; their ink
            # is chrome, not content, so flag them out.
            _add, _dec = cls.add_page, cls._decorate_void

            def add_page(s, *aa, **kk):
                s._in_chrome = True
                try:
                    return _add(s, *aa, **kk)
                finally:
                    s._in_chrome = False

            for m, fn in saved.items():
                setattr(cls, m, probe(m, fn))
            cls.add_page = add_page
            try:
                out = orig(self, *a, **k)
            finally:
                for m, fn in saved.items():
                    setattr(cls, m, fn)
                cls.add_page = _add
                self._in_chrome = False
            label, hpage = pending.pop()
            started = first[0] if first else self.page_no()
            if started != hpage:
                seen.append(f"{label} on p{hpage} but {name} first drew on p{started}")
            return out
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


# Table sizes chosen to sit on the seams, not at random:
#   18 — the size that was reported broken (the 130mm cap vs the real height);
#   27 — the largest table still kept whole under its heading;
#   28 — the first that cannot be, and which the FIRST fix still orphaned
#        because `_PAGE_CAP` measured a fresh page without the heading on it;
#   36, 60 — long enough to span pages, where the block legitimately splits
#        under its heading and must NOT be reported as an orphan.
@pytest.mark.parametrize("n_obs", [18, 27, 28, 36, 60])
def test_no_orphaned_headings_across_table_sizes(n_obs):
    """The heading/table seam holds at every table size, not just the fixture's."""
    from core.note import NoteTerms

    original = gf.note_terms

    def monthly(kind="phoenix"):
        d = original(kind).to_dict()
        d["payment_freq"] = "monthly"
        d["maturity"] = n_obs / 12.0
        return NoteTerms.from_dict(d)

    gf.note_terms = monthly
    try:
        bad = _orphans("mercator")
    finally:
        gf.note_terms = original
    assert not bad, f"n_obs={n_obs}: orphaned heading(s):\n  " + "\n  ".join(bad)


def test_split_room_lets_a_long_table_start_under_its_heading():
    """`_SPLIT_ROOM` is derived from data_table's own give-up threshold.

    A heading that draws at the very bottom of its reservation must still leave
    the cursor above the point where data_table breaks regardless — otherwise
    the guard cannot save it and the heading is stranded anyway.
    """
    import pdf_report as P

    worst_y_after_heading = (297.0 - 28.0 - P._SPLIT_ROOM) + P._HEAD_ROOM
    assert worst_y_after_heading <= 297.0 - 55.0, (
        f"_SPLIT_ROOM={P._SPLIT_ROOM} leaves the cursor at "
        f"{worst_y_after_heading:.1f}mm, past data_table's {297.0 - 55.0:.1f}mm "
        "give-up point — a long table would orphan its heading")


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
