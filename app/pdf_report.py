"""
app/pdf_report.py
-----------------
Institutional-grade PDF report generator for the Structured Note Simulator.

Visual language modelled on sell-side QIS / wealth-management publications:
  - Cover page: full-width brand band with report title in white; note name
    large below; issuer + date in subtitle style; underlyings sidebar with
    logos; "About this report" blurb; TOC.
  - Inner pages: running header (firm name left, note name right) with thin
    rule; section headers in SemiBold with rule below; metric bands; filled-
    header data tables with zebra rows; callout boxes; figure captions.
  - Footer: page N of M, generation datetime, 6pt disclaimer.
  - Typography: IBM Plex Sans (Regular / SemiBold / Bold / Light /
    Italic / Bold Italic) with automatic Helvetica fallback.

Public API (unchanged)
----------------------
generate_pdf_report(terms, results, asset_names, figures, lang,
                    bt_summary, bt_figures, live_data, live_figure,
                    logo_urls, issuer_logo_url, branding=None,
                    logo_tickers=None) -> bytes

Branding dict schema — the single source of truth (all keys optional; unknown
keys warn; malformed hex falls back to the default with a warning):

  {
    "firm_name":             "Acme Capital",      # cover + running header
    "primary_color":         "#003366",           # headers, table fills, panel tint
    "accent_color":          "#00A0DC",           # rules, hero data series, median
    "chart_secondary_color": "#C69426",           # 2nd chart category (default: gold)
    "section_rule_color":    "#00A0DC",           # rule under section titles (default: accent)
    "panel_color":           "#EAF1F8",           # cover sidebar + card fill (default: light primary tint)
    "sidebar_bar_color":     "#003366",           # solid bar atop the cover sidebar (default: primary, = table headers)
    "logo_file":             "branding/acme.png", # local path, repo-root relative (preferred)
    "logo_base64":           "",                  # OR a base64 / data: URI
    "logo_url":              "https://...",        # OR a remote URL (last resort)
    "report_title":          "Structured Note Analytics",  # cover eyebrow + subtitle
    "website":               "www.acme.com",      # cover identity line
    "contact":               "research@acme.com", # cover identity line
    "footer_note":           "...",               # overrides the default footer disclaimer line
    "disclaimer_body":       "..."                # overrides the full "Important Information" body
  }

The text content fields (report_title, footer_note, disclaimer_body) may be EITHER
a plain string (one language, used as-is) OR a per-language dict, e.g.
  "footer_note": {"en": "For information only…", "es": "Solo a título…"}
in which case the report renders the field in its own language and falls back to
the built-in translated default when the requested language is absent (so a
Spanish-only firm disclaimer no longer bleeds into an English report).

Branding affects the PDF only; the React UI theme is set separately in
web/src/index.css + web/src/theme/. Logo resolution order is local file →
base64 → URL (see _load_logo). Chart colours are remapped from the fixed
navy/blue source palette of app/charts.py onto (accent, secondary) with the
green-ramp hue derived from the accent — see _rebrand_figure.
"""

from __future__ import annotations

import io
import re
import base64
import datetime
import urllib.request
import warnings
import numpy as np
from contextvars import ContextVar
from pathlib import Path
from fpdf import FPDF

# An optional interception point for figure rasterisation, called as
# `hook(fig, width, height, primary, accent, secondary)`. Returning bytes short-
# circuits Kaleido; returning None falls through to the normal render. The
# proof/preview endpoint installs one to serve placeholders (fast mode) or to
# memoise real renders (a chart costs ~2s of Chrome IPC, so repeating one across
# previews is the single biggest cost worth avoiding). A real report sets
# nothing. It is a ContextVar rather than a module flag so one caller's preview
# can never strip the charts out of another caller's PDF.

# Visual-identity layer — now lives in the reusable `reportkit` package (the
# theme engine is domain-agnostic). The chamfer primitives are re-exported under
# their original names so existing call sites here are unchanged; the neutral
# tokens are single-sourced from there too.
from reportkit.theme import (  # noqa: E402
    _dev_rgb, _chamfer_outline, _chamfer_dims,
    _fill_chamfer, _stroke_chamfer, _hex_cluster,
    build_tokens, resolve_theme, paint_shape, resolve_color, resolve_watermark,
    blend as _blend,
    AMBER as _AMBER, AMBER_DARK as _AMBER_DARK, MUTED as _MUTED,
    BODY_INK as _BODY_INK, RULE_SOFT as _RULE_SOFT, FOOTNOTE_GREY as _FOOTNOTE_GREY,
    TEXT as _TEXT, TEXT_SOFT as _TEXT_SOFT, ROW_ALT as _ROW_ALT,
    WHITE as _WHITE, BLACK as _BLACK,
)
from reportkit.images import _cover_crop  # noqa: E402
# Colour parsing / palette remapping — core (no plotly); the chart layer that
# consumes them is what moves behind the [charts] extra, not these.
import reportkit.images as _rk_images  # noqa: E402
import reportkit.charts as _rk_charts  # noqa: E402
import reportkit.fonts as _rk_fonts  # noqa: E402
import reportkit.branding as _rk_branding  # noqa: E402
from reportkit.document import ReportDocument  # noqa: E402
from reportkit.text import _safe, _EMOJI_STRIP  # noqa: E402,F401
from reportkit.color import (  # noqa: E402
    rgb_to_hue as _rgb_to_hue, parse_rgb as _parse_rgb, remap_color as _remap_color,
)

_REPO_ROOT       = Path(__file__).parent.parent

# Ceiling on any single image the report embeds — see reportkit.images
# .dimensions_sane(), which enforces it from the header. ~4900x4900 is far past
# any real cover or logo. `configure_limits` also raises Pillow's own
# MAX_IMAGE_PIXELS as a backstop for decodes that bypass our check; reportkit
# does NOT do that at import time, because a library mutating another library's
# global behind the host's back is exactly the kind of surprise this extraction
# is meant to remove. The application opts in, here, once.
_MAX_IMAGE_PX = _rk_images.MAX_IMAGE_PX
_rk_images.configure_limits(_MAX_IMAGE_PX)
_TICKER_LOGO_DIR = _REPO_ROOT / "branding" / "ticker_logos"
_FONT_DIR        = _REPO_ROOT / "fonts"
_IBM_REGULAR     = _FONT_DIR / "IBMPlexSans-Regular.ttf"
_IBM_BOLD        = _FONT_DIR / "IBMPlexSans-Bold.ttf"
_IBM_SEMIBOLD    = _FONT_DIR / "IBMPlexSans-SemiBold.ttf"
_IBM_LIGHT       = _FONT_DIR / "IBMPlexSans-Light.ttf"
_IBM_ITALIC      = _FONT_DIR / "IBMPlexSans-Italic.ttf"
_IBM_BOLDITALIC  = _FONT_DIR / "IBMPlexSans-BoldItalic.ttf"

# ──────────────────────────────────────────────────────────────────────────────
# Default palette — institutional deep-navy / mid-blue / warm-grey
# ──────────────────────────────────────────────────────────────────────────────
_DEFAULT_PRIMARY  = (26,  46, 74)   # deep navy  #1a2e4a
_DEFAULT_ACCENT   = (37,  99, 235)  # mid-blue   #2563eb
_DEFAULT_SECONDARY = (198, 148, 38) # warm institutional gold #C69426 — 2nd chart category

# ──────────────────────────────────────────────────────────────────────────────
# Mercator/CADIEM green design language — palette-driven tokens
# ──────────────────────────────────────────────────────────────────────────────
# The design derives every identity colour from the brand palette so ANY brand
# inherits its theme's layout in its own colours. The per-instance tokens are
# computed by pdf_theme.build_tokens() from the resolved palette (see
# _NotePDF.__init__). The brand-neutral constants the design shares live in
# pdf_theme.py and are imported at the top of this module (_AMBER, _AMBER_DARK,
# _MUTED, _BODY_INK, _RULE_SOFT, _FOOTNOTE_GREY).

# The full branding schema. Anything outside this set warns (mirrors
# NoteTerms.from_dict) so a typo like "primary_colour" surfaces immediately
# instead of being silently ignored.
# Brand-config resolution lives in reportkit.branding. Two things stay here
# because they are ours, not a library's: the note-specific config keys, and the
# default firm name that reaches the running header.
_NOTE_BRANDING_KEYS = {
    "cover_metrics",       # which key-TERM chips the cover footer band shows
    "underlying_labels",   # "ticker" (default) or "name" for the underlying sub-lines
}
_DEFAULT_FIRM_NAME = "Structured Note Analytics"

_hex_to_rgb     = _rk_branding.hex_to_rgb
_brand_text     = _rk_branding.brand_text
_branding_color = _rk_branding.branding_color
_DEFAULT_PRIMARY   = _rk_branding.DEFAULT_PRIMARY
_DEFAULT_ACCENT    = _rk_branding.DEFAULT_ACCENT
_DEFAULT_SECONDARY = _rk_branding.DEFAULT_SECONDARY


def _validate_branding(branding: dict | None) -> None:
    return _rk_branding.validate_branding(branding, extra_keys=_NOTE_BRANDING_KEYS)


def _resolve_palette(branding: dict | None):
    return _rk_branding.resolve_palette(branding, default_firm_name=_DEFAULT_FIRM_NAME)


