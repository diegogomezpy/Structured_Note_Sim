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

import re

import pytest

pytest.importorskip("fpdf")
pytest.importorskip("pypdfium2")

import tests.golden_fixture as gf              # noqa: E402
from tests.golden_fixture import render_report  # noqa: E402

THEMES = ["mercator", "hexagon", "custom", "hexcluster", "photos"]

# Calls that draw a heading and then expect content under it.
# `open_section` is the current name; `start_section` is reportkit's 0.7
# deprecation shim, kept here so a stray legacy call site is still probed
# rather than silently uninstrumented — which is what happened when the rename
# landed and this list still named only the old one.
HEADINGS = ["subsection", "secondary_head", "section_divider", "section_title",
            "open_section", "start_section"]
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


# ──────────────────────────────────────────────────────────────────────────────
# Outline invariants — the contents list and the pages must agree
# ──────────────────────────────────────────────────────────────────────────────
# The cover's "In this report" list numbered every leaf while the body numbered
# chapters from hard-coded literals, so the two sequences described different
# things: the cover's "04 Price Paths" against the body's "04 · Monte Carlo".
# They also disagreed on omission (no issuer ⇒ the body jumped 01 → 03) and on
# membership (the Comparison chapter was numbered on the page but absent from
# the list). These pin the agreement rather than either sequence.

def _render_and_read(theme: str, *, kind: str = "phoenix",
                     include_sections: list[str] | None = None):
    """Render, and return `(body_numbers, contents_numbers, cover_pages, pages)`.

    Body numbers are captured by instrumenting the two numbered heading calls —
    exact, unlike scraping them back out of the page text. The contents list is
    read from the rendered page, because the point is to check what a reader
    actually sees on it, not what was passed to the builder.
    """
    import pypdfium2 as pdfium
    import pdf_report

    cls = pdf_report._NotePDF
    body: list[str] = []
    built: list = []
    orig_sec, orig_div = cls.secondary_head, cls.section_divider
    orig_init = cls.__init__

    def sec(self, number, *a, **k):
        body.append(number)
        return orig_sec(self, number, *a, **k)

    def div(self, number, *a, **k):
        body.append(number)
        return orig_div(self, number, *a, **k)

    def init(self, *a, **k):
        orig_init(self, *a, **k)
        built.append(self)

    cls.secondary_head, cls.section_divider, cls.__init__ = sec, div, init
    try:
        raw = render_report(theme=theme, kind=kind, real_figures=False,
                            include_sections=include_sections)
    finally:
        cls.secondary_head, cls.section_divider, cls.__init__ = orig_sec, orig_div, orig_init

    doc = pdfium.PdfDocument(raw)
    pages = [doc[i].get_textpage().get_text_range() for i in range(len(doc))]

    marker = pdf_report._t("in_this_report", "en").upper()
    contents: list[str] = []
    for text in pages:
        at = text.upper().find(marker)
        if at < 0:
            continue
        for line in text[at:].splitlines():
            m = re.match(r"^(\d{2})\s+\S", line.strip())
            if m:
                contents.append(m.group(1))
        break

    # De-duplicate the body list in order: the Underlying chapter heads one page
    # per underlying, so its number legitimately repeats.
    seen, body_uniq = set(), []
    for n in body:
        if n not in seen:
            seen.add(n)
            body_uniq.append(n)
    return body_uniq, contents, built[-1]._cover_pages, pages


@pytest.mark.parametrize("theme", THEMES)
def test_contents_list_numbers_match_the_body(theme):
    body, contents, _, _ = _render_and_read(theme)
    assert body, "no numbered chapter heads were drawn at all"
    assert contents == body, (
        f"[{theme}] the contents page lists {contents} but the body prints {body} — "
        "a number in the list points at a different chapter than the same number "
        "on the page")


@pytest.mark.parametrize("theme", THEMES)
def test_chapter_numbers_are_gapless(theme):
    body, _, _, _ = _render_and_read(theme)
    assert body == [f"{i:02d}" for i in range(1, len(body) + 1)], (
        f"[{theme}] chapter numbers {body} skip or repeat — they must run 01..N "
        "over the chapters this report actually contains")


def test_omitting_a_chapter_renumbers_both_surfaces():
    """Turning a chapter off must close the gap on the page AND in the list.

    With the literals, dropping the Underlying Breakdown left the body reading
    01 · … · 04 Monte Carlo with nothing numbered 02 or 03.
    """
    keep = ["cover", "note_terms", "obs_schedule", "note_diagram", "note_description",
            "mc_metrics", "mc_irr", "bt_metrics", "live_metrics"]
    body, contents, _, _ = _render_and_read("mercator", include_sections=keep)
    assert body == [f"{i:02d}" for i in range(1, len(body) + 1)], body
    assert contents == body, (f"contents {contents} vs body {body}")
    # Underlying Breakdown was excluded, so the chapter count must have dropped.
    full, _, _, _ = _render_and_read("mercator")
    assert len(body) < len(full), "the reduced report kept every chapter"


