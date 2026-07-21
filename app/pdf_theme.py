"""
app/pdf_theme.py
----------------
Pluggable visual-identity layer for the PDF report (app/pdf_report.py).

The report's *content* (tables, metric bands, figures, glossary, cover copy,
disclaimer body, chart rebranding) is theme-agnostic and lives in pdf_report.py.
Everything that is a *look* — the shape vocabulary (chamfered hexagons), the
running header/footer chrome, section heads and chapter dividers, the cover
masthead, and the empty-space decorations — is owned by a ReportTheme here, so a
brand can swap the entire visual language without touching the content code.

Themes
------
- HexagonTheme  — the CADIEM / "green" language: chamfer-hexagon mastheads,
  lime number-chips, hex-cluster watermarks. This is the original look, moved
  verbatim; CADIEM selects it via branding["report_theme"] = "cadiem".
- MercatorTheme — a cleaner, website-inspired language (rounded cards, accent
  keylines, no chamfers/hexagons). The default for un-themed brands.

Selection: branding["report_theme"] → resolve_theme(); an absent/unknown value
falls back to the default theme. The theme is handed the palette-derived
ThemeTokens and draws through the live _NotePDF instance (passed as `pdf`), so it
has full access to fpdf primitives, fonts, and page geometry.

Byte-identity contract: the HexagonTheme must reproduce the pre-refactor CADIEM
output pixel-for-pixel (see scratchpad/golden.py). Any change to a drawing
routine here that alters CADIEM output is a regression.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from fpdf.drawing import DeviceRGB


# ──────────────────────────────────────────────────────────────────────────────
# Design tokens — the palette-derived colour vocabulary every theme shares.
# ──────────────────────────────────────────────────────────────────────────────
# Brand-neutral constants (the design has NO red; downside is amber). These are
# the canonical home; pdf_report.py re-imports them so there is one source.
WHITE         = (255, 255, 255)
BLACK         = (0,   0,   0)
AMBER         = (201, 119,  45)  # #C9772D — downside / capital-loss
AMBER_DARK    = (154, 123,  18)  # #9A7B12 — deep amber (knock-in)
MUTED         = (139, 151, 160)  # #8B97A0 — eyebrow/label grey
BODY_INK      = ( 36,  59,  51)  # #243B33 — paragraph text on white
RULE_SOFT     = (201, 210, 204)  # #C9D2CC — secondary-head hairline
FOOTNOTE_GREY = (166, 176, 184)  # #A6B0B8 — footnote / caption
TEXT          = ( 43,  61,  79)  # #2B3D4F — default body/running text ink


def blend(rgb: tuple, target: tuple, f: float) -> tuple:
    """Linear blend of `rgb` toward `target` by fraction `f` (0..1), rounded."""
    return tuple(round(rgb[i] * (1 - f) + target[i] * f) for i in range(3))


@dataclass
class ThemeTokens:
    """Palette-derived colour tokens handed to a ReportTheme. `ink` = darkened
    primary (mastheads/banners/stat values); `lime` = the section-rule colour
    (keylines, number chips, accents); `teal` = the accent (secondary series,
    kickers). The neutral tokens match the reference's grey-green family; `panel`
    is the card/tile fill; `sidebar_bar` the solid bar atop the cover sidebar."""
    primary: tuple
    accent: tuple
    section_rule: tuple
    ink: tuple
    lime: tuple
    teal: tuple
    amber: tuple
    amber_dark: tuple
    muted: tuple
    body_ink: tuple
    rule_soft: tuple
    footnote_grey: tuple
    panel: tuple
    sidebar_bar: tuple


def build_tokens(primary: tuple, accent: tuple, section_rule: tuple,
                 panel: tuple | None = None,
                 sidebar_bar: tuple | None = None) -> ThemeTokens:
    """Derive the full token set from the resolved brand palette. `panel` and
    `sidebar_bar` may be pinned by the brand; otherwise `panel` is a very light
    tint of PRIMARY (so a bold accent never yields a pink card) and `sidebar_bar`
    is the primary (matching the table headers). Mirrors the original
    _NotePDF.__init__ derivation exactly — byte-identity depends on it."""
    return ThemeTokens(
        primary=primary,
        accent=accent,
        section_rule=section_rule,
        ink=blend(primary, BLACK, 0.46),
        lime=section_rule,
        teal=accent,
        amber=AMBER,
        amber_dark=AMBER_DARK,
        muted=MUTED,
        body_ink=BODY_INK,
        rule_soft=RULE_SOFT,
        footnote_grey=FOOTNOTE_GREY,
        panel=(panel if panel is not None else blend(primary, WHITE, 0.93)),
        sidebar_bar=(sidebar_bar if sidebar_bar is not None else primary),
    )


# ──────────────────────────────────────────────────────────────────────────────
# The CADIEM "hexagon" — a rectangular chamfer (rectangle with the top-right and
# bottom-left corners cut at 45°, all corners rounded). Reproduced as a true
# vector path (PaintedPath) so it scales crisply at any size — used for the dark
# mastheads/banners, the lime number chips, and faint watermark clusters.
# ──────────────────────────────────────────────────────────────────────────────
def _dev_rgb(t: tuple[int, int, int]) -> DeviceRGB:
    return DeviceRGB(t[0] / 255.0, t[1] / 255.0, t[2] / 255.0)


def _chamfer_outline(path, x: float, y: float, w: float, h: float,
                     c: float, q: float, r: float) -> None:
    """Trace the chamfer path into `path`. Transcribes the prototype's
    hexPath(W,H,c,q,r): chamfer depth `c`, chamfer-corner round `q`, normal
    corner radius `r`. (x, y) = top-left in mm."""
    s = q * 0.70710678
    X = lambda v: x + v
    Y = lambda v: y + v
    path.move_to(X(r), Y(0))
    path.line_to(X(w - c - q), Y(0))
    path.quadratic_curve_to(X(w - c), Y(0), X(w - c + s), Y(s))
    path.line_to(X(w - s), Y(c - s))
    path.quadratic_curve_to(X(w), Y(c), X(w), Y(c + q))
    path.line_to(X(w), Y(h - r))
    path.quadratic_curve_to(X(w), Y(h), X(w - r), Y(h))
    path.line_to(X(c + q), Y(h))
    path.quadratic_curve_to(X(c), Y(h), X(c - s), Y(h - s))
    path.line_to(X(s), Y(h - c + s))
    path.quadratic_curve_to(X(0), Y(h - c), X(0), Y(h - c - q))
    path.line_to(X(0), Y(r))
    path.quadratic_curve_to(X(0), Y(0), X(r), Y(0))
    path.close()


def _chamfer_dims(w: float, h: float, c=None, q=None, r=None):
    """Default chamfer parameters proportional to the shape; any may be pinned."""
    m = min(w, h)
    if c is None:
        c = m * 0.14
    if q is None:
        q = c * 0.28
    if r is None:
        r = min(m * 0.10, 6.0)
    return c, q, r


def _fill_chamfer(pdf, x: float, y: float, w: float, h: float,
                  rgb: tuple[int, int, int], c=None, q=None, r=None,
                  opacity: float = 1.0) -> None:
    """Draw a filled chamfer-hexagon panel (banner / chip / masthead)."""
    c, q, r = _chamfer_dims(w, h, c, q, r)
    with pdf.new_path() as p:
        p.style.fill_color = _dev_rgb(rgb)
        p.style.stroke_color = None
        if opacity != 1.0:
            p.style.fill_opacity = opacity
        _chamfer_outline(p, x, y, w, h, c, q, r)


def _stroke_chamfer(pdf, x: float, y: float, w: float, h: float,
                    rgb: tuple[int, int, int], c=None, q=None, r=None,
                    line_w: float = 0.4, opacity: float = 1.0) -> None:
    """Draw an unfilled chamfer-hexagon outline (watermark decoration)."""
    c, q, r = _chamfer_dims(w, h, c, q, r)
    with pdf.new_path() as p:
        p.style.fill_color = None
        p.style.stroke_color = _dev_rgb(rgb)
        p.style.stroke_width = line_w
        if opacity != 1.0:
            p.style.stroke_opacity = opacity
        _chamfer_outline(p, x, y, w, h, c, q, r)


def _hex_cluster(pdf, x: float, y: float, scale: float,
                 rgb: tuple[int, int, int], variant: int = 0,
                 opacity: float = 0.5) -> None:
    """A faint decorative cluster of 2–3 varied chamfer-hexagons (outlines plus
    one filled), bleeding from (x, y). Brand-graphic only — callers place it in
    genuinely empty space, behind content, never over text. `variant` 0/1/2
    picks one of three arrangements so the clusters differ page-to-page."""
    # (dx, dy, size, filled) tuples in `scale` units — three hand-tuned layouts.
    layouts = [
        [(0.0, 0.0, 1.0, False), (0.72, 0.46, 0.62, True), (0.30, 0.92, 0.44, False)],
        [(0.0, 0.30, 0.82, False), (0.58, 0.0, 1.0, False), (0.94, 0.66, 0.5, True)],
        [(0.0, 0.0, 0.7, True), (0.46, 0.36, 1.0, False), (1.04, 0.10, 0.5, False)],
    ]
    for dx, dy, sz, filled in layouts[variant % len(layouts)]:
        s = scale * sz
        bx, by = x + scale * dx, y + scale * dy
        if filled:
            _fill_chamfer(pdf, bx, by, s, s, rgb,
                          c=s * 0.2, q=s * 0.06, r=s * 0.2, opacity=opacity)
        else:
            _stroke_chamfer(pdf, bx, by, s, s, rgb,
                            c=s * 0.2, q=s * 0.06, r=s * 0.2,
                            line_w=max(0.25, s * 0.02), opacity=opacity)


# ──────────────────────────────────────────────────────────────────────────────
# ReportTheme — the pluggable visual-identity interface.
# ──────────────────────────────────────────────────────────────────────────────
# A theme owns every "look" decision. Each hook receives the live _NotePDF
# instance (`pdf`) and draws through it — so it has full access to fpdf
# primitives, the active fonts, page geometry, and the palette tokens on
# pdf.tokens / pdf.ink / pdf.lime / … . Content code (tables, figures, copy)
# never calls these directly; it calls the _NotePDF wrappers which delegate to
# pdf.theme, so swapping the theme swaps the entire identity.
#
# Cross-module note: a couple of hooks need report helpers that live in
# pdf_report.py (the translated footer strings via pdf.t(); the photo cropper).
# These are reached through the `pdf` instance or a deferred import to avoid an
# import cycle (pdf_report imports this module at top level).
class ReportTheme:
    """Base interface. Subclasses implement the chrome hooks. The default
    implementations raise so a partial theme fails loudly rather than silently
    drawing nothing."""

    name = "base"

    def header(self, pdf) -> None:
        raise NotImplementedError

    def footer(self, pdf) -> None:
        raise NotImplementedError

    def eyebrow(self, pdf, x, y, text, color, size=7.0, tracking=0.4,
                w=0.0, align="L") -> None:
        raise NotImplementedError

    def section_title(self, pdf, text) -> None:
        raise NotImplementedError

    def secondary_head(self, pdf, number, kicker, title, min_room=40.0,
                       badge=None, badge_color=None, badge_logo=None) -> None:
        raise NotImplementedError

    def section_divider(self, pdf, number, kicker, heading) -> None:
        raise NotImplementedError

    def subsection(self, pdf, text, min_room=27.0) -> None:
        raise NotImplementedError

    def decorate_void(self, pdf, variant=0, min_gap=44.0) -> None:
        raise NotImplementedError

    def decorate_void_photo(self, pdf, x0, x1, y, floor, gap, filler) -> bool:
        raise NotImplementedError

    # ── cover (summary page) brand graphics ────────────────────────────────
    def cover_masthead(self, pdf, x0, y_m, W, MH) -> None:
        """Draw the cover masthead background panel (the eyebrow / note-name /
        KPI text is drawn on top by the cover builder, in white)."""
        raise NotImplementedError

    def cover_left_void_fill(self, pdf, x0, sc, bottom) -> None:
        """Fill the cover's empty left column (below the rail) when no photo took
        it — a faint brand-graphic composition."""
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────────────────
# HexagonTheme — the CADIEM / "green" design language (the original look, moved
# here verbatim). Chamfer-hexagon mastheads, lime number-chips, hex-cluster
# watermarks. Byte-identity contract: this must reproduce the pre-refactor CADIEM
# output pixel-for-pixel (see scratchpad/golden.py).
# ──────────────────────────────────────────────────────────────────────────────
class HexagonTheme(ReportTheme):
    name = "hexagon"

    # Voids at/above this height read as egregiously empty — fill them with an
    # actual brand photo band rather than only a faint sigil/hex composition.
    EGREGIOUS_VOID = 70.0

    # ── running header / footer ────────────────────────────────────────────
    def header(self, pdf) -> None:
        if pdf._is_cover:
            return

        # ── Firm logo (top-left) — original colour on the white page, sized by
        #    true aspect ratio so a wide wordmark isn't squashed ─────────────
        logo_w = 0.0
        if pdf.firm_logo_bytes:
            try:
                h = 6.0
                w = min(h * pdf.firm_logo_aspect, 46.0)
                pdf.image(io.BytesIO(pdf.firm_logo_bytes),
                          x=pdf.l_margin, y=8, w=w, h=h)
                logo_w = w + 3.0
            except Exception:
                logo_w = 0.0

        # ── Note name (right) ────────────────────────────────────────
        # The firm name is intentionally NOT printed here — the logo alone
        # identifies the firm (printing both is redundant). Keep the note name on
        # the right, vertically centred on the logo's centreline (logo at y=8,
        # height 6 → centre y=11; a 4.5mm cell centres at y = 11 - 4.5/2 = 8.75).
        _row_y = 8.75
        pdf._sf(7, "regular")
        pdf.set_text_color(*pdf.muted)
        pdf.set_xy(pdf.w - pdf.r_margin - 95, _row_y)
        note_label = pdf._safe(pdf.doc_ref.split("|")[-1].strip() if "|" in pdf.doc_ref else pdf.doc_ref)
        pdf.cell(95, 4.5, note_label, align="R")

        # ── 2px primary rule below the header (prototype interior chrome) ──
        pdf.set_draw_color(*pdf.primary_color)
        pdf.set_line_width(0.6)
        pdf.line(pdf.l_margin, 16.5, pdf.w - pdf.r_margin, 16.5)
        pdf.set_text_color(*TEXT)
        pdf.set_y(21)

    def footer(self, pdf) -> None:
        # The cover renders its own self-contained bottom disclaimer band; the
        # running footer (rule + footer_line + page number) would print on top of
        # it, producing the garbled overlap seen at the bottom of page 1. Skip it.
        if pdf._is_cover or pdf.page_no() in pdf._cover_pages:
            return
        # ── Thin rule above footer ────────────────────────────────────
        pdf.set_draw_color(*pdf.rule_soft)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, pdf.h - 22, pdf.w - pdf.r_margin, pdf.h - 22)

        # ── Disclaimer line (branding may override with footer_note) ───
        pdf.set_y(-20)
        pdf._sf(6, "light")
        pdf.set_text_color(*pdf.footnote_grey)
        pdf.multi_cell(0, 2.9, pdf.footer_note or pdf.t("footer_line"), align="L")

        # ── Page number (no generation date — the report carries no visible
        # date; provenance lives only in the PDF metadata) ────────────
        pdf.set_y(-11)
        pdf._sf(6.5, "light")
        pdf.set_text_color(*pdf.footnote_grey)
        _page = pdf.t("page_of")
        _mid  = pdf.t("page_of_mid")
        pdf.cell(0, 4.5, f"{_page} {pdf.page_no()} {_mid} {{nb}}", align="R")
        pdf.set_text_color(*TEXT)

    # ── section heads ──────────────────────────────────────────────────────
    def eyebrow(self, pdf, x, y, text, color, size=7.0, tracking=0.4,
                w=0.0, align="L") -> None:
        """A tracked uppercase label — the design's 'eyebrow'/kicker. Uses the
        BODY font bold (per the reference) and letter-spacing, then resets it."""
        pdf._sf(size, "body_bold")
        pdf.set_text_color(*color)
        try:
            pdf.set_char_spacing(tracking)
        except Exception:
            pass
        pdf.set_xy(x, y)
        pdf.cell(w, size * 0.55, pdf._safe(str(text).upper()), align=align)
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    def section_title(self, pdf, text) -> None:
        """Generic section title — an ink heading over a short lime keyline on a
        soft full-width hairline."""
        if pdf.get_y() > pdf.h - 60:
            pdf.add_page()
        pdf.ln(4)
        pdf._sf(13, "bold")
        pdf.set_text_color(*pdf.ink)
        pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        band_w = pdf.w - pdf.l_margin - pdf.r_margin
        y = pdf.get_y()
        # Soft full-width hairline with a short lime keyline overlaid at the left.
        pdf.set_fill_color(*pdf.rule_soft)
        pdf.rect(pdf.l_margin, y + 0.4, band_w, 0.4, style="F")
        pdf.set_fill_color(*pdf.lime)
        pdf.rect(pdf.l_margin, y, 22, 1.2, style="F")
        pdf.ln(5)
        pdf.set_text_color(*TEXT)

    def secondary_head(self, pdf, number, kicker, title, min_room=40.0,
                       badge=None, badge_color=None, badge_logo=None) -> None:
        """Reference-section secondary head: a lime chamfer number-chip beside a
        green eyebrow kicker over an ink title, on a soft rule."""
        if pdf.page_no() == 0:
            pdf.add_page()
        elif pdf.get_y() > pdf.h - pdf.b_margin - min_room:
            pdf.add_page()
        else:
            pdf.ln(4)
        x0 = pdf.l_margin
        w  = pdf.w - pdf.l_margin - pdf.r_margin
        y0 = pdf.get_y()
        chip = 12.0
        _fill_chamfer(pdf, x0, y0, chip, chip, pdf.lime, c=2.4, q=0.9, r=2.4)
        pdf.set_xy(x0, y0 + 2.6)
        pdf._sf(11, "bold")
        pdf.set_text_color(*pdf.ink)
        pdf.cell(chip, 7, number, align="C")
        tx = x0 + chip + 5
        tw = w - chip - 5
        self.eyebrow(pdf, tx, y0 + 0.5, kicker, pdf.primary_color,
                     size=7.0, tracking=0.5, w=tw)
        # Right-aligned identity: the company logo when available, else a small
        # filled ticker chip.
        if badge_logo:
            try:
                lw = 12.0
                pdf.image(io.BytesIO(badge_logo), x=x0 + w - lw, y=y0, w=lw, h=lw)
                tw -= lw + 3
                badge = None
            except Exception:
                badge_logo = None
        if badge:
            bc = badge_color or pdf.primary_color
            pdf._sf(8, "bold")
            bw = pdf.get_string_width(pdf._safe(badge)) + 5
            pdf.set_fill_color(*bc)
            pdf.rect(x0 + w - bw, y0 + 4.5, bw, 6.5, style="F",
                     round_corners=True, corner_radius=1.4)
            pdf.set_xy(x0 + w - bw, y0 + 5.0)
            pdf.set_text_color(*WHITE)
            pdf.cell(bw, 5.5, pdf._safe(badge), align="C")
            tw -= bw + 3
        pdf.set_xy(tx, y0 + 4.8)
        pdf._fit_font(pdf._safe(title), tw, 15, "bold")
        pdf.set_text_color(*pdf.ink)
        pdf.cell(tw, 7, pdf._safe(title))
        ry = y0 + chip + 2
        pdf.set_fill_color(*pdf.rule_soft)
        pdf.rect(x0, ry, w, 0.4, style="F")
        pdf.set_y(ry + 4)
        pdf.set_text_color(*TEXT)

    def section_divider(self, pdf, number, kicker, heading) -> None:
        """Primary section head for an analytical lens: a full-width dark chamfer
        banner with a big lime section number, a thin divider, a lime eyebrow
        kicker over a white heading, and a faint hex watermark."""
        if pdf.page_no() == 0:
            pdf.add_page()
        elif pdf.get_y() > pdf.t_margin + 2:
            pdf.add_page()
        x0 = pdf.l_margin
        w  = pdf.w - pdf.l_margin - pdf.r_margin
        y0 = pdf.get_y() + 2
        H  = 30.0
        _fill_chamfer(pdf, x0, y0, w, H, pdf.ink, c=4.4, q=1.3, r=3.4)
        # Faint hex watermark, top-right, bleeding toward the banner edge.
        try:
            _var = int(str(number)) % 3
        except ValueError:
            _var = 0
        _hex_cluster(pdf, x0 + w - 30, y0 - 5, 20, WHITE, variant=_var, opacity=0.10)
        # Big lime section number (Neulis), vertically centred.
        pdf.set_xy(x0 + 9, y0 + 9)
        pdf._sf(26, "bold")
        pdf.set_text_color(*pdf.lime)
        pdf.cell(20, 12, str(number), align="L")
        # Thin vertical divider (a muted tint of the ink).
        pdf.set_fill_color(*blend(pdf.ink, WHITE, 0.30))
        pdf.rect(x0 + 31, y0 + 7, 0.5, H - 14, style="F")
        # Lime kicker over the white heading.
        self.eyebrow(pdf, x0 + 37, y0 + 7.5, kicker, pdf.lime,
                     size=7.0, tracking=0.6, w=w - 50)
        pdf.set_xy(x0 + 37, y0 + 12.5)
        pdf._sf(16, "bold")
        pdf.set_text_color(*WHITE)
        pdf.cell(w - 50, 9, pdf._safe(heading))
        pdf.set_y(y0 + H + 6)
        pdf.set_text_color(*TEXT)

    def subsection(self, pdf, text, min_room=27.0) -> None:
        """SemiBold 9pt sub-header."""
        if pdf.get_y() > pdf.h - pdf.b_margin - min_room:
            pdf.add_page()
        pdf.ln(2)
        pdf._sf(9, "semibold")
        pdf.set_text_color(*TEXT)
        pdf.cell(0, 6, text.upper(), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*TEXT)
        pdf.ln(2)

    # ── empty-space decoration ─────────────────────────────────────────────
    def decorate_void(self, pdf, variant=0, min_gap=44.0) -> None:
        """Fill a large empty band before the footer so a short page reads as
        composed. Egregious voids (with a brand photo) get a full-width photo
        band; smaller voids get a faint sigil + hex-cluster composition. Kept
        clear of the footer rule so a graphic never overlaps the footnote."""
        if pdf._is_cover or pdf.page_no() in pdf._cover_pages:
            return
        y = pdf.get_y() + 4.0
        # Hard floor for ALL decoration: a clear margin above the footer rule
        # (drawn at h-22) and its text, so a graphic NEVER overlaps the footnote.
        floor = pdf.h - 28.0
        gap = floor - y
        if gap < min_gap:
            return
        x0 = pdf.l_margin
        x1 = pdf.w - pdf.r_margin
        # Draw from the chosen pool of report images, cycling so each egregious
        # void gets the next image rather than repeating one (falls back to the
        # single cover/back photo when only one image is available).
        pool = getattr(pdf, "filler_image_list", None) or [
            b for b in (getattr(pdf, "cover_image_bytes", None),
                        getattr(pdf, "back_image_bytes", None)) if b]
        if gap >= self.EGREGIOUS_VOID and pool:
            filler = pool[pdf._void_photo_idx % len(pool)]
            if self.decorate_void_photo(pdf, x0, x1, y, floor, gap, filler):
                pdf._void_photo_idx += 1
                return
        # A hex-cluster's lowest shape can reach ~1.4x its scale below the origin
        # (see _hex_cluster layouts) — account for that so it stays above `floor`.
        HEX_VEXT = 1.45
        try:
            # Big sigil watermark — centred in the void, bleeding off the right.
            sig = getattr(pdf, "cover_sigil_bytes", None)
            if sig:
                from PIL import Image
                iw, ih = Image.open(io.BytesIO(sig)).size
                sh = min(gap * 0.92, 150.0)
                sw = sh * iw / ih
                with pdf.local_context(fill_opacity=0.07):
                    pdf.image(io.BytesIO(sig), x=x1 - sw * 0.60,
                              y=y + (gap - sh) / 2.0, w=sw, h=sh)
            # Hex cluster anchored low-left — placed so its FULL extent (incl. the
            # downward overflow) ends at `floor`, never reaching the footnote.
            scale = min(gap / HEX_VEXT, 52.0)
            if scale >= 12:
                _hex_cluster(pdf, x0 - scale * 0.22, floor - scale * HEX_VEXT,
                             scale, pdf.primary_color, variant=variant, opacity=0.13)
            # Tall voids: two small outlined hexes mid-band tie the corners.
            if gap > 120:
                cxm = (x0 + x1) / 2
                _stroke_chamfer(pdf, cxm - 10, y + gap * 0.28, 18, 18,
                                pdf.primary_color, c=3.6, q=1.1, r=3.6,
                                line_w=0.45, opacity=0.11)
                _stroke_chamfer(pdf, cxm + 20, y + gap * 0.28 + 17, 11, 11,
                                pdf.lime, c=2.2, q=0.7, r=2.2,
                                line_w=0.45, opacity=0.18)
        except Exception:
            pass

    def decorate_void_photo(self, pdf, x0, x1, y, floor, gap, filler) -> bool:
        """Render the egregious-void photo band (see decorate_void). Returns True
        on success so the caller can skip the graphic composition."""
        # _cover_crop lives in pdf_report; deferred import avoids an import cycle.
        from pdf_report import _cover_crop
        try:
            pad_top = 13.0                       # breathing room below the content
            band_w = x1 - x0
            band_h = min(gap - pad_top, 104.0)   # a band, not a giant square
            if band_h < 52.0:
                return False
            by = floor - band_h                  # anchored at the floor
            # Shift the crop window per page so a repeated filler photo shows a
            # different region rather than the identical band on consecutive pages.
            _bx = (-0.6, 0.0, 0.6)[pdf.page_no() % 3]
            _by = (0.0, -0.5, 0.5)[(pdf.page_no() // 3) % 3]
            cropped = _cover_crop(filler, band_w / band_h, bias_x=_bx, bias_y=_by) or filler
            # Re-encode the band as JPEG (each page gets a distinct crop, so fpdf2
            # can't dedupe them) — a PNG photo per page would bloat the PDF, JPEG
            # keeps a multi-photo report a few hundred KB instead of multi-MB.
            try:
                from PIL import Image
                _bim = Image.open(io.BytesIO(cropped)).convert("RGB")
                _buf = io.BytesIO(); _bim.save(_buf, "JPEG", quality=78, optimize=True)
                cropped = _buf.getvalue()
            except Exception:
                pass
            pdf.image(io.BytesIO(cropped), x=x0, y=by, w=band_w, h=band_h)
            # Light brand tint so the photo harmonises with the palette without
            # hiding it — this is meant to read as an image, not a colour block.
            tint = getattr(pdf, "cover_overlay_color", pdf.primary_color)
            with pdf.local_context(fill_opacity=0.30):
                pdf.set_fill_color(*tint)
                pdf.rect(x0, by, band_w, band_h, style="F")
            # A darker brand wash along the bottom edge grounds the band and lets
            # the corner sigil read; kept short so the photo stays visible.
            with pdf.local_context(fill_opacity=0.34):
                pdf.set_fill_color(*pdf.ink)
                pdf.rect(x0, floor - 16.0, band_w, 16.0, style="F")
            # Lime accent rule across the top edge — the brand's signature line.
            pdf.set_fill_color(*pdf.lime)
            pdf.rect(x0, by, band_w, 1.5, style="F")
            # White-knockout sigil tucked into the bottom-right corner.
            sig = getattr(pdf, "cover_sigil_bytes", None)
            if sig:
                from PIL import Image
                iw, ih = Image.open(io.BytesIO(sig)).size
                sh = min(band_h * 0.42, 26.0)
                sw = sh * iw / ih
                with pdf.local_context(fill_opacity=0.55):
                    pdf.image(io.BytesIO(sig), x=x1 - sw - 6.0,
                              y=floor - sh - 3.5, w=sw, h=sh)
            return True
        except Exception:
            return False

    # ── cover (summary page) brand graphics ────────────────────────────────
    def cover_masthead(self, pdf, x0, y_m, W, MH) -> None:
        _fill_chamfer(pdf, x0, y_m, W, MH, pdf.ink, c=7.5, q=2.0, r=5.0)
        _hex_cluster(pdf, x0 + W - 42, y_m - 6, 30, WHITE, variant=0, opacity=0.12)

    def cover_left_void_fill(self, pdf, x0, sc, bottom) -> None:
        _hex_cluster(pdf, x0 - sc * 0.2, bottom - sc, sc,
                     pdf.primary_color, variant=1, opacity=0.13)


# ──────────────────────────────────────────────────────────────────────────────
# MercatorTheme — the website-inspired language (the app's own look, translated
# to print). Where the hexagon theme uses chamfers, dark banners and hex-cluster
# watermarks, Mercator is airy and editorial: rounded number-chips, a light
# chapter opener with a big ghosted numeral, thin accent keylines, and generous
# whitespace — no chamfers, no hexagons. Palette-driven like every theme, so the
# brand's own colours flow through it (the app's viridian-on-paper is simply the
# default palette rendered this way).
# ──────────────────────────────────────────────────────────────────────────────
def _accent_weak(pdf):
    """A pale wash of the accent (the app's --accent-weak) for chip/panel fills."""
    return blend(pdf.lime, WHITE, 0.86)


class MercatorTheme(ReportTheme):
    name = "mercator"

    EGREGIOUS_VOID = 70.0

    # ── running header / footer ────────────────────────────────────────────
    def header(self, pdf) -> None:
        if pdf._is_cover:
            return
        # Firm logo (top-left), true aspect ratio.
        if pdf.firm_logo_bytes:
            try:
                h = 6.0
                w = min(h * pdf.firm_logo_aspect, 46.0)
                pdf.image(io.BytesIO(pdf.firm_logo_bytes),
                          x=pdf.l_margin, y=8, w=w, h=h)
            except Exception:
                pass
        # Note name (right), muted.
        pdf._sf(7, "regular")
        pdf.set_text_color(*pdf.muted)
        pdf.set_xy(pdf.w - pdf.r_margin - 95, 8.75)
        note_label = pdf._safe(pdf.doc_ref.split("|")[-1].strip() if "|" in pdf.doc_ref else pdf.doc_ref)
        pdf.cell(95, 4.5, note_label, align="R")
        # A light full-width hairline with a short accent tick at the left — the
        # web's thin-rule chrome, replacing the hexagon theme's heavy primary rule.
        pdf.set_draw_color(*pdf.rule_soft)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, 16.5, pdf.w - pdf.r_margin, 16.5)
        pdf.set_fill_color(*pdf.lime)
        pdf.rect(pdf.l_margin, 16.1, 15, 0.8, style="F", round_corners=True, corner_radius=0.4)
        pdf.set_text_color(*TEXT)
        pdf.set_y(21)

    def footer(self, pdf) -> None:
        if pdf._is_cover or pdf.page_no() in pdf._cover_pages:
            return
        pdf.set_draw_color(*pdf.rule_soft)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, pdf.h - 22, pdf.w - pdf.r_margin, pdf.h - 22)
        pdf.set_y(-20)
        pdf._sf(6, "light")
        pdf.set_text_color(*pdf.footnote_grey)
        pdf.multi_cell(0, 2.9, pdf.footer_note or pdf.t("footer_line"), align="L")
        pdf.set_y(-11)
        pdf._sf(6.5, "light")
        pdf.set_text_color(*pdf.footnote_grey)
        _page = pdf.t("page_of")
        _mid  = pdf.t("page_of_mid")
        pdf.cell(0, 4.5, f"{_page} {pdf.page_no()} {_mid} {{nb}}", align="R")
        pdf.set_text_color(*TEXT)

    # ── section heads ──────────────────────────────────────────────────────
    def eyebrow(self, pdf, x, y, text, color, size=7.0, tracking=0.4,
                w=0.0, align="L") -> None:
        pdf._sf(size, "body_bold")
        pdf.set_text_color(*color)
        try:
            pdf.set_char_spacing(tracking)
        except Exception:
            pass
        pdf.set_xy(x, y)
        pdf.cell(w, size * 0.55, pdf._safe(str(text).upper()), align=align)
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    def section_title(self, pdf, text) -> None:
        """Ink heading under a short accent tab — editorial, no fill block."""
        if pdf.get_y() > pdf.h - 60:
            pdf.add_page()
        pdf.ln(4)
        y0 = pdf.get_y()
        pdf.set_fill_color(*pdf.lime)
        pdf.rect(pdf.l_margin, y0, 9, 1.0, style="F", round_corners=True, corner_radius=0.5)
        pdf.set_y(y0 + 2.4)
        pdf._sf(13, "bold")
        pdf.set_text_color(*pdf.ink)
        pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        band_w = pdf.w - pdf.l_margin - pdf.r_margin
        y = pdf.get_y()
        pdf.set_fill_color(*pdf.rule_soft)
        pdf.rect(pdf.l_margin, y + 0.4, band_w, 0.3, style="F")
        pdf.ln(5)
        pdf.set_text_color(*TEXT)

    def secondary_head(self, pdf, number, kicker, title, min_room=40.0,
                       badge=None, badge_color=None, badge_logo=None) -> None:
        """A rounded number-chip (accent-weak fill, accent numeral) beside a
        kicker over an ink title, on a hairline — the web's card-label look."""
        if pdf.page_no() == 0:
            pdf.add_page()
        elif pdf.get_y() > pdf.h - pdf.b_margin - min_room:
            pdf.add_page()
        else:
            pdf.ln(4)
        x0 = pdf.l_margin
        w  = pdf.w - pdf.l_margin - pdf.r_margin
        y0 = pdf.get_y()
        chip = 12.0
        pdf.set_fill_color(*_accent_weak(pdf))
        pdf.rect(x0, y0, chip, chip, style="F", round_corners=True, corner_radius=2.6)
        pdf.set_xy(x0, y0 + 2.6)
        pdf._sf(11, "bold")
        pdf.set_text_color(*pdf.lime)
        pdf.cell(chip, 7, number, align="C")
        tx = x0 + chip + 5
        tw = w - chip - 5
        self.eyebrow(pdf, tx, y0 + 0.5, kicker, pdf.lime,
                     size=7.0, tracking=0.5, w=tw)
        if badge_logo:
            try:
                lw = 12.0
                pdf.image(io.BytesIO(badge_logo), x=x0 + w - lw, y=y0, w=lw, h=lw)
                tw -= lw + 3
                badge = None
            except Exception:
                badge_logo = None
        if badge:
            bc = badge_color or pdf.primary_color
            pdf._sf(8, "bold")
            bw = pdf.get_string_width(pdf._safe(badge)) + 5
            pdf.set_fill_color(*bc)
            pdf.rect(x0 + w - bw, y0 + 4.5, bw, 6.5, style="F",
                     round_corners=True, corner_radius=1.4)
            pdf.set_xy(x0 + w - bw, y0 + 5.0)
            pdf.set_text_color(*WHITE)
            pdf.cell(bw, 5.5, pdf._safe(badge), align="C")
            tw -= bw + 3
        pdf.set_xy(tx, y0 + 4.8)
        pdf._fit_font(pdf._safe(title), tw, 15, "bold")
        pdf.set_text_color(*pdf.ink)
        pdf.cell(tw, 7, pdf._safe(title))
        ry = y0 + chip + 2
        pdf.set_fill_color(*pdf.rule_soft)
        pdf.rect(x0, ry, w, 0.3, style="F")
        pdf.set_y(ry + 4)
        pdf.set_text_color(*TEXT)

    def section_divider(self, pdf, number, kicker, heading) -> None:
        """A light editorial chapter opener: a big ghosted numeral at the left, a
        kicker over an ink heading, and a thin accent keyline — no dark banner."""
        if pdf.page_no() == 0:
            pdf.add_page()
        elif pdf.get_y() > pdf.t_margin + 2:
            pdf.add_page()
        x0 = pdf.l_margin
        w  = pdf.w - pdf.l_margin - pdf.r_margin
        y0 = pdf.get_y() + 2
        H  = 30.0
        # Big ghosted numeral (pale accent) anchored low-left.
        pdf.set_xy(x0, y0 + 2)
        pdf._sf(34, "bold")
        pdf.set_text_color(*blend(pdf.lime, WHITE, 0.66))
        pdf.cell(26, 20, str(number), align="L")
        # Kicker over heading, to the right of the numeral.
        tx = x0 + 30
        self.eyebrow(pdf, tx, y0 + 4.5, kicker, pdf.lime,
                     size=7.5, tracking=0.6, w=w - 30)
        pdf.set_xy(tx, y0 + 9.5)
        pdf._sf(17, "bold")
        pdf.set_text_color(*pdf.ink)
        pdf.cell(w - 30, 9, pdf._safe(heading))
        # Full-width hairline with a short accent segment at the left.
        ry = y0 + H - 2
        pdf.set_fill_color(*pdf.rule_soft)
        pdf.rect(x0, ry, w, 0.4, style="F")
        pdf.set_fill_color(*pdf.lime)
        pdf.rect(x0, ry - 0.1, 26, 0.9, style="F", round_corners=True, corner_radius=0.4)
        pdf.set_y(y0 + H + 6)
        pdf.set_text_color(*TEXT)

    def subsection(self, pdf, text, min_room=27.0) -> None:
        if pdf.get_y() > pdf.h - pdf.b_margin - min_room:
            pdf.add_page()
        pdf.ln(2)
        pdf._sf(9, "semibold")
        pdf.set_text_color(*TEXT)
        pdf.cell(0, 6, text.upper(), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*TEXT)
        pdf.ln(2)

    # ── empty-space decoration ─────────────────────────────────────────────
    def decorate_void(self, pdf, variant=0, min_gap=44.0) -> None:
        """Airy: an egregious void with a brand photo gets the photo band; smaller
        voids get a faint sigil watermark (if any) and a thin accent keyline —
        never a hex cluster."""
        if pdf._is_cover or pdf.page_no() in pdf._cover_pages:
            return
        y = pdf.get_y() + 4.0
        floor = pdf.h - 28.0
        gap = floor - y
        if gap < min_gap:
            return
        x0 = pdf.l_margin
        x1 = pdf.w - pdf.r_margin
        pool = getattr(pdf, "filler_image_list", None) or [
            b for b in (getattr(pdf, "cover_image_bytes", None),
                        getattr(pdf, "back_image_bytes", None)) if b]
        if gap >= self.EGREGIOUS_VOID and pool:
            filler = pool[pdf._void_photo_idx % len(pool)]
            if self.decorate_void_photo(pdf, x0, x1, y, floor, gap, filler):
                pdf._void_photo_idx += 1
                return
        try:
            # Faint sigil watermark, centred, bleeding off the right (image-based —
            # no hexagons). Then a thin accent keyline low in the void.
            sig = getattr(pdf, "cover_sigil_bytes", None)
            if sig:
                from PIL import Image
                iw, ih = Image.open(io.BytesIO(sig)).size
                sh = min(gap * 0.9, 140.0)
                sw = sh * iw / ih
                with pdf.local_context(fill_opacity=0.05):
                    pdf.image(io.BytesIO(sig), x=x1 - sw * 0.60,
                              y=y + (gap - sh) / 2.0, w=sw, h=sh)
            ry = floor - 10.0
            pdf.set_fill_color(*pdf.rule_soft)
            pdf.rect(x0, ry, x1 - x0, 0.3, style="F")
            pdf.set_fill_color(*pdf.lime)
            pdf.rect(x0, ry - 0.1, 22, 0.8, style="F", round_corners=True, corner_radius=0.4)
        except Exception:
            pass

    def decorate_void_photo(self, pdf, x0, x1, y, floor, gap, filler) -> bool:
        """Photo band (image + brand tint + accent top rule). Shape-neutral."""
        from pdf_report import _cover_crop
        try:
            pad_top = 13.0
            band_w = x1 - x0
            band_h = min(gap - pad_top, 104.0)
            if band_h < 52.0:
                return False
            by = floor - band_h
            _bx = (-0.6, 0.0, 0.6)[pdf.page_no() % 3]
            _by = (0.0, -0.5, 0.5)[(pdf.page_no() // 3) % 3]
            cropped = _cover_crop(filler, band_w / band_h, bias_x=_bx, bias_y=_by) or filler
            try:
                from PIL import Image
                _bim = Image.open(io.BytesIO(cropped)).convert("RGB")
                _buf = io.BytesIO(); _bim.save(_buf, "JPEG", quality=78, optimize=True)
                cropped = _buf.getvalue()
            except Exception:
                pass
            pdf.image(io.BytesIO(cropped), x=x0, y=by, w=band_w, h=band_h)
            tint = getattr(pdf, "cover_overlay_color", pdf.primary_color)
            with pdf.local_context(fill_opacity=0.28):
                pdf.set_fill_color(*tint)
                pdf.rect(x0, by, band_w, band_h, style="F")
            with pdf.local_context(fill_opacity=0.32):
                pdf.set_fill_color(*pdf.ink)
                pdf.rect(x0, floor - 16.0, band_w, 16.0, style="F")
            pdf.set_fill_color(*pdf.lime)
            pdf.rect(x0, by, band_w, 1.2, style="F")
            sig = getattr(pdf, "cover_sigil_bytes", None)
            if sig:
                from PIL import Image
                iw, ih = Image.open(io.BytesIO(sig)).size
                sh = min(band_h * 0.42, 26.0)
                sw = sh * iw / ih
                with pdf.local_context(fill_opacity=0.55):
                    pdf.image(io.BytesIO(sig), x=x1 - sw - 6.0,
                              y=floor - sh - 3.5, w=sw, h=sh)
            return True
        except Exception:
            return False

    # ── cover (summary page) brand graphics ────────────────────────────────
    def cover_masthead(self, pdf, x0, y_m, W, MH) -> None:
        """A rounded dark panel (no chamfer, no hex watermark) with a thin accent
        rule along the bottom edge. White masthead text reads on top as before."""
        pdf.set_fill_color(*pdf.ink)
        pdf.rect(x0, y_m, W, MH, style="F", round_corners=True, corner_radius=3.0)
        pdf.set_fill_color(*pdf.lime)
        pdf.rect(x0 + 4, y_m + MH - 1.6, W - 8, 1.2, style="F",
                 round_corners=True, corner_radius=0.5)

    def cover_left_void_fill(self, pdf, x0, sc, bottom) -> None:
        """Airy fill for the cover's empty left column — a short accent keyline,
        not a hex cluster."""
        ry = bottom - 6.0
        pdf.set_fill_color(*pdf.lime)
        pdf.rect(x0, ry, min(sc, 40.0), 0.9, style="F",
                 round_corners=True, corner_radius=0.4)


# ── theme registry ────────────────────────────────────────────────────────────
# resolve_theme(name) maps branding["report_theme"] to a theme instance. Unknown
# / absent names fall back to DEFAULT_THEME — the website-inspired Mercator look,
# so a generic (un-themed) brand gets the clean airy report. CADIEM opts back into
# the hexagon language via branding["report_theme"] = "cadiem".
DEFAULT_THEME = "mercator"
_THEMES: dict[str, type[ReportTheme]] = {
    "hexagon":  HexagonTheme,
    "cadiem":   HexagonTheme,   # alias — CADIEM's config selects the hexagon look
    "mercator": MercatorTheme,
}


def register_theme(name: str, cls: type[ReportTheme]) -> None:
    _THEMES[name] = cls


def resolve_theme(name: str | None) -> ReportTheme:
    cls = _THEMES.get((name or "").strip().lower()) or _THEMES[DEFAULT_THEME]
    return cls()


def known_themes() -> list[str]:
    return sorted(_THEMES)