# ──────────────────────────────────────────────────────────────────────────────
# Translations
# ──────────────────────────────────────────────────────────────────────────────
_LABELS: dict[str, dict[str, str]] = {
    "series_title":          {"en": "Structured Note Analytics",         "es": "Análisis de Nota Estructurada"},
    "report_eyebrow":        {"en": "STRUCTURED NOTE",                   "es": "NOTA ESTRUCTURADA"},
    # Report-type subtitle on the cover — keyed by the audience preset the report
    # was built for (see ReportRequest.report_kind). An unknown/absent kind draws
    # no subtitle at all.
    "kind_full":             {"en": "Full report",                       "es": "Informe completo"},
    "kind_advisor":          {"en": "Advisory report",                   "es": "Informe comercial"},
    "kind_client":           {"en": "Client report",                     "es": "Informe para el cliente"},
    "kind_ic":               {"en": "Investment committee report",       "es": "Informe para el comité de inversiones"},
    "kind_risk":             {"en": "Risk report",                       "es": "Informe de riesgos"},
    "generated":             {"en": "Publication date",                  "es": "Fecha de publicación"},
    "underlyings":           {"en": "UNDERLYINGS",                       "es": "SUBYACENTES"},
    "key_terms":             {"en": "KEY TERMS",                         "es": "TÉRMINOS CLAVE"},
    "exec_summary":          {"en": "Executive Summary",                 "es": "Resumen Ejecutivo"},
    "note_terms":            {"en": "Note Terms",                        "es": "Términos de la Nota"},
    "key_terms_col_characteristic": {"en": "Characteristic",              "es": "Característica"},
    "key_terms_col_description":    {"en": "Description",                 "es": "Descripción"},
    "issuer_info":           {"en": "Issuer Information",                 "es": "Información del Emisor"},
    "rating_sp":             {"en": "S&P",                               "es": "S&P"},
    "rating_moody":          {"en": "Moody's",                           "es": "Moody's"},
    "rating_fitch":          {"en": "Fitch",                             "es": "Fitch"},
    "obs_schedule":          {"en": "Observation Schedule",              "es": "Calendario de Observaciones"},
    "note_diagram":          {"en": "Structure Diagram",                 "es": "Diagrama de la Estructura"},
    "note_desc_title":       {"en": "Note Description",                  "es": "Descripción de la Nota"},
    "diag_autocall":         {"en": "Autocall",                          "es": "Autocall"},
    "diag_coupon":           {"en": "Coupon",                            "es": "Cupón"},
    "diag_knockin":          {"en": "Knock-in",                          "es": "Knock-in"},
    "diag_onestar":          {"en": "One-Star",                          "es": "One-Star"},
    "diag_issue":            {"en": "issue",                             "es": "emisión"},
    "diag_maturity":         {"en": "maturity",                          "es": "venc."},
    "diag_window":           {"en": "Autocall window",                   "es": "Ventana de autocancelación"},
    "diag_zone_protected":   {"en": "Capital protected",                 "es": "Capital protegido"},
    "diag_zone_atrisk":      {"en": "Capital at risk",                   "es": "Capital en riesgo"},
    "diag_axis_level":       {"en": "Worst-of level",                    "es": "Nivel del peor de"},
    "pp_x_axis":             {"en": "Final basket level (% of initial)", "es": "Nivel final de la cesta (% del inicial)"},
    "pp_x_axis_period":      {"en": "Period-end level (% of period start)", "es": "Nivel al cierre del período (% del inicio del período)"},
    "pp_y_axis":             {"en": "Redemption (% of notional)",        "es": "Redención (% del nominal)"},
    "pp_cliquet_badge":      {"en": "Cliquet · resets each period",      "es": "Cliquet · reinicia cada período"},
    "pp_periodic_caption":   {"en": "Payoff of a single period — paid each reset, then the strike resets.",
                              "es": "Pago de un solo período — se paga en cada reinicio y luego el strike se reinicia."},
    "sim_summary":           {"en": "Monte Carlo Simulation",            "es": "Simulación Monte Carlo"},
    "model_box_title":       {"en": "Model & Methodology",               "es": "Modelo y Metodología"},
    "model_box_body":        {
        "en": "Multi-asset Heston stochastic-volatility model calibrated on "
              "dividend-adjusted (total-return) closes; drift, variance and "
              "correlation blocks estimated by method of moments. Simulation "
              "runs on a real trading-day grid; predictable dividend ex-date "
              "drops are applied as deterministic jumps so barrier levels are "
              "observed on price (not total-return) paths. Antithetic "
              "variates; Student-t copula for joint tail dependence. The "
              "payoff engine is shared between simulation and historical "
              "backtest.",
        "es": "Modelo Heston multi-activo de volatilidad estocástica calibrado "
              "sobre cierres ajustados por dividendos (retorno total); deriva, "
              "varianza y correlaciones estimadas por método de momentos. La "
              "simulación corre sobre un calendario real de días hábiles; las "
              "caídas previsibles por ex-dividendo se aplican como saltos "
              "deterministas, de modo que las barreras se observan sobre "
              "precios (no retorno total). Variables antitéticas; cópula "
              "t-Student para dependencia de colas. El motor de pagos es "
              "compartido entre simulación y backtest histórico.",
    },
    "calibration":           {"en": "Model Calibration",                 "es": "Calibración del Modelo"},
    "backtest":              {"en": "Historical Backtest",               "es": "Backtest Histórico"},
    "live":                  {"en": "Current Performance",               "es": "Rendimiento Actual"},
    "glossary_title":        {"en": "Glossary of Terms",                 "es": "Glosario de Términos"},
    "disclaimer_title":      {"en": "Disclaimer",                        "es": "Aviso legal"},
    "maturity":              {"en": "Maturity",                          "es": "Vencimiento"},
    "freq":                  {"en": "Payment frequency",                 "es": "Frecuencia de pago"},
    "coupon_pa":             {"en": "Coupon p.a.",                       "es": "Cupón anual"},
    "coupon_barrier":        {"en": "Coupon barrier",                    "es": "Barrera de cupón"},
    "autocall_barrier":      {"en": "Autocall barrier",                  "es": "Barrera de autocall"},
    "autocall_start":        {"en": "First autocall observation",        "es": "Primera observación autocall"},
    "ki_barrier":            {"en": "Knock-in barrier (European)",       "es": "Barrera knock-in (europea)"},
    "memory":                {"en": "Memory coupon",                     "es": "Cupón con memoria"},
    "coupon_basket":         {"en": "Coupon rule",                       "es": "Regla del cupón"},
    "autocall_basket":       {"en": "Autocall rule",                     "es": "Regla del autocall"},
    "one_star":              {"en": "One Star feature",                  "es": "Función One Star"},
    "one_star_level":        {"en": "One Star level",                    "es": "Nivel One Star"},
    "ac_step_down":          {"en": "Autocall step-down / period",       "es": "Reducción de barrera / período"},
    "ac_floor":              {"en": "Autocall barrier floor",            "es": "Suelo de barrera autocall"},
    "premium_at_call":       {"en": "Premium paid only at autocall",     "es": "Prima pagada solo al autocall"},
    "issue_date":            {"en": "Issue date",                        "es": "Fecha de emisión"},
    "settlement_date":       {"en": "Settlement date",                   "es": "Fecha de liquidación"},
    "purchase_price":        {"en": "Purchase price",                    "es": "Precio de compra"},
    "accrued_at_purchase":   {"en": "Accrued at purchase",               "es": "Cupón corrido"},
    "cost_basis":            {"en": "Cost basis",                        "es": "Coste de la posición"},
    # P(negative return ON COST) — distinct from P(knock-in), since coupons can
    # carry a knocked-in path back into profit and a discount can rescue a
    # below-par redemption. Only the A/B comparison table quotes it, which is why
    # a missing entry went unnoticed: it printed the raw key "p_loss" as a label.
    "p_loss":                {"en": "P(loss on cost)",                   "es": "P(pérdida sobre coste)"},
    "seasoned":              {"en": "Modelled horizon",                  "es": "Horizonte modelado"},
    "seasoned_row":          {"en": "Remaining life only",               "es": "Solo la vida restante"},
    "issuer":                {"en": "Issuer",                            "es": "Emisor"},
    "expected_irr":          {"en": "Expected IRR p.a.",                 "es": "TIR esperada anual"},
    "expected_total_return": {"en": "Expected total return",             "es": "Retorno total esperado"},
    "expected_redemption":   {"en": "Expected redemption",               "es": "Redención esperada"},
    "p_below_par":           {"en": "P(below par)",                      "es": "P(bajo la par)"},
    "p_above_par":           {"en": "P(above par)",                      "es": "P(sobre la par)"},
    "p_at_cap":              {"en": "P(at cap)",                         "es": "P(en el tope)"},
    "p_knocked_out":         {"en": "P(knocked out)",                    "es": "P(knock-out)"},
    "p5_redemption":         {"en": "5th-pctile redemption",             "es": "Redención pct. 5"},
    "fig_redemption":        {"en": "Redemption distribution",           "es": "Distribución de redención"},
    "total_return_short":    {"en": "Total return",                      "es": "Retorno total"},
    "in_this_report":        {"en": "In this report",                    "es": "En este informe"},
    "mean_hist_irr":         {"en": "Mean historical IRR",               "es": "TIR media histórica"},
    "payoff_scenarios":      {"en": "Payoff scenarios",                  "es": "Escenarios de pago"},
    "payoff_prob":           {"en": "Probability",                       "es": "Probabilidad"},
    "payoff_irr":            {"en": "IRR p.a.",                          "es": "TIR anual"},
    "outcome_autocalled":    {"en": "Autocalled",                        "es": "Autocancelado"},
    "outcome_held":          {"en": "Held to maturity",                  "es": "Mantenido al venc."},
    "outcome_loss":          {"en": "Capital loss",                      "es": "Pérdida de capital"},
    # ── Participation notes (payoff = redemption profile, no coupons/autocall) ──
    "redemption_outcomes":   {"en": "Redemption outcomes",               "es": "Resultados de redención"},
    "outcome_above_par":     {"en": "Redeemed above par",                "es": "Redime sobre la par"},
    "outcome_at_par":        {"en": "Capital returned (par)",            "es": "Capital devuelto (par)"},
    "outcome_below_par":     {"en": "Capital loss (below par)",          "es": "Pérdida de capital (bajo par)"},
    "protection_level":      {"en": "Protection level",                  "es": "Nivel de protección"},
    "participation_rate":    {"en": "Participation rate",                "es": "Tasa de participación"},
    "participation_strike":  {"en": "Strike",                            "es": "Strike"},
    "upside_cap":            {"en": "Upside cap",                        "es": "Tope al alza"},
    "period_cap":            {"en": "Per-period cap",                    "es": "Tope por período"},
    "participation_profile": {"en": "Payoff profile",                    "es": "Perfil de pago"},
    "participation_basket_lbl": {"en": "Basket",                         "es": "Cesta"},
    "downside_style":        {"en": "Downside",                          "es": "A la baja"},
    "upside_style":          {"en": "Upside",                            "es": "Al alza"},
    "digital_payout":        {"en": "Digital payout",                    "es": "Pago digital"},
    "knockout_level":        {"en": "Knock-out level",                   "es": "Nivel de knock-out"},
    "knockout_rebate":       {"en": "Knock-out redemption",              "es": "Redención de knock-out"},
    "grp_cliquet":           {"en": "Cliquet",                           "es": "Cliquet"},
    "pd_full":               {"en": "Full protection",                   "es": "Protección total"},
    "pd_buffer":             {"en": "Buffer",                            "es": "Colchón (buffer)"},
    "pd_airbag":             {"en": "Airbag",                            "es": "Airbag"},
    "pd_bear":               {"en": "Bear participation",                "es": "Participación bajista"},
    "pu_linear":             {"en": "Linear",                            "es": "Lineal"},
    "pu_digital":            {"en": "Digital",                           "es": "Digital"},
    "pu_shark_fin":          {"en": "Shark fin",                         "es": "Aleta de tiburón"},
    "expected_coupon":       {"en": "Expected coupon income",            "es": "Cupón total esperado"},
    "expected_gain":         {"en": "Expected gain",                     "es": "Ganancia esperada"},
    "prob_autocall":         {"en": "P(autocall)",                       "es": "P(autocall)"},
    "avg_time_autocall":     {"en": "Avg. time to call",                 "es": "T. medio a autocall"},
    "prob_knock_in":         {"en": "P(knock-in)",                       "es": "P(knock-in)"},
    "loss_given_ki":         {"en": "Loss given knock-in",               "es": "Pérdida dado knock-in"},
    "n_paths":               {"en": "Simulated paths",                   "es": "Caminos simulados"},
    "autocall_by_period":    {"en": "Autocall Probability by Period",    "es": "Probabilidad de Autocall por Período"},
    "fig_outcome":           {"en": "Outcome breakdown",                 "es": "Distribución de resultados"},
    "fig_sample":            {"en": "Sample worst-of paths",             "es": "Muestra de trayectorias del peor de"},
    "period":                {"en": "Period",                            "es": "Período"},
    "time_y":                {"en": "Time (mo)",                         "es": "Tiempo (m)"},
    "p_autocall":            {"en": "P(autocall)",                       "es": "P(autocall)"},
    "ac_level":              {"en": "Barrier",                           "es": "Barrera"},
    "eligible":              {"en": "Eligible",                          "es": "Elegible"},
    "yes":                   {"en": "Yes",                               "es": "Sí"},
    "no":                    {"en": "No",                                "es": "No"},
    "fig_irr":               {"en": "Distribution of simple annualised IRR across simulated paths",
                              "es": "Distribución de TIR anual simple en los caminos simulados"},
    "fig_wof":               {"en": "Worst-of performance fan with barrier levels",
                              "es": "Abanico worst-of con niveles de barrera"},
    "fig_wof_part":          {"en": "Basket performance fan (percentile bands)",
                              "es": "Abanico de rendimiento de la cesta (bandas percentiles)"},
    "fig_corr":              {"en": "Calibrated return correlation matrix",
                              "es": "Matriz de correlaciones de retorno calibrada"},
    "fig_bt_outcome":        {"en": "Distribution of historical outcomes by issue date",
                              "es": "Distribución de resultados históricos por fecha de emisión"},
    "fig_bt_irr":            {"en": "Realised simple annualised IRR by historical issue date",
                              "es": "TIR anual simple realizada por fecha de emisión histórica"},
    "fig_live":              {"en": "Underlying performance since issue date with observation outcomes",
                              "es": "Rendimiento de los subyacentes desde emisión con resultados de observación"},
    # Three-lens part dividers — the report is one note seen through three
    # lenses (forward-looking model → realised history → live today). Each lens
    # opens with a part divider carrying its number, name and the question it
    # answers; the sub-section titles below drop the lens prefix to avoid echoing
    # the divider (the grouped table of contents re-attaches the lens).
    "lens_mc":               {"en": "Monte Carlo",                  "es": "Monte Carlo"},
    "lens_bt":               {"en": "Historical Backtest",          "es": "Backtest Histórico"},
    "lens_live":             {"en": "Current Performance",          "es": "Rendimiento Actual"},
    "lens_q_mc":             {"en": "What could happen?",           "es": "¿Qué podría pasar?"},
    "lens_q_bt":             {"en": "What would have happened?",    "es": "¿Qué habría pasado?"},
    "lens_q_live":           {"en": "What is happening now?",       "es": "¿Qué está pasando ahora?"},
    # Institutional section headings for the analytical-lens primary banners
    # (the prototype uses statements, not questions — see section_divider).
    "sec_mc_heading":        {"en": "Projected Outcomes",           "es": "Resultados Proyectados"},
    "sec_bt_heading":        {"en": "Realised Outcomes",            "es": "Resultados Históricos"},
    "sec_live_heading":      {"en": "Position to Date",             "es": "Posición a la Fecha"},
    # A/B comparison lens
    "lens_compare":          {"en": "Comparison",                   "es": "Comparación"},
    "sec_compare_heading":   {"en": "Note A vs Note B",             "es": "Nota A vs Nota B"},
    "cmp_terms_title":       {"en": "Terms — A vs B",               "es": "Términos — A vs B"},
    "cmp_metrics_title":     {"en": "Projected metrics — A vs B",   "es": "Métricas proyectadas — A vs B"},
    "cmp_col_metric":        {"en": "Metric",                       "es": "Métrica"},
    "cmp_col_term":          {"en": "Term",                         "es": "Término"},
    "cmp_col_a":             {"en": "Note A",                       "es": "Nota A"},
    "cmp_col_b":             {"en": "Note B",                       "es": "Nota B"},
    "cmp_col_delta":         {"en": "Δ (B − A)",                    "es": "Δ (B − A)"},
    "cmp_fig_irr":           {"en": "IRR p.a. distribution — A vs B",
                             "es": "Distribución de TIR anual — A vs B"},
    "cmp_fig_outcome":       {"en": "Outcome / redemption — A vs B",
                             "es": "Resultado / reembolso — A vs B"},
    "cmp_shared_note":       {"en": "Both notes priced on one shared simulation — differences are pure term effects.",
                             "es": "Ambas notas valoradas sobre una simulación compartida — las diferencias son efecto puro de los términos."},
    "cmp_indep_note":        {"en": "Different underlyings or maturity — priced on independent simulations.",
                             "es": "Subyacentes o vencimiento distintos — valoradas en simulaciones independientes."},
    # Eyebrow kickers for the reference-section secondary heads.
    "kick_note_terms":       {"en": "NOTE TERMS",                   "es": "TÉRMINOS DE LA NOTA"},
    "nt_page_title":         {"en": "Terms & Structure",            "es": "Términos y Estructura"},
    "kick_issuer":           {"en": "ISSUER",                       "es": "EMISOR"},
    "kick_underlying":       {"en": "UNDERLYING",                   "es": "SUBYACENTE"},
    # Section titles for the per-subtab analyses (mirror the dashboard tabs).
    # Prefix-free: they sit under their lens divider, which names the lens.
    "mc_subtab_payoff":      {"en": "Payoff & Distribution",
                              "es": "Payoff y Distribución"},
    "mc_subtab_paths":       {"en": "Price Paths",
                              "es": "Trayectorias de Precio"},
    "mc_subtab_explorer":    {"en": "Path Explorer",
                              "es": "Explorador de Trayectorias"},
    "bt_subtab_outcomes":    {"en": "Outcomes & Summary",
                              "es": "Resultados y Resumen"},
    "bt_subtab_prices":      {"en": "Price History",
                              "es": "Histórico de Precios"},
    "bt_subtab_explorer":    {"en": "Path Explorer",
                              "es": "Explorador de Trayectorias"},
    # Captions for the newly-includable figures
    "fig_individual":        {"en": "Simulated price distribution — {name}",
                              "es": "Distribución simulada de precios — {name}"},
    "fig_single_price":      {"en": "Simulated asset price paths — path #{n}",
                              "es": "Trayectorias de precio simuladas — camino #{n}"},
    "fig_single_wof":        {"en": "Worst-of performance with barriers — path #{n}",
                              "es": "Rendimiento worst-of con barreras — camino #{n}"},
    "fig_bt_pie":            {"en": "Worst-performing asset at the end of each backtest window",
                              "es": "Activo con peor desempeño al final de cada ventana de backtest"},
    "fig_bt_prices":         {"en": "Underlying price history over the backtest window",
                              "es": "Histórico de precios de los subyacentes en la ventana de backtest"},
    "fig_bt_path":           {"en": "Historical worst-of path — issue {issue}",
                              "es": "Trayectoria worst-of histórica — emisión {issue}"},
    "src_mc":                {"en": "Source: Heston Monte Carlo simulation",
                              "es": "Fuente: simulación Monte Carlo Heston"},
    "src_hist":              {"en": "Source: Yahoo Finance daily closing prices",
                              "es": "Fuente: precios de cierre diarios de Yahoo Finance"},
    "asset":                 {"en": "Asset",                             "es": "Activo"},
    "feller":                {"en": "Feller",                            "es": "Feller"},
    "bt_n_issues":           {"en": "Issue dates tested",                "es": "Fechas de emisión probadas"},
    "bt_mean_irr":           {"en": "Mean IRR p.a.",                     "es": "TIR media anual"},
    "bt_median_irr":         {"en": "Median IRR p.a.",                   "es": "TIR mediana anual"},
    "bt_knock_in_pct":       {"en": "Knock-in rate",                     "es": "Tasa de knock-in"},
    "bt_autocalled_pct":     {"en": "Autocall rate",                     "es": "Tasa de autocall"},
    "bt_loss_given_ki":      {"en": "IRR if knocked in",                 "es": "TIR si knock-in"},
    "live_wof_today":        {"en": "Worst-of today",                    "es": "Worst-of hoy"},
    "live_worst_asset":      {"en": "Worst asset",                       "es": "Peor activo"},
    "live_irr_to_date":      {"en": "Coupon IRR to date (ann.)",         "es": "TIR de cupones a fecha (anual)"},
    "live_elapsed":          {"en": "Elapsed (months)",                  "es": "Transcurrido (meses)"},
    "live_asset_perf":       {"en": "Current Asset Performance",         "es": "Rendimiento Actual por Activo"},
    "live_obs_history":      {"en": "Observation History",               "es": "Historial de Observaciones"},
    "performance":           {"en": "Performance",                       "es": "Rendimiento"},
    # ── Underlying Breakdown section ──
    "underlying_breakdown":  {"en": "Underlying Breakdown",              "es": "Análisis por Subyacente"},
    "u_market_cap":          {"en": "Market cap",                        "es": "Capitalización"},
    "u_iv_3m":               {"en": "3M ATM implied vol",                "es": "Vol. implícita ATM 3M"},
    "u_vol_3m_realized":     {"en": "3M realized vol",                   "es": "Vol. realizada 3M"},
    "u_last_price":          {"en": "Last price",                        "es": "Último precio"},
    "u_rsi":                 {"en": "RSI (14)",                          "es": "RSI (14)"},
    "u_sector":              {"en": "Sector",                            "es": "Sector"},
    "u_type":                {"en": "Type",                              "es": "Tipo"},
    "u_analyst":             {"en": "Analyst consensus",                 "es": "Consenso de analistas"},
    "sent_buy":              {"en": "Buy",                               "es": "Comprar"},
    "sent_hold":             {"en": "Hold",                              "es": "Mantener"},
    "sent_sell":             {"en": "Sell",                              "es": "Vender"},
    "fig_u_price":           {"en": "Trailing 12-month price — {name}",
                              "es": "Precio últimos 12 meses — {name}"},
    # Inline fragments that get interpolated into f-strings — kept here so the
    # whole report (not just the standalone labels) translates.
    "page_of":               {"en": "Page",                              "es": "Página"},
    "page_of_mid":           {"en": "of",                                "es": "de"},
    "paths_word":            {"en": "paths",                             "es": "caminos"},
    "observations_word":     {"en": "observations",                      "es": "observaciones"},
    "per_period":            {"en": "per period",                        "es": "por período"},
    "pa_short":              {"en": "p.a.",                              "es": "anual"},
    "guaranteed_zero":       {"en": "Guaranteed (0%)",                   "es": "Garantizado (0%)"},
    "about_report_head":     {"en": "About this report",                 "es": "Acerca de este informe"},
    "calib_s0":              {"en": "S0",                                "es": "S0"},
    "calib_mu":              {"en": "mu p.a.",                           "es": "mu anual"},
    "calib_v0":              {"en": "Vol (V0)",                          "es": "Vol (V0)"},
    "calib_theta":           {"en": "Vol (theta)",                       "es": "Vol (theta)"},
    "figure_word":           {"en": "Figure",                            "es": "Figura"},
    "about_this_report": {
        "en": "This report presents a quantitative analysis of the structured note's expected "
              "performance under a multi-asset Heston stochastic-volatility model. It covers "
              "Monte Carlo simulation results, model calibration, and where applicable, a "
              "historical backtest and live tracking of the current note.",
        "es": "Este informe presenta un análisis cuantitativo del rendimiento esperado de la nota "
              "estructurada bajo un modelo de volatilidad estocástica Heston multi-activo. Incluye "
              "resultados de simulación Monte Carlo, calibración del modelo y, cuando corresponde, "
              "un backtest histórico y seguimiento en tiempo real de la nota.",
    },
    "footer_line": {
        "en": "For information only. Output of an automated quantitative simulation — not investment advice, an offer, or a solicitation.",
        "es": "Solo a título informativo. Resultado de una simulación cuantitativa automatizada — no es asesoramiento ni oferta de inversión.",
    },
    "cover_topline": {
        "en": "This document was generated by an automated quantitative simulation tool and has not been reviewed by any research department. "
              "Refer to the Important Information section at the end of this document.",
        "es": "Este documento fue generado por una herramienta automatizada de simulación cuantitativa y no ha sido revisado por ningún departamento de análisis. "
              "Consulte la sección de Información Importante al final del documento.",
    },
    "disclaimer_body": {
        "en": "This report is the output of an automated quantitative simulation tool and is provided for information purposes only. "
              "It does not constitute investment research, investment advice, a recommendation, an offer to sell or a solicitation of an "
              "offer to buy any security or financial instrument.\n\n"
              "Simulated performance is based on a Heston stochastic-volatility model calibrated to historical market data. Model "
              "parameters, correlations and dividend forecasts are estimates and may differ materially from realised market behaviour. "
              "Simulated and backtested results are hypothetical, do not reflect actual trading, and are not a reliable indicator of "
              "future results. Historical backtest windows overlap and the resulting statistics are autocorrelated.\n\n"
              "Structured notes are complex instruments that may result in the loss of some or all of the capital invested. Payments "
              "depend on the creditworthiness of the issuer. Barrier observation levels, dates and payoff mechanics are simplified "
              "representations of the relevant term sheet; in case of any discrepancy the official offering documentation prevails.\n\n"
              "Market data sourced from Yahoo Finance and may be delayed, incomplete or inaccurate. No representation or warranty, "
              "express or implied, is made as to the accuracy or completeness of the information contained herein.",
        "es": "Este informe es el resultado de una herramienta automatizada de simulación cuantitativa y se proporciona únicamente con "
              "fines informativos. No constituye análisis financiero, asesoramiento de inversión, una recomendación, una oferta de venta "
              "ni una solicitud de compra de ningún valor o instrumento financiero.\n\n"
              "El rendimiento simulado se basa en un modelo de volatilidad estocástica de Heston calibrado con datos históricos de "
              "mercado. Los parámetros del modelo, las correlaciones y las previsiones de dividendos son estimaciones y pueden diferir "
              "materialmente del comportamiento realizado del mercado. Los resultados simulados y de backtest son hipotéticos, no "
              "reflejan operaciones reales y no son un indicador fiable de resultados futuros. Las ventanas del backtest histórico se "
              "solapan y las estadísticas resultantes están autocorrelacionadas.\n\n"
              "Las notas estructuradas son instrumentos complejos que pueden conllevar la pérdida parcial o total del capital invertido. "
              "Los pagos dependen de la solvencia del emisor. Los niveles de barrera, fechas y mecánica de pagos son representaciones "
              "simplificadas del term sheet correspondiente; en caso de discrepancia prevalece la documentación oficial de la emisión.\n\n"
              "Datos de mercado procedentes de Yahoo Finance, que pueden estar retrasados, incompletos o ser inexactos. No se ofrece "
              "ninguna garantía, expresa o implícita, sobre la exactitud o integridad de la información aquí contenida.",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Glossary — relevant financial terms, rendered near the end of every report.
# Each entry is (term, definition); kept here so both languages stay in sync.
# ──────────────────────────────────────────────────────────────────────────────
_GLOSSARY: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("Autocallable note", "A structured note that redeems early ('autocalls') if the underlyings are at or above the autocall barrier on a scheduled observation date."),
        ("Autocall barrier", "The level the reference performance must reach on an observation date to trigger early redemption at par."),
        ("Autocall observation", "A scheduled date on which the autocall and coupon conditions are tested; the first eligible date may be later than the first coupon date."),
        ("Coupon (p.a.)", "Periodic income, quoted as an annualised rate; the per-period amount is the annual rate divided by the number of observations per year."),
        ("Coupon barrier", "The performance level at or above which a coupon is paid on an observation date. A barrier of 0% means the coupon is guaranteed."),
        ("Memory coupon", "Coupons missed because the barrier was not met accumulate and are paid in full on the next date the barrier is met."),
        ("Knock-in barrier", "A downside level which, if breached, removes capital protection. European knock-in means it is observed only at maturity."),
        ("Knock-in", "The event of the knock-in barrier being breached. For a note with a One Star clause this does not by itself cause a loss."),
        ("Capital loss", "Redemption below par: the knock-in barrier was breached AND the One Star condition was not met."),
        ("Worst-of", "The payoff references the weakest-performing underlying on each observation date, rather than an average of the basket."),
        ("Phoenix", "An autocallable paying conditional (often memory) coupons above a coupon barrier, with capital at risk below a knock-in barrier."),
        ("One Star", "A clause whereby a single underlying at or above a set level redeems capital at par even when the worst performer breached its barrier; it can optionally also satisfy the coupon and autocall conditions on its own."),
        ("Strike / initial fixing", "The reference price of each underlying at issue, set to 100%; all performance levels are measured against it."),
        ("Total return", "The note's overall return at redemption as a fraction of par: all coupons received plus principal repaid, minus 1. Measured over the realised holding period and NOT annualised."),
        ("IRR (simple, p.a.)", "Annualised return on a path, computed as total return divided by time held — the convention used to quote note coupons. Differs from total return whenever the note is held for other than exactly one year (e.g. an early autocall annualises a small total return up to a larger figure)."),
        ("Heston model", "A stochastic-volatility model in which variance itself follows a mean-reverting random process; used here to simulate the underlyings."),
        ("Student-t copula", "A dependence structure linking the assets' shocks with fatter joint tails than a Gaussian copula, capturing co-movement in stress."),
        ("Volatility (σ)", "The annualised standard deviation of an asset's returns — a measure of how much its price fluctuates. Higher volatility widens the outcome distribution and raises the chance of breaching a barrier."),
        ("Implied volatility (ATM, 3M)", "Forward-looking volatility backed out from option prices — the market's expectation of future movement. 'ATM' uses the strike nearest spot (~100% moneyness, call and put averaged) at the expiry nearest three months."),
        ("Realized volatility", "Backward-looking volatility: the annualised standard deviation of recent daily log-returns (~3 months here). Shown in place of implied vol when an underlying has no listed options on the data source."),
        ("Moneyness / at-the-money (ATM)", "An option's strike relative to spot. At-the-money is a strike at ~100% of spot, and is the reference point for quoting a single headline implied volatility."),
        ("RSI (14)", "The 14-day Relative Strength Index — a momentum oscillator ranging from 0 to 100 that gauges the speed and magnitude of recent price moves. Readings above 70 are conventionally read as 'overbought' and below 30 as 'oversold'; around 50 is neutral. Shown per underlying as a snapshot of recent momentum, not a forecast."),
        ("Monte Carlo simulation", "Estimating the note's outcomes by generating many random price paths under the model, pricing the payoff on each, and summarising across all paths."),
        ("Backtest", "Re-running the note's payoff over historical price windows — one per past issue date — to see how it would have performed in realised market history, as opposed to simulated paths."),
        ("Participation note", "A note whose redemption is a direct function of the final basket level — a downside profile combined with an upside profile — with no periodic coupons or autocall. Capital is repaid according to where the basket finishes."),
        ("Protection level", "The basket level down to which capital is returned at par. Full protection returns par whenever the basket is at or above this level; below it, losses accrue according to the downside style."),
        ("Participation rate", "The multiplier applied to the basket's move (above the strike for upside, or below it for a bear note) when computing the note's return."),
        ("Upside cap", "A ceiling on redemption above par: once the basket gain reaches the cap, the payoff plateaus and does not rise further. On a cliquet the cap applies to each period's participation."),
        ("Downside style", "How losses accrue below protection. Buffer: par down to the protection level, then 1:1 below. Airbag: par down to a barrier, then a geared loss of final/barrier. Bear: the note gains as the basket falls."),
        ("Upside style", "How gains accrue above the strike. Linear: the participation rate times the basket gain, optionally capped. Digital: a fixed payout if the basket ends at or above the strike. Shark fin: participation up to a knock-out level, else a flat rebate."),
        ("Cliquet", "A participation that resets its reference level each period, locking in that period's (capped) participation as income and measuring the next period from the new level."),
    ],
    "es": [
        ("Nota autocancelable", "Nota estructurada que se rescata anticipadamente ('autocancela') si los subyacentes están en o sobre la barrera de autocall en una fecha de observación."),
        ("Barrera de autocall", "Nivel que el rendimiento de referencia debe alcanzar en una fecha de observación para activar el rescate anticipado a la par."),
        ("Observación de autocall", "Fecha programada en la que se evalúan las condiciones de autocall y cupón; la primera fecha elegible puede ser posterior al primer cupón."),
        ("Cupón (anual)", "Renta periódica, expresada como tasa anual; el importe por período es la tasa anual dividida por el número de observaciones al año."),
        ("Barrera de cupón", "Nivel de rendimiento en o sobre el cual se paga un cupón en una observación. Una barrera del 0% significa cupón garantizado."),
        ("Cupón con memoria", "Los cupones no pagados por no alcanzarse la barrera se acumulan y se pagan íntegros en la siguiente fecha en que se cumpla la barrera."),
        ("Barrera de knock-in", "Nivel a la baja que, si se toca, elimina la protección del capital. Knock-in europeo significa que solo se observa al vencimiento."),
        ("Knock-in", "El evento de tocar la barrera de knock-in. En una nota con cláusula de rescate no provoca por sí solo una pérdida."),
        ("Pérdida de capital", "Rescate por debajo de la par: se tocó la barrera de knock-in Y no se cumplió la condición de redención final (rescate)."),
        ("Worst-of", "El pago se basa en el subyacente con peor rendimiento en cada observación, no en un promedio de la cesta."),
        ("Phoenix", "Autocancelable que paga cupones condicionales (a menudo con memoria) sobre una barrera de cupón, con capital en riesgo bajo el knock-in."),
        ("Redención final / rescate best-of", "Cláusula que rescata la nota a la par si el mejor subyacente termina en o sobre un nivel dado, incluso si se tocó el knock-in."),
        ("Strike / fijación inicial", "Precio de referencia de cada subyacente en la emisión, fijado al 100%; todos los niveles de rendimiento se miden contra él."),
        ("Retorno total", "El rendimiento global de la nota al rescate como fracción de la par: todos los cupones recibidos más el principal devuelto, menos 1. Medido sobre el período de tenencia real y NO anualizado."),
        ("TIR (simple, anual)", "Retorno anualizado de una trayectoria, calculado como retorno total dividido por el tiempo mantenido — convención usada para cotizar cupones. Difiere del retorno total siempre que la nota se mantenga un plazo distinto de exactamente un año (p. ej. un autocall temprano anualiza un retorno total pequeño hasta una cifra mayor)."),
        ("Modelo de Heston", "Modelo de volatilidad estocástica en el que la varianza sigue un proceso aleatorio con reversión a la media; usado para simular los subyacentes."),
        ("Cópula t-Student", "Estructura de dependencia que une los choques de los activos con colas conjuntas más gruesas que una cópula gaussiana, capturando el co-movimiento en estrés."),
        ("Volatilidad (σ)", "Desviación estándar anualizada de los retornos de un activo — cuánto fluctúa su precio. Mayor volatilidad amplía la distribución de resultados y eleva la probabilidad de tocar una barrera."),
        ("Volatilidad implícita (ATM, 3M)", "Volatilidad prospectiva derivada de los precios de las opciones — la expectativa del mercado sobre el movimiento futuro. 'ATM' usa el strike más cercano al spot (~100% de moneyness, promedio de call y put) en el vencimiento más próximo a tres meses."),
        ("Volatilidad realizada", "Volatilidad retrospectiva: desviación estándar anualizada de los log-retornos diarios recientes (~3 meses aquí). Se muestra en lugar de la implícita cuando un subyacente no tiene opciones listadas en la fuente de datos."),
        ("Moneyness / at-the-money (ATM)", "El strike de una opción respecto al spot. At-the-money es un strike al ~100% del spot, y es la referencia para cotizar una única volatilidad implícita de referencia."),
        ("RSI (14)", "Índice de Fuerza Relativa de 14 días — un oscilador de momento de 0 a 100 que mide la velocidad y magnitud de los movimientos de precio recientes. Lecturas por encima de 70 se leen convencionalmente como 'sobrecompra' y por debajo de 30 como 'sobreventa'; alrededor de 50 es neutral. Se muestra por subyacente como una instantánea del momento reciente, no un pronóstico."),
        ("Simulación de Monte Carlo", "Estimación de los resultados de la nota generando muchas trayectorias de precio aleatorias bajo el modelo, valorando el pago en cada una y resumiendo sobre todas las trayectorias."),
        ("Backtest", "Re-ejecución del pago de la nota sobre ventanas históricas de precios — una por cada fecha de emisión pasada — para ver cómo habría rendido en el mercado real, frente a las trayectorias simuladas."),
        ("Nota de participación", "Nota cuya redención es función directa del nivel final de la cesta — un perfil a la baja combinado con un perfil al alza — sin cupones periódicos ni autocall. El capital se devuelve según dónde termine la cesta."),
        ("Nivel de protección", "Nivel de la cesta hasta el cual el capital se devuelve a la par. La protección total devuelve la par cuando la cesta está en o sobre este nivel; por debajo, las pérdidas se acumulan según el estilo a la baja."),
        ("Tasa de participación", "Multiplicador aplicado al movimiento de la cesta (sobre el strike al alza, o bajo él en una nota bajista) al calcular el retorno de la nota."),
        ("Tope al alza", "Techo a la redención sobre la par: una vez que la ganancia de la cesta alcanza el tope, el pago se estabiliza y no sube más. En un cliquet el tope se aplica a la participación de cada período."),
        ("Estilo a la baja", "Cómo se acumulan las pérdidas bajo la protección. Buffer: par hasta el nivel de protección, luego 1:1 por debajo. Airbag: par hasta una barrera, luego pérdida apalancada de final/barrera. Bajista: la nota gana cuando la cesta cae."),
        ("Estilo al alza", "Cómo se acumulan las ganancias sobre el strike. Lineal: la tasa de participación por la ganancia de la cesta, con tope opcional. Digital: pago fijo si la cesta termina en o sobre el strike. Aleta de tiburón: participación hasta un nivel de knock-out, si no un reembolso fijo."),
        ("Cliquet", "Participación que reinicia su nivel de referencia cada período, fijando la participación (con tope) de ese período como renta y midiendo el siguiente período desde el nuevo nivel."),
    ],
}

# Which report content each glossary term explains — index-aligned with the en/es
# lists above (both have the same 24 entries in the same order; index 11 is the
# One-Star / best-of-redemption clause in either language). A term only prints
# when the content that needs it is in the report. "core" = always relevant when
# there is a note at all.
# "phx" = Phoenix-family mechanics (coupon/autocall/knock-in) — irrelevant to a
# Participation note; "part" = Participation payoff terms — irrelevant to Phoenix.
# "core" = shared by both families (worst-of, strike, total return, IRR).
_GLOSSARY_TAGS: list[set[str]] = [
    {"phx"},         # 0  Autocallable note
    {"phx"},         # 1  Autocall barrier
    {"phx"},         # 2  Autocall observation
    {"phx"},         # 3  Coupon (p.a.)
    {"phx"},         # 4  Coupon barrier
    {"mem"},         # 5  Memory coupon
    {"phx"},         # 6  Knock-in barrier
    {"phx"},         # 7  Knock-in
    {"phx"},         # 8  Capital loss
    {"core"},        # 9  Worst-of
    {"phx"},         # 10 Phoenix
    {"os"},          # 11 One Star / Redención final
    {"core"},        # 12 Strike / initial fixing
    {"mc", "bt"},    # 13 Total return
    {"mc", "bt"},    # 14 IRR (simple, p.a.)
    {"mc"},          # 15 Heston model
    {"mc"},          # 16 Student-t copula
    {"mc", "ul"},    # 17 Volatility (σ)
    {"ul"},          # 18 Implied volatility (ATM, 3M)
    {"ul"},          # 19 Realized volatility
    {"ul"},          # 20 Moneyness / ATM
    {"ul"},          # 21 RSI (14)
    {"mc"},          # 22 Monte Carlo simulation
    {"bt"},          # 23 Backtest
    {"part"},        # 24 Participation note
    {"part"},        # 25 Protection level
    {"part"},        # 26 Participation rate
    {"part"},        # 27 Upside cap
    {"part"},        # 28 Downside styles (buffer / airbag / bear)
    {"part"},        # 29 Upside styles (linear / digital / shark fin)
    {"part"},        # 30 Cliquet
]


def _t(key: str, lang: str) -> str:
    return _LABELS.get(key, {}).get(lang, _LABELS.get(key, {}).get("en", key))



# payment_freq enum (core/note.py) -> Spanish wording. Unknown values pass
# through unchanged so a custom freq label is never mangled.
_FREQ_ES = {
    "monthly":     "mensual",
    "quarterly":   "trimestral",
    "semi-annual": "semestral",
    "annual":      "anual",
}


def _fmt_freq(freq: str, lang: str) -> str:
    return _FREQ_ES.get(str(freq).lower(), str(freq)) if lang == "es" else str(freq)






# ──────────────────────────────────────────────────────────────────────────────
# Text sanitisation
# IBM Plex Sans covers all Latin/Greek/punctuation/math Unicode natively, so we
# only need to neutralise emojis and a handful of symbols it omits.
# ──────────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
# Font registration
# Primary: IBM Plex Sans individual TTF files (institutional quality, Unicode).
# Fallback: Helvetica (built-in, Latin-1 only).
# ──────────────────────────────────────────────────────────────────────────────

# Font family name exposed to _sf() — switches based on what is available