def test_plan_chapters_numbers_in_document_order():
    import pdf_report as P

    assert P._plan_chapters({"note_terms": True, "mc": True, "bt": True}) == {
        "note_terms": "01", "mc": "02", "bt": "03"}
    # Absent ⇒ no entry, so a head drawn for a chapter nobody declared prints an
    # empty number instead of borrowing someone else's.
    assert "issuer" not in P._plan_chapters({"note_terms": True})
    assert P._plan_chapters({}) == {}


@pytest.mark.parametrize("theme", THEMES)
def test_every_content_page_carries_a_footer(theme):
    """Only the designed cover pages may lack the running footer.

    The glossary silently lost its footer because `footer()` consulted
    `_is_cover`, a flag describing the page about to be DRAWN, while fpdf2 runs
    the footer for the page being CLOSED — so the last content page ahead of any
    cover was treated as one.
    """
    import pdf_report

    _, _, cover_pages, pages = _render_and_read(theme)
    stamp = re.compile(
        rf"{re.escape(pdf_report._t('page_of', 'en'))}\s+\d+\s+"
        rf"{re.escape(pdf_report._t('page_of_mid', 'en'))}\s+\d+")
    missing = [i + 1 for i, text in enumerate(pages)
               if (i + 1) not in cover_pages and not stamp.search(text)]
    assert not missing, f"[{theme}] content pages with no footer: {missing}"


# ──────────────────────────────────────────────────────────────────────────────
# The contents list is one designed page — it must fit, and it must line up
# ──────────────────────────────────────────────────────────────────────────────
# The summary page turns auto page break OFF, so an overlong list does not wrap:
# it draws off the bottom edge. Every underlying adds a row to the rail above it,
# and the Comparison chapter added three more rows, so the list has to shed
# detail rather than overflow.

def _toc_cells(n_assets: int = 3, theme: str = "mercator"):
    """Render with `n_assets` underlyings; return the (x, y, text) of every cell
    drawn on the summary page, plus the page geometry."""
    import pdf_report

    names = ["Alpha Corp", "Beta SA", "Gamma Inc", "Delta NV", "Epsilon Plc",
             "Zeta AG", "Eta Oyj"]
    syms = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]
    orig_terms = gf.note_terms

    def terms(kind="phoenix"):
        t = orig_terms(kind)
        t.tickers = {syms[i]: names[i] for i in range(n_assets)}
        return t

    cls = pdf_report._NotePDF
    drawn: list[tuple[float, float, str]] = []
    orig_cell = cls.cell

    def cell(self, w=0, h=0, txt="", *a, **k):
        if self._is_cover and self.page_no() == 2:
            drawn.append((self.get_x(), self.get_y(), str(txt)))
        return orig_cell(self, w, h, txt, *a, **k)

    cls.cell, gf.note_terms = cell, terms
    try:
        gf.render_report(theme=theme, real_figures=False)
    finally:
        cls.cell, gf.note_terms = orig_cell, orig_terms
    return drawn


@pytest.mark.parametrize("n_assets", [2, 3, 4, 5, 6, 7])
def test_contents_list_never_overflows_the_summary_page(n_assets):
    drawn = _toc_cells(n_assets)
    bottom = 297.0 - 14.0                     # `_toc_bottom` on A4
    over = [(y, t) for _, y, t in drawn if y > bottom]
    assert not over, (
        f"{n_assets} underlyings: contents rows drawn below y={bottom} "
        f"(page is 297mm, auto page break is off, so these fall off the sheet): {over}")


def test_contents_rows_share_one_left_edge():
    """Numbered and unnumbered rows must line up.

    The reference rows (Glossary, Disclaimer) carry no number, and when the
    number column was only reserved for rows that had one they hung 7mm left of
    every other title.
    """
    drawn = _toc_cells(3)
    titles = {"Note Terms", "Underlying Breakdown", "Payoff & Distribution",
              "Price Paths", "Glossary of Terms", "Disclaimer"}
    xs = {t: x for x, _, t in drawn if t in titles}
    assert len(xs) >= 4, f"only found {sorted(xs)} — the probe missed rows"
    assert len(set(round(x, 2) for x in xs.values())) == 1, (
        f"contents rows start at different x: {xs}")


def test_comparison_leaves_follow_the_built_tables():
    """A sub-section is listed only if the body will render it.

    The leaves were derived from the raw `compare_data` while the body gates on
    the tables `_compare_tables` actually builds — so a Note B differing only in
    its basket (no differing *term sheet* rows) was promised a terms table the
    document did not contain.
    """
    import pypdfium2 as pdfium
    import pdf_report

    orig = pdf_report._compare_tables
    # No differing terms, but real metric rows — the basket-only comparison.
    pdf_report._compare_tables = lambda t, c, l: ([], orig(t, c, l)[1])
    try:
        raw = render_report(theme="mercator", real_figures=False)
    finally:
        pdf_report._compare_tables = orig

    cover = pdfium.PdfDocument(raw)[1].get_textpage().get_text_range()
    terms_leaf = pdf_report._t("cmp_terms_title", "en")
    metrics_leaf = pdf_report._t("cmp_metrics_title", "en")
    assert terms_leaf not in cover, (
        f"contents lists {terms_leaf!r} but the body renders no terms table")
    assert metrics_leaf in cover, "the metrics table is rendered but not listed"