class _NotePDF(ReportDocument):
    """The Structured-Note adapter's document.

    Deliberately THIN. Everything generic — chrome, tables, metric bands,
    figures, the keep-together pagination — is `ReportDocument`. Only blocks that
    know what a structured note is live here.

    Do not re-declare inherited methods for convenience: tests/test_pdf_layout.py
    `setattr`s 17 method names onto this class to instrument pagination, and a
    redefinition here would shadow the instrumented base method and silently
    blind the orphaned-heading probe.
    """

    def __init__(self, *args, issuer: str = "", **kwargs):
        # This repo's own fonts/ and label table — identical bytes and identical
        # strings to before, so the extraction cannot move a glyph or a word.
        kwargs.setdefault("font_dir", _FONT_DIR)
        kwargs.setdefault("labels", _t)
        super().__init__(*args, **kwargs)
        self.issuer = issuer          # note state, not document state

    def issuer_info_block(self, name: str, logo_bytes: bytes | None,
                          description: str, ratings: list[tuple[str, str]]):
        """Factsheet-style issuer panel: logo + name (brand primary), a blurb, and S&P/
        Moody's/Fitch rating chips. Mirrors the reference 'Información del Emisor'.
        `ratings` is a list of (label, value) with empty values already removed."""
        x0 = self.l_margin
        w  = self.w - self.l_margin - self.r_margin
        pad = 6.0
        inner_w = w - 2 * pad
        name_h  = 9.0
        # Measure the description so the panel sizes to its content.
        self._sf(8, "regular")
        desc_lines = (self.multi_cell(inner_w, 4.2, self._safe(description),
                                      dry_run=True, output="LINES")
                      if description else [])
        desc_h  = len(desc_lines) * 4.2
        chip_h  = 11.0
        box_h = (pad + name_h
                 + (2 + desc_h if description else 0)
                 + (4 + chip_h if ratings else 0)
                 + pad)
        y0 = self.get_y()
        if y0 + box_h > self.h - 28:
            self.add_page()
            y0 = self.get_y()
        # Panel
        self.set_fill_color(*self.panel_color)   # brand-tinted panel
        try:
            self.rect(x0, y0, w, box_h, style="F", round_corners=True, corner_radius=2)
        except TypeError:
            self.rect(x0, y0, w, box_h, style="F")
        # Logo + issuer name (brand primary)
        cy = y0 + pad
        tx = x0 + pad
        if logo_bytes:
            try:
                self.image(io.BytesIO(logo_bytes), x=x0 + pad, y=cy, w=8, h=8)
                tx = x0 + pad + 11
            except Exception:
                pass
        self.set_xy(tx, cy + 1.0)
        self._sf(13, "bold")
        self.set_text_color(*self.ink)
        self.cell(inner_w, 6, self._safe(name))
        cy += name_h
        # Description
        if description:
            self.set_xy(x0 + pad, cy + 2)
            self._sf(8, "regular")
            self.set_text_color(*self.body_ink)
            self.multi_cell(inner_w, 4.2, self._safe(description))
            cy = self.get_y()
        # Rating chips (white rounded boxes, label over value)
        if ratings:
            cy += 2
            chip_w, gap = 34.0, 4.0
            cx = x0 + pad
            for lbl, val in ratings:
                self.set_fill_color(*_WHITE)
                try:
                    self.rect(cx, cy, chip_w, chip_h, style="F",
                              round_corners=True, corner_radius=1.5)
                except TypeError:
                    self.rect(cx, cy, chip_w, chip_h, style="F")
                self.set_xy(cx, cy + 1.5)
                self._sf(6.8, "body_bold")
                self.set_text_color(*self.muted)
                self.cell(chip_w, 3.5, self._safe(lbl), align="C")
                self.set_xy(cx, cy + 5.5)
                self._sf(11, "bold")
                self.set_text_color(*self.primary_color)
                self.cell(chip_w, 5, self._safe(val), align="C")
                cx += chip_w + gap
        self.set_y(y0 + box_h + 4)

    def underlying_block(self, long_name: str, logo_bytes: bytes | None,
                         subtitle: str, metrics: list[tuple[str, str]],
                         description: str, chart_png: bytes | None,
                         chart_caption: str, section_title: str | None = None,
                         analyst: list[tuple[str, float, tuple]] | None = None,
                         analyst_title: str = "", ticker: str | None = None,
                         color: tuple | None = None):
        """One full page per underlying (prototype layout): a '03 · Underlying'
        secondary head with the company name and a small ticker badge, a type·sector
        eyebrow, a row of ECF1F6 metric tiles (market cap / 3M vol / last / RSI), the
        company description, an optional analyst-consensus bar, and the trailing
        12-month price chart in a white bordered card. `section_title` and
        `logo_bytes` are accepted for backward compatibility; each page is now
        self-headed by the secondary head (the badge identifies the underlying)."""
        x0 = self.l_margin
        w  = self.w - self.l_margin - self.r_margin
        self.add_page()
        self.secondary_head(self.chapter_nums.get("underlying", ""),
                            _t("kick_underlying", self.lang),
                            self._safe(long_name), badge=ticker,
                            badge_color=(color or self.primary_color),
                            badge_logo=logo_bytes)
        if subtitle:
            self._eyebrow(x0, self.get_y(), subtitle, self.muted,
                          size=7.5, tracking=0.4, w=w)
            self.ln(6)
        # ECF1F6 metric tiles.
        if metrics:
            self.metric_band(list(metrics))
        # Company description (justified body).
        if description:
            self._sf(8.5, "regular")
            self.set_text_color(*self.body_ink)
            self.multi_cell(w, 4.6, self._safe(description), align="J")
            self.ln(3)
        # Analyst consensus bar (optional) — matches the web card.
        if analyst:
            cy = self.get_y() + 1
            self._eyebrow(x0, cy, analyst_title, self.muted, size=7.0,
                          tracking=0.4, w=w)
            cy += 4.6
            bar_h = 2.8
            rad = bar_h / 2
            self.set_fill_color(*_blend(self.muted, _WHITE, 0.84))
            try:
                self.rect(x0, cy, w, bar_h, style="F", round_corners=True, corner_radius=rad)
            except TypeError:
                self.rect(x0, cy, w, bar_h, style="F")
            segs = [(c, w * max(0.0, f)) for (_l, f, c) in analyst if f > 0.001]
            bx = x0
            for _i, (_col, _wd) in enumerate(segs):
                self.set_fill_color(*_col)
                _corn = (True if len(segs) == 1 else
                         ("TOP_LEFT", "BOTTOM_LEFT") if _i == 0 else
                         ("TOP_RIGHT", "BOTTOM_RIGHT") if _i == len(segs) - 1 else None)
                try:
                    if _corn is True:
                        self.rect(bx, cy, _wd, bar_h, style="F", round_corners=True, corner_radius=rad)
                    elif _corn:
                        self.rect(bx, cy, _wd, bar_h, style="F", round_corners=_corn, corner_radius=rad)
                    else:
                        self.rect(bx, cy, _wd, bar_h, style="F")
                except TypeError:
                    self.rect(bx, cy, _wd, bar_h, style="F")
                bx += _wd
            cy += bar_h + 3.0
            self._sf(7, "regular")
            lx = x0
            for _lbl, _frac, _col in analyst:
                self.set_fill_color(*_col)
                self.ellipse(lx, cy - 1.9, 1.8, 1.8, style="F")
                self.set_xy(lx + 2.8, cy - 2.6)
                self.set_text_color(*self.body_ink)
                _txt = f"{_lbl} {_frac:.0%}"
                self.cell(self.get_string_width(_txt) + 1, 3.2, self._safe(_txt))
                lx += 2.8 + self.get_string_width(_txt) + 6
            self.set_y(cy + 3.0)
        # Trailing-12M price chart in a white bordered card.
        if chart_png:
            self.ln(2)
            self._eyebrow(x0, self.get_y(), chart_caption, self.muted,
                          size=8.0, tracking=0.4, w=w)
            self.ln(5.5)
            try:
                from PIL import Image
                iw, ih = Image.open(io.BytesIO(chart_png)).size
                ch = min(w * ih / iw, 80.0)
                cw = ch * iw / ih
            except Exception:
                cw, ch = w, w * 0.4
            fpad = 3.0
            top = self.get_y()
            imgx = x0 + (w - cw) / 2
            self.set_fill_color(*_WHITE)
            self.set_draw_color(*self.rule_soft)
            self.set_line_width(0.2)
            try:
                self.rect(x0, top, w, ch + 2 * fpad, style="DF",
                          round_corners=True, corner_radius=2)
            except TypeError:
                self.rect(x0, top, w, ch + 2 * fpad, style="DF")
            try:
                self.image(io.BytesIO(chart_png), x=imgx, y=top + fpad, w=cw, h=ch)
            except Exception:
                pass
            self.set_y(top + ch + 2 * fpad + 4)


# ──────────────────────────────────────────────────────────────────────────────
# Logo fetching
# ──────────────────────────────────────────────────────────────────────────────

# fpdf2 can only embed PNG, JPEG and GIF. Favicon services frequently hand back
# ICO (Google s2/favicons, duckduckgo), and some CDNs return WEBP — both make
# pdf.image() raise, which previously silently dropped the logo. We normalise
# *every* logo byte string through Pillow to a clean RGBA PNG before it ever
# reaches pdf.image(): the format is guaranteed embeddable, the alpha channel is
# preserved, and a multi-resolution ICO is collapsed to its largest frame.
# Image loading / sanitising / embedding now lives in reportkit.images. Every
# name is re-bound here under its original private spelling, as a MODULE GLOBAL
# resolved at call time — `tests/golden_fixture.py` neutralises the network by
# rebinding `pdf_report._fetch_image_bytes`, and `_load_logo` below looks it up
# through this module, so the indirection is the test seam, not an accident.
_dimensions_sane   = _rk_images.dimensions_sane
_to_embeddable_png = _rk_images.to_embeddable_png
_logo_aspect       = _rk_images.logo_aspect
_fetch_image_bytes = _rk_images.fetch_image_bytes
_read_local_image  = _rk_images.read_local_image
_EMBEDDABLE_MAGIC  = _rk_images._EMBEDDABLE_MAGIC


def _resolve_local_path(spec: str) -> Path | None:
    """Resolve a branding `logo_file` against THIS repo's root.

    The containment rule is reportkit's; the root is the host's, because an
    installed library has no repo to be relative to.
    """
    return _rk_images.resolve_within(spec, _REPO_ROOT)


def _load_logo(branding: dict | None) -> bytes | None:
    """Resolve the firm/issuer logo. `_REPO_ROOT` is the containment root for
    `logo_file`, and `_fetch_image_bytes` is passed EXPLICITLY rather than let
    reportkit reach for its own — that keeps the module-global seam
    tests/golden_fixture.py rebinds to neutralise the network.
    """
    return _rk_branding.load_logo(branding, root=_REPO_ROOT,
                                  fetch=_fetch_image_bytes)


def _find_ticker_logo_file(ticker: str) -> Path | None:
    """Look for a local logo at branding/ticker_logos/{TICKER}.{png,jpg,svg}.

    Case-insensitive match on the file stem; tries png, jpg, jpeg, svg in order.
    SVG matches are returned (the caller's loader skips them gracefully).
    Returns the first matching Path or None.
    """
    if not ticker or not _TICKER_LOGO_DIR.is_dir():
        return None
    want = ticker.strip().lower()
    try:
        candidates = list(_TICKER_LOGO_DIR.iterdir())
    except Exception:
        return None
    # Preferred extension order
    for ext in (".png", ".jpg", ".jpeg", ".svg"):
        for f in candidates:
            if f.is_file() and f.stem.lower() == want and f.suffix.lower() == ext:
                return f
    return None


# Successful logo loads are memoised; FAILURES (None) are deliberately NOT cached.
# The old @lru_cache cached None too, so a single transient favicon/CDN fetch
# failure at report-build time (timeout, proxy, egress blip) left that logo —
# e.g. the BBVA issuer favicon — missing for the rest of a long-running app
# session, with no retry until restart. Caching only non-None results means the
# next report build re-attempts the fetch.
_TICKER_LOGO_CACHE: dict[tuple, bytes] = {}


def _load_ticker_logo(display_name: str, url: str | None,
                      symbol: str | None = None) -> bytes | None:
    """Cached wrapper around _load_ticker_logo_uncached. Caches only successful
    (non-None) loads so a transient fetch failure is retried, not stuck."""
    key = (display_name, url, symbol)
    cached = _TICKER_LOGO_CACHE.get(key)
    if cached is not None:
        return cached
    data = _load_ticker_logo_uncached(display_name, url, symbol)
    if data:
        _TICKER_LOGO_CACHE[key] = data
    return data


def _load_ticker_logo_uncached(display_name: str, url: str | None,
                               symbol: str | None = None) -> bytes | None:
    """Resolve a single underlying/ticker logo, local-folder-first.

    Looks for branding/ticker_logos/{STEM}.{png,jpg,...} where STEM is tried as
    the ticker symbol first, then the display name. Falls back to the supplied
    URL. Never raises; returns None if nothing yields usable bytes. Successful
    results are memoised by the _load_ticker_logo wrapper (failures are retried).
    """
    for stem in (symbol, display_name):
        if not stem:
            continue
        local = _find_ticker_logo_file(stem)
        if local is not None:
            data = _to_embeddable_png(_read_local_image(local))
            if data:
                return data
    if url:
        return _to_embeddable_png(_fetch_image_bytes(url))
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Figure export helper
# ──────────────────────────────────────────────────────────────────────────────

# ── Branded recolouring ───────────────────────────────────────────────────────
# The app charts (app/charts.py) are built on a fixed navy/blue palette. For the
# PDF we remap that known source palette onto a BRANDED palette that pairs the
# firm's brand colour with a complementary warm gold, so charts read as branded
# yet are not monochrome (a green report gets green data series + gold contrast).
# The remap is keyed on exact source values, so semantic colours not in the map
# (red KI line, grey autocall line, orange coupon line, white) pass through
# untouched, and the fan-chart band hierarchy is preserved (both bands share the
# brand RGB but keep their distinct 0.08 vs 0.20 alpha). Categorical blue-ramp
# colours (the backtest's hsl(217,…) autocall periods) are hue-rotated to a green
# ramp; the correlation heat-scale endpoint is kept in the brand colour via a
# separate scale map so the heatmap stays on-brand rather than going gold.
_SRC_NAVY  = (26, 46, 74)     # #1a2e4a  maturity bars / dark "second category"
_SRC_BLUE  = (37, 99, 235)    # #2563eb  median / mean line / primary series / band fills
_SRC_LIGHT = (96, 165, 250)   # #60a5fa  autocalled bars / light secondary series
_SRC_EXTRA = {(8, 145, 178), (124, 58, 237), (13, 148, 136)}  # >3-asset series colours




def _build_color_remap(primary: tuple, accent: tuple, secondary: tuple) -> dict:
    """Series/marker map: charts.py source palette -> brand accent + secondary.

    SEMANTIC COLOURS ALWAYS WIN over branding: red (#dc2626) = loss / knock-in /
    danger and the brand-accent "good outcome" series are intentionally handled so
    that bad things stay red and good things stay (brand) accent regardless of the
    firm palette. Red/orange/grey are NOT in this map, so they pass through
    untouched; the secondary colour (gold by default) is only ever assigned to the
    *neutral* second category (held-to-maturity), never to a loss or a gain. Do
    not add red/green semantic hexes as remap keys."""
    white = (255, 255, 255)
    extras = list(_SRC_EXTRA)
    return {
        _SRC_BLUE:  accent,                       # hero series / median / mean
        _SRC_NAVY:  secondary,                    # second category (maturity) -> secondary
        _SRC_LIGHT: _blend(accent, white, 0.45),  # light series / autocalled bars
        extras[0]:  _blend(secondary, white, 0.40),
        extras[1]:  primary,
        extras[2]:  secondary,
        # Downside stays a "warning" colour but in the brand's amber, not red —
        # the green design language has no red. Semantics are preserved (amber is
        # still clearly downside); only branded reports rebrand, so the default
        # navy report keeps its conventional red.
        (220, 38, 38): _AMBER,
        (239, 68, 68): _AMBER,
        # Outcome-breakdown autocall ramp (charts.py `blues`): a fixed blue ramp
        # unique to that chart — map it onto a dark→light brand-green ramp so the
        # dominant autocall bar isn't blue on a green report.
        (30,  58, 138): _blend(primary, _BLACK, 0.45),   # #1e3a8a  P1 deepest
        (29,  78, 216): _blend(primary, _BLACK, 0.12),   # #1d4ed8  P2
        (59, 130, 246): _blend(primary, white, 0.28),    # #3b82f6  P4
        (147, 197, 253): _blend(primary, white, 0.55),   # #93c5fd  lightest
    }


def _build_scale_remap(primary: tuple, accent: tuple) -> dict:
    """Colour-scale map (heatmaps): keep the intensity ramp on-brand (primary/
    accent), never gold — the navy/blue endpoints map to the brand, red stays red."""
    return {_SRC_NAVY: primary, _SRC_BLUE: accent}


def _rebrand_figure(fig, primary: tuple, accent: tuple, secondary: tuple):
    """Remap the figure's navy/blue source palette onto the branding colours."""
    # Identity short-circuit: default palette == source palette, nothing to do.
    if primary == _SRC_NAVY and accent == _SRC_BLUE:
        return
    remap = _build_color_remap(primary, accent, secondary)
    scale = _build_scale_remap(primary, accent)
    ramp_hue = _rgb_to_hue(accent)          # blue autocall ramp -> brand accent hue
    rc = lambda c: _remap_color(c, remap, ramp_hue)   # series / marker colours
    sc = lambda c: _remap_color(c, scale, ramp_hue)   # intensity scales (stay brand)
    # colorway (most charts) and piecolorway (px.pie stores its slice palette
    # here, NOT on the trace) — remap both or a branded report keeps blue pies.
    for _attr in ("colorway", "piecolorway"):
        try:
            cw = getattr(fig.layout, _attr, None)
            if cw:
                setattr(fig.layout, _attr, tuple(rc(c) for c in cw))
        except Exception:
            pass
    for tr in fig.data:
        # "marker.colors" (plural) is the per-slice colour list on pie/donut
        # traces — without it, px.pie's color_discrete_sequence is never
        # rebranded and the pie stays blue on a green report.
        for path in ("line.color", "fillcolor", "marker.color", "marker.colors",
                     "marker.line.color"):
            try:
                obj = tr
                parts = path.split(".")
                for p in parts[:-1]:
                    obj = getattr(obj, p)
                val = getattr(obj, parts[-1], None)
                if val is None:
                    continue
                if isinstance(val, (list, tuple)):
                    setattr(obj, parts[-1], type(val)(rc(v) for v in val))
                else:
                    setattr(obj, parts[-1], rc(val))
            except Exception:
                pass
        # Heatmap / continuous colorscale: [(pos, color), ...] — use the scale map.
        try:
            cs = getattr(tr, "colorscale", None)
            if cs:
                tr.colorscale = tuple((pos, sc(col)) for pos, col in cs)
        except Exception:
            pass
    # add_vline / add_hline (e.g. the mean / expected-IRR line) are layout
    # shapes, not traces — remap their line colour too. Semantic shapes
    # (red zero line, grey coupon line) aren't in the source map, so untouched.
    try:
        for shp in fig.layout.shapes or ():
            try:
                if getattr(shp.line, "color", None) is not None:
                    shp.line.color = rc(shp.line.color)
            except Exception:
                pass
    except Exception:
        pass
    # px.imshow heatmaps keep their colourscale on layout.coloraxis, not on the
    # trace — remap the navy endpoint to the brand colour (scale map, not gold).
    try:
        cax = fig.layout.coloraxis
        if cax is not None and getattr(cax, "colorscale", None):
            cax.colorscale = tuple((pos, sc(col)) for pos, col in cax.colorscale)
    except Exception:
        pass


# Chart rasterisation lives in reportkit.charts, behind the [charts] extra.
# `_FIG_HOOK` is an ALIAS OF THE SAME ContextVar, not a new one: api/proof.py and
# tests/golden_fixture.py .set()/.reset() through `pdf_report._FIG_HOOK`, and a
# second ContextVar would silently disable the proof's placeholder mode and put a
# real headless Chrome in CI.
_FIG_HOOK = _rk_charts.FIG_HOOK
_theme_figure = _rk_charts.theme_figure


def _fig_to_png(fig, width: int = 900, height: int = 500,
                primary_color: tuple = _DEFAULT_PRIMARY,
                accent_color: tuple = _DEFAULT_ACCENT,
                secondary_color: tuple = _DEFAULT_SECONDARY) -> bytes | None:
    """Rasterise a figure, re-coloured into the brand palette.

    `_rebrand_figure` is injected rather than moved: it knows this app's SOURCE
    palette (the navy/blue `app/charts.py` builders emit) and short-circuits when
    the brand happens to equal it. That is domain knowledge about our own charts,
    not something a reusable library can assume.
    """
    return _rk_charts.fig_to_png(fig, width, height, primary_color, accent_color,
                                 secondary_color, rebrand=_rebrand_figure)


# ──────────────────────────────────────────────────────────────────────────────
# Page builders
# ──────────────────────────────────────────────────────────────────────────────

def _fmt_mcap(v) -> str:
    """Compact currency market cap (—, $1.2T, $265.0B, $980.0M)."""
    if v in (None, ""):
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if v >= div:
            return f"${v/div:.1f}{unit}"
    return f"${v:,.0f}"


def _fmt_pct(v) -> str:
    try:
        return f"{float(v) * 100:.1f}%" if v not in (None, "") else "—"
    except (TypeError, ValueError):
        return "—"


def _fmt_num(v) -> str:
    try:
        return f"{float(v):,.2f}" if v not in (None, "") else "—"
    except (TypeError, ValueError):
        return "—"


def _fmt_rsi(v) -> str:
    try:
        return f"{float(v):.0f}" if v not in (None, "") else "—"
    except (TypeError, ValueError):
        return "—"


def _is_participation(terms) -> bool:
    """A Participation note (payoff = a redemption profile, not a coupon/autocall
    ladder). Legacy capital-guarantee configs migrate to this family too."""
    return (getattr(terms, "note_type", "") == "participation"
            or (getattr(terms, "capital_guarantee", 0) or 0) > 0)


def _part_cap_value(terms):
    """Active upside cap as a redemption level (e.g. 1.08), or None. A cliquet caps
    each period via `period_cap`; a single-shot note caps the whole payoff via
    `upside_cap`."""
    periodic = bool(getattr(terms, "participation_periodic", False))
    cap = getattr(terms, "period_cap", None) if periodic else getattr(terms, "upside_cap", None)
    return (1.0 + float(cap)) if cap is not None else None


def _part_profile_str(terms, lang: str) -> str:
    """One-line downside×upside payoff profile — the PDF mirror of the web's
    `participationSummary` (web/src/lib/terms.ts). Keep the two in sync. E.g.
    'Full protection · Linear 100% · upside cap 108%', with a 'Cliquet · quarterly'
    prefix for a periodic note."""
    dn = getattr(terms, "participation_downside", "full") or "full"
    up = getattr(terms, "participation_upside", "linear") or "linear"
    prot = float(getattr(terms, "protection_level", 1.0) or 1.0)
    rate = float(getattr(terms, "participation_rate", 1.0) or 1.0)
    strike = float(getattr(terms, "participation_strike", 1.0) or 1.0)
    periodic = bool(getattr(terms, "participation_periodic", False))
    cap = _part_cap_value(terms)
    segs: list[str] = []
    if periodic:
        segs.append(f"{_t('grp_cliquet', lang)} · {_fmt_freq(terms.payment_freq, lang)}")
    if dn == "bear":
        segs.append(f"{_t('pd_bear', lang)} {rate:.0%}")
    elif dn == "full":
        segs.append(_t("pd_full", lang) if prot >= 0.999 else f"{_t('pd_full', lang)} {prot:.0%}")
    else:
        segs.append(f"{_t('pd_' + dn, lang)} {prot:.0%}")
    if dn != "bear":   # a bear note defines its own payoff — no separate upside leg
        if up == "digital":
            segs.append(f"{_t('pu_digital', lang)} +{float(getattr(terms, 'digital_payout', 0) or 0):.0%}")
        elif up == "shark_fin":
            ko = getattr(terms, "knockout_level", None)
            segs.append(f"{_t('pu_shark_fin', lang)} {float(ko):.0%}" if ko is not None
                        else _t("pu_shark_fin", lang))
        else:
            _c = f" · {_t('upside_cap', lang).lower()} {cap:.0%}" if cap is not None else ""
            segs.append(f"{_t('pu_linear', lang)} {rate:.0%}{_c}")
    if abs(strike - 1.0) > 1e-6:
        segs.append(f"{_t('participation_strike', lang).lower()} {strike:.0%}")
    return " · ".join(segs)


def _participation_term_rows(terms, lang: str) -> list[tuple[str, str]]:
    """Note-terms table rows for a Participation note — its downside × upside payoff
    profile, protection, cap and strike — instead of the (irrelevant) coupon /
    autocall / knock-in ladder used by the Phoenix family."""
    periodic = bool(getattr(terms, "participation_periodic", False))
    prot = float(getattr(terms, "protection_level", 1.0) or 1.0)
    rate = float(getattr(terms, "participation_rate", 1.0) or 1.0)
    strike = float(getattr(terms, "participation_strike", 1.0) or 1.0)
    dn = getattr(terms, "participation_downside", "full") or "full"
    up = getattr(terms, "participation_upside", "linear") or "linear"
    cap = _part_cap_value(terms)
    if periodic:
        mat = (f"{_mat_label(terms)} ({_t('grp_cliquet', lang)}, "
               f"{_fmt_freq(terms.payment_freq, lang)}, {terms.n_obs} {_t('observations_word', lang)})")
    else:
        mat = _mat_label(terms)
    rows: list[tuple[str, str]] = [
        (_t("maturity", lang), mat),
        (_t("participation_profile", lang), _part_profile_str(terms, lang)),
        (_t("participation_basket_lbl", lang),
         str(getattr(terms, "participation_basket", "worst_of") or "worst_of").replace("_", "-")),
        (_t("downside_style", lang), _t("pd_" + dn, lang)),
        (_t("protection_level", lang), f"{prot:.1%}"),
    ]
    if dn != "bear":
        rows.append((_t("upside_style", lang), _t("pu_" + up, lang)))
        if up == "digital":
            rows.append((_t("digital_payout", lang),
                         f"{float(getattr(terms, 'digital_payout', 0) or 0):+.1%}"))
        elif up == "shark_fin":
            ko = getattr(terms, "knockout_level", None)
            if ko is not None:
                rows.append((_t("knockout_level", lang), f"{float(ko):.1%}"))
            rows.append((_t("knockout_rebate", lang),
                         f"{float(getattr(terms, 'knockout_payout', 1.0) or 1.0):.1%}"))
        else:  # linear
            rows.append((_t("participation_rate", lang), f"{rate:.1%}"))
        if cap is not None:
            rows.append((_t("period_cap" if periodic else "upside_cap", lang), f"{cap:.1%}"))
    else:
        rows.append((_t("participation_rate", lang), f"{rate:.1%}"))
    if abs(strike - 1.0) > 1e-6:
        rows.append((_t("participation_strike", lang), f"{strike:.1%}"))
    if getattr(terms, "issue_date", None):
        rows.append((_t("issue_date", lang), terms.issue_date))
    rows.extend(_position_rows(terms, lang))
    return rows


def _position_rows(terms, lang: str) -> list[tuple[str, str]]:
    """Term rows describing the POSITION rather than the note — present only for a
    secondary-market purchase, so a plain subscription's table is unchanged (and
    the golden PDF hashes with it). The web mirror is web/src/lib/terms.ts."""
    rows: list[tuple[str, str]] = []
    if getattr(terms, "is_secondary", False):
        if getattr(terms, "settlement_date", None):
            rows.append((_t("settlement_date", lang), terms.settlement_date))
        rows.append((_t("purchase_price", lang), f"{float(terms.purchase_price or 1.0):.3%}"))
        accrued = float(getattr(terms, "accrued_at_purchase", 0.0) or 0.0)
        if accrued > 0:
            rows.append((_t("accrued_at_purchase", lang), f"{accrued:.3%}"))
            rows.append((_t("cost_basis", lang), f"{terms.cost_basis:.3%}"))
    # Seasoning belongs on the term sheet's face: it is why the modelled horizon
    # is shorter than the tenor printed above it.
    if getattr(terms, "seasoned", False):
        rows.append((_t("seasoned", lang), _t("seasoned_row", lang)))
    return rows


def _underlying_labels(pdf, terms, asset_names=None, logo_tickers=None) -> list[str]:
    """How to name the underlyings in running text — exchange SYMBOLS by default,
    display NAMES when branding sets `underlying_labels: "name"`.

    `terms.tickers` is {symbol: display name}, so both are already to hand. Two
    call shapes: from the cover (terms only) and from the summary masthead, which
    works in display names and carries a {name: symbol} map to get back."""
    by_name = bool(getattr(pdf, "underlying_labels", "ticker") == "name")
    if asset_names is not None:
        if by_name:
            return [str(nm) for nm in asset_names]
        return [(logo_tickers or {}).get(nm) or str(nm)[:5].upper() for nm in asset_names]
    tk = getattr(terms, "tickers", {}) or {}
    return [str(v) for v in tk.values()] if by_name else [str(k) for k in tk.keys()]


def _term_rows(terms, lang: str) -> list[tuple[str, str]]:
    if _is_participation(terms):
        return _participation_term_rows(terms, lang)
    rows = [
        (_t("maturity",         lang), f"{_mat_label(terms)} ({terms.n_obs} {_t('observations_word', lang)}, {_fmt_freq(terms.payment_freq, lang)})"),
        (_t("coupon_pa",        lang), f"{terms.coupon_pa * 100:.2f}%  ({terms.coupon_rate * 100:.4f}% {_t('per_period', lang)})"),
        (_t("coupon_barrier",   lang), f"{terms.coupon_barrier:.1%}" if terms.coupon_barrier > 0 else
                                       _t("guaranteed_zero", lang)),
        (_t("memory",           lang), _t("yes", lang) if terms.memory else _t("no", lang)),
        (_t("autocall_barrier", lang), f"{terms.autocall_barrier:.1%}"),
        (_t("autocall_start",   lang), f"P{terms.autocall_start_period}"),
        (_t("ki_barrier",       lang), f"{terms.knock_in_barrier:.1%}"),
        (_t("coupon_basket",    lang), terms.coupon_basket.replace("_", "-")),
        (_t("autocall_basket",  lang), terms.autocall_basket.replace("_", "-")),
        (_t("one_star",         lang), (f"{_t('one_star_level', lang)} {terms.one_star_level:.0%}"
                                          if terms.one_star_level is not None
                                          else ("Off" if lang == "en" else "Desactivado"))),
    ]
    if getattr(terms, "autocall_step_down", 0.0):
        rows.append((_t("ac_step_down", lang), f"{terms.autocall_step_down:.1%}"))
        if getattr(terms, "autocall_floor", None) is not None:
            rows.append((_t("ac_floor", lang), f"{terms.autocall_floor:.0%}"))
    if getattr(terms, "coupon_at_autocall_only", False):
        rows.append((_t("premium_at_call", lang),
                     f"{_t('yes', lang)} ({terms.coupon_pa * 100:.2f}% {_t('pa_short', lang)})"))
    if getattr(terms, "issue_date", None):
        rows.append((_t("issue_date", lang), terms.issue_date))
    rows.extend(_position_rows(terms, lang))
    return rows


def _about_this_report(lang, inc, results, bt_summary, live_data, n_assets) -> str:
    """An 'About this report' blurb that names the parts actually included, rather
    than a fixed sentence (a terms-only report no longer claims a backtest etc.)."""
    es = (lang == "es")
    parts: list[str] = []
    if any(inc(k) for k in ("note_terms", "note_diagram", "obs_schedule",
                            "underlying_breakdown", "issuer_info", "note_description")):
        parts.append("los términos y la estructura de la nota" if es
                     else "the note's terms and structure")
    _any_fan = any(inc(f"mc_fan_{i}") for i in range(n_assets))
    if results and any(inc(k) for k in ("mc_metrics", "mc_irr", "mc_autocall",
                                        "mc_wof", "mc_single_wof", "mc_sample")) or _any_fan:
        parts.append("resultados de la simulación de Monte Carlo" if es
                     else "Monte Carlo simulation results")
    if results and (inc("calib_table") or inc("calib_corr")):
        parts.append("la calibración del modelo" if es else "model calibration")
    if bt_summary and any(inc(k) for k in ("bt_metrics", "bt_outcome", "bt_pie",
                                           "bt_irr", "bt_prices", "bt_sample")):
        parts.append("un backtest histórico" if es else "a historical backtest")
    if live_data and any(inc(k) for k in ("live_metrics", "live_asset_table",
                                          "live_obs_table", "live_chart")):
        parts.append("el seguimiento en vivo de la nota" if es
                     else "live tracking of the current note")
    if not parts:
        parts.append("los términos de la nota" if es else "the note's terms")
    if len(parts) == 1:
        body = parts[0]
    else:
        conj = "y" if es else "and"
        body = ", ".join(parts[:-1]) + f" {conj} " + parts[-1]
    lead = ("Este informe presenta un análisis cuantitativo de la nota estructurada y cubre "
            if es else "This report presents a quantitative analysis of the structured note and covers ")
    return lead + body + "."


def _exec_bullets(terms, results, bt_summary, live_data, lang: str) -> list[str]:
    b = []
    # Monte Carlo bullets only when the sim actually ran (a report of just
    # Note-details / backtest / live sections skips it, so there are no paths).
    _has_mc = len(results.get("annualized_returns", [])) > 0
    if lang == "es":
        if _has_mc:
            b.append(
                f"La simulación Monte Carlo (modelo Heston multi-activo, "
                f"{len(results.get('annualized_returns', [])):,} caminos) estima una TIR anual simple "
                f"esperada de {results.get('expected_irr', 0):.1%} y un retorno total esperado de "
                f"{results.get('expected_total_return', 0):.1%} a vencimiento ({terms.maturity:g} años).")
            if getattr(terms, "note_type", "") == "participation":
                b.append(
                    f"La redención esperada al vencimiento es {results.get('expected_nominal_payout', 1):.1%} del "
                    f"nominal; la probabilidad de redimir por debajo de la par es "
                    f"{results.get('prob_knock_in_total', 0):.1%} y por encima de la par "
                    f"{results.get('prob_above_par', 0):.0%}.")
            else:
                b.append(
                    f"La probabilidad de autocall anticipado es {results.get('prob_autocall', 0):.0%}; "
                    f"la probabilidad de pérdida de capital a vencimiento (knock-in sin rescate) es "
                    f"{results.get('prob_knock_in_total', 0):.1%} con barrera al {terms.knock_in_barrier:.1%}.")
        if bt_summary and getattr(terms, "note_type", "") == "participation":
            b.append(
                f"En el backtest histórico ({bt_summary.get('n_issues', 0)} fechas de emisión), la redención "
                f"media realizada fue {bt_summary.get('expected_nominal_payout', 1):.1%} del nominal "
                f"(TIR media {bt_summary.get('mean_irr', 0):.1%}); redimió por encima de la par en el "
                f"{bt_summary.get('prob_above_par', 0):.0%} de los casos y por debajo en el "
                f"{bt_summary.get('prob_knock_in_total', bt_summary.get('prob_below_par', 0)):.1%}.")
        elif bt_summary:
            b.append(
                f"En el backtest histórico ({bt_summary.get('n_issues', 0)} fechas de emisión), la TIR media "
                f"realizada fue {bt_summary.get('mean_irr', 0):.1%} (mediana {bt_summary.get('median_irr', 0):.1%}), "
                f"con autocall en el {bt_summary.get('prob_called', 0):.0%} de los casos y knock-in en el "
                f"{bt_summary.get('prob_knock_in', 0):.1%}.")
        if live_data:
            b.append(
                f"Desde emisión, el worst-of cotiza al {live_data.get('wof_today', 0):.1%} del strike "
                f"({live_data.get('worst_asset', '')} es el peor activo); la TIR de cupones a fecha es "
                f"{live_data.get('irr_to_date', 0):.1%} anualizada.")
    else:
        if _has_mc:
            b.append(
                f"Monte Carlo simulation (multi-asset Heston model, "
                f"{len(results.get('annualized_returns', [])):,} paths) estimates an expected simple "
                f"annualised IRR of {results.get('expected_irr', 0):.1%} and an expected total return of "
                f"{results.get('expected_total_return', 0):.1%} over the {terms.maturity:g}-year tenor.")
            if getattr(terms, "note_type", "") == "participation":
                b.append(
                    f"Expected redemption at maturity is {results.get('expected_nominal_payout', 1):.1%} of notional; "
                    f"the probability of redeeming below par is {results.get('prob_knock_in_total', 0):.1%} "
                    f"and above par {results.get('prob_above_par', 0):.0%}.")
            else:
                b.append(
                    f"The probability of early redemption (autocall) is {results.get('prob_autocall', 0):.0%}; "
                    f"the probability of capital loss at maturity (knock-in without rescue) is "
                    f"{results.get('prob_knock_in_total', 0):.1%} against a {terms.knock_in_barrier:.1%} barrier.")
        if bt_summary and getattr(terms, "note_type", "") == "participation":
            b.append(
                f"Across {bt_summary.get('n_issues', 0)} historical issue dates, the realised mean redemption "
                f"was {bt_summary.get('expected_nominal_payout', 1):.1%} of notional "
                f"(mean IRR {bt_summary.get('mean_irr', 0):.1%}); it redeemed above par in "
                f"{bt_summary.get('prob_above_par', 0):.0%} of cases and below par in "
                f"{bt_summary.get('prob_knock_in_total', bt_summary.get('prob_below_par', 0)):.1%}.")
        elif bt_summary:
            b.append(
                f"Across {bt_summary.get('n_issues', 0)} historical issue dates, the realised mean IRR was "
                f"{bt_summary.get('mean_irr', 0):.1%} (median {bt_summary.get('median_irr', 0):.1%}); the note "
                f"autocalled in {bt_summary.get('prob_called', 0):.0%} of cases and knocked in on "
                f"{bt_summary.get('prob_knock_in', 0):.1%}.")
        if live_data:
            b.append(
                f"Since issue, the worst-of trades at {live_data.get('wof_today', 0):.1%} of strike "
                f"({live_data.get('worst_asset', '')} is the worst performer); coupon IRR to date is "
                f"{live_data.get('irr_to_date', 0):.1%} annualised.")
    return b


def _cover_left_photo(pdf: "_NotePDF", x0: float, top: float, w: float,
                      bottom: float, img: bytes) -> bool:
    """Fill the summary page's short left column with a tall (portrait) brand
    photo so a client / terms-only report doesn't leave that column half-empty.
    Mirrors the in-body egregious-void band treatment (brand tint + lime accent
    rule + corner sigil) but vertical. Returns True on success; False to fall
    back to the lighter hex/sigil composition."""
    try:
        avail = bottom - top
        if avail < 58.0 or w < 40.0:
            return False
        cropped = _cover_crop(img, w / avail) or img
        # Re-encode as JPEG so a photo on the cover doesn't bloat the PDF.
        try:
            from PIL import Image
            _im = Image.open(io.BytesIO(cropped)).convert("RGB")
            _buf = io.BytesIO(); _im.save(_buf, "JPEG", quality=80, optimize=True)
            cropped = _buf.getvalue()
        except Exception:
            pass
        pdf.image(io.BytesIO(cropped), x=x0, y=top, w=w, h=avail)
        # Light brand tint so the photo harmonises with the palette without
        # hiding it — meant to read as an image, not a colour block.
        tint = getattr(pdf, "cover_overlay_color", pdf.primary_color)
        with pdf.local_context(fill_opacity=0.26):
            pdf.set_fill_color(*tint)
            pdf.rect(x0, top, w, avail, style="F")
        # Darker brand wash along the bottom edge grounds the band + corner sigil.
        with pdf.local_context(fill_opacity=0.34):
            pdf.set_fill_color(*pdf.ink)
            pdf.rect(x0, bottom - 18.0, w, 18.0, style="F")
        # Lime accent rule across the top edge — the brand's signature line.
        pdf.set_fill_color(*pdf.lime)
        pdf.rect(x0, top, w, 1.5, style="F")
        # White-knockout sigil tucked into the bottom-left corner.
        sig = getattr(pdf, "cover_sigil_bytes", None)
        if sig:
            from PIL import Image
            iw, ih = Image.open(io.BytesIO(sig)).size
            sh = min(avail * 0.30, 24.0); sw = sh * iw / ih
            with pdf.local_context(fill_opacity=0.55):
                pdf.image(io.BytesIO(sig), x=x0 + 5.0, y=bottom - sh - 4.0,
                          w=sw, h=sh)
        return True
    except Exception:
        return False


def _mat_label(terms) -> str:
    """Maturity for display. The term sheet stores it in YEARS (the JSON contract
    and what the quant core computes on); tenors are quoted in MONTHS, so convert
    only here, at the render boundary. e.g. 1.5 -> "18M"."""
    return f"{round(float(terms.maturity) * 12)}M"


def _draw_logo_fit(pdf, logo_b, x: float, y: float, max_h: float, max_w: float,
                   *, cover: bool = False) -> None:
    """Draw a logo at (x, y) fit inside (max_w, max_h) preserving aspect — never
    stretched. The cover wordmark uses its OWN aspect (cover_logo_aspect), not the
    header logo's, so a wide cover logo isn't squished into the header's box."""
    if not logo_b:
        return
    if cover and getattr(pdf, "cover_logo_bytes", None):
        asp = getattr(pdf, "cover_logo_aspect", None) or pdf.firm_logo_aspect
    else:
        asp = pdf.firm_logo_aspect
    asp = asp or 1.0
    h, w = max_h, max_h * asp
    if w > max_w:
        w, h = max_w, (max_w / asp if asp else max_h)
    try:
        pdf.image(io.BytesIO(logo_b), x=x, y=y, w=w, h=h)
    except Exception:
        pass


def _cover_fill(pdf: _NotePDF):
    """The active theme's `cover.fill`, or None when it declares nothing."""
    spec = getattr(getattr(pdf, "theme", None), "spec", None)
    if isinstance(spec, dict):
        return (spec.get("cover") or {}).get("fill")
    return None


def _paint_cover_overlay(pdf: _NotePDF, W: float, H: float) -> None:
    """Tint a full-bleed photo with the cover's colour identity.

    A cover photo is drawn opaque over the whole page, so it completely hides
    the background painted underneath — which means the tint drawn ON TOP of the
    photo is the only thing that carries the cover's colour. That tint IS the
    theme's cover-background fill at the configured opacity: a gradient tints as
    a gradient, a radial as a radial, a solid as that solid colour. The photo
    and the themed background compose (photo shows through at opacity < 1)
    instead of the photo throwing the fill away.

    There is deliberately a SINGLE source for the cover's colour — the theme's
    `cover.fill`, edited under "Cover page background". A brand's legacy flat
    `cover_overlay_color` is only the fallback tint when the theme declares no
    cover fill at all, so old configs still render and a themeless brand keeps a
    legible primary wash over its photo.
    """
    op = getattr(pdf, "cover_overlay_opacity", 0.0)
    if not op or op <= 0:
        return
    fill = _cover_fill(pdf)
    if isinstance(fill, dict) and fill.get("type") in ("linear", "radial"):
        try:
            paint_shape(pdf, 0, 0, W, H, {"kind": "square"}, fill, opacity=op)
            return
        except Exception:
            pass
    if isinstance(fill, dict) and fill.get("type") == "solid":
        try:
            pdf.set_fill_color(*resolve_color(fill.get("color", "primary"), pdf))
        except Exception:
            pdf.set_fill_color(*getattr(pdf, "cover_overlay_color", pdf.primary_color))
    else:
        pdf.set_fill_color(*getattr(pdf, "cover_overlay_color", pdf.primary_color))
    try:
        with pdf.local_context(fill_opacity=op):
            pdf.rect(0, 0, W, H, style="F")
    except Exception:
        pass


def _paint_cover_bg(pdf: _NotePDF, W: float, H: float) -> None:
    """Fill a full-bleed page with the theme's cover background — a solid brand
    colour by default, or a gradient when the active theme spec sets
    `cover.fill`. Falls back to solid primary if anything is off."""
    fill = _cover_fill(pdf)
    try:
        if fill and fill.get("type") in ("linear", "radial"):
            paint_shape(pdf, 0, 0, W, H, {"kind": "square"}, fill)
            return
        if fill and fill.get("type") == "solid":
            pdf.set_fill_color(*resolve_color(fill.get("color", "primary"), pdf))
            pdf.rect(0, 0, W, H, style="F")
            return
    except Exception:
        pass
    pdf.set_fill_color(*pdf.primary_color)
    pdf.rect(0, 0, W, H, style="F")


def _front_cover_page(pdf: _NotePDF, terms, lang: str, report_title: str, website: str,
                      report_kind: str | None = None):
    """Full-bleed branded cover (page 1, toggleable): brand-colour background, the
    centred firm logo, a 'Nota Estructurada' eyebrow, the note name and the report
    month — modelled on the CADIEM cover. Uses the brand palette + logo; a brand
    may also supply `cover_image_base64` for a full-bleed background photo.

    `report_kind` (the audience preset the report was built for) is stamped under
    the note as a report-type subtitle — "Risk report", "Client report", … — so a
    printed PDF says what kind of report it is. Unknown/None ⇒ no subtitle."""
    import re
    pdf.set_auto_page_break(auto=False)
    pdf._is_cover = True
    pdf.add_page()
    pdf._cover_pages.add(pdf.page_no())
    W, H = pdf.w, pdf.h
    cx = W / 2

    # Full-bleed background: brand primary colour (or a theme gradient), or an
    # optional photo with a colour overlay at the configured opacity (so text
    # stays legible over it).
    _paint_cover_bg(pdf, W, H)
    if getattr(pdf, "cover_image_bytes", None):
        try:
            _cov = _cover_crop(pdf.cover_image_bytes, W / H)
            pdf.image(io.BytesIO(_cov), x=0, y=0, w=W, h=H)
        except Exception:
            pass
        _paint_cover_overlay(pdf, W, H)

    ml = pdf.l_margin
    inner = W - 2 * ml
    # Faint sigil/arcs motif, bleeding off the top-right (decorative, like the
    # prototype). Knocked white via the brand's white sigil when supplied.
    sig_b = getattr(pdf, "cover_sigil_bytes", None)
    if sig_b:
        try:
            # Size / position / opacity are brand-overridable (% of page); absent
            # values reproduce the original top-right bleed at 0.22 opacity.
            _ssz = getattr(pdf, "cover_sigil_size_pct", None)
            sw = W * (_ssz / 100.0) if _ssz is not None else W * 0.58
            sh = sw * _logo_aspect(sig_b, default=1.0)
            _sx = getattr(pdf, "cover_sigil_x_pct", None)
            _sy = getattr(pdf, "cover_sigil_y_pct", None)
            sx = W * (_sx / 100.0) if _sx is not None else (W - sw * 0.62)
            sy = H * (_sy / 100.0) if _sy is not None else (-sh * 0.30)
            _sop = getattr(pdf, "cover_sigil_opacity", None)
            op = _sop if _sop is not None else 0.22
            with pdf.local_context(fill_opacity=op):
                pdf.image(io.BytesIO(sig_b), x=sx, y=sy, w=sw, h=sh)
        except Exception:
            pass

    # Logo (white wordmark) top-left. A brand may supply a white knockout logo
    # (`cover_logo_base64`); otherwise the normal logo is used. Position (% of
    # page) and size (% of page width) are brand-overridable; the size % is the
    # max WIDTH, with the max height kept at the original 16:90 box ratio so the
    # default reproduces the original 16×90 mm fit box exactly.
    logo_b = getattr(pdf, "cover_logo_bytes", None) or pdf.firm_logo_bytes
    _lsz = getattr(pdf, "cover_logo_size_pct", None)
    _max_w = W * (_lsz / 100.0) if _lsz is not None else 90.0
    _max_h = _max_w * (16.0 / 90.0)
    _lx = getattr(pdf, "cover_logo_x_pct", None)
    _ly = getattr(pdf, "cover_logo_y_pct", None)
    _logo_x = W * (_lx / 100.0) if _lx is not None else ml
    _logo_y = H * (_ly / 100.0) if _ly is not None else H * 0.07
    _draw_logo_fit(pdf, logo_b, _logo_x, _logo_y, _max_h, _max_w, cover=True)

    # Hero block, left-aligned in the lower-middle of the page.
    eb = (report_title or _t("report_eyebrow", lang)).upper()
    hero_y = H * 0.40
    pdf._eyebrow(ml, hero_y, eb, pdf.section_rule_color,
                 size=11.0, tracking=1.6, w=inner)
    # Big white Neulis title — wraps to as many lines as needed.
    _name = _safe(terms.name)
    _ts = 40.0
    pdf._sf(_ts, "bold")
    while _ts > 22.0 and pdf.get_string_width(_name) > inner * 2.4:
        _ts -= 1.0
        pdf._sf(_ts, "bold")
    pdf.set_xy(ml, hero_y + 9)
    pdf.set_text_color(255, 255, 255)
    pdf.multi_cell(inner, _ts * 0.40, _name, align="L")
    # Underlyings sub-line (muted mint) — symbols or display names per branding.
    _tk = " / ".join(_underlying_labels(pdf, terms))
    if _tk:
        pdf.ln(2)
        pdf.set_x(ml)
        pdf._sf(13, "regular")
        pdf.set_text_color(159, 196, 179)
        pdf.cell(inner, 7, _safe(_tk))
    # Short lime rule beneath.
    pdf.ln(8)
    pdf.set_fill_color(*pdf.section_rule_color)
    pdf.rect(ml, pdf.get_y(), 22, 1.6, style="F")

    # Report-type subtitle under the rule ("Risk report", "Client report", …).
    _kind_lbl = _LABELS.get(f"kind_{report_kind}") if report_kind else None
    if _kind_lbl:
        pdf.ln(6)
        pdf._eyebrow(ml, pdf.get_y(), _t(f"kind_{report_kind}", lang).upper(),
                     pdf.section_rule_color, size=9.0, tracking=1.4, w=inner)

    # ── Bottom band: user-selectable key terms + website ──────────────────
    # Which figures appear here (and their order) is driven by branding
    # `cover_metrics`: absent → the classic three; an explicit (possibly empty)
    # list → exactly those, so the whole strip can be turned off. Capped to what
    # the strip fits alongside the website.
    band_h = 30.0
    band_y = H - band_h
    pdf.set_fill_color(*pdf.ink)
    pdf.rect(0, band_y, W, band_h, style="F")
    _ki_lbl = _t("ki_barrier", lang).split(' (')[0]
    _part = _is_participation(terms)
    _cap_v = _part_cap_value(terms)
    _fcat = {
        "maturity":         (_t("maturity", lang),         _mat_label(terms)),
        "coupon_pa":        (_t("coupon_pa", lang),        f"{terms.coupon_pa * 100:.2f}%"),
        "coupon_barrier":   (_t("coupon_barrier", lang),   f"{terms.coupon_barrier:.0%}"),
        "autocall_barrier": (_t("autocall_barrier", lang), f"{terms.autocall_barrier:.0%}"),
        "knock_in_barrier": (_ki_lbl,                      f"{terms.knock_in_barrier:.0%}"),
        # Participation payoff metrics (shown in place of coupon/knock-in on a
        # participation note, where those are 0 and meaningless).
        "protection_level": (_t("protection_level", lang), f"{float(getattr(terms, 'protection_level', 1.0) or 1.0):.0%}"),
        "participation_rate": (_t("participation_rate", lang), f"{float(getattr(terms, 'participation_rate', 1.0) or 1.0):.0%}"),
        "upside_cap":       (_t("period_cap" if getattr(terms, "participation_periodic", False) else "upside_cap", lang),
                             f"{_cap_v:.0%}" if _cap_v is not None else ""),
        "issue_date":       (_t("issue_date", lang),       str(getattr(terms, "issue_date", "") or "")),
        "issuer":           (_t("issuer", lang),           getattr(pdf, "issuer", "") or ""),
    }
    _sel = getattr(pdf, "cover_metrics", None)
    if _sel is not None:
        _keys = list(_sel)
    elif _part:
        # Participation default: protection + participation + (cap or maturity).
        _keys = (["protection_level", "participation_rate", "upside_cap"]
                 if _cap_v is not None else ["protection_level", "participation_rate", "maturity"])
    else:
        _keys = ["coupon_pa", "maturity", "knock_in_barrier"]
    _kt = [_fcat[k] for k in _keys if k in _fcat and _fcat[k][1] != ""][:4]
    if _kt:
        web_w = 54.0 if website else 0.0
        span  = (W - 2 * ml) - web_w
        step  = min(48.0, span / len(_kt))
        cellw = step - 2.0
        kx = ml
        for lbl, val in _kt:
            pdf._eyebrow(kx, band_y + 9, lbl, (159, 196, 179), size=7.5,
                         tracking=0.4, w=cellw)
            pdf.set_xy(kx, band_y + 14)
            pdf._sf(15, "bold"); pdf.set_text_color(255, 255, 255)
            pdf.cell(cellw, 8, _safe(val))
            kx += step
    if website:
        pdf._eyebrow(W - ml - 70, band_y + 12.5, website, pdf.section_rule_color,
                     size=10.0, tracking=0.6, w=70, align="R")
    pdf._is_cover = False


def _full_bleed_disclaimer(pdf: _NotePDF, lang: str, text: str, website: str = ""):
    """Disclaimer as a branded full-bleed back page — white text on the brand
    colour with the logo header and a footer, pairing the branded front cover."""
    pdf.set_auto_page_break(auto=False)
    pdf._is_cover = True
    pdf.add_page()
    pdf._cover_pages.add(pdf.page_no())
    W, H = pdf.w, pdf.h
    _paint_cover_bg(pdf, W, H)

    # Optional full-bleed photo with a colour overlay (mirrors the front cover) so
    # the back page matches the cover treatment.
    if getattr(pdf, "back_image_bytes", None):
        try:
            _bk = _cover_crop(pdf.back_image_bytes, W / H)
            pdf.image(io.BytesIO(_bk), x=0, y=0, w=W, h=H)
        except Exception:
            pass
        _paint_cover_overlay(pdf, W, H)

    logo_b = getattr(pdf, "cover_logo_bytes", None) or pdf.firm_logo_bytes
    _draw_logo_fit(pdf, logo_b, pdf.l_margin, 15, 12.0, 58.0, cover=True)
    pdf.set_draw_color(*pdf.section_rule_color)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, 33, W - pdf.r_margin, 33)

    inner = W - pdf.l_margin - pdf.r_margin
    _paras = (text or "").split("\n\n")

    # Backing panel behind the title + body so the white legal text stays legible
    # over the photo (which can be light in places). A darkened brand-colour card,
    # semi-opaque and rounded like the figure cards — measured to fit the text.
    if _paras and _paras[0]:
        body_h = 0.0
        try:
            from fpdf.enums import MethodReturnValue as _MRV
            for _i, _para in enumerate(_paras):
                pdf._sf(7.6, "bold" if _i == len(_paras) - 1 else "regular")
                body_h += pdf.multi_cell(inner, 4.0, _safe(_para), align="J",
                                         dry_run=True, output=_MRV.HEIGHT) + 2.6
        except Exception:
            body_h = H * 0.42   # generous fallback if measurement isn't available
        ptop, pbot = 37.0, min(54.0 + body_h + 6.0, H - 26.0)
        pdf.set_fill_color(*_blend(pdf.primary_color, (0, 0, 0), 0.68))   # near-black green
        try:
            with pdf.local_context(fill_opacity=0.86):
                pdf.rect(pdf.l_margin - 6, ptop, inner + 12, pbot - ptop,
                         style="F", round_corners=True, corner_radius=4)
        except Exception:
            try:
                pdf.rect(pdf.l_margin - 6, ptop, inner + 12, pbot - ptop, style="F")
            except Exception:
                pass

    pdf.set_xy(pdf.l_margin, 41)
    pdf._sf(16, "bold")
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, _safe(_t("disclaimer_title", lang)), new_x="LMARGIN", new_y="NEXT")
    # Lime keyline under the title (mirrors the prototype).
    pdf.set_fill_color(*pdf.section_rule_color)
    pdf.rect(pdf.l_margin, 50.5, 18, 1.4, style="F")

    pdf.set_xy(pdf.l_margin, 55)
    for _i, _para in enumerate(_paras):
        pdf.set_x(pdf.l_margin)
        pdf._sf(7.6, "bold" if _i == len(_paras) - 1 else "regular")
        pdf.set_text_color(255, 255, 255)
        pdf.multi_cell(inner, 4.0, _safe(_para), align="J")
        pdf.ln(2.6)

    # Footer: lime top hairline, website in lime, grey copyright (prototype).
    pdf.set_fill_color(*pdf.section_rule_color)
    try:
        with pdf.local_context(fill_opacity=0.4):
            pdf.rect(pdf.l_margin, H - 26, W - 2 * pdf.l_margin, 0.4, style="F")
    except Exception:
        pdf.rect(pdf.l_margin, H - 26, W - 2 * pdf.l_margin, 0.4, style="F")
    if website:
        pdf.set_xy(0, H - 22)
        pdf._sf(9, "bold")
        pdf.set_text_color(*pdf.section_rule_color)
        pdf.cell(W - pdf.r_margin, 5, _safe(website), align="R")
    pdf.set_xy(0, H - 15)
    pdf._sf(7, "light")
    pdf.set_text_color(159, 196, 179)
    pdf.cell(W - pdf.r_margin, 4,
             _safe(f"© {datetime.date.today().year} {pdf.firm_name} — All Rights Reserved."),
             align="R")
    pdf._is_cover = False


# ──────────────────────────────────────────────────────────────────────────────
# Report outline — the single source of the chapter numbers
# ──────────────────────────────────────────────────────────────────────────────
# The cover's "In this report" list and the numbered heads in the body used to
# count independently, and agreed on nothing past the first entry. The cover
# numbered every LEAF (01 Note Terms · 02 Underlying Breakdown · 03 Payoff &
# Distribution · …) while the body numbered CHAPTERS from hard-coded literals
# (01 Note Terms · 03 Underlying · 04 Monte Carlo · 05 Backtest · …). So the
# cover's "04 Price Paths" and the body's "04 · Monte Carlo" were different
# things, the body skipped a number whenever a chapter was toggled off (no
# issuer ⇒ 01 then 03), and the Comparison chapter was numbered in the body but
# missing from the list altogether.
#
# Both surfaces now read `_plan_chapters`. A number printed on a page and the
# same number in the contents list cannot drift, and toggling a chapter off
# renumbers both. Sub-sections inside a lens are deliberately NOT numbered —
# they carry no number in the body either, so numbering them in the list was
# what invented the second, conflicting sequence.
_CHAPTERS = ("note_terms", "issuer", "underlying", "mc", "bt", "live", "compare")


def _plan_chapters(present: dict) -> dict:
    """`{chapter_key: bool}` → `{chapter_key: "01"}`, numbered in document order.

    Absent/false chapters get no entry, so a caller that renders a chapter it
    did not declare present prints an empty number rather than a wrong one.
    """
    out, n = {}, 0
    for key in _CHAPTERS:
        if present.get(key):
            n += 1
            out[key] = f"{n:02d}"
    return out


# Which projected metrics the A/B table reports, and how to format each.
_CMP_LBL = {
    "expected_irr":            ("expected_irr",        "pct"),
    "expected_total_return":   ("total_return_short",  "pct"),
    "expected_coupon":         ("expected_coupon",     "pct"),
    "expected_nominal_payout": ("expected_redemption", "pct"),
    "prob_autocall":           ("prob_autocall",       "pct"),
    "prob_knock_in_total":     ("prob_knock_in",       "pct"),
    "avg_time_to_autocall":    ("avg_time_autocall",   "months"),
    "expected_gain":           ("expected_gain",       "pct"),
    "prob_above_par":          ("p_above_par",         "pct"),
    "prob_at_cap":             ("p_at_cap",            "pct"),
    "prob_knocked_out":        ("p_knocked_out",       "pct"),
    "p5_redemption":           ("p5_redemption",       "pct"),
    "prob_loss":               ("p_loss",              "pct"),
    "cost_basis":              ("cost_basis",          "pct"),
}


def _compare_tables(terms, compare_data, lang: str):
    """`(differing-terms rows, projected-metric rows)` for the Comparison chapter.

    Pure data prep, split out from the rendering block because the outline has to
    know whether the chapter has any content before the contents page is drawn —
    a comparison whose tables are both empty is not a chapter.
    """
    if not compare_data:
        return [], []

    diff_terms = []
    terms_b = compare_data.get("terms_b")
    if terms_b is not None:
        rows_a = _term_rows(terms, lang)
        map_b  = dict(_term_rows(terms_b, lang))
        diff_terms = [[lbl, av, map_b.get(lbl, "—")]
                      for lbl, av in rows_a if map_b.get(lbl, "—") != av]

    def _val(v, kind):
        if v is None or v != v:                                   # nan-safe
            return "—"
        return f"{v * 12:.1f} mo" if kind == "months" else f"{v:.2%}"

    def _dlt(d, kind):
        if d is None or d != d:
            return "—"
        sgn = "+" if d >= 0 else ""
        return f"{sgn}{d * 12:.1f} mo" if kind == "months" else f"{sgn}{d:.2%}"

    cmp_rows = []
    for r in compare_data.get("diff", {}).get("rows", []):
        m = _CMP_LBL.get(r.get("key"))
        if not m:
            continue
        lbl, kind = m
        cmp_rows.append([_t(lbl, lang), _val(r.get("a"), kind),
                         _val(r.get("b"), kind), _dlt(r.get("delta"), kind)])
    return diff_terms, cmp_rows


def _cover_page(
    pdf: _NotePDF,
    terms,
    results,
    asset_names: list[str],
    bt_summary,
    live_data,
    lang: str,
    logo_urls: dict[str, str] | None,
    issuer_logo_bytes: bytes | None,
    logo_tickers: dict[str, str] | None = None,
    inc=None,
    logo_overrides: dict[str, bytes] | None = None,
    chapters: dict | None = None,
    cmp_terms: bool = False,
    cmp_metrics: bool = False,
):
    # inc(section_key) -> bool: which optional sections are included, so the
    # cover "In this report" list matches the body. Defaults to all-on.
    if inc is None:
        inc = lambda _k: True
    pdf._is_cover = True
    # No auto-page-break: the summary is a single designed page — overflow must
    # never spill a blank page 2 (the TOC compresses to fit instead).
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    # Remember which page is the cover so footer() suppresses the running footer
    # there even after _is_cover is reset (footer fires lazily on the next page).
    pdf._cover_pages.add(pdf.page_no())

    x0 = pdf.l_margin
    W  = pdf.w - pdf.l_margin - pdf.r_margin
    eyebrow    = (pdf.report_title or _t("report_eyebrow", lang)).upper()
    INK_SUB    = (159, 196, 179)   # muted mint for sub-text on the ink masthead
    KV_GREY    = (80, 90, 84)      # key-term label grey-green

    def _ul_colors(n):
        base = [pdf.primary_color, pdf.teal,
                _blend(pdf.primary_color, pdf.lime, 0.55),
                pdf.amber_dark, _blend(pdf.teal, _BLACK, 0.30)]
        return [base[i % len(base)] for i in range(max(1, n))]

    # ── Header — logo left, eyebrow right, 2px primary rule ─────────────────
    has_logo = False
    if pdf.firm_logo_bytes:
        try:
            lh = 11.0
            lw = min(lh * pdf.firm_logo_aspect, 60.0)
            pdf.image(io.BytesIO(pdf.firm_logo_bytes), x=x0, y=8.5, w=lw, h=lh)
            has_logo = True
        except Exception:
            has_logo = False
    if not has_logo:
        pdf.set_xy(x0, 10)
        pdf._sf(14, "bold"); pdf.set_text_color(*pdf.primary_color)
        pdf.cell(120, 8, _safe(pdf.firm_name))
    rx, rw = pdf.w - pdf.r_margin - 95, 95
    pdf._eyebrow(rx, 12.5, eyebrow, pdf.primary_color, size=8.0, tracking=0.8,
                 w=rw, align="R")
    pdf.set_draw_color(*pdf.primary_color); pdf.set_line_width(0.7)
    pdf.line(x0, 23.5, pdf.w - pdf.r_margin, 23.5)

    # ── Masthead — dark chamfer panel with a KPI strip when analytics exist ──
    # The analytical KPIs (IRR / autocall / knock-in / mean historical IRR) show
    # whenever the report carries Monte-Carlo or backtest output; a client /
    # terms-only report has no analysis, so the masthead stays compact. The
    # theme's decorative accent bar along the bottom edge is deliberately NOT
    # drawn here (see the mercator spec) — the strip is the KPIs alone.
    _has_mc = len(results.get("annualized_returns", [])) > 0
    _show_kpis = _has_mc or bool(bt_summary)
    y_m, pad = 28.5, 9.0
    MH = 58.0 if _show_kpis else 34.0
    pdf.theme.cover_masthead(pdf, x0, y_m, W, MH)
    pdf._eyebrow(x0 + pad, y_m + 7, eyebrow, pdf.lime,
                 size=8.0, tracking=0.9, w=W - 2 * pad)
    # Title (Neulis): one big line, shrinking to fit; if a very long note name
    # still overflows at the floor, wrap it onto two smaller lines.
    _name = _safe(terms.name)
    avail = W - 2 * pad
    _ts = 21.0
    pdf._sf(_ts, "bold")
    while _ts > 13.0 and pdf.get_string_width(_name) > avail:
        _ts -= 0.4
        pdf._sf(_ts, "bold")
    pdf.set_text_color(*_WHITE)
    if pdf.get_string_width(_name) <= avail:
        pdf.set_xy(x0 + pad, y_m + 12)
        pdf.cell(avail, 10, _name)
        _sub_y = y_m + 24
    else:
        pdf._sf(14.0, "bold")
        pdf.set_xy(x0 + pad, y_m + 9.5)
        pdf.multi_cell(avail, 6.0, _name, align="L")
        _sub_y = pdf.get_y() + 1.5
    _tk = " / ".join(_underlying_labels(pdf, None, asset_names or [], logo_tickers))
    _sub = pdf.report_title or _t("series_title", lang)
    if _tk:
        _sub = f"{_sub}  ·  {_tk}"
    pdf.set_xy(x0 + pad, _sub_y)
    pdf._sf(9.5, "regular"); pdf.set_text_color(*INK_SUB)
    pdf.cell(W - 2 * pad, 5, _safe(_sub))

    # KPI strip — analytical only (Monte Carlo and/or backtest). Skipped for a
    # client / terms-only report (compact masthead), where these would just echo
    # the key-terms rail.
    if _show_kpis:
        if _has_mc and getattr(terms, "note_type", "") == "participation":
            kpis = [(_t("expected_redemption", lang), f"{results.get('expected_nominal_payout', 1):.2%}"),
                    (_t("expected_irr", lang),        f"{results.get('expected_irr', 0):.2%}"),
                    (_t("p_below_par", lang),         f"{results.get('prob_knock_in_total', 0):.2%}"),
                    (_t("p_above_par", lang),         f"{results.get('prob_above_par', 0):.1%}")]
        elif _has_mc:
            kpis = [(_t("expected_irr", lang),  f"{results.get('expected_irr', 0):.2%}"),
                    (_t("prob_autocall", lang), f"{results.get('prob_autocall', 0):.1%}"),
                    (_t("prob_knock_in", lang), f"{results.get('prob_knock_in_total', 0):.2%}")]
            if bt_summary:
                kpis.append((_t("mean_hist_irr", lang), f"{bt_summary.get('mean_irr', 0):.2%}"))
            else:
                kpis.append((_t("expected_total_return", lang),
                             f"{results.get('expected_total_return', 0):.2%}"))
        else:  # backtest only
            kpis = [(_t("mean_hist_irr", lang),  f"{bt_summary.get('mean_irr', 0):.2%}"),
                    (_t("p_autocall", lang),     f"{bt_summary.get('prob_called', 0):.1%}"),
                    (_t("prob_knock_in", lang),  f"{bt_summary.get('prob_knock_in', 0):.2%}"),
                    (_t("coupon_pa", lang),      f"{terms.coupon_pa * 100:.2f}%")]

        strip_y = y_m + MH - 24
        pdf.set_fill_color(*_blend(pdf.ink, _WHITE, 0.18))
        pdf.rect(x0 + pad, strip_y, W - 2 * pad, 0.3, style="F")
        kw = (W - 2 * pad) / len(kpis)
        for i, (lbl, val) in enumerate(kpis):
            cx = x0 + pad + i * kw
            pdf.set_fill_color(*pdf.lime)
            pdf.rect(cx, strip_y + 4, 0.8, 14, style="F")
            pdf.set_xy(cx + 3, strip_y + 4)
            pdf._sf(6.3, "body_bold"); pdf.set_text_color(*INK_SUB)
            pdf.multi_cell(kw - 4, 3.1, _safe(lbl.upper()), align="L")
            pdf.set_xy(cx + 3, strip_y + 12)
            pdf._sf(13.5, "bold"); pdf.set_text_color(*_WHITE)
            pdf.cell(kw - 4, 7, _safe(val))

    # ── Body: two vertical stacks (left ≈ 100mm, right rail ≈ 70mm) ─────────
    Lw, Rx, Rw = 100.0, x0 + 108.0, W - 108.0
    y_body = y_m + MH + 7.0
    ly = ry = y_body

    def _l_head(y, text):
        pdf._eyebrow(x0, y, text, pdf.muted, size=8.0, tracking=0.6, w=Lw)
        pdf.set_fill_color(*pdf.lime)
        pdf.rect(x0, y + 4.6, 18, 1.2, style="F")
        return y + 8.5

    # 1) Executive summary (only when there are bullets).
    _exec = list(_exec_bullets(terms, results, bt_summary, live_data, lang))
    if _exec:
        ly = _l_head(ly, _t("exec_summary", lang))
        for txt in _exec:
            pdf.set_fill_color(*pdf.primary_color)
            pdf.ellipse(x0, ly + 1.7, 1.5, 1.5, style="F")
            pdf.set_xy(x0 + 5, ly)
            pdf._sf(8.2, "regular"); pdf.set_text_color(*pdf.body_ink)
            pdf.multi_cell(Lw - 5, 4.4, _safe(txt), align="L")
            ly = pdf.get_y() + 2.0
        ly += 2.5

    # 2) About this report.
    ly = _l_head(ly, _t("about_report_head", lang))
    pdf.set_xy(x0, ly)
    pdf._sf(8.0, "regular"); pdf.set_text_color(*pdf.body_ink)
    pdf.multi_cell(Lw, 4.3, _safe(_about_this_report(
        lang, inc, results, bt_summary, live_data, len(asset_names or []))))
    ly = pdf.get_y() + 5.0

    # 3) Payoff scenarios panel (only when the sim ran). A participation note has no
    #    autocall/coupon ladder, so it shows redemption outcomes (above / at / below
    #    par) with an expected-redemption footer instead of per-scenario IRRs.
    if _has_mc and _is_participation(terms):
        p_below = float(results.get("prob_knock_in_total", 0.0))   # below par = capital loss
        p_above = float(results.get("prob_above_par", 0.0))
        p_at    = max(0.0, 1.0 - p_below - p_above)
        prows = [
            (_t("outcome_above_par", lang), f"{p_above:.1%}", pdf.primary_color),
            (_t("outcome_at_par", lang),    f"{p_at:.1%}",    pdf.teal),
            (_t("outcome_below_par", lang), f"{p_below:.1%}", pdf.amber),
        ]
        _foot = (f"{_t('expected_redemption', lang)} {results.get('expected_nominal_payout', 1):.1%}"
                 f"  ·  {_t('expected_irr', lang)} {results.get('expected_irr', 0):+.1%}")
        ph = 10.5 + len(prows) * 8.0 + 8.0
        pdf.set_fill_color(*pdf.panel_color)
        try:
            pdf.rect(x0, ly, Lw, ph, style="F", round_corners=True, corner_radius=2)
            pdf.set_fill_color(*pdf.primary_color)
            pdf.rect(x0, ly, Lw, 1.1, style="F",
                     round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=2)
        except TypeError:
            pdf.rect(x0, ly, Lw, ph, style="F")
            pdf.set_fill_color(*pdf.primary_color)
            pdf.rect(x0, ly, Lw, 1.1, style="F")
        pdf._eyebrow(x0 + 4, ly + 4, _t("redemption_outcomes", lang), pdf.muted,
                     size=7.0, tracking=0.4, w=70)
        pdf._eyebrow(x0 + Lw - 30, ly + 4.2, _t("payoff_prob", lang),
                     _FOOTNOTE_GREY, size=5.6, tracking=0.2, w=26, align="R")
        yy = ly + 10.5
        for lab, p, col in prows:
            pdf.set_draw_color(*_RULE_SOFT); pdf.set_line_width(0.2)
            pdf.line(x0 + 4, yy, x0 + Lw - 4, yy)
            pdf.set_fill_color(*col)
            pdf.rect(x0 + 4, yy + 2.7, 2.4, 2.4, style="F")
            pdf.set_xy(x0 + 9, yy + 1.5)
            pdf._sf(8.2, "regular"); pdf.set_text_color(*pdf.body_ink)
            pdf.cell(Lw - 9 - 30, 5, _safe(lab))
            pdf.set_xy(x0 + Lw - 32, yy + 1.4)
            pdf._sf(10.0, "bold"); pdf.set_text_color(*col)
            pdf.cell(28, 5, _safe(p), align="R")
            yy += 8.0
        # Footer: expected redemption / IRR (whole-note aggregate).
        pdf.set_draw_color(*_RULE_SOFT); pdf.set_line_width(0.2)
        pdf.line(x0 + 4, yy, x0 + Lw - 4, yy)
        pdf.set_xy(x0 + 9, yy + 1.6)
        pdf._sf(7.4, "regular"); pdf.set_text_color(*KV_GREY)
        pdf.cell(Lw - 13, 5, _safe(_foot))
        ly += ph + 5.0
    elif _has_mc:
        ar = np.asarray(results.get("annualized_returns", []), dtype=float)
        _ap = results.get("autocall_period")
        ap = np.asarray(_ap, dtype=int) if _ap is not None else np.array([], dtype=int)
        p_ac = float(results.get("prob_autocall", 0.0))
        p_ki = float(results.get("prob_knock_in_total", 0.0))
        p_held = max(0.0, 1.0 - p_ac - p_ki)
        if ar.size and ap.size == ar.size and bool((ap > 0).any()):
            irr_ac = float(ar[ap > 0].mean())
        else:
            irr_ac = float(terms.coupon_pa)
        irr_loss = results.get("loss_given_knock_in", None)
        if irr_loss is None or (isinstance(irr_loss, float) and np.isnan(irr_loss)):
            irr_loss = -(1.0 - float(terms.knock_in_barrier))
        prows = [
            (_t("outcome_autocalled", lang), f"{p_ac:.1%}",   f"{irr_ac:+.1%}",        pdf.primary_color),
            (_t("outcome_held", lang),       f"{p_held:.1%}", f"{terms.coupon_pa:+.1%}", pdf.teal),
            (_t("outcome_loss", lang),       f"{p_ki:.1%}",   f"{float(irr_loss):+.1%}", pdf.amber),
        ]
        ph = 10.5 + len(prows) * 8.0 + 3.0
        pdf.set_fill_color(*pdf.panel_color)
        try:
            pdf.rect(x0, ly, Lw, ph, style="F", round_corners=True, corner_radius=2)
            pdf.set_fill_color(*pdf.primary_color)
            pdf.rect(x0, ly, Lw, 1.1, style="F",
                     round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=2)
        except TypeError:
            pdf.rect(x0, ly, Lw, ph, style="F")
            pdf.set_fill_color(*pdf.primary_color)
            pdf.rect(x0, ly, Lw, 1.1, style="F")
        pdf._eyebrow(x0 + 4, ly + 4, _t("payoff_scenarios", lang), pdf.muted,
                     size=7.0, tracking=0.4, w=52)
        pdf._eyebrow(x0 + Lw - 44, ly + 4.2, _t("payoff_prob", lang),
                     _FOOTNOTE_GREY, size=5.6, tracking=0.2, w=22, align="R")
        pdf._eyebrow(x0 + Lw - 22, ly + 4.2, _t("payoff_irr", lang),
                     _FOOTNOTE_GREY, size=5.6, tracking=0.2, w=18, align="R")
        yy = ly + 10.5
        for lab, p, v, col in prows:
            pdf.set_draw_color(*_RULE_SOFT); pdf.set_line_width(0.2)
            pdf.line(x0 + 4, yy, x0 + Lw - 4, yy)
            pdf.set_fill_color(*col)
            pdf.rect(x0 + 4, yy + 2.7, 2.4, 2.4, style="F")
            pdf.set_xy(x0 + 9, yy + 1.5)
            pdf._sf(8.2, "regular"); pdf.set_text_color(*pdf.body_ink)
            pdf.cell(Lw - 9 - 46, 5, _safe(lab))
            pdf.set_xy(x0 + Lw - 46, yy + 1.6)
            pdf._sf(8.0, "regular"); pdf.set_text_color(*KV_GREY)
            pdf.cell(22, 5, _safe(p), align="R")
            pdf.set_xy(x0 + Lw - 24, yy + 1.2)
            pdf._sf(10.0, "bold"); pdf.set_text_color(*col)
            pdf.cell(20, 5, _safe(v), align="R")
            yy += 8.0
        ly += ph + 5.0

    # ── Right rail: underlyings + key terms panel ──────────────────────────
    # The at-a-glance rail always shows the core terms (issue date / issuer only
    # when present on the note). The user-selectable `cover_metrics` toggles drive
    # the *cover* footer strip, not this rail.
    _ki_lbl = _t("ki_barrier", lang).split(' (')[0]
    _metric_catalog = {
        "maturity":         (_t("maturity", lang),         f"{_mat_label(terms)} {_fmt_freq(terms.payment_freq, lang)}"),
        "coupon_pa":        (_t("coupon_pa", lang),        f"{terms.coupon_pa * 100:.2f}%"),
        "coupon_barrier":   (_t("coupon_barrier", lang),   f"{terms.coupon_barrier:.0%}"),
        "autocall_barrier": (_t("autocall_barrier", lang), f"{terms.autocall_barrier:.0%}"),
        "knock_in_barrier": (_ki_lbl,                      f"{terms.knock_in_barrier:.1%}"),
        "issue_date":       (_t("issue_date", lang),       str(getattr(terms, "issue_date", "") or "")),
        "issuer":           (_t("issuer", lang),           pdf.issuer or ""),
    }
    if _is_participation(terms):
        # Participation notes carry no coupon/autocall/knock-in — show the payoff
        # profile (protection, participation, cap) instead.
        _cap_v = _part_cap_value(terms)
        mini = [_metric_catalog["maturity"],
                (_t("protection_level", lang), f"{float(getattr(terms, 'protection_level', 1.0) or 1.0):.0%}"),
                (_t("participation_rate", lang), f"{float(getattr(terms, 'participation_rate', 1.0) or 1.0):.0%}")]
        if _cap_v is not None:
            mini.append((_t("period_cap" if getattr(terms, "participation_periodic", False) else "upside_cap", lang),
                         f"{_cap_v:.0%}"))
    else:
        mini = [_metric_catalog["maturity"], _metric_catalog["coupon_pa"],
                _metric_catalog["autocall_barrier"], _metric_catalog["knock_in_barrier"]]
    if getattr(terms, "issue_date", None):
        mini.append(_metric_catalog["issue_date"])
    if pdf.issuer:
        mini.append(_metric_catalog["issuer"])
    n_a = len(asset_names or [])
    # Row pitch for the underlyings list. The logo box is smaller than the pitch
    # so consecutive marks (which can be solid-colour tiles) keep a clear gap
    # instead of melding into one another.
    _UL_ROW, _UL_LOGO = 12.5, 8.6
    rail_h = 5.0 + 5.5 + n_a * _UL_ROW + 5.0 + 5.5 + len(mini) * 8.0 + 3.0
    pdf.set_fill_color(*pdf.panel_color)
    try:
        pdf.rect(Rx, ry, Rw, rail_h, style="F", round_corners=True, corner_radius=3)
        pdf.set_fill_color(*pdf.primary_color)
        pdf.rect(Rx, ry, Rw, 1.1, style="F",
                 round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=3)
    except TypeError:
        pdf.rect(Rx, ry, Rw, rail_h, style="F")
        pdf.set_fill_color(*pdf.primary_color)
        pdf.rect(Rx, ry, Rw, 1.1, style="F")
    yy = ry + 5.0
    pdf._eyebrow(Rx + 5, yy, _t("underlyings", lang), pdf.muted,
                 size=7.0, tracking=0.6, w=Rw - 10)
    yy += 5.5
    _cols = _ul_colors(n_a)
    for i, nm in enumerate(asset_names or []):
        # Company logo when available; fall back to a colored ticker chip. Logo
        # box + name are vertically centred within the row's pitch so the extra
        # spacing sits evenly above and below each mark.
        _ld = ((logo_overrides or {}).get(nm)
               or _load_ticker_logo(nm, (logo_urls or {}).get(nm, ""),
                                    (logo_tickers or {}).get(nm)))
        # Logo drawn directly — no white backing tile — and fit to a consistent
        # square box (aspect preserved, so wide/tall marks aren't squashed).
        _LS = _UL_LOGO
        _box_y = yy + (_UL_ROW - _LS) / 2.0
        _drew = False
        if _ld:
            try:
                _ar = _logo_aspect(_ld, default=1.0)        # height / width
                if _ar <= 1.0:
                    _lw, _lh = _LS, _LS * _ar
                else:
                    _lw, _lh = _LS / _ar, _LS
                pdf.image(io.BytesIO(_ld), x=Rx + 5 + (_LS - _lw) / 2.0,
                          y=_box_y + (_LS - _lh) / 2.0, w=_lw, h=_lh)
                _drew = True
            except Exception:
                _drew = False
        if not _drew:
            tk = (logo_tickers or {}).get(nm) or str(nm)[:4].upper()
            # Subtle tinted chip (NOT white) behind the ticker fallback.
            pdf.set_fill_color(*_blend(_cols[i], _WHITE, 0.86))
            try:
                pdf.rect(Rx + 5, _box_y, _LS, _LS, style="F",
                         round_corners=True, corner_radius=1.8)
            except TypeError:
                pdf.rect(Rx + 5, _box_y, _LS, _LS, style="F")
            pdf.set_xy(Rx + 5, _box_y + 2.3)
            pdf._sf(6.0, "bold"); pdf.set_text_color(*_cols[i])
            pdf.cell(_LS, 4, _safe(tk[:4]), align="C")
        # Company name — larger and bolder so it reads as the primary label.
        pdf.set_xy(Rx + 18, yy + (_UL_ROW - 5.4) / 2.0)
        _nm_w = Rw - 18 - 4
        pdf._fit_font(_safe(nm), _nm_w, 9.6, "bold", min_size=6.5)
        pdf.set_text_color(*pdf.ink)
        pdf.cell(_nm_w, 5.4, _safe(nm))
        yy += _UL_ROW
    yy += 1.0
    pdf.set_draw_color(*_RULE_SOFT); pdf.set_line_width(0.2)
    pdf.line(Rx + 5, yy, Rx + Rw - 5, yy)
    yy += 4.0
    pdf._eyebrow(Rx + 5, yy, _t("key_terms", lang), pdf.muted,
                 size=7.0, tracking=0.6, w=Rw - 10)
    yy += 5.5
    for k, v in mini:
        pdf.set_xy(Rx + 5, yy); pdf._sf(7.5, "regular"); pdf.set_text_color(*KV_GREY)
        pdf.cell((Rw - 10) * 0.5, 4.6, _safe(k))
        pdf.set_xy(Rx + 5, yy)
        pdf._fit_font(_safe(v), (Rw - 10) * 0.5, 8.5, "bold", min_size=6.0)
        pdf.set_text_color(*pdf.ink)
        pdf.cell(Rw - 10, 4.6, _safe(v), align="R")
        pdf.set_draw_color(*_RULE_SOFT)
        pdf.line(Rx + 5, yy + 5.6, Rx + Rw - 5, yy + 5.6)
        yy += 8.0
    ry += rail_h + 6.0

    # ── Right rail: In this report (grouped contents) ──────────────────────
    # Entries are `(head, head_number, [sub-section titles])`. A chapter's number
    # comes from `chapters` — the same mapping the body's numbered heads read —
    # and a chapter absent from it is one the body will not render, so it is not
    # listed either. Sub-sections stay unnumbered: they carry no number on the
    # page, and numbering them here is what used to invent a second sequence
    # that disagreed with every heading in the document.
    _ch = chapters or {}
    _n_assets = len(asset_names or [])
    _any_fan  = any(inc(f"mc_fan_{i}") for i in range(_n_assets))
    toc_groups = []
    _top = []
    if _ch.get("note_terms"):
        _top.append((_t("note_terms", lang), _ch["note_terms"]))
    if _ch.get("issuer"):
        _top.append((_t("issuer_info", lang), _ch["issuer"]))
    if _ch.get("underlying"):
        _top.append((_t("underlying_breakdown", lang), _ch["underlying"]))
    if _top:
        toc_groups.append((None, None, _top))
    if _ch.get("mc"):
        _mc = []
        if inc("mc_metrics") or inc("mc_irr") or inc("mc_autocall"):
            _mc.append(_t("mc_subtab_payoff", lang))
        if inc("mc_wof") or _any_fan:
            _mc.append(_t("mc_subtab_paths", lang))
        if inc("mc_single_wof"):
            _mc.append(_t("mc_subtab_explorer", lang))
        if results.get("params") and (inc("calib_table") or inc("calib_corr")):
            _mc.append(_t("calibration", lang))
        toc_groups.append((_t("lens_mc", lang), _ch["mc"], _mc))
    if _ch.get("bt"):
        _bt = []
        if inc("bt_metrics") or inc("bt_outcome") or inc("bt_pie") or inc("bt_irr"):
            _bt.append(_t("bt_subtab_outcomes", lang))
        if inc("bt_prices"):
            _bt.append(_t("bt_subtab_prices", lang))
        toc_groups.append((_t("lens_bt", lang), _ch["bt"], _bt))
    if _ch.get("live"):
        _live = []
        if inc("live_asset_table"):
            _live.append(_t("live_asset_perf", lang))
        if inc("live_obs_table"):
            _live.append(_t("live_obs_history", lang))
        toc_groups.append((_t("lens_live", lang), _ch["live"], _live))
    if _ch.get("compare"):
        # The comparison chapter printed a numbered banner in the body but never
        # appeared in this list at all. Both leaves are gated on the BUILT tables
        # (`_compare_tables`, passed in), not on the raw payload: a Note B that
        # differs only in its basket has a `terms_b` but no differing rows —
        # `_term_rows` doesn't print the underlyings — so the body renders no
        # terms table and listing one here would promise a section that isn't
        # there.
        _cmp = []
        if cmp_terms:
            _cmp.append(_t("cmp_terms_title", lang))
        if cmp_metrics:
            _cmp.append(_t("cmp_metrics_title", lang))
        toc_groups.append((_t("lens_compare", lang), _ch["compare"], _cmp))
    # Reference matter — unnumbered in the body (`start_section`), so unnumbered
    # here too.
    toc_groups.append((None, None, [(_t("glossary_title", lang), None),
                                    (_t("disclaimer_title", lang), None)]))

    pdf._eyebrow(Rx, ry, _t("in_this_report", lang), pdf.muted,
                 size=8.0, tracking=0.6, w=Rw)
    pdf.set_fill_color(*pdf.lime); pdf.rect(Rx, ry + 4.6, 18, 1.2, style="F")
    ry += 8.0

    _toc_top    = ry
    _toc_bottom = pdf.h - 14.0
    _toc_avail  = _toc_bottom - _toc_top
    _MIN_ROW_H  = 3.9            # below this the 8pt rows stop being legible

    def _fit(groups, row_h=5.4, gap=1.2):
        """Row height / gap that fit `groups`, or None if they can't at any.

        Shrink first, shed only when even the minimum row height overflows —
        a squeezed list is better than an incomplete one.
        """
        heads = sum(1 for nm, _, _ in groups if nm is not None)
        rows  = sum(len(lv) for _, _, lv in groups) + heads
        if rows <= 0 or rows * row_h + heads * gap <= _toc_avail:
            return row_h, gap
        scale = min(1.0, max(0.0, _toc_avail - heads * gap) / (rows * row_h))
        row_h, gap = row_h * scale, gap * scale
        if row_h >= _MIN_ROW_H:
            return row_h, gap
        row_h = _MIN_ROW_H
        return (row_h, gap) if rows * row_h + heads * gap <= _toc_avail else None

    # The summary page has auto page break OFF — it is one designed page, and an
    # overlong list does not wrap, it draws off the bottom. Every underlying adds
    # a row to the rail above, pushing `ry` down, so past ~4 underlyings the full
    # list cannot fit even at the minimum row height. Shed lens SUB-SECTIONS —
    # the optional detail — a group at a time, biggest first, until it fits. The
    # numbered chapters always survive: they are what the body's headings refer
    # to, and a chapter listed nowhere is the defect this file exists to prevent.
    _fitted = _fit(toc_groups)
    while _fitted is None:
        _fat = max((i for i, (nm, _, lv) in enumerate(toc_groups) if nm is not None and lv),
                   key=lambda i: len(toc_groups[i][2]), default=None)
        if _fat is None:
            _fitted = (_MIN_ROW_H, 0.0)      # heads only and still tight — draw it
            break
        toc_groups[_fat] = (toc_groups[_fat][0], toc_groups[_fat][1], [])
        _fitted = _fit(toc_groups)
    _row_h, _gap = _fitted
    _yc = [ry]
    _NUM_W = 7.0

    def _toc_leaf(text, number=None, indent=0.0):
        # The number column is RESERVED whether or not it is filled, so an
        # unnumbered row (glossary, disclaimer, a lens sub-section) still lines
        # its title up with every numbered one instead of hanging 7mm left.
        if number:
            pdf.set_xy(Rx + indent, _yc[0])
            pdf._sf(7.5, "bold"); pdf.set_text_color(*pdf.lime)
            pdf.cell(_NUM_W, _row_h, number)
        indent += _NUM_W
        pdf.set_xy(Rx + indent, _yc[0])
        pdf._sf(8.0, "regular"); pdf.set_text_color(*pdf.body_ink)
        pdf.cell(Rw - indent, _row_h, _safe(text))
        pdf.set_draw_color(*_RULE_SOFT); pdf.set_line_width(0.2)
        pdf.line(Rx, _yc[0] + _row_h, Rx + Rw, _yc[0] + _row_h)
        _yc[0] += _row_h

    def _toc_head(name, number=None):
        _yc[0] += _gap
        _ind = 0.0
        if number:
            pdf.set_xy(Rx, _yc[0])
            pdf._sf(7.5, "bold"); pdf.set_text_color(*pdf.lime)
            pdf.cell(_NUM_W, _row_h, number)
            _ind = _NUM_W
        pdf._eyebrow(Rx + _ind, _yc[0] + 0.4, name, pdf.primary_color,
                     size=7.0, tracking=0.5, w=Rw - _ind)
        _yc[0] += _row_h

    for name, number, leaves in toc_groups:
        if name is not None:
            # A lens: the chapter number sits on the head, and its sub-sections
            # hang under it aligned to the head's text — unnumbered, because
            # nothing numbers them on the page either.
            _toc_head(name, number)
            for leaf in leaves:
                _toc_leaf(leaf)
        else:
            for leaf, leaf_no in leaves:
                _toc_leaf(leaf, leaf_no)

    # Client / short reports leave a big empty band below the left stack — fill
    # the shorter left column with a tall brand photo when one is available
    # (client-version request), else compose the void with the lighter graphic
    # treatment (sigil watermark + low-left hex-cluster).
    _bottom = pdf.h - 18.0
    _void_top = max(ly, _yc[0]) + 8.0
    _left_filled = False
    try:
        # `filler_image_list` is already the report-body photos (cover/back
        # excluded), so the first one differs from the cover by construction —
        # the summary's vertical photo and the cover won't show the same shot.
        _pool = getattr(pdf, "filler_image_list", None) or []
        _vimg = _pool[0] if _pool else None
        if ly + 45 < _yc[0] and _vimg is not None:
            _left_filled = _cover_left_photo(pdf, x0, ly + 6.0, Lw, _bottom, _vimg)
        # Sigil watermark — only in a void below BOTH stacks (rare on client
        # reports, where the TOC runs long); harmless alongside the left photo.
        _sig = getattr(pdf, "cover_sigil_bytes", None)
        if _sig and _bottom - _void_top > 40:
            from PIL import Image as _Img
            _iw, _ih = _Img.open(io.BytesIO(_sig)).size
            _sh = min((_bottom - _void_top) * 0.95, 150.0); _sw = _sh * _iw / _ih
            with pdf.local_context(fill_opacity=0.07):
                pdf.image(io.BytesIO(_sig), x=pdf.w - pdf.r_margin - _sw * 0.60,
                          y=_void_top + ((_bottom - _void_top) - _sh) / 2.0,
                          w=_sw, h=_sh)
        # No photo for the left column → fall back to the hex cluster.
        if not _left_filled and ly + 45 < _yc[0] and _bottom - ly > 50:
            _sc = min((_bottom - ly) * 0.5, 54.0)
            pdf.theme.cover_left_void_fill(pdf, x0, _sc, _bottom)
    except Exception:
        pass

    pdf._is_cover = False
    # Re-enable auto-page-break for all content pages that follow
    pdf.set_auto_page_break(auto=True, margin=28)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

# Page-geometry constants shared by the heading reservation and the table's own
# break rule. They MUST agree: the orphaned-heading bug was two independent
# estimates of the same quantity. `_table_room` says how much room a heading has
# to see before it may draw; `data_table` uses the same numbers to decide whether
# to break. Change one, change both.
# Page geometry + the heading-reservation rule now live in reportkit.document,
# with the table code that breaks on the same numbers. Re-exported under their
# original names: tests/test_pdf_layout.py reads all seven off this module.
from reportkit.document import (  # noqa: E402
    _TBL_ROW_H, _TBL_HEAD_H, _TBL_PAD, _PAGE_CAP, _HEAD_ROOM, _SPLIT_ROOM,
    _table_room,
)

def _draw_participation_profile(pdf, terms, lang: str) -> None:
    """Payoff-profile diagram for a Participation Note — redemption (y) versus the
    final basket level (x), a server-side mirror of the web ParticipationProfile in
    its curve-only (setup) form. The curve is sampled from the SAME redemption formula
    the engine prices (core.note._participation_redemption), so the picture matches the
    payoff. Pure fpdf primitives, wrapped so a drawing glitch can't abort the report."""
    try:
        import math
        import dataclasses
        from core.note import _participation_redemption

        # Cliquet (periodic): the profile is ONE period's payoff — same downside ×
        # upside, but off a par strike with the per-period cap (mirrors the web `eff`).
        periodic = bool(getattr(terms, "participation_periodic", False))
        eff = (dataclasses.replace(terms, participation_strike=1.0,
                                   upside_cap=getattr(terms, "period_cap", None))
               if periodic else terms)
        pd_style = getattr(eff, "participation_downside", "full") or "full"
        strike = float(getattr(eff, "participation_strike", 1.0) or 1.0)
        prot   = float(getattr(eff, "protection_level", 1.0) or 0.0)
        _capf  = getattr(eff, "upside_cap", None)
        cap    = (1.0 + _capf) if _capf is not None else float("inf")
        ko     = getattr(eff, "knockout_level", None)

        # Frame the view around where the payoff actually varies (mirrors the web
        # ParticipationProfile) so a small-cap or fully-protected profile fills the
        # box instead of sitting as a flat line in a fixed 40–180% / 60–140% frame.
        _capf_finite = math.isfinite(cap)
        x_min = 0.6 if pd_style == "full" else 0.4
        x_max = max(1.3, cap + 0.15 if _capf_finite else 1.8, (ko + 0.2) if ko is not None else 0.0)
        N, EPS = 160, 1e-3
        xset = {x_min + (i / N) * (x_max - x_min) for i in range(N + 1)}
        for b in (strike - EPS, strike, (ko - EPS) if ko is not None else None, ko):
            if b is not None and x_min < b < x_max:
                xset.add(b)
        xs = sorted(xset)
        rs = [float(v) for v in _participation_redemption(np.asarray(xs, dtype=float), eff)]
        # y-domain hugs the actual redemption range (always including par) with a
        # little padding, rounded to 5% — not a fixed 60–140% box.
        r_min, r_max = min(1.0, min(rs)), max(1.0, max(rs))
        pad_y = max(0.05, (r_max - r_min) * 0.18)
        y_lo = math.floor((r_min - pad_y) * 20) / 20
        y_hi = math.ceil((r_max + pad_y) * 20) / 20
        y_span = y_hi - y_lo
        y_step = 0.05 if y_span <= 0.35 else 0.1 if y_span <= 0.7 else 0.2
        x_span = x_max - x_min
        x_step = 0.25 if x_span <= 1.0 else 0.5

        # Centre a plot box on the page: left gutter for the rotated y-title + ticks.
        x0 = pdf.l_margin + 22.0
        x1 = pdf.w - pdf.r_margin - 8.0
        top = pdf.get_y() + 6.0
        plot_h = 58.0
        bottom = top + plot_h

        def mapX(b: float) -> float:
            return x0 + (b - x_min) / (x_max - x_min) * (x1 - x0)

        def mapY(r: float) -> float:
            return bottom - (min(max(r, y_lo), y_hi) - y_lo) / (y_hi - y_lo) * plot_h

        in_y = lambda r: y_lo <= r <= y_hi

        # periodic badge (centred, above the plot)
        if periodic:
            pdf._sf(7.5, "bold")
            pdf.set_text_color(*pdf.accent_color)
            _bl = pdf._safe(f"↻ {_t('pp_cliquet_badge', lang)}")
            pdf.text((x0 + x1) / 2 - pdf.get_string_width(_bl) / 2, top - 1.0, _bl)
            top += 4.0
            bottom = top + plot_h

        # y grid + tick labels (par line at 100% emphasised). Tick step scales to the
        # (now variable) domain span so a tight axis still gets several gridlines.
        r = math.ceil(y_lo / y_step) * y_step
        while r <= y_hi + 1e-9:
            gy = mapY(r)
            is_par = abs(r - 1.0) < 1e-9
            pdf.set_draw_color(*( (150, 162, 180) if is_par else (223, 229, 237)))
            pdf.set_line_width(0.4 if is_par else 0.2)
            pdf.line(x0, gy, x1, gy)
            pdf._sf(6.8, "regular")
            pdf.set_text_color(150, 162, 180)
            _tl = f"{r:.0%}"
            pdf.text(x0 - 2 - pdf.get_string_width(_tl), gy + 1.0, _tl)
            r += y_step

        # x tick labels (basket level %)
        pdf._sf(6.8, "regular")
        pdf.set_text_color(150, 162, 180)
        _xt_b = math.ceil(x_min / x_step) * x_step
        while _xt_b <= x_max + 1e-9:
            _xt = f"{_xt_b:.0%}"
            pdf.text(mapX(_xt_b) - pdf.get_string_width(_xt) / 2, bottom + 5.0, _xt)
            _xt_b += x_step

        # reference lines (dashed, bare — matching the web setup diagram)
        pdf.set_line_width(0.3)
        # strike marker (vertical)
        if x_min < strike < x_max:
            pdf.set_draw_color(200, 208, 220)
            pdf.set_dash_pattern(dash=1.0, gap=1.0)
            pdf.line(mapX(strike), top, mapX(strike), bottom)
        # protection floor (non-bear) → amber (brand has no red)
        if pd_style != "bear" and in_y(min(prot, 1.0)):
            pdf.set_draw_color(*pdf.amber)
            pdf.set_dash_pattern(dash=1.6, gap=1.2)
            pdf.line(x0, mapY(min(prot, 1.0)), x1, mapY(min(prot, 1.0)))
        # cap ceiling
        if math.isfinite(cap) and in_y(cap):
            pdf.set_draw_color(150, 162, 180)
            pdf.set_dash_pattern(dash=1.6, gap=1.2)
            pdf.line(x0, mapY(cap), x1, mapY(cap))
        # direct-underlying 1:1 reference (diagonal)
        d_lo, d_hi = max(x_min, y_lo), min(x_max, y_hi)
        if d_hi > d_lo:
            pdf.set_draw_color(170, 180, 195)
            pdf.set_dash_pattern(dash=0.8, gap=1.6)
            pdf.line(mapX(d_lo), mapY(d_lo), mapX(d_hi), mapY(d_hi))
        pdf.set_dash_pattern()

        # payoff curve (thick brand line)
        pdf.set_draw_color(*pdf.primary_color)
        pdf.set_line_width(1.1)
        for i in range(1, len(xs)):
            pdf.line(mapX(xs[i - 1]), mapY(rs[i - 1]), mapX(xs[i]), mapY(rs[i]))

        # axes
        pdf.set_draw_color(120, 132, 150)
        pdf.set_line_width(0.4)
        pdf.line(x0, top, x0, bottom)
        pdf.line(x0, bottom, x1, bottom)

        # axis titles (x centred below, y rotated on the left)
        pdf._sf(7.5, "regular")
        pdf.set_text_color(90, 100, 120)
        _xa = pdf._safe(_t("pp_x_axis_period" if periodic else "pp_x_axis", lang))
        pdf.text((x0 + x1) / 2 - pdf.get_string_width(_xa) / 2, bottom + 10.5, _xa)
        _ya = pdf._safe(_t("pp_y_axis", lang))
        with pdf.rotation(90, pdf.l_margin + 4.0, (top + bottom) / 2 + pdf.get_string_width(_ya) / 2):
            pdf.text(pdf.l_margin + 4.0, (top + bottom) / 2 + pdf.get_string_width(_ya) / 2, _ya)

        pdf.set_dash_pattern()
        pdf.set_line_width(0.2)
        pdf.set_y(bottom + 13)

        # periodic caption below the plot
        if periodic:
            pdf._sf(7, "regular")
            pdf.set_text_color(150, 162, 180)
            _cap = pdf._safe(_t("pp_periodic_caption", lang))
            usable = pdf.w - pdf.l_margin - pdf.r_margin
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(usable, 4.2, _cap, align="C")
            pdf.ln(1)
    except Exception as e:                                  # never break the report
        print(f"[report] participation profile skipped: {e}")
        try:
            pdf.set_dash_pattern()
        except Exception:
            pass


def _draw_note_diagram(pdf, terms, lang: str) -> None:
    """Draw the note-structure schematic (the React NoteTimeline, server-side):
    an observation timeline at the autocall level, the coupon / knock-in / One-Star
    barriers as dashed reference lines, and a floating value label for each. Pure
    fpdf primitives — wrapped so a drawing glitch can never abort the report."""
    # A Participation note has no observation ladder — it's a maturity payoff, so
    # show its redemption profile instead of the barrier timeline (mirrors the web
    # NoteTimeline, which routes participation → ParticipationProfile).
    if getattr(terms, "note_type", "") == "participation" or (getattr(terms, "capital_guarantee", 0) or 0) > 0:
        _draw_participation_profile(pdf, terms, lang)
        return
    try:
        from datetime import date, timedelta
        # Green design language: autocall / One-Star in green, coupon / knock-in
        # in amber (the brand has no red), protected zone green, at-risk amber.
        C_COUPON, C_KI, C_OS = pdf.amber, pdf.amber_dark, pdf.primary_color
        C_PROT, C_RISK = pdf.primary_color, pdf.amber
        # Centre the plot box on the page with symmetric side margins (left holds
        # the y-axis ticks, right holds the floating barrier labels), and make it
        # tall enough to read as a proper chart rather than a thin strip.
        side = 23.0
        x0 = pdf.l_margin + side
        x1 = pdf.w - pdf.r_margin - side
        top = pdf.get_y() + 9            # headroom for the y-axis arrow + title
        plot_h, domain = 54.0, 1.40
        bottom = top + plot_h

        def mapY(level: float) -> float:
            return bottom - min(max(level, 0.0), domain) / domain * plot_h

        def mapX(frac: float) -> float:
            return x0 + frac * (x1 - x0)

        # Barrier percent with up to 3 decimals, trailing zeros trimmed (50%, not
        # 50%→51% rounding; 50.5%; 50.125%) so fine barrier levels aren't lost.
        def _bp(level: float) -> str:
            return f"{level * 100:.3f}".rstrip("0").rstrip(".") + "%"

        n      = terms.n_obs
        ac, cp, ki = terms.autocall_barrier, terms.coupon_barrier, terms.knock_in_barrier
        os_lvl = terms.one_star_level
        start  = min(max(terms.autocall_start_period, 1), n)
        par_y, ac_y, ki_y = mapY(1.0), mapY(ac), mapY(ki)
        obs_t  = list(terms.obs_times())
        T      = obs_t[-1] if obs_t else 1.0
        fracs  = [t / T for t in obs_t]
        acX    = mapX((start - 1) / n)
        coupon_per  = terms.coupon_pa / max(1, terms.periods_per_year)
        show_coupon = (n <= 8 and coupon_per > 0)
        show_yr_ticks = (n <= 6)
        barriers_equal = abs(cp - ki) < 1e-6

        # step-down autocall: the trigger declines each callable period toward a
        # floor. Reuse the quant core's schedule (NoteTerms.autocall_barrier_schedule),
        # the same one the payoff and the web diagram use, so all three stay in step.
        stepped = bool(getattr(terms, "autocall_step_down", 0.0) or 0.0)
        ac_sched = [float(x) for x in terms.autocall_barrier_schedule()]
        min_ac = min(ac_sched) if ac_sched else ac

        # x-axis time: real dates when the note has an issue date, else the tenor.
        # Quoted in months to match the web NoteTimeline (tenorLabel → "30M").
        _mat_yrs = terms.maturity
        _tenor = f"{int(round(_mat_yrs * 12))}M"
        issue_iso = getattr(terms, "issue_date", None)
        issue_lbl, mat_lbl = None, _tenor
        if issue_iso:
            try:
                _y, _m, _d = (int(v) for v in str(issue_iso).split("-")[:3])
                _id = date(_y, _m, _d)
                issue_lbl = _id.strftime("%b %Y")
                mat_lbl = (_id + timedelta(days=round(_mat_yrs * 365.25))).strftime("%b %Y")
            except Exception:
                issue_lbl, mat_lbl = None, _tenor

        # payoff zones: protected (>= knock-in) green, at-risk (< knock-in) red
        pdf.set_fill_color(*_blend(C_PROT, _WHITE, 0.90))
        pdf.rect(x0, top, x1 - x0, max(0.0, ki_y - top), style="F")
        pdf.set_fill_color(*_blend(C_RISK, _WHITE, 0.90))
        pdf.rect(x0, ki_y, x1 - x0, max(0.0, bottom - ki_y), style="F")

        # autocall window: above the autocall barrier, over the callable periods.
        # Caption centres in its (variable-height) band but stays above the par
        # line so it never strands outside a thin band or overlaps the dots.
        if start <= n:
            pdf.set_fill_color(*_blend(pdf.accent_color, _WHITE, 0.82))
            pdf.rect(acX, top, max(0.0, x1 - acX), max(0.0, ac_y - top), style="F")
            pdf._sf(8, "bold")
            pdf.set_text_color(*pdf.accent_color)
            _wl = _t("diag_window", lang)
            _wy = min((top + ac_y) / 2 + 1.5, par_y - 2.0)
            pdf.text((acX + x1) / 2 - pdf.get_string_width(_wl) / 2, _wy, _wl)

        # y gridlines + tick labels (0 / 50 / 100%)
        pdf._sf(6.8, "regular")
        for lvl in (0.0, 0.5, 1.0):
            gy = mapY(lvl)
            pdf.set_draw_color(223, 229, 237)
            pdf.set_line_width(0.2)
            pdf.line(x0, gy, x1, gy)
            pdf.set_text_color(150, 162, 180)
            _tl = f"{lvl:.0%}"
            pdf.text(x0 - 2 - pdf.get_string_width(_tl), gy + 1.0, _tl)

        # zone captions
        pdf._sf(8, "bold")
        pdf.set_text_color(*C_PROT)
        pdf.text(x0 + 2.5, (par_y + ki_y) / 2 + 1.0, _t("diag_zone_protected", lang))
        if ki_y < bottom - 2:
            pdf.set_text_color(*C_RISK)
            pdf.text(x0 + 2, (ki_y + bottom) / 2 + 1.0, _t("diag_zone_atrisk", lang))

        # barrier dashed lines
        pdf.set_line_width(0.3)
        def _dash(level, color):
            pdf.set_draw_color(*color)
            pdf.set_dash_pattern(dash=1.3, gap=1.0)
            pdf.line(x0, mapY(level), x1, mapY(level))
            pdf.set_dash_pattern()
        if barriers_equal:
            _dash(ki, C_KI)
        else:
            _dash(cp, C_COUPON)
            _dash(ki, C_KI)
        if os_lvl is not None:
            _dash(os_lvl, C_OS)

        # step-down autocall staircase — matches the web NoteTimeline stepPath:
        # from the issue at the initial barrier, hold across each period then drop
        # to that period's (declining) trigger. Drawn before the dots so they sit
        # on top.
        if stepped:
            pdf.set_draw_color(*pdf.accent_color)
            pdf.set_line_width(0.4)
            pdf.set_dash_pattern(dash=1.6, gap=1.2)
            cur_x, cur_y = x0, mapY(ac)
            for i, f in enumerate(fracs):
                nx, ny = mapX(f), mapY(ac_sched[i])
                pdf.line(cur_x, cur_y, nx, cur_y)
                pdf.line(nx, cur_y, nx, ny)
                cur_x, cur_y = nx, ny
            pdf.set_dash_pattern()

        # axes — extended past the data with arrowheads so it doesn't end abruptly
        pdf.set_draw_color(150, 162, 180)
        pdf.set_line_width(0.4)
        pdf.line(x0, bottom, x0, top - 4)
        pdf.line(x0, bottom, x1 + 6, bottom)
        pdf.set_fill_color(150, 162, 180)
        pdf.polygon([(x0 - 1.4, top - 3), (x0 + 1.4, top - 3), (x0, top - 6)], style="F")
        pdf.polygon([(x1 + 4, bottom - 1.4), (x1 + 4, bottom + 1.4), (x1 + 7, bottom)], style="F")
        pdf._sf(6.5, "bold")
        pdf.set_text_color(150, 162, 180)
        pdf.text(x0 - 3, top - 5.5, _t("diag_axis_level", lang))

        # observation dots on the par line + per-period coupon above
        def _dot(cx, r, fill):
            pdf.set_fill_color(*fill)
            pdf.ellipse(cx - r, par_y - r, 2 * r, 2 * r, style="F")
        for i, f in enumerate(fracs):
            is_mat = (i + 1 == n)
            is_ac = (i + 1 >= start)
            col = pdf.primary_color if is_mat else (pdf.accent_color if is_ac else (205, 214, 228))
            _dot(mapX(f), 1.7 if is_mat else 1.5, col)
            if show_coupon:
                pdf._sf(6.5, "regular")
                pdf.set_text_color(*C_COUPON)
                _ct = f"+{coupon_per:.2%}"
                pdf.text(mapX(f) - pdf.get_string_width(_ct) / 2, par_y - 3.5, _ct)
            if show_yr_ticks and not is_mat:
                _yt = f"{round(f * _mat_yrs * 12)}M"   # months, matching the web yrTick
                pdf._sf(6, "regular")
                pdf.set_text_color(170, 180, 195)
                pdf.text(mapX(f) - pdf.get_string_width(_yt) / 2, bottom + 4.6, _yt)

        # issue / maturity captions (below the x-axis) + the real date or tenor
        pdf._sf(7.5, "regular")
        pdf.set_text_color(110, 122, 145)
        _iss, _mat = _t("diag_issue", lang), _t("diag_maturity", lang)
        pdf.text(x0 - pdf.get_string_width(_iss) / 2, bottom + 4.6, _iss)
        pdf.text(x1 - pdf.get_string_width(_mat) / 2, bottom + 4.6, _mat)
        pdf._sf(6.5, "regular")
        pdf.set_text_color(150, 162, 180)
        if issue_lbl:
            pdf.text(x0 - pdf.get_string_width(issue_lbl) / 2, bottom + 8.6, issue_lbl)
        pdf.set_text_color(110, 122, 145)
        pdf.text(x1 - pdf.get_string_width(mat_lbl) / 2, bottom + 8.6, mat_lbl)

        # floating barrier labels (right gutter): name over value on two lines so
        # they stay narrow and the plot box can sit centred on the page.
        lx = x1 + 4
        _ac_val = f"{_bp(ac)} → {_bp(min_ac)}" if stepped else _bp(ac)
        entries = [(ac_y, pdf.primary_color, _t("diag_autocall", lang), _ac_val)]
        if barriers_equal:
            entries.append((ki_y, C_COUPON, f"{_t('diag_coupon', lang)} / {_t('diag_knockin', lang)}", _bp(cp)))
        else:
            entries.append((mapY(cp), C_COUPON, _t("diag_coupon", lang), _bp(cp)))
            entries.append((ki_y, C_KI, _t("diag_knockin", lang), _bp(ki)))
        if os_lvl is not None:
            entries.append((mapY(os_lvl), C_OS, _t("diag_onestar", lang), _bp(os_lvl)))
        entries.sort(key=lambda e: e[0])
        prev_y = -100.0
        for ty, color, name, val in entries:
            ly = max(ty, prev_y + 7.4)
            prev_y = ly
            pdf.set_draw_color(190, 198, 210)
            pdf.set_line_width(0.2)
            pdf.line(x1 + 1, ty, lx - 1, ly - 1.0)
            pdf._sf(7, "regular")
            pdf.set_text_color(*color)
            pdf.text(lx, ly, name)
            pdf._sf(8.5, "bold")
            pdf.set_text_color(*pdf.primary_color)
            pdf.text(lx, ly + 4.0, val)

        pdf.set_dash_pattern()
        pdf.set_line_width(0.2)
        pdf.set_y(bottom + 12)
    except Exception as e:                                  # never break the report
        print(f"[report] note diagram skipped: {e}")
        try:
            pdf.set_dash_pattern()
        except Exception:
            pass


# ── report attribution (invisible metadata watermark) ────────────────────────
# Authorship baked into every generated PDF's (hidden) document metadata. The
# string is stored base64-encoded, split across literals, and assembled at call
# time so it isn't a grep-able plain-text string; `_stamp_attribution` is called
# from two places (right after the doc is built AND just before output) so
# deleting one call still leaves the mark. This is DETERRENCE, not DRM — a
# source-available build can always be edited to strip it; the point is only to
# make casual removal tedious and to travel invisibly in normal use.
_A64 = ("U3RydWN0dXJlZCBOb3RlIFNpbXVsYXRvciDCtyDCqSBEaWVnbyBTZWJhc3RpYW4g"
        "R29tZXogSGFyaWthIDxkaWVnb2dvbWV6enhAZ21haWwuY29tPg==")


def _stamp_attribution(_p) -> None:
    try:
        _a = base64.b64decode(_A64).decode("utf-8")
        _p.set_author(_a)
        _p.set_creator(_a)
        _p.set_producer(_a)
        _p.set_keywords(_a)
    except Exception:
        pass


def _stamp_provenance(_p, terms, report_title: str = "") -> None:
    """Readable, NON-PII provenance in the PDF metadata: the document title, a UTC
    generation timestamp, the note + underlyings, and the creation date. Safe to
    travel with a distributed (white-label) document. The generating user's IP is
    deliberately NOT embedded here — that's personal data; it belongs in the
    server request log, visible only to the operator (see api/main.py:report)."""
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        nm = (getattr(terms, "name", "") or "Structured Note").strip()
        tks = "/".join((getattr(terms, "tickers", {}) or {}).keys())
        _p.set_title((report_title or nm)[:120])
        _subj = f"Generated {now.strftime('%Y-%m-%d %H:%M UTC')} · {nm}"
        if tks:
            _subj += f" · {tks}"
        _p.set_subject(f"{_subj} · Structured Note Simulator")
        try:
            _p.creation_date = now
        except Exception:
            pass
    except Exception:
        pass


def generate_pdf_report(*args, **kwargs) -> bytes:
    """Public entry point — see _build_pdf_report for the full signature/docs.

    Wraps the build in a single persistent Kaleido server so every Plotly figure
    export shares one Chrome instead of cold-booting one per figure (~40s → ~5s
    of export for a full report), and tears the Chrome subprocess down in a
    finally so it never outlives the build. The server is best-effort: if it
    can't start, figure export silently falls back to the per-call path."""
    with _rk_charts.kaleido_session():
        return _build_pdf_report(*args, **kwargs)


def _build_pdf_report(
    terms,
    results: dict,
    asset_names: list[str],
    figures: dict,
    lang: str = "en",
    bt_summary: dict | None = None,
    bt_figures: dict | None = None,
    live_data: dict | None = None,
    live_figure=None,
    logo_urls: dict[str, str] | None = None,
    issuer_logo_url: str | None = None,
    issuer_logo_override: bytes | None = None,
    branding: dict | None = None,
    logo_tickers: dict[str, str] | None = None,
    include_sections: set[str] | None = None,
    logo_overrides: dict[str, bytes] | None = None,
    underlying_metrics: dict | None = None,
    underlying_price_figs: dict | None = None,
    issuer_description: str | None = None,
    compare_data: dict | None = None,
    compare_figures: dict | None = None,
    report_kind: str | None = None,
) -> bytes:
    """
    Build the full institutional-style PDF report.

    report_kind     — the audience preset the report was built for ("advisor",
                      "client", "ic", "risk", "full"). Stamped on the cover as a
                      report-type subtitle; None / unknown ⇒ no subtitle.

    logo_urls       — {display_name: url} for underlying ticker logos.
    logo_overrides  — {display_name: raw image bytes} for user-uploaded custom
                      ticker logos; when present they win over logo_urls and the
                      local branding/ticker_logos/ files (cover, calibration and
                      performance tables all honour them).
    issuer_logo_url — favicon / logo URL for the issuer (shown on cover).
    branding        — optional dict; see the module docstring for the full schema
                      (firm_name, primary/accent/chart_secondary colours, a
                      logo_file/logo_base64/logo_url, and report_title / website /
                      contact / footer_note content keys). Unknown keys warn and
                      malformed hex falls back to defaults.
    include_sections — set of per-chart item keys to write. One key per figure
                      / table / metric-block, e.g. {"mc_metrics", "mc_irr",
                      "mc_autocall", "mc_wof", "mc_fan_0", "mc_fan_1", ...,
                      "mc_single_price", "mc_single_wof", "calib_table",
                      "calib_corr", "bt_metrics", "bt_outcome", "bt_pie",
                      "bt_irr", "bt_prices", "live_metrics",
                      "live_asset_table", "live_obs_table", "live_chart"}.
                      None (default) includes every item for which data is
                      available, so existing callers are unaffected. The cover,
                      Note Terms and disclaimer are always written. An item is
                      rendered only when BOTH selected here AND its data/figure
                      was supplied; section headers appear only when at least one
                      of their items is included.
    All optional parameters default to None; existing callers are unaffected.
    """
    # results may be None/empty when the report needs no Monte Carlo output (the
    # sim was skipped). Every read is via .get with a default, so {} is safe and
    # the MC lens simply renders nothing (its items are gated off).
    results = results or {}
    # None = include everything; otherwise only the listed sections. The cover,
    # Note Terms and disclaimer ignore this gate (always present).
    def _inc(key: str) -> bool:
        return include_sections is None or key in include_sections
    # ── Resolve + validate branding ───────────────────────────────────
    _validate_branding(branding)
    primary_color, accent_color, secondary_color, section_rule_color, firm_name = _resolve_palette(branding)
    # Panel fill: explicit branding `panel_color` wins; else a light primary tint.
    panel_color = _branding_color(branding, "panel_color", _blend(primary_color, _WHITE, 0.93))
    # Cover sidebar top bar: explicit `sidebar_bar_color` wins; else the accent.
    sidebar_bar_color = _branding_color(branding, "sidebar_bar_color", primary_color)
    # Visual-identity theme — branding["report_theme"] selects the look (e.g.
    # "cadiem" = hexagon, "mercator" = default); unknown/absent → the default.
    report_theme = resolve_theme((branding or {}).get("report_theme"))
    # User-uploaded custom ticker logos: normalise to embeddable PNG once, drop
    # any that fail to decode. {display_name: png_bytes}; win over URLs/local files.
    _logo_ovr = {nm: png for nm, b in (logo_overrides or {}).items()
                 if b and (png := _to_embeddable_png(b))}
    # Local-file-first: logo_file -> logo_base64 -> logo_url
    brand_logo_bytes = _load_logo(branding)
    # Optional content keys (B5)
    _b = branding or {}
    # report_title / footer_note may be a plain string or an {en, es} dict, so a
    # branded report renders these in the report's own language instead of the
    # firm's single configured language.
    report_title = _brand_text(_b.get("report_title"), lang)
    website      = _b.get("website", "") or ""
    contact      = _b.get("contact", "") or ""
    footer_note  = _brand_text(_b.get("footer_note"), lang)

    # Issuer split: `issuer` is the display NAME (falls back to the identifier so a
    # note that filled only the id still shows something); `issuer_lookup` is the
    # identifier used to FIND the logo. Legacy configs set only `issuer`, so both
    # resolve to it and behaviour is unchanged.
    _iss_name = (getattr(terms, "issuer", "") or "").strip()
    _iss_id   = (getattr(terms, "issuer_id", "") or "").strip()
    issuer        = _iss_name or _iss_id
    issuer_lookup = _iss_id or _iss_name
    # Issuer logo: a user-uploaded image wins (normalised to an embeddable PNG);
    # otherwise try a local branding/ticker_logos/{identifier}.png, else the favicon
    # URL — both keyed on the lookup identifier, not the display name.
    if issuer_logo_override:
        issuer_logo_bytes = _to_embeddable_png(issuer_logo_override)
    else:
        issuer_logo_bytes = _load_ticker_logo(issuer_lookup, issuer_logo_url) if (issuer_lookup or issuer_logo_url) else None

    doc_ref = f"{report_title or _t('series_title', lang)} | {terms.name}"
    pdf = _NotePDF(
        lang            = lang,
        issuer          = issuer,
        doc_ref         = doc_ref,
        primary_color   = primary_color,
        accent_color    = accent_color,
        firm_name       = firm_name,
        firm_logo_bytes = brand_logo_bytes,
        report_title    = report_title,
        website         = website,
        contact         = contact,
        footer_note     = footer_note,
        section_rule_color = section_rule_color,   # NEW
        panel_color     = panel_color,             # NEW
        sidebar_bar_color = sidebar_bar_color,     # NEW
        theme           = report_theme,            # NEW — pluggable visual identity
    )
    # Custom brand typography (title_font / body_font) — no-op + IBM Plex fallback
    # when the brand ships no fonts or the TTF files are absent.
    _stamp_attribution(pdf)
    # Usable content width — a page-geometry constant used by every table. Defined
    # here (not inside the Note-Terms block) so later sections never hit an unbound
    # `usable` when Note details is toggled off.
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    # ── Brand assets, copy and placement ───────────────────────────────────
    # One call. reportkit.branding resolves the config — the positional photo
    # slots, watermark (including the legacy flat keys), overlay, sigil, cover
    # logo, copy overrides and placement percentages — and `apply_brand` writes
    # them in the order that matters. This used to be ~90 lines here, which is
    # why a config could be recognised and then only partly honoured.
    #
    # `root` and `fetch` are passed EXPLICITLY: reportkit refuses `logo_file`
    # and `logo_url` unless a host opts in, and `_fetch_image_bytes` stays the
    # module global tests/golden_fixture.py rebinds to neutralise the network.
    _brand = _rk_branding.resolve(
        _b, lang=lang, root=_REPO_ROOT, fetch=_fetch_image_bytes,
        extra_keys=_NOTE_BRANDING_KEYS, default_firm_name=_DEFAULT_FIRM_NAME)
    for _w in _brand.warnings:
        print(f"[PDF branding] {_w}")
    pdf.apply_brand(_brand, font_dir=_FONT_DIR / "brand")

    # Note-specific, deliberately NOT reportkit's: which key-TERM chips the
    # cover band shows, and whether the sub-lines name underlyings by ticker or
    # by display name. A law firm's quarterly report has neither.
    _cm = _brand.extras.get("cover_metrics")
    pdf.cover_metrics = list(_cm) if isinstance(_cm, (list, tuple)) else None
    pdf.underlying_labels = ("name" if _brand.extras.get("underlying_labels") == "name"
                             else "ticker")

    # ── Outline ────────────────────────────────────────────────────────────
    # Decide which chapters this report actually contains BEFORE the contents
    # page is drawn, because the contents page is page 2 and the body that it
    # lists has not run yet. Each flag below is the OR of exactly the conditions
    # the corresponding block uses further down, hoisted here so the list and the
    # headings are settled by one evaluation instead of two guesses.
    _show_terms = _inc("note_terms")
    # The observation schedule (coupon / autocall ladder) is a Phoenix concept — a
    # Participation note is a single maturity payoff, so it doesn't apply there.
    _is_part_note = getattr(terms, "note_type", "") == "participation" or (getattr(terms, "capital_guarantee", 0) or 0) > 0
    _show_obs   = _inc("obs_schedule") and not _is_part_note
    _show_diag  = _inc("note_diagram")
    _show_desc  = _inc("note_description")

    bt_figures  = bt_figures or {}
    params      = results.get("params", [])
    prob_by_period = results.get("prob_autocall_by_period", [])
    # Back-compat: sessions from before multi-panel only stored one wof figure.
    _panels = figures.get("panels")
    if not _panels and figures.get("single_path_wof") is not None:
        _panels = [{"title": None, "wof": figures.get("single_path_wof"),
                    "num": figures.get("single_path_num", 0)}]
    _bt_panels = bt_figures.get("panels") or []

    _has_mc = bool(
        _inc("mc_metrics")
        or (_inc("mc_outcome") and figures.get("outcome") is not None)
        or _inc("mc_irr")
        or (_inc("mc_autocall") and any(p > 0 for p in prob_by_period))
        or _inc("mc_wof")
        # The per-asset fans are indexed off `figures["individual"]`, not off
        # `asset_names` — a figure set can be short of one.
        or any(_inc(f"mc_fan_{i}")
               for i in range(len(figures.get("individual") or [])))
        or (_inc("mc_sample") and figures.get("sample") is not None)
        or (_inc("mc_single_wof")
            and (any(p.get("wof") is not None for p in (_panels or []))
                 or any(pi.get("png") for pi in (figures.get("panel_images") or []))))
        or (params and _inc("calib_table"))
        or (_inc("calib_corr") and figures.get("corr") is not None)
    )
    _has_bt = bool(bt_summary) and bool(
        _inc("bt_metrics")
        or (_inc("bt_outcome") and bt_figures.get("outcome") is not None)
        or (_inc("bt_pie") and bt_figures.get("pie") is not None)
        or (_inc("bt_irr") and bt_figures.get("irr_scatter") is not None)
        or (_inc("bt_prices") and bt_figures.get("prices") is not None)
        or (_inc("bt_path") and _bt_panels)
    )
    _has_live = bool(live_data) and bool(
        _inc("live_metrics")
        or (_inc("live_asset_table") and live_data.get("perf_today"))
        or (_inc("live_obs_table") and live_data.get("obs_rows"))
        or (_inc("live_chart") and live_figure is not None)
    )
    # The comparison tables are built here rather than at the point of use: the
    # chapter only exists if one of them has rows, and that has to be known
    # before the contents page is drawn.
    _diff_terms, _cmp_rows = _compare_tables(terms, compare_data, lang)
    _cmp_figs = compare_figures or {}
    _has_cmp = bool(compare_data) and bool(
        _diff_terms or _cmp_rows
        or _cmp_figs.get("irr") is not None or _cmp_figs.get("outcome") is not None
    )

    _chap = _plan_chapters({
        "note_terms": _show_terms or _show_obs or _show_diag or _show_desc,
        "issuer":     bool(pdf.issuer) and _inc("issuer_info"),
        "underlying": bool(underlying_metrics) and _inc("underlying_breakdown"),
        "mc":         _has_mc,
        "bt":         _has_bt,
        "live":       _has_live,
        "compare":    _has_cmp,
    })
    # `underlying_block` draws one page per underlying and needs the number.
    pdf.chapter_nums = _chap

    # ── 0. Front cover (toggleable, default on) ────────────────────────────
    if _inc("cover"):
        _front_cover_page(pdf, terms, lang, report_title, website, report_kind)

    # ── 1. Summary / contents page ─────────────────────────────────────────
    _cover_page(pdf, terms, results, asset_names, bt_summary, live_data, lang,
                logo_urls, issuer_logo_bytes, logo_tickers, inc=_inc,
                logo_overrides=_logo_ovr, chapters=_chap,
                cmp_terms=bool(_diff_terms), cmp_metrics=bool(_cmp_rows))

    # ── 2. Note terms + observation schedule (each toggleable) ──────────────
    # The first content page. Note Terms, the Observation Schedule, the Issuer
    # block and the Underlying Breakdown are all toggleable from the Build-report
    # panel's "Note details" category; with include_sections=None (programmatic
    # callers) every one renders, so existing callers are unaffected.
    if _show_terms or _show_obs or _show_diag or _show_desc:
        pdf.add_page()
        usable = pdf.w - pdf.l_margin - pdf.r_margin
        # 01 · Note Terms secondary head for the whole reference section.
        pdf.secondary_head(_chap.get("note_terms", ""), _t("kick_note_terms", lang),
                           _t("nt_page_title", lang))
        if _show_desc:
            # Systematic prose blurb (override or auto-generated from the terms).
            from core.note_description import describe_note
            _nd = (getattr(terms, "note_description", "") or "").strip() or describe_note(terms, lang)
            pdf.set_font(pdf._font_family, "", 9.5)
            pdf.set_text_color(*pdf.body_ink)
            # One paragraph per feature (step-down, One Star, Zenith, …) — the
            # generator separates them with a blank line.
            for _i, _para in enumerate([x for x in _nd.split("\n\n") if x.strip()]):
                if _i:
                    pdf.ln(1.6)
                pdf.multi_cell(usable, 5.0, pdf._safe(_para.strip()), align="J")
            pdf.ln(3)
        if _show_diag:
            pdf.subsection(_t("note_diagram", lang))
            _draw_note_diagram(pdf, terms, lang)
            pdf.ln(2)
        if _show_terms:
            _term_data = _term_rows(terms, lang)
            pdf.subsection(_t("note_terms", lang),
                           min_room=_table_room(len(_term_data)))
            pdf.data_table(
                [_t("key_terms_col_characteristic", lang), _t("key_terms_col_description", lang)],
                [[k, v] for k, v in _term_data],
                col_widths=[usable * 0.40, usable * 0.60],
                aligns=["L", "L"],
                rounded=True,
            )
        if _show_obs:
            # A sub-header under Note Terms (always a sub-label now — the 01 head
            # labels the section).
            pdf.subsection(_t("obs_schedule", lang),
                           min_room=_table_room(terms.n_obs))
            obs_times = terms.obs_times()
            sched     = terms.autocall_barrier_schedule()
            ac_rows = []
            for i, t_obs in enumerate(obs_times):
                eligible = _t("yes", lang) if (i + 1) >= terms.autocall_start_period else _t("no", lang)
                ac_rows.append([f"P{i+1}", f"{t_obs * 12:.0f}", f"{sched[i]:.0%}", eligible])
            pdf.data_table(
                [_t("period", lang), _t("time_y", lang), _t("ac_level", lang), _t("eligible", lang)],
                ac_rows,
                col_widths=[usable * 0.2, usable * 0.25, usable * 0.3, usable * 0.25],
                aligns=["L", "R", "R", "R"],
                rounded=True,
            )
        # The Model & Methodology callout describes the Heston Monte Carlo engine,
        # so it is included only when the report actually carries MC output. A
        # Note-details / backtest / live-only report (sim skipped) omits it.
        _mc_keys = {"mc_metrics", "mc_outcome", "mc_irr", "mc_autocall", "mc_wof",
                    "mc_sample", "mc_single_wof", "calib_table", "calib_corr"}
        _mc_keys |= {f"mc_fan_{i}" for i in range(len(asset_names or []))}
        if any(_inc(k) for k in _mc_keys):
            pdf.ln(8)   # breathing room before the model box
            pdf.callout(_t("model_box_title", lang), _t("model_box_body", lang))

    # ── 2b. Issuer information (toggleable; shown whenever an issuer is set) ──
    if pdf.issuer and _inc("issuer_info"):
        _issuer_desc = (getattr(terms, "issuer_description", "") or "") or (issuer_description or "")
        _ratings = [
            (_t("rating_sp", lang),    getattr(terms, "issuer_rating_sp", "") or ""),
            (_t("rating_moody", lang), getattr(terms, "issuer_rating_moody", "") or ""),
            (_t("rating_fitch", lang), getattr(terms, "issuer_rating_fitch", "") or ""),
        ]
        _ratings = [(l, v) for l, v in _ratings if v.strip()]
        pdf.secondary_head(_chap.get("issuer", ""), _t("kick_issuer", lang),
                           _t("issuer_info", lang), min_room=70.0)
        pdf.issuer_info_block(pdf.issuer, issuer_logo_bytes, _issuer_desc, _ratings)

    # ── 2c. Underlying Breakdown (per-underlying summary + 1Y price chart) ───
    # Toggleable; renders when underlying metrics were supplied. Metric values
    # come from the live pull; a per-field JSON override in terms.underlyings
    # wins, and 'description' is the curated company blurb.
    if underlying_metrics and _inc("underlying_breakdown"):
        _uls = getattr(terms, "underlyings", {}) or {}
        # Each underlying renders on its own page via underlying_block (one page
        # per underlying, like the prototype). Series-colour cycle for the ticker
        # badges mirrors the summary rail.
        _ul_pal = [primary_color, accent_color,
                   _blend(primary_color, section_rule_color, 0.55),
                   _AMBER_DARK, _blend(accent_color, _BLACK, 0.30)]
        for _ai, _nm in enumerate(asset_names):
            _m  = underlying_metrics.get(_nm, {}) or {}
            _ov = _uls.get(_nm, {}) or {}

            def _g(k, _m=_m, _ov=_ov):
                v = _ov.get(k)
                return v if v not in (None, "") else _m.get(k)

            _long = _g("long_name") or _nm
            # Prefer the fine-grained Yahoo industry ("Aerospace & Defense") over
            # the coarse sector ("Industrials"); fall back to sector when absent.
            _sub  = " · ".join(s for s in (_g("type"), _g("industry") or _g("sector")) if s)
            _iv_key = ("u_vol_3m_realized" if _g("iv_source") == "realized"
                       else "u_iv_3m")
            _band = [
                (_t("u_market_cap", lang), _fmt_mcap(_g("market_cap"))),
                (_t(_iv_key,        lang), _fmt_pct(_g("iv_3m"))),
                (_t("u_last_price", lang), _fmt_num(_g("last_price"))),
                (_t("u_rsi",        lang), _fmt_rsi(_g("rsi_14"))),
            ]
            # Fall back to the auto-pulled business summary (what the web card
            # shows) when the user never saved an explicit per-underlying override.
            _desc = _ov.get("description") or _m.get("business_summary") or ""
            _fig  = (underlying_price_figs or {}).get(_nm)
            _png  = (_fig_to_png(_fig, width=900, height=360,
                                 primary_color=primary_color, accent_color=accent_color,
                                 secondary_color=secondary_color)
                     if _fig is not None else None)
            _logo = (_logo_ovr.get(_nm)
                     or _load_ticker_logo(_nm, (logo_urls or {}).get(_nm, ""),
                                          (logo_tickers or {}).get(_nm)))
            _cap  = _t("fig_u_price", lang).format(name=_long)
            # Analyst consensus (buy/hold/sell) — a manual override wins, else the
            # Yahoo autofill carried on the metric (mirrors the web card fallback).
            _an_ov = _ov.get("analyst") or _m.get("analyst")
            _analyst = None
            if isinstance(_an_ov, dict):
                _tot = sum(float(_an_ov.get(k, 0) or 0) for k in ("buy", "hold", "sell"))
                if _tot > 0:
                    _analyst = [
                        (_t("sent_buy",  lang), float(_an_ov.get("buy", 0)  or 0) / _tot, (22, 163, 74)),
                        (_t("sent_hold", lang), float(_an_ov.get("hold", 0) or 0) / _tot, (245, 158, 11)),
                        (_t("sent_sell", lang), float(_an_ov.get("sell", 0) or 0) / _tot, (220, 38, 38)),
                    ]
            _tk  = (logo_tickers or {}).get(_nm) or str(_nm)[:5].upper()
            _col = _ul_pal[_ai % len(_ul_pal)]
            pdf.underlying_block(
                _long, _logo, _sub, _band, _desc, _png, _cap,
                analyst=_analyst, analyst_title=_t("u_analyst", lang),
                ticker=_tk, color=_col)

    # ── 3. Monte Carlo ─────────────────────────────────────────────────────
    # Low min_room: the metric band + first figure caption pack onto the Note
    # Terms page if there is room; figure() then moves any figure that won't fit
    # to the next page on its own. This keeps page 2 full instead of breaking
    # the whole MC block to a fresh page and leaving Note Terms half-empty.
    n_paths_val = int(np.asarray(results.get("annualized_returns", np.array([]))).shape[0])
    # Shared figure-rebrand kwargs — used by the MC, calibration, backtest and
    # live figures, so it must be defined regardless of which sections are on.
    _kw = dict(primary_color=primary_color, accent_color=accent_color,
               secondary_color=secondary_color)
    src_mc = f"{_t('src_mc', lang)}, {n_paths_val:,} {_t('paths_word', lang)}"

    def _lazy_divider(number, kicker, heading):
        """Emit a three-lens primary banner at most once, when the lens's first
        included item is drawn — so a fully-toggled-off lens leaves no divider."""
        state = {"done": False}
        def ensure():
            if not state["done"]:
                pdf.section_divider(number, kicker, heading)
                state["done"] = True
        return ensure

    def _lazy_section(title, min_room=146.0, before=None):
        """Emit a section header at most once, only when its first included item
        is actually drawn — so a section with everything toggled off leaves no
        empty header behind. ``before`` is a lazy part divider fired first (it is
        idempotent), so whichever sub-section of a lens renders first also draws
        that lens's divider."""
        state = {"done": False}
        def ensure():
            if before is not None:
                before()
            if not state["done"]:
                pdf.start_section(title, min_room=min_room)
                state["done"] = True
        return ensure

    # Lens 1 of 3 — the forward-looking model. Drawn once, before whichever MC
    # sub-section renders first.
    _mc_div = _lazy_divider(_chap.get("mc", ""), _t("lens_mc", lang), _t("sec_mc_heading", lang))

    # 3a. Payoff & Distribution — summary metrics, IRR distribution, autocall table.
    # Reserve enough room for the metric band + the IRR figure so the section
    # doesn't start a band at the bottom of a page and orphan its chart overleaf.
    _sec = _lazy_section(_t("mc_subtab_payoff", lang), min_room=150.0, before=_mc_div)
    if _inc("mc_metrics"):
        _sec()
        # Knock-in metrics: probability of a capital-costing knock-in (barrier
        # breached AND not rescued) and the mean IRR conditional on it. Rescued
        # breaches are excluded — they redeem at par, so they aren't knock-ins.
        _p_ki = results.get("prob_knock_in_total", 0)
        _lgki = results.get("loss_given_knock_in")
        _lgki_str = f"{_lgki:.2%}" if _lgki is not None and _lgki == _lgki else "—"  # nan-safe
        _att = results.get("avg_time_to_autocall")
        # Durations are quoted in months; the engine reports years.
        _att_str = f"{_att * 12:.1f} mo" if _att is not None and _att == _att else "—"  # nan-safe
        if getattr(terms, "note_type", "") == "participation":
            # Participation never autocalls / pays coupons — show redemption metrics.
            _band = [
                (_t("expected_redemption", lang), f"{results.get('expected_nominal_payout', 1):.2%}"),
                (_t("expected_irr",        lang), f"{results.get('expected_irr', 0):.2%}"),
                (_t("p_below_par",         lang), f"{_p_ki:.2%}"),
                (_t("p_above_par",         lang), f"{results.get('prob_above_par', 0):.1%}"),
            ]
            if results.get("prob_at_cap") is not None:
                _band.append((_t("p_at_cap", lang), f"{results.get('prob_at_cap', 0):.1%}"))
            if results.get("prob_knocked_out") is not None:
                _band.append((_t("p_knocked_out", lang), f"{results.get('prob_knocked_out', 0):.1%}"))
            _band += [
                (_t("p5_redemption", lang), f"{results.get('p5_redemption', 1):.2%}"),
                (_t("n_paths",       lang), f"{n_paths_val:,}"),
            ]
            pdf.metric_band(_band)
        else:
            pdf.metric_band([
                (_t("expected_irr",       lang), f"{results.get('expected_irr', 0):.2%}"),
                (_t("total_return_short", lang), f"{results.get('expected_total_return', 0):.2%}"),
                (_t("prob_autocall",      lang), f"{results.get('prob_autocall', 0):.1%}"),
                (_t("avg_time_autocall",  lang), _att_str),
                (_t("prob_knock_in",      lang), f"{_p_ki:.2%}"),
                (_t("loss_given_ki",      lang), _lgki_str),
                (_t("n_paths",            lang), f"{n_paths_val:,}"),
            ])
    if _inc("mc_outcome") and figures.get("outcome") is not None:
        _sec()
        _outcome_cap = "fig_redemption" if getattr(terms, "note_type", "") == "participation" else "fig_outcome"
        pdf.figure(_fig_to_png(figures.get("outcome"), width=900, height=300, **_kw),
                   _t(_outcome_cap, lang), src_mc)
    if _inc("mc_irr"):
        _sec()
        pdf.figure(_fig_to_png(figures.get("irr_dist"), **_kw), _t("fig_irr", lang), src_mc)
    # Skip when the note can't autocall (participation ⇒ all-zero) — the table is
    # meaningless there, and `obs_times` isn't bound (the obs schedule is hidden).
    if _inc("mc_autocall") and any(p > 0 for p in prob_by_period):
        _sec()
        # Seasoning indexing contract (see CLAUDE.md): every per-period array is
        # aligned to the PRICED WINDOW, and column i describes term-sheet period
        # `period_offset + i + 1`. Display layers add the offset — the web ones
        # did, this table did not. It labelled window indices as term-sheet
        # periods, zipped the FIRST observation times against the REMAINING
        # probabilities, and tested eligibility on the window index, so a
        # seasoned note's report was wrong in three ways at once.
        _off = int(results.get("period_offset", results.get("periods_elapsed", 0)) or 0)
        _obs_times = list(terms.obs_times())[_off:]
        pdf.subsection(_t("autocall_by_period", lang),
                       min_room=_table_room(len(prob_by_period)))
        rows = []
        for i, (t_obs, p_ac) in enumerate(zip(_obs_times, prob_by_period)):
            _abs = _off + i + 1                       # term-sheet period number
            eligible = _t("yes", lang) if _abs >= terms.autocall_start_period else _t("no", lang)
            rows.append([f"P{_abs}", f"{t_obs * 12:.0f}", f"{p_ac:.2%}", eligible])
        pdf.data_table(
            [_t("period", lang), _t("time_y", lang), _t("p_autocall", lang), _t("eligible", lang)],
            rows,
            col_widths=[usable * 0.2, usable * 0.25, usable * 0.3, usable * 0.25],
            aligns=["L", "R", "R", "R"],
            rounded=True,
        )

    # 3b. Price Paths — worst-of fan + per-underlying simulated distributions
    _sec = _lazy_section(_t("mc_subtab_paths", lang), before=_mc_div)
    if _inc("mc_wof"):
        _sec()
        _wof_cap = "fig_wof_part" if _is_participation(terms) else "fig_wof"
        pdf.figure(_fig_to_png(figures.get("wof_fan"), **_kw), _t(_wof_cap, lang), src_mc)
    for i, (nm, fig) in enumerate(figures.get("individual") or []):
        if _inc(f"mc_fan_{i}"):
            _sec()
            pdf.figure(_fig_to_png(fig, **_kw),
                       _t("fig_individual", lang).format(name=nm), src_mc)
    if _inc("mc_sample") and figures.get("sample") is not None:
        _sec()
        pdf.figure(_fig_to_png(figures.get("sample"), **_kw), _t("fig_sample", lang), src_mc)

    # 3c. Path Explorer — the simulated path(s) the user last viewed. One worst-of
    # chart per comparison panel, captioned with the user's panel title (or the
    # default "Worst-of path #N"). The per-asset price chart was removed from the
    # explorer, so it is no longer in the report either.
    _sec = _lazy_section(_t("mc_subtab_explorer", lang), before=_mc_div)
    if _inc("mc_single_wof") and _panels:
        for _p in _panels:
            if _p.get("wof") is None:
                continue
            _sec()
            _cap = _p.get("title") or _t("fig_single_wof", lang).format(n=_p.get("num", 0))
            pdf.figure(_fig_to_png(_p["wof"], **_kw), _cap, src_mc)
    # Client-captured path-explorer selection(s) — the exact chart(s) the user was
    # viewing, embedded as report-styled PNGs (already the light report palette).
    if _inc("mc_single_wof"):
        for _i, _pi in enumerate(figures.get("panel_images") or []):
            if not _pi.get("png"):
                continue
            _sec()
            _cap = _pi.get("title") or _t("fig_single_wof", lang).format(n=_i + 1)
            pdf.figure(_pi["png"], _cap, src_mc)

    # ── 4. Calibration ─────────────────────────────────────────────────────
    # Still part of the Monte Carlo lens (the model behind the simulation), so it
    # carries the same "01" divider rather than opening a new part.
    _sec = _lazy_section(_t("calibration", lang), before=_mc_div)
    if params and _inc("calib_table"):
        _sec()
        # Build the calibration table.  The "Asset" column uses an inline logo +
        # name approach: we draw the table row-by-row so we can interleave the
        # small logo image at the left edge of each asset row.
        n_assets   = len(params)
        # Asset column widened (long company names like "International Business
        # Machines" were clipped at 0.18); the eight numeric columns absorb the
        # difference and still fit their short values/headers.
        col_w_asset = usable * 0.24
        col_w_rest  = usable * 0.095
        col_widths  = [col_w_asset] + [col_w_rest] * 8
        headers     = [_t("asset", lang), _t("calib_s0", lang), _t("calib_mu", lang),
                       _t("calib_v0", lang), _t("calib_theta", lang),
                       "kappa", "xi", "rho", _t("feller", lang)]
        aligns      = ["L"] + ["R"] * 8

        # Prefetch each asset's logo so the table can place it inline.
        logo_cache: dict[str, bytes | None] = {}
        for p in params:
            nm  = str(p.name)
            url = (logo_urls or {}).get(nm, "")
            sym = (logo_tickers or {}).get(nm)
            logo_cache[nm] = _logo_ovr.get(nm) or _load_ticker_logo(nm, url, sym)

        # Render via the shared rounded logo table (rounded card + rounded-top
        # header + zebra rows + inline ticker logos) so the calibration table
        # matches the Note Terms / observation tables. (It used to be a
        # hand-rolled square table — the only one in the report without rounded
        # corners.)
        calib_rows = []
        for p in params:
            try:
                ok, _ = p.feller_condition()
            except Exception:
                ok = False
            calib_rows.append([
                str(p.name),
                f"{p.S0:,.2f}", f"{p.mu * 100:.1f}%",
                f"{np.sqrt(p.V0) * 100:.1f}%", f"{np.sqrt(p.theta) * 100:.1f}%",
                f"{p.kappa:.2f}", f"{p.xi:.2f}", f"{p.rho:.2f}",
                "OK" if ok else "!",
            ])
        pdf.logo_row_table(headers, calib_rows, logos=logo_cache,
                           col_widths=col_widths, aligns=aligns)
    if _inc("calib_corr") and figures.get("corr") is not None:
        _sec()
        pdf.figure(_fig_to_png(figures.get("corr"), width=560, height=460, **_kw),
                   _t("fig_corr", lang), _t("src_hist", lang), w=105, h=86)

    # ── 5. Historical backtest ─────────────────────────────────────────────
    # Lens 2 of 3 — the realised-history lens.
    _bt_div = _lazy_divider(_chap.get("bt", ""), _t("lens_bt", lang), _t("sec_bt_heading", lang))
    # 5a. Outcomes & Summary — metrics, outcome bar, worst-asset pie, IRR scatter.
    # Same keep-together reserve as the MC payoff section (band + first chart).
    _sec = _lazy_section(_t("bt_subtab_outcomes", lang), min_room=150.0, before=_bt_div)
    if bt_summary and _inc("bt_metrics"):
        _sec()
        # Mirror the Monte Carlo metric band (same measures, same order) so the
        # two lenses read in parallel: IRR, total return, P(autocall), P(knock-in),
        # loss-given-knock-in, sample size. Median IRR (a backtest extra) is in
        # the executive summary rather than the band.
        _bt_lgki = bt_summary.get("loss_given_ki")
        if _bt_lgki is None:
            _bt_lgki = bt_summary.get("loss_given_knock_in")
        _bt_lgki_pdf = (f"{_bt_lgki:.2%}"
                        if _bt_lgki is not None and _bt_lgki == _bt_lgki else "—")  # nan-safe
        _bt_att = bt_summary.get("avg_time_to_autocall")
        _bt_att_str = f"{_bt_att * 12:.1f} mo" if _bt_att is not None and _bt_att == _bt_att else "—"  # nan-safe
        if _is_participation(terms):
            # Participation: realised redemption outcomes, mirroring the MC band —
            # no autocall / knock-in ladder.
            pdf.metric_band([
                (_t("expected_redemption", lang), f"{bt_summary.get('expected_nominal_payout', 1):.2%}"),
                (_t("bt_mean_irr",         lang), f"{bt_summary.get('mean_irr', 0):.2%}"),
                (_t("total_return_short",  lang), f"{bt_summary.get('expected_total_return', 0):.2%}"),
                (_t("p_above_par",         lang), f"{bt_summary.get('prob_above_par', 0):.1%}"),
                (_t("p_below_par",         lang), f"{bt_summary.get('prob_knock_in_total', bt_summary.get('prob_below_par', 0)):.2%}"),
                (_t("bt_n_issues",         lang), str(bt_summary.get("n_issues", 0))),
            ])
        else:
            pdf.metric_band([
                (_t("bt_mean_irr",        lang), f"{bt_summary.get('mean_irr', 0):.2%}"),
                (_t("total_return_short", lang), f"{bt_summary.get('expected_total_return', 0):.2%}"),
                (_t("bt_autocalled_pct",  lang), f"{bt_summary.get('prob_called', 0):.1%}"),
                (_t("avg_time_autocall",  lang), _bt_att_str),
                (_t("bt_knock_in_pct",    lang), f"{bt_summary.get('prob_knock_in', 0):.1%}"),
                (_t("bt_loss_given_ki",   lang), _bt_lgki_pdf),
                (_t("bt_n_issues",        lang), str(bt_summary.get("n_issues", 0))),
            ])
    if bt_summary and _inc("bt_outcome") and bt_figures.get("outcome") is not None:
        _sec()
        _bt_out_cap = "fig_redemption" if _is_participation(terms) else "fig_bt_outcome"
        pdf.figure(_fig_to_png(bt_figures.get("outcome"), **_kw),
                   _t(_bt_out_cap, lang), _t("src_hist", lang))
    if bt_summary and _inc("bt_pie") and bt_figures.get("pie") is not None:
        _sec()
        pdf.figure(_fig_to_png(bt_figures.get("pie"), **_kw),
                   _t("fig_bt_pie", lang), _t("src_hist", lang))
    if bt_summary and _inc("bt_irr") and bt_figures.get("irr_scatter") is not None:
        _sec()
        pdf.figure(_fig_to_png(bt_figures.get("irr_scatter"), **_kw),
                   _t("fig_bt_irr", lang), _t("src_hist", lang))

    # 5b. Price History — normalised underlying price paths over the window
    if bt_summary and bt_figures.get("prices") is not None and _inc("bt_prices"):
        _bt_div()
        pdf.start_section(_t("bt_subtab_prices", lang))
        pdf.figure(_fig_to_png(bt_figures.get("prices"), **_kw),
                   _t("fig_bt_prices", lang), _t("src_hist", lang))

    # 5c. Historical Path Explorer — one worst-of path per comparison panel, with
    # the user's panel title (or the issue date). Mirrors the on-screen explorer.
    if bt_summary and _inc("bt_path") and _bt_panels:
        _bt_div()
        pdf.start_section(_t("bt_subtab_explorer", lang))
        for _p in _bt_panels:
            if _p.get("path") is None:
                continue
            _cap = _p.get("title") or _t("fig_bt_path", lang).format(issue=_p.get("issue", ""))
            pdf.figure(_fig_to_png(_p["path"], **_kw), _cap, _t("src_hist", lang))

    # ── 6. Current performance ─────────────────────────────────────────────
    if live_data:
        # Lens 3 of 3 — the live, today lens. No section_title: the divider names
        # it; the metric band and the asset/observation sub-tables follow.
        _live_div = _lazy_divider(_chap.get("live", ""), _t("lens_live", lang),
                                  _t("sec_live_heading", lang))
        if _inc("live_metrics"):
            _live_div()
            pdf.metric_band([
                (_t("live_wof_today",   lang), f"{live_data.get('wof_today', 0):.1%}"),
                (_t("live_worst_asset", lang), str(live_data.get("worst_asset", ""))),
                (_t("live_irr_to_date", lang), f"{live_data.get('irr_to_date', 0):.2%}"),
                (_t("live_elapsed",     lang), f"{live_data.get('elapsed_years', 0) * 12:.1f}"),
            ])

        perf_today = live_data.get("perf_today", {})
        if perf_today and _inc("live_asset_table"):
            _live_div()
            pdf.subsection(_t("live_asset_perf", lang),
                           min_room=_table_room(len(perf_today), row_h=10.0))
            _perf_logos = {
                nm: (_logo_ovr.get(nm)
                     or _load_ticker_logo(nm, (logo_urls or {}).get(nm, ""),
                                          (logo_tickers or {}).get(nm)))
                for nm in perf_today
            }
            pdf.logo_row_table(
                [_t("asset", lang), _t("performance", lang)],
                [[name, f"{perf:.2%}"] for name, perf in perf_today.items()],
                _perf_logos,
                col_widths=[usable * 0.5, usable * 0.5],
                aligns=["L", "R"],
            )

        obs_rows = live_data.get("obs_rows", [])
        if obs_rows and _inc("live_obs_table"):
            _live_div()
            pdf.subsection(_t("live_obs_history", lang),
                           min_room=_table_room(len(obs_rows)))
            obs_headers = list(obs_rows[0].keys())
            obs_data    = [[str(r.get(h, "")) for h in obs_headers] for r in obs_rows]
            n_cols = len(obs_headers)
            if n_cols == 6:
                obs_w = [usable * f for f in (0.08, 0.13, 0.37, 0.14, 0.13, 0.15)]
            else:
                obs_w = [usable / n_cols] * n_cols
            pdf.data_table(obs_headers, obs_data, col_widths=obs_w,
                           aligns=["L"] * n_cols, rounded=True)

        if _inc("live_chart") and live_figure is not None:
            _live_div()
            pdf.figure(_fig_to_png(live_figure, **_kw), _t("fig_live", lang), _t("src_hist", lang))

    # ── 6b. Comparison (A vs B) ────────────────────────────────────────────
    # Optional lens: a side-by-side of the primary note (A) and a variant (B).
    # Renders a differing-terms table, a projected-metrics A/B/Δ table and the
    # overlaid IRR + outcome charts. Only present when a Note B was supplied.
    if _has_cmp:
        _cmp_div = _lazy_divider(_chap.get("compare", ""), _t("lens_compare", lang),
                                 _t("sec_compare_heading", lang))

        # 6b-i. Differing terms — one row per term that changed between A and B.
        # (Both tables are built by `_compare_tables`, above the contents page.)
        if _diff_terms:
            _cmp_div()
            pdf.start_section(_t("cmp_terms_title", lang),
                              min_room=_table_room(len(_diff_terms)))
            pdf.data_table(
                [_t("cmp_col_term", lang), _t("cmp_col_a", lang), _t("cmp_col_b", lang)],
                _diff_terms,
                col_widths=[usable * 0.4, usable * 0.3, usable * 0.3],
                aligns=["L", "R", "R"])

        # 6b-ii. Projected metrics — A · B · Δ.
        if _cmp_rows:
            _cmp_div()
            pdf.start_section(_t("cmp_metrics_title", lang),
                              min_room=_table_room(len(_cmp_rows)))
            pdf.data_table(
                [_t("cmp_col_metric", lang), _t("cmp_col_a", lang),
                 _t("cmp_col_b", lang), _t("cmp_col_delta", lang)],
                _cmp_rows,
                col_widths=[usable * 0.4, usable * 0.2, usable * 0.2, usable * 0.2],
                aligns=["L", "R", "R", "R"])

        # 6b-iii. Overlaid distributions.
        if _cmp_figs.get("irr") is not None:
            _cmp_div()
            pdf.figure(_fig_to_png(_cmp_figs["irr"], **_kw), _t("cmp_fig_irr", lang), src_mc)
        if _cmp_figs.get("outcome") is not None:
            _cmp_div()
            pdf.figure(_fig_to_png(_cmp_figs["outcome"], **_kw), _t("cmp_fig_outcome", lang), src_mc)

    # ── 7. Glossary ────────────────────────────────────────────────────────
    # Reference list of the financial terms used throughout the report. Always
    # included (like the disclaimer). Each entry flows as a bold term followed
    # by its definition, wrapping naturally. Starts on its own fresh page so the
    # reference block is never stranded a few lines below an unrelated chart.
    pdf.add_page()
    pdf.start_section(_t("glossary_title", lang), min_room=70.0)
    # Only print terms whose content is actually in this report (memory/one-star
    # only when the note uses them; MC/backtest/underlying/vol terms only when
    # those sections are present); "core" note mechanics always print.
    _g_active = {"core"}
    # Phoenix mechanics vs participation payoff terms are mutually exclusive families.
    if _is_participation(terms):
        _g_active.add("part")
    else:
        _g_active.add("phx")
        if getattr(terms, "memory", False):             _g_active.add("mem")
        if getattr(terms, "one_star_level", None) is not None: _g_active.add("os")
    if results:                                         _g_active.add("mc")
    if bt_summary:                                      _g_active.add("bt")
    if underlying_metrics:                              _g_active.add("ul")
    _glos = _GLOSSARY.get(lang, _GLOSSARY["en"])
    _entries = []
    for _i, (_term, _defn) in enumerate(_glos):
        _tags = _GLOSSARY_TAGS[_i] if _i < len(_GLOSSARY_TAGS) else {"core"}
        if _g_active.isdisjoint(_tags):
            continue
        _entries.append((_term, _defn))
    # Two-column flow (the prototype layout): green bold term + ' — ' + grey
    # definition, each a break-avoiding paragraph, balanced across the columns.
    pdf.ln(1)
    try:
        with pdf.text_columns(ncols=2, gutter=9, balance=True) as _cols:
            for _term, _defn in _entries:
                _par = _cols.paragraph(bottom_margin=2.4, line_height=1.35)
                pdf._sf(8, "semibold"); pdf.set_text_color(*pdf.primary_color)
                _par.write(pdf._safe(f"{_term} — "))
                pdf._sf(8, "regular"); pdf.set_text_color(*pdf.body_ink)
                _par.write(pdf._safe(_defn))
                _cols.end_paragraph()
    except Exception as _e:                     # robust fallback to single-column flow
        print(f"[report] glossary columns fell back: {_e}")
        for _term, _defn in _entries:
            if pdf.get_y() > pdf.h - 34:
                pdf.add_page()
            pdf._sf(8, "semibold"); pdf.set_text_color(*pdf.primary_color)
            pdf.write(4.4, pdf._safe(f"{_term} — "))
            pdf._sf(8, "regular"); pdf.set_text_color(*pdf.body_ink)
            pdf.write(4.4, pdf._safe(_defn))
            pdf.ln(6.2)
    pdf.set_text_color(*_TEXT)

    # ── 8. Disclaimers (own back page) ─────────────────────────────────────
    _disclaimer_text = (_brand_text(_b.get("disclaimer_body"), lang)
                        or _t("disclaimer_body", lang))
    if _inc("cover"):
        # Branded full-bleed back page, pairing the branded front cover.
        _full_bleed_disclaimer(pdf, lang, _disclaimer_text, website)
    else:
        pdf.add_page()
        pdf.start_section(_t("disclaimer_title", lang), min_room=90.0)
        pdf.set_text_color(*_TEXT_SOFT)
        _disclaimer_paras = _disclaimer_text.split("\n\n")
        for idx, para in enumerate(_disclaimer_paras):
            pdf._sf(7.5, "bold" if idx == len(_disclaimer_paras) - 1 else "regular")
            pdf.multi_cell(0, 3.8, _safe(para))
            pdf.ln(2.5)
        pdf.set_text_color(*_TEXT)

    # The final page never triggers add_page, so decorate its void directly
    # (no-op on a full-bleed disclaimer / cover page).
    pdf._decorate_void()
    _stamp_attribution(pdf)
    _stamp_provenance(pdf, terms, report_title)
    return bytes(pdf.output())
