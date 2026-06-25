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

Branding affects the PDF only; the Streamlit UI theme is set separately in
app/style.css + .streamlit/config.toml. Logo resolution order is local file →
base64 → URL (see _load_logo). Chart colours are remapped from the fixed
navy/blue source palette of app/charts.py onto (accent, secondary) with the
green-ramp hue derived from the accent — see _rebrand_figure.
"""

from __future__ import annotations

import io
import re
import base64
import colorsys
import datetime
import urllib.request
import warnings
import numpy as np
from pathlib import Path
from fpdf import FPDF

_REPO_ROOT       = Path(__file__).parent.parent
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
_TEXT             = (43,  61, 79)   # dark navy-slate #2B3D4F  (was near-black #212121)
_TEXT_SOFT        = (107, 114, 128) # warm grey  #6b7280
_HAIRLINE         = (203, 213, 225) # cool grey  #cbd5e1
_RULE_LIGHT       = (226, 232, 240) # slate-100  #e2e8f0
_ROW_ALT          = (245, 246, 250) # slate-50   #F5F6FA — zebra rows
_WHITE            = (255, 255, 255)
_COVER_BAND_H     = 38              # mm — height of the top cover band
_DEFAULT_SECONDARY = (198, 148, 38) # warm institutional gold #C69426 — 2nd chart category

# The full branding schema. Anything outside this set warns (mirrors
# NoteTerms.from_dict) so a typo like "primary_colour" surfaces immediately
# instead of being silently ignored.
_KNOWN_BRANDING_KEYS = {
    "firm_name", "primary_color", "accent_color", "chart_secondary_color",
    "logo_file", "logo_base64", "logo_url",
    "report_title", "website", "contact", "footer_note",
    "section_rule_color",   # NEW — color of the rule drawn under section titles
    "panel_color",          # NEW — fill of the cover sidebar + figure/callout/issuer cards
    "sidebar_bar_color",    # NEW — solid bar across the top of the cover sidebar
    "disclaimer_body",      # NEW — overrides the full disclaimer body text
    "cover_logo_base64",    # NEW — white knockout logo for the full-bleed cover
    "cover_image_base64",   # NEW — optional full-bleed cover background photo
    "cover_overlay_color",  # NEW — colour of the overlay drawn over the cover photo
    "cover_overlay_opacity",# NEW — 0..1 opacity of that overlay
    "title_font", "body_font",  # NEW — custom report fonts (see _register_brand_fonts)
}
_HEX_KEYS = ("primary_color", "accent_color", "chart_secondary_color",
             "section_rule_color", "panel_color", "sidebar_bar_color",
             "cover_overlay_color")


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert '#RGB' or '#RRGGBB' to an (R, G, B) integer tuple. Raises ValueError
    on anything that is not a clean 3- or 6-digit hex string."""
    h = hex_str.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        raise ValueError(f"not a 6-digit hex colour: {hex_str!r}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _validate_branding(branding: dict | None) -> None:
    """Warn (don't raise) on unrecognised branding keys — mirrors the early-typo
    surfacing of NoteTerms.from_dict. A no-op when branding is empty."""
    if not branding:
        return
    unknown = [k for k in branding if k not in _KNOWN_BRANDING_KEYS]
    if unknown:
        warnings.warn(
            f"branding: ignoring unrecognised keys {unknown}. "
            f"Known keys: {sorted(_KNOWN_BRANDING_KEYS)}.",
            stacklevel=2,
        )


def _brand_text(value, lang: str):
    """Resolve a branding text field that may be a plain string (single language,
    used as-is) OR a per-language dict like {"en": "...", "es": "..."}. For a dict,
    returns the requested language; if that language is absent it returns None so
    the caller falls back to the built-in translated default — this is what lets a
    Spanish-only firm disclaimer NOT bleed into an English report. None/empty in,
    None out."""
    if isinstance(value, dict):
        v = value.get(lang)
        return v or None
    return value or None


def _branding_color(branding: dict | None, key: str,
                    default: tuple[int, int, int]) -> tuple[int, int, int]:
    """Resolve one hex colour from the branding dict, falling back to `default`
    (with a warning) when absent or malformed — never raises deep inside the PDF."""
    if not branding:
        return default
    raw = branding.get(key)
    if not raw:
        return default
    try:
        return _hex_to_rgb(raw)
    except (ValueError, TypeError):
        warnings.warn(
            f"branding['{key}'] = {raw!r} is not a valid hex colour "
            f"(e.g. '#003366'); using the default.",
            stacklevel=2,
        )
        return default


def _resolve_palette(branding: dict | None) -> tuple[
    tuple[int, int, int], tuple[int, int, int],
    tuple[int, int, int], tuple[int, int, int], str
]:
    """Return (primary, accent, secondary, section_rule, firm_name) from the
    branding dict. Malformed hex values fall back to defaults with a warning;
    never raises. section_rule defaults to the accent colour when absent."""
    if not branding:
        return _DEFAULT_PRIMARY, _DEFAULT_ACCENT, _DEFAULT_SECONDARY, _DEFAULT_ACCENT, "Structured Note Analytics"
    primary      = _branding_color(branding, "primary_color",         _DEFAULT_PRIMARY)
    accent       = _branding_color(branding, "accent_color",          _DEFAULT_ACCENT)
    secondary    = _branding_color(branding, "chart_secondary_color", _DEFAULT_SECONDARY)
    section_rule = _branding_color(branding, "section_rule_color",    accent)
    firm         = branding.get("firm_name", "Structured Note Analytics") or "Structured Note Analytics"
    return primary, accent, secondary, section_rule, firm


# ──────────────────────────────────────────────────────────────────────────────
# Translations
# ──────────────────────────────────────────────────────────────────────────────
_LABELS: dict[str, dict[str, str]] = {
    "series_title":          {"en": "Structured Note Analytics",         "es": "Análisis de Nota Estructurada"},
    "report_eyebrow":        {"en": "STRUCTURED NOTE ANALYTICS",         "es": "ANÁLISIS DE NOTA ESTRUCTURADA"},
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
    "disclaimer_title":      {"en": "Important Information",             "es": "Información Importante"},
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
    "issuer":                {"en": "Issuer",                            "es": "Emisor"},
    "expected_irr":          {"en": "Expected IRR p.a.",                 "es": "TIR esperada anual"},
    "expected_total_return": {"en": "Expected total return",             "es": "Retorno total esperado"},
    "total_return_short":    {"en": "Total return",                      "es": "Retorno total"},
    "in_this_report":        {"en": "In this report",                    "es": "En este informe"},
    "expected_coupon":       {"en": "Expected coupon income",            "es": "Cupón total esperado"},
    "prob_autocall":         {"en": "P(autocall)",                       "es": "P(autocall)"},
    "prob_knock_in":         {"en": "P(knock-in)",                       "es": "P(knock-in)"},
    "loss_given_ki":         {"en": "Loss given knock-in",               "es": "Pérdida dado knock-in"},
    "n_paths":               {"en": "Simulated paths",                   "es": "Caminos simulados"},
    "autocall_by_period":    {"en": "Autocall Probability by Period",    "es": "Probabilidad de Autocall por Período"},
    "fig_outcome":           {"en": "Outcome breakdown",                 "es": "Distribución de resultados"},
    "period":                {"en": "Period",                            "es": "Período"},
    "time_y":                {"en": "Time (yrs)",                        "es": "Tiempo (años)"},
    "p_autocall":            {"en": "P(autocall)",                       "es": "P(autocall)"},
    "ac_level":              {"en": "Barrier",                           "es": "Barrera"},
    "eligible":              {"en": "Eligible",                          "es": "Elegible"},
    "yes":                   {"en": "Yes",                               "es": "Sí"},
    "no":                    {"en": "No",                                "es": "No"},
    "fig_irr":               {"en": "Distribution of simple annualised IRR across simulated paths",
                              "es": "Distribución de TIR anual simple en los caminos simulados"},
    "fig_wof":               {"en": "Worst-of performance fan with barrier levels",
                              "es": "Abanico worst-of con niveles de barrera"},
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
    "live_elapsed":          {"en": "Elapsed (years)",                   "es": "Transcurrido (años)"},
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
        ("One Star", "A clause whereby a single underlying at or above a set level satisfies the coupon, autocall and par-redemption conditions on its own, even when the worst performer breached its barrier."),
        ("Strike / initial fixing", "The reference price of each underlying at issue, set to 100%; all performance levels are measured against it."),
        ("Total return", "The note's overall return at redemption as a fraction of par: all coupons received plus principal repaid, minus 1. Measured over the realised holding period and NOT annualised."),
        ("IRR (simple, p.a.)", "Annualised return on a path, computed as total return divided by time held — the convention used to quote note coupons. Differs from total return whenever the note is held for other than exactly one year (e.g. an early autocall annualises a small total return up to a larger figure)."),
        ("Heston model", "A stochastic-volatility model in which variance itself follows a mean-reverting random process; used here to simulate the underlyings."),
        ("Student-t copula", "A dependence structure linking the assets' shocks with fatter joint tails than a Gaussian copula, capturing co-movement in stress."),
        ("Volatility (σ)", "The annualised standard deviation of an asset's returns — a measure of how much its price fluctuates. Higher volatility widens the outcome distribution and raises the chance of breaching a barrier."),
        ("Implied volatility (ATM, 3M)", "Forward-looking volatility backed out from option prices — the market's expectation of future movement. 'ATM' uses the strike nearest spot (~100% moneyness, call and put averaged) at the expiry nearest three months."),
        ("Realized volatility", "Backward-looking volatility: the annualised standard deviation of recent daily log-returns (~3 months here). Shown in place of implied vol when an underlying has no listed options on the data source."),
        ("Moneyness / at-the-money (ATM)", "An option's strike relative to spot. At-the-money is a strike at ~100% of spot, and is the reference point for quoting a single headline implied volatility."),
        ("Monte Carlo simulation", "Estimating the note's outcomes by generating many random price paths under the model, pricing the payoff on each, and summarising across all paths."),
        ("Backtest", "Re-running the note's payoff over historical price windows — one per past issue date — to see how it would have performed in realised market history, as opposed to simulated paths."),
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
        ("Simulación de Monte Carlo", "Estimación de los resultados de la nota generando muchas trayectorias de precio aleatorias bajo el modelo, valorando el pago en cada una y resumiendo sobre todas las trayectorias."),
        ("Backtest", "Re-ejecución del pago de la nota sobre ventanas históricas de precios — una por cada fecha de emisión pasada — para ver cómo habría rendido en el mercado real, frente a las trayectorias simuladas."),
    ],
}

# Which report content each glossary term explains — index-aligned with the en/es
# lists above (both have the same 23 entries in the same order; index 11 is the
# One-Star / best-of-redemption clause in either language). A term only prints
# when the content that needs it is in the report. "core" = always relevant when
# there is a note at all.
_GLOSSARY_TAGS: list[set[str]] = [
    {"core"},        # 0  Autocallable note
    {"core"},        # 1  Autocall barrier
    {"core"},        # 2  Autocall observation
    {"core"},        # 3  Coupon (p.a.)
    {"core"},        # 4  Coupon barrier
    {"mem"},         # 5  Memory coupon
    {"core"},        # 6  Knock-in barrier
    {"core"},        # 7  Knock-in
    {"core"},        # 8  Capital loss
    {"core"},        # 9  Worst-of
    {"core"},        # 10 Phoenix
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
    {"mc"},          # 21 Monte Carlo simulation
    {"bt"},          # 22 Backtest
]


def _t(key: str, lang: str) -> str:
    return _LABELS.get(key, {}).get(lang, _LABELS.get(key, {}).get("en", key))


_ES_MONTHS = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio",
              "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

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


def _fmt_long_date(d: datetime.date, lang: str) -> str:
    """Locale-aware long date. English uses the platform month name; Spanish uses
    a built-in month table (no system locale dependency, no leftover English)."""
    if lang == "es":
        return f"{d.day} de {_ES_MONTHS[d.month]} de {d.year}"
    return d.strftime("%-d %B %Y")


def _fmt_month_year(d: datetime.date, lang: str) -> str:
    """Month + year (e.g. 'JUNIO 2026' / 'June 2026') for the cover."""
    if lang == "es":
        return f"{_ES_MONTHS[d.month]} {d.year}"
    return d.strftime("%B %Y")


# ──────────────────────────────────────────────────────────────────────────────
# Text sanitisation
# IBM Plex Sans covers all Latin/Greek/punctuation/math Unicode natively, so we
# only need to neutralise emojis and a handful of symbols it omits.
# ──────────────────────────────────────────────────────────────────────────────
_EMOJI_STRIP = {
    "✅": "OK", "⚠️": "!", "❌": "x", "🚀": ">>", "⏳": "...",
    "®": "", "™": "", "©": "",
}


def _safe(text: object, *, latin1: bool = False) -> str:
    """Sanitise text for the PDF.

    With IBM Plex Sans (Unicode font) only emojis need neutralising.
    Pass latin1=True only for the Helvetica fallback path.
    """
    s = str(text)
    for bad, good in _EMOJI_STRIP.items():
        s = s.replace(bad, good)
    if latin1:
        _LATIN1_MAP = {
            "—": "-", "–": "-", "−": "-", "·": "-", "•": "-",
            "→": "->", "←": "<-", "≥": ">=", "≤": "<=",
            "“": '"', "”": '"', "‘": "'", "’": "'",
            "…": "...", "×": "x", "÷": "/",
            "€": "EUR", "£": "GBP",
            "κ": "kappa", "θ": "theta", "ξ": "xi", "ρ": "rho",
            "σ": "sigma", "μ": "mu", "ν": "nu", "₀": "0", "√": "sqrt ",
        }
        for bad, good in _LATIN1_MAP.items():
            s = s.replace(bad, good)
        s = s.encode("latin-1", "ignore").decode("latin-1")
    return s


# ──────────────────────────────────────────────────────────────────────────────
# Font registration
# Primary: IBM Plex Sans individual TTF files (institutional quality, Unicode).
# Fallback: Helvetica (built-in, Latin-1 only).
# ──────────────────────────────────────────────────────────────────────────────

# Font family name exposed to _sf() — switches based on what is available
_FONT_FAMILY = "IBMPlexSans"   # overridden to "Helvetica" if IBM files absent


def _register_ibm_plex(pdf: FPDF) -> bool:
    """Register IBM Plex Sans TTF files. Returns True if all variants loaded."""
    _required = [_IBM_REGULAR, _IBM_BOLD, _IBM_SEMIBOLD, _IBM_LIGHT,
                 _IBM_ITALIC, _IBM_BOLDITALIC]
    if not all(p.exists() for p in _required):
        return False
    try:
        pdf.add_font("IBMPlexSans",      "",   str(_IBM_REGULAR),    uni=True)
        pdf.add_font("IBMPlexSans",      "B",  str(_IBM_BOLD),       uni=True)
        pdf.add_font("IBMPlexSans",      "I",  str(_IBM_ITALIC),     uni=True)
        pdf.add_font("IBMPlexSans",      "BI", str(_IBM_BOLDITALIC), uni=True)
        pdf.add_font("IBMPlexSansSB",    "",   str(_IBM_SEMIBOLD),   uni=True)
        pdf.add_font("IBMPlexSansLight", "",   str(_IBM_LIGHT),      uni=True)
        return True
    except Exception as exc:
        print(f"[PDF font] IBM Plex Sans registration failed: {exc}")
        return False


def _register_brand_fonts(pdf, branding: dict | None) -> None:
    """Route the report's title / body type to custom brand fonts when the brand
    provides them and the files exist. The branding keys `title_font` / `body_font`
    name a font (e.g. "Neulis Alt", "Galanti"); the TTF files are looked up as
    fonts/brand/<AlnumName>-<Style>.ttf (Style in Regular/Bold/Italic/BoldItalic).

    Title type is the bold/semibold (heading) weights; body type is regular/light/
    italic. Anything that can't be loaded silently keeps the IBM Plex mapping, so
    a brand that only ships some weights — or none — never breaks the report."""
    if getattr(pdf, "_font_family", "") != "IBMPlexSans":   # need the unicode TTF path
        return
    b = branding or {}
    if not (b.get("title_font") or b.get("body_font")):
        return

    def _register(font_name: str | None, styles: list[tuple[str, str]]):
        if not font_name:
            return None
        fam = "Brand" + "".join(c for c in str(font_name) if c.isalnum())
        loaded: set[str] = set()
        for code, suffix in styles:
            for cand in (_FONT_DIR / "brand" / f"{''.join(c for c in font_name if c.isalnum())}-{suffix}.ttf",):
                if cand.exists():
                    try:
                        pdf.add_font(fam, code, str(cand), uni=True)
                        loaded.add(code)
                    except Exception as e:
                        print(f"[PDF font] {font_name} {suffix} failed: {e}")
                    break
        if "" not in loaded:
            if font_name:
                print(f"[PDF font] brand font '{font_name}' not found in fonts/brand/ — using IBM Plex")
            return None
        print(f"[PDF font] brand font '{font_name}' registered ({sorted(loaded)})")
        return fam, loaded

    title = _register(b.get("title_font"), [("", "Bold")])
    body  = _register(b.get("body_font"),
                      [("", "Regular"), ("B", "Bold"), ("I", "Italic"), ("BI", "BoldItalic")])
    if title:
        tfam, _ = title
        pdf._sf_map["bold"] = (tfam, "")
        pdf._sf_map["semibold"] = (tfam, "")
    if body:
        bfam, bl = body
        pdf._sf_map["regular"] = (bfam, "")
        pdf._sf_map["light"]   = (bfam, "")
        pdf._sf_map["italic"]  = (bfam, "I" if "I" in bl else "")
        pdf._sf_map["bold_italic"] = (bfam, "BI" if "BI" in bl else ("I" if "I" in bl else ""))
        if not title and "B" in bl:   # no title font → body bold also carries headings
            pdf._sf_map["bold"] = (bfam, "B")
            pdf._sf_map["semibold"] = (bfam, "B")


# ──────────────────────────────────────────────────────────────────────────────
# FPDF subclass
# ──────────────────────────────────────────────────────────────────────────────

class _NotePDF(FPDF):
    """A4 portrait document with QIS-publication styling and IBM Plex Sans typography."""

    def __init__(self, lang: str = "en", issuer: str = "", doc_ref: str = "",
                 primary_color: tuple = _DEFAULT_PRIMARY,
                 accent_color: tuple = _DEFAULT_ACCENT,
                 firm_name: str = "Structured Note Analytics",
                 firm_logo_bytes: bytes | None = None,
                 report_title: str | None = None,
                 website: str = "", contact: str = "",
                 footer_note: str | None = None,
                 section_rule_color: tuple = _DEFAULT_ACCENT,
                 panel_color: tuple | None = None,
                 sidebar_bar_color: tuple | None = None):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.lang          = lang
        self.issuer        = issuer
        self.doc_ref       = doc_ref
        self.primary_color = primary_color
        self.accent_color  = accent_color
        self.section_rule_color = section_rule_color
        # Solid bar across the top of the cover sidebar panel. Defaults to the
        # PRIMARY colour so it matches the table headers (one brand colour across
        # the whole report); a brand may still pin it via `sidebar_bar_color`.
        self.sidebar_bar_color = sidebar_bar_color if sidebar_bar_color is not None else primary_color
        # Panel fill (cover sidebar, figure/callout/issuer cards). A brand may set
        # it explicitly via the `panel_color` key; otherwise it's a very light
        # tint of the brand PRIMARY so every panel echoes the firm palette. The
        # auto tint is derived from primary (not accent) so a bold accent — e.g. a
        # red — never produces a pink card; for the default navy it resolves to a
        # neutral cool-grey. An explicit value gives the firm exact control (e.g.
        # CADIEM pins its mint green that a 7% teal tint would wash out).
        self.panel_color = (panel_color if panel_color is not None
                            else _blend(primary_color, _WHITE, 0.93))
        self.firm_name     = firm_name
        self.firm_logo_bytes = firm_logo_bytes
        # Optional branding content (B5). report_title overrides the default
        # "Structured Note Analytics" eyebrow/subtitle; footer_note overrides the
        # default footer disclaimer line; website/contact print on the cover.
        self.report_title  = report_title
        self.website       = website or ""
        self.contact       = contact or ""
        self.footer_note   = footer_note
        # Aspect ratio so a wide wordmark isn't squashed into a square box.
        self.firm_logo_aspect = _logo_aspect(firm_logo_bytes, default=1.0)
        self._is_cover     = False
        self._cover_pages  = set()   # page numbers with no running header/footer (covers)
        self._fig_no       = 0
        # Locale-neutral numeric timestamp so the footer never shows an English
        # month abbreviation in a Spanish report.
        self._gen_dt       = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M")
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(auto=True, margin=28)
        self.alias_nb_pages()
        # IBM Plex Sans (Unicode); last resort the built-in Helvetica (Latin-1).
        if _register_ibm_plex(self):
            self._font_family = "IBMPlexSans"
            self._use_unicode = True
            self._sf_map = {
                "regular":     ("IBMPlexSans",      ""),
                "bold":        ("IBMPlexSans",      "B"),
                "bold_italic": ("IBMPlexSans",      "BI"),
                "italic":      ("IBMPlexSans",      "I"),
                "semibold":    ("IBMPlexSansSB",    ""),
                "light":       ("IBMPlexSansLight", ""),
            }
            print("[PDF font] Using IBM Plex Sans")
        else:
            self._font_family = "Helvetica"
            self._use_unicode = False
            self._sf_map = {
                "regular":     ("Helvetica", ""),
                "bold":        ("Helvetica", "B"),
                "bold_italic": ("Helvetica", "BI"),
                "italic":      ("Helvetica", "I"),
                "semibold":    ("Helvetica", "B"),
                "light":       ("Helvetica", ""),
            }
            print("[PDF font] Using Helvetica fallback")

    # ------------------------------------------------------------------
    # Font helpers
    # ------------------------------------------------------------------
    def _sf(self, size: float, weight: str = "regular") -> None:
        """Set font by semantic weight via the active font map — IBM Plex Sans
        (or Helvetica) by default, overridden by custom brand fonts when a brand
        registers them (see _register_brand_fonts)."""
        family, style = self._sf_map.get(weight, self._sf_map["regular"])
        self.set_font(family, style, size)

    def _fit_font(self, text: str, max_w: float, size: float,
                  weight: str = "regular", min_size: float = 5.5) -> None:
        """Set the font to the largest size <= `size` at which `text` fits in
        `max_w` mm on one line, never going below `min_size`. Prevents the
        single-line name cells (calibration table, cover sidebar) from either
        overflowing into the neighbouring column or being clipped — long names
        shrink just enough to fit instead."""
        s = size
        self._sf(s, weight)
        safe = self._safe(text)
        while s > min_size and self.get_string_width(safe) > max_w:
            s -= 0.25
            self._sf(s, weight)

    def _safe(self, text: object) -> str:
        return _safe(text, latin1=not self._use_unicode)

    # ------------------------------------------------------------------
    # Cell/multi_cell overrides for automatic text sanitisation
    # ------------------------------------------------------------------
    def cell(self, *args, **kwargs):
        if len(args) >= 3 and isinstance(args[2], str):
            args = (args[0], args[1], self._safe(args[2]), *args[3:])
        for k in ("text", "txt"):
            if k in kwargs and isinstance(kwargs[k], str):
                kwargs[k] = self._safe(kwargs[k])
        return super().cell(*args, **kwargs)

    def multi_cell(self, *args, **kwargs):
        if len(args) >= 3 and isinstance(args[2], str):
            args = (args[0], args[1], self._safe(args[2]), *args[3:])
        for k in ("text", "txt"):
            if k in kwargs and isinstance(kwargs[k], str):
                kwargs[k] = self._safe(kwargs[k])
        return super().multi_cell(*args, **kwargs)

    # ------------------------------------------------------------------
    # Page chrome — running header / footer
    # ------------------------------------------------------------------
    def header(self):
        if self._is_cover:
            return

        # ── Firm logo (top-left) — original colour on the white page, sized by
        #    true aspect ratio so a wide wordmark isn't squashed ─────────────
        logo_w = 0.0
        if self.firm_logo_bytes:
            try:
                h = 6.0
                w = min(h * self.firm_logo_aspect, 46.0)
                self.image(io.BytesIO(self.firm_logo_bytes),
                           x=self.l_margin, y=8, w=w, h=h)
                logo_w = w + 3.0
            except Exception:
                logo_w = 0.0

        # ── Firm name (left) + Note name (right) ─────────────────────
        # Vertically centre the text row on the logo's centreline: the logo sits
        # at y=8 with height 6 (centre y=11); a 4.5mm-tall text cell is centred
        # there at y = 11 - 4.5/2 = 8.75. (Was 9.5, which sat 0.75mm low.)
        _row_y = 8.75
        self.set_xy(self.l_margin + logo_w, _row_y)
        self._sf(7.5, "semibold")
        self.set_text_color(*self.primary_color)
        firm_label = self._safe(self.firm_name.upper())
        self.cell(100, 4.5, firm_label)

        self._sf(7, "light")
        self.set_text_color(*_TEXT_SOFT)
        self.set_xy(self.w - self.r_margin - 85, _row_y)
        note_label = self._safe(self.doc_ref.split("|")[-1].strip() if "|" in self.doc_ref else self.doc_ref)
        self.cell(85, 4.5, note_label, align="R")

        # ── Thin rule below header ────────────────────────────────────
        self.set_draw_color(*_HAIRLINE)
        self.set_line_width(0.3)
        self.line(self.l_margin, 16.5, self.w - self.r_margin, 16.5)
        self.set_text_color(*_TEXT)
        self.set_y(21)

    def footer(self):
        # The cover renders its own self-contained bottom disclaimer band; the
        # running footer (rule + footer_line + page number) would print on top of
        # it, producing the garbled overlap seen at the bottom of page 1. Skip it.
        if self._is_cover or self.page_no() in self._cover_pages:
            return
        # ── Thin rule above footer ────────────────────────────────────
        self.set_draw_color(*_HAIRLINE)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.h - 22, self.w - self.r_margin, self.h - 22)

        # ── Disclaimer line (branding may override with footer_note) ───
        self.set_y(-20)
        self._sf(6, "light")
        self.set_text_color(*_TEXT_SOFT)
        self.multi_cell(0, 2.9, self.footer_note or _t("footer_line", self.lang), align="L")

        # ── Page number + generation datetime ────────────────────────
        self.set_y(-11)
        self._sf(6.5, "light")
        self.set_text_color(*_TEXT_SOFT)
        self.cell(0, 4.5, self._safe(self._gen_dt), align="L")
        self.set_y(-11)
        _page = _t("page_of", self.lang)
        _mid  = _t("page_of_mid", self.lang)
        self.cell(0, 4.5, f"{_page} {self.page_no()} {_mid} {{nb}}", align="R")
        self.set_text_color(*_TEXT)

    # ------------------------------------------------------------------
    # Building blocks
    # ------------------------------------------------------------------
    def start_section(self, text: str, min_room: float = 146.0):
        """Begin a major section, breaking to a new page only when needed.

        ``min_room`` is the space the section title PLUS its first block need; we
        break to a fresh page when fewer than that many mm remain, so a title is
        never left stranded at the foot of a page with its chart/table overleaf.
        The default (150) covers a title + a full-width chart (~120mm); sections
        whose first block is short (issuer panel, glossary, disclaimer) pass a
        smaller value so they don't leave a big void.
        """
        if self.page_no() == 0:
            self.add_page()
        elif self.get_y() > self.h - self.b_margin - min_room:
            self.add_page()
        else:
            self.ln(6)   # generous separation between stacked sections
        self.section_title(text)

    def section_title(self, text: str):
        """Section title in the brand primary colour + a thin filled-rect band below.

        The band is a thin filled rectangle in section_rule_color, ~0.6mm tall,
        spanning the full usable width. No drawn lines anywhere.
        """
        if self.get_y() > self.h - 60:
            self.add_page()
        self.ln(4)
        self._sf(13, "semibold")           # slightly larger than the old 11pt — factsheet titles are ~13pt
        self.set_text_color(*self.primary_color)
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        # Thin band in section_rule_color, full width.
        band_h = 0.6   # mm — thin section rule
        band_w = self.w - self.l_margin - self.r_margin
        self.set_fill_color(*self.section_rule_color)
        self.rect(self.l_margin, self.get_y(), band_w, band_h, style="F")
        self.ln(band_h + 4)
        self.set_text_color(*_TEXT)

    def section_divider(self, name: str, question: str):
        """Part divider for one of the three analysis lenses (Monte Carlo →
        Backtest → Live). Always opens a fresh page so the three lenses are
        clearly delineated, then draws a band: the lens name in brand primary
        (larger than a section title) above the question the lens answers, in
        soft grey. Section content flows below it. Deliberately unnumbered — the
        build-report panel can include any subset of lenses, so a fixed 01/02/03
        would leave gaps (e.g. just '02', or '01' then '03')."""
        # A part break always starts a new page (unless we're already at the top
        # of a blank one), so each lens reads as a distinct chapter.
        if self.page_no() == 0:
            self.add_page()
        elif self.get_y() > self.t_margin + 2:
            self.add_page()
        x0 = self.l_margin
        w  = self.w - self.l_margin - self.r_margin
        y0 = self.get_y() + 2
        # Lens name (primary) above the question (soft grey), at the left margin.
        self.set_xy(x0, y0)
        self._sf(17, "semibold")
        self.set_text_color(*self.primary_color)
        self.cell(w, 9, self._safe(name), new_x="LMARGIN", new_y="NEXT")
        self.set_xy(x0, y0 + 9)
        self._sf(10, "regular")
        self.set_text_color(*_TEXT_SOFT)
        self.cell(w, 5, self._safe(question))
        # Accent rule under the band — slightly bolder than a section rule.
        ry = y0 + 16
        self.set_fill_color(*self.section_rule_color)
        self.rect(x0, ry, w, 0.9, style="F")
        self.set_y(ry + 1)
        self.set_text_color(*_TEXT)

    def subsection(self, text: str, min_room: float = 27.0):
        """SemiBold 9pt sub-header. ``min_room`` is the space the header plus the
        block that follows need; break first so the header isn't orphaned above a
        table/figure that flows to the next page. Callers preceding a table pass
        the table's height (see _table_room)."""
        if self.get_y() > self.h - self.b_margin - min_room:
            self.add_page()
        self.ln(2)
        self._sf(9, "semibold")
        self.set_text_color(*_TEXT)
        self.cell(0, 6, text.upper(), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_TEXT)
        self.ln(2)

    def body(self, text: str, h: float = 4.5):
        """8.5pt regular body text."""
        self._sf(8.5, "regular")
        self.set_text_color(*_TEXT)
        self.multi_cell(0, h, text)
        self.ln(1.5)

    def bullet(self, text: str):
        """8.5pt bullet point with proper indent."""
        self._sf(8.5, "regular")
        self.set_text_color(*_TEXT)
        x0 = self.get_x()
        self.cell(5, 5, "•" if self._use_unicode else chr(149))
        self.multi_cell(self.w - self.r_margin - x0 - 5, 5, text)
        self.ln(1.5)

    def kv_table(self, rows: list[tuple[str, str]], col_w: tuple[float, float] = (78, 100)):
        """Label/value table with thin rules and consistent alignment."""
        self.set_text_color(*_TEXT)
        for row_idx, (k, v) in enumerate(rows):
            y0 = self.get_y()
            if y0 > self.h - 32:
                self.add_page()
                y0 = self.get_y()
            # Light zebra on alternating rows — subtle background
            if row_idx % 2 == 0:
                self.set_fill_color(*_ROW_ALT)
                self.rect(self.l_margin, y0, col_w[0] + col_w[1], 8.5, style="F")
            self._sf(8.5, "regular")    # label — reference uses regular weight in table cells
            self.set_text_color(*_TEXT)
            self.cell(col_w[0], 8.5, k)
            self._sf(8.5, "regular")
            self.cell(col_w[1], 8.5, v, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def data_table(self, headers: list[str], rows: list[list[str]],
                   col_widths: list[float] | None = None,
                   aligns: list[str] | None = None,
                   rounded: bool = True):
        """Filled-header table with zebra rows and proper number alignment.

        rounded=True (default) draws a rounded-rect card behind the whole table
        so the outer corners round off; pass rounded=False for plain rects.
        """
        n = len(headers)
        usable = self.w - self.l_margin - self.r_margin
        if col_widths is None:
            col_widths = [usable / n] * n
        if aligns is None:
            aligns = ["L"] + ["R"] * (n - 1)
        tbl_w  = sum(col_widths)
        _CR    = 3.0   # corner radius (mm)
        # _use_round flips off when the table can't fully fit (multi-page) — a
        # rounded card across a page break looks broken, so fall back to rects.
        _use_round = [False]

        def _header_row(rounded_card: bool = False):
            # Header strip: rounded-top green card (so the table's top corners
            # round) with transparent text cells, else a plain green filled row.
            if rounded_card:
                self.set_fill_color(*self.primary_color)
                try:
                    self.rect(self.l_margin, self.get_y(), tbl_w, 9, style="F",
                              round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=_CR)
                except TypeError:
                    self.rect(self.l_margin, self.get_y(), tbl_w, 9, style="F")
            else:
                self.set_fill_color(*self.primary_color)
            self.set_text_color(*_WHITE)
            self._sf(7.5, "semibold")
            for h, w, a in zip(headers, col_widths, aligns):
                self.cell(w, 9, f" {h} ", border=0, fill=not rounded_card, align=a)
            self.ln()
            self.set_text_color(*_TEXT)
            self._sf(8, "regular")

        # Keep the whole table together when it can fit on one page: if the
        # header + all rows won't fit in the space left but WOULD fit on a fresh
        # page, break first instead of splitting a short table across pages.
        _needed   = 9 + len(rows) * 8 + 6
        _avail    = self.h - 30 - self.get_y()
        _page_cap = self.h - 30 - 21   # usable height below the running header
        if _needed > _avail and _needed <= _page_cap:
            self.add_page()
        elif self.get_y() > self.h - 55:
            self.add_page()

        # Rounded card: a white rounded rect behind the whole table rounds the
        # bottom corners; the header's rounded-top green strip rounds the top.
        # Header text and white rows draw transparent over it; only alt zebra
        # rows get an opaque fill (the last one rounded so it doesn't square the
        # bottom). Only when the whole table fits the page; older fpdf2 → rects.
        if rounded:
            _ch = 9 + len(rows) * 8
            _cy = self.get_y()
            if _cy + _ch <= self.h - 28:
                try:
                    self.set_fill_color(*_WHITE)
                    self.rect(self.l_margin, _cy, tbl_w, _ch, style="F",
                              round_corners=True, corner_radius=_CR)
                    _use_round[0] = True
                except TypeError:
                    _use_round[0] = False
        _header_row(_use_round[0])

        _last = len(rows) - 1
        for i, row in enumerate(rows):
            if self.get_y() > self.h - 30:
                self.add_page()
                _header_row(False)   # continuation header is always a plain row
            is_alt = (i % 2 == 0)
            if _use_round[0]:
                # Transparent cells over the white card; paint only alt rows.
                if is_alt:
                    self.set_fill_color(*_ROW_ALT)
                    if i == _last:
                        try:
                            self.rect(self.l_margin, self.get_y(), tbl_w, 8, style="F",
                                      round_corners=("BOTTOM_LEFT", "BOTTOM_RIGHT"),
                                      corner_radius=_CR)
                        except TypeError:
                            self.rect(self.l_margin, self.get_y(), tbl_w, 8, style="F")
                    else:
                        self.rect(self.l_margin, self.get_y(), tbl_w, 8, style="F")
                for cell_val, w, a in zip(row, col_widths, aligns):
                    self.cell(w, 8, f" {cell_val} ", border=0, fill=False, align=a)
                self.ln()
            else:
                self.set_fill_color(*(_ROW_ALT if is_alt else _WHITE))
                for cell_val, w, a in zip(row, col_widths, aligns):
                    self.cell(w, 8, f" {cell_val} ", border=0, fill=True, align=a)
                self.ln()

    def logo_row_table(self, headers: list[str], rows: list[list[str]],
                       logos: dict, col_widths: list[float] | None = None,
                       aligns: list[str] | None = None):
        """Like data_table but draws a small inline ticker logo to the left of the
        first-column name. `rows[i][0]` is the asset name and `logos[name]` its
        PNG bytes (or None). Rounded outer corners match data_table."""
        n = len(headers)
        usable = self.w - self.l_margin - self.r_margin
        if col_widths is None:
            col_widths = [usable / n] * n
        if aligns is None:
            aligns = ["L"] + ["R"] * (n - 1)
        LW = LH = 6.0
        ROW_H  = 10.0
        HEAD_H = 9.0
        tbl_w  = sum(col_widths)
        _CR    = 3.0
        # Rounded card disables on a multi-page split (a rounded card across a
        # page break looks broken) — same fallback as data_table.
        _use_round = [False]

        def _header_row(rounded_card: bool = False):
            if rounded_card:
                self.set_fill_color(*self.primary_color)
                try:
                    self.rect(self.l_margin, self.get_y(), tbl_w, HEAD_H, style="F",
                              round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=_CR)
                except TypeError:
                    self.rect(self.l_margin, self.get_y(), tbl_w, HEAD_H, style="F")
            else:
                self.set_fill_color(*self.primary_color)
            self.set_text_color(*_WHITE)
            self._sf(7.5, "semibold")
            for h, w, a in zip(headers, col_widths, aligns):
                self.cell(w, HEAD_H, f" {h} ", border=0, fill=not rounded_card, align=a)
            self.ln()
            self.set_text_color(*_TEXT)
            self._sf(8, "regular")

        # Keep the whole table together when it fits on one page (see data_table).
        _needed   = HEAD_H + len(rows) * ROW_H + 6
        _avail    = self.h - 30 - self.get_y()
        _page_cap = self.h - 30 - 21
        if _needed > _avail and _needed <= _page_cap:
            self.add_page()
        elif self.get_y() > self.h - 55:
            self.add_page()

        # White rounded card behind the whole table rounds the bottom corners;
        # the header's rounded-top strip rounds the top. Only when it fits the
        # page; older fpdf2 (no round_corners kwarg) → plain rects.
        _ch = HEAD_H + len(rows) * ROW_H
        _cy = self.get_y()
        if _cy + _ch <= self.h - 28:
            try:
                self.set_fill_color(*_WHITE)
                self.rect(self.l_margin, _cy, tbl_w, _ch, style="F",
                          round_corners=True, corner_radius=_CR)
                _use_round[0] = True
            except TypeError:
                _use_round[0] = False
        _header_row(_use_round[0])

        _last = len(rows) - 1
        for i, row in enumerate(rows):
            if self.get_y() > self.h - 30:
                self.add_page()
                _header_row(False)   # continuation header is a plain row
            name  = str(row[0])
            is_alt = (i % 2 == 0)
            row_y = self.get_y()
            # Full-width row background: alt rows get a zebra fill (the last one
            # rounded at the bottom so the card's corners stay round); white rows
            # are transparent over the white card.
            if _use_round[0]:
                if is_alt:
                    self.set_fill_color(*_ROW_ALT)
                    if i == _last:
                        try:
                            self.rect(self.l_margin, row_y, tbl_w, ROW_H, style="F",
                                      round_corners=("BOTTOM_LEFT", "BOTTOM_RIGHT"),
                                      corner_radius=_CR)
                        except TypeError:
                            self.rect(self.l_margin, row_y, tbl_w, ROW_H, style="F")
                    else:
                        self.rect(self.l_margin, row_y, tbl_w, ROW_H, style="F")
            else:
                self.set_fill_color(*(_ROW_ALT if is_alt else _WHITE))
                self.rect(self.l_margin, row_y, tbl_w, ROW_H, style="F")
            # First column: inline logo, then name
            ldata  = (logos or {}).get(name)
            text_x = self.l_margin + 2
            if ldata:
                try:
                    self.image(io.BytesIO(ldata), x=self.l_margin + 1,
                               y=row_y + (ROW_H - LH) / 2, w=LW, h=LH)
                    text_x = self.l_margin + LW + 3
                except Exception:
                    pass
            self.set_xy(text_x, row_y + (ROW_H - 4) / 2)
            _name_w = col_widths[0] - (text_x - self.l_margin) - 1
            self._fit_font(name, _name_w, 8, "semibold")
            self.set_text_color(*_TEXT)
            self.cell(_name_w, 4, self._safe(name))
            # Remaining columns — transparent text over the row background
            self._sf(8, "regular")
            self.set_text_color(*_TEXT)
            self.set_xy(self.l_margin + col_widths[0], row_y)
            for cell_val, w, a in zip(row[1:], col_widths[1:], aligns[1:]):
                self.cell(w, ROW_H, f" {cell_val} ", border=0, fill=False, align=a)
            self.set_y(row_y + ROW_H)

        self.ln(4)

    def metric_band(self, metrics: list[tuple[str, str]]):
        """Horizontal band of key metrics. No top rule — the section's rule
        band already separates it (avoids a 'double bar' under the header)."""
        n = len(metrics)
        usable = self.w - self.l_margin - self.r_margin
        w = usable / n
        y0 = self.get_y()

        x = self.l_margin
        for label, value in metrics:
            lbl  = self._safe(label.upper())
            size = 6.5
            self._sf(size, "semibold")
            while self.get_string_width(lbl) > (w - 3) and size > 4.5:
                size -= 0.2
                self._sf(size, "semibold")
            self.set_xy(x, y0 + 3)
            self.set_text_color(*_TEXT_SOFT)
            self.cell(w - 2, 3.5, lbl)

            # Value. Numbers fit at the big 13pt size, but a long free-text value
            # (e.g. a worst-asset name) would otherwise overflow into the next
            # metric — cell() neither wraps nor clips. Shrink it to the column and,
            # if it still doesn't fit, wrap it onto two lines within the column.
            self.set_text_color(*self.primary_color)
            val   = self._safe(str(value))
            vsize = 13.0
            self._sf(vsize, "bold")
            while self.get_string_width(val) > (w - 2) and vsize > 9.0:
                vsize -= 0.3
                self._sf(vsize, "bold")
            if self.get_string_width(val) > (w - 2):
                self.set_xy(x, y0 + 7)
                self.multi_cell(w - 2, vsize * 0.42, val,
                                align="L", new_x="LMARGIN", new_y="TOP")
            else:
                self.set_xy(x, y0 + 8.5)
                self.cell(w - 2, 7, val)
            x += w

        self.set_y(y0 + 18)
        self.set_text_color(*_TEXT)
        self.ln(4)

    def figure(self, img_bytes: bytes | None, caption: str, source: str,
               w: float = 172, h: float | None = None, max_h: float = 118):
        if img_bytes is None:
            return
        self._fig_no += 1
        # Derive the placement height from the PNG's true pixel aspect ratio so
        # charts keep their natural proportions instead of being squashed into a
        # fixed box. A very tall chart is fitted by height and re-centred.
        if h is None:
            try:
                from PIL import Image
                iw, ih = Image.open(io.BytesIO(img_bytes)).size
                h = w * ih / iw
                if h > max_h:
                    h = max_h
                    w = h * iw / ih
            except Exception:
                h = 80
        _fpad = 3.0   # padding between the chart and its panel edge
        needed = h + 18 + 2 * _fpad
        if self.get_y() + needed > self.h - 28:
            self.add_page()
        # Caption above figure — SemiBold 8.5pt in the brand primary colour
        # (matches the section titles). Deliberately NOT the accent: the accent
        # now drives the chart series palette, and a caption that tracks the chart
        # lines looked off — the caption is chrome, so it stays on the brand head
        # colour like every other heading.
        self._sf(8.5, "semibold")
        self.set_text_color(*self.primary_color)
        self.multi_cell(0, 4.5, f"{_t('figure_word', self.lang)} {self._fig_no}: {caption}", align="C")
        self.ln(1)
        x = (self.w - w) / 2
        # Faint rounded panel behind the chart, matching the text/issuer panels.
        self.ln(_fpad)
        _img_y = self.get_y()
        self.set_fill_color(*self.panel_color)   # brand-tinted panel
        try:
            self.rect(x - _fpad, _img_y - _fpad, w + 2 * _fpad, h + 2 * _fpad,
                      style="F", round_corners=True, corner_radius=2)
        except TypeError:
            self.rect(x - _fpad, _img_y - _fpad, w + 2 * _fpad, h + 2 * _fpad, style="F")
        self.image(io.BytesIO(img_bytes), x=x, y=_img_y, w=w, h=h)
        self.set_y(_img_y + h + _fpad)
        self.ln(1.5)
        # Source line — Light 7pt
        self._sf(7, "light")
        self.set_text_color(*_TEXT_SOFT)
        self.cell(0, 3.5, source, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_TEXT)
        self.ln(3.5)

    def callout(self, title: str, text: str, w: float | None = None):
        if w is None:
            w = self.w - self.l_margin - self.r_margin
        x0, y0 = self.l_margin, self.get_y()
        self._sf(8, "regular")
        lines = self.multi_cell(w - 8, 4.3, self._safe(text), dry_run=True, output="LINES")
        box_h = 10 + len(lines) * 4.3 + 4
        if y0 + box_h > self.h - 28:
            self.add_page()
            y0 = self.get_y()
        self.set_fill_color(*self.panel_color)   # brand-tinted blurb panel
        try:
            self.rect(x0, y0, w, box_h, style="F", round_corners=True, corner_radius=2)
        except TypeError:
            self.rect(x0, y0, w, box_h, style="F")
        self.set_xy(x0 + 6, y0 + 3.5)
        self._sf(8.5, "semibold")
        self.set_text_color(*_TEXT)
        self.cell(w - 10, 5, title)
        self.set_xy(x0 + 6, y0 + 10)
        self._sf(8, "regular")
        self.set_text_color(*_TEXT)
        self.multi_cell(w - 10, 4.3, text)
        self.set_y(y0 + box_h + 4)

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
        self._sf(11, "semibold")
        self.set_text_color(*self.primary_color)
        self.cell(inner_w, 6, self._safe(name))
        cy += name_h
        # Description
        if description:
            self.set_xy(x0 + pad, cy + 2)
            self._sf(8, "regular")
            self.set_text_color(*_TEXT_SOFT)
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
                self._sf(7, "semibold")
                self.set_text_color(*self.primary_color)
                self.cell(chip_w, 3.5, self._safe(lbl), align="C")
                self.set_xy(cx, cy + 6)
                self._sf(8.5, "semibold")
                self.set_text_color(*_TEXT)
                self.cell(chip_w, 4, self._safe(val), align="C")
                cx += chip_w + gap
        self.set_y(y0 + box_h + 4)

    def underlying_block(self, long_name: str, logo_bytes: bytes | None,
                         subtitle: str, metrics: list[tuple[str, str]],
                         description: str, chart_png: bytes | None,
                         chart_caption: str, section_title: str | None = None,
                         analyst: list[tuple[str, float, tuple]] | None = None,
                         analyst_title: str = ""):
        """Self-contained per-underlying card — a tinted rounded panel, like the
        issuer block: logo + name + a type·sector line, the key figures as white
        chips (market cap / 3M IV / last price / RSI), the company description, and
        the trailing-1Y price chart (transparent, so the panel tint shows through).
        The whole card is measured up front and moved to a fresh page if it would
        not fit, so it never splits across a page break.

        ``section_title`` (passed only for the FIRST card) draws the section header
        as part of the same atomic unit, so the title is never stranded on the
        previous page above a card that breaks over."""
        x0 = self.l_margin
        w  = self.w - self.l_margin - self.r_margin
        pad     = 6.0
        inner_w = w - 2 * pad
        gap     = 4.0
        n_chips = max(1, len(metrics))
        header_h, chip_h = 13.0, 13.0
        chart_w = inner_w
        chart_h = (chart_w * 0.40) if chart_png else 0.0   # PNG aspect = 900x360
        cap_h   = 5.5 if chart_png else 0.0
        # Measure the (wrapped) description so the panel sizes to its content.
        self._sf(8.5, "regular")
        desc_lines = (self.multi_cell(inner_w, 4.3, self._safe(description),
                                      dry_run=True, output="LINES") if description else [])
        desc_h = len(desc_lines) * 4.3
        analyst_h = 12.5 if analyst else 0.0
        box_h = (pad + header_h + chip_h
                 + (3 + analyst_h if analyst else 0)
                 + (3 + desc_h if description else 0)
                 + (4 + cap_h + chart_h if chart_png else 0)
                 + pad)
        title_h = 18.0 if section_title else 0.0
        y0 = self.get_y()
        # Keep the (optional) section title + the whole card together — break
        # before the unit rather than split it.
        if y0 + title_h + box_h > self.h - 28:
            self.add_page()
            y0 = self.get_y()
        if section_title:
            self.section_title(section_title)
            y0 = self.get_y()
        # Panel.
        self.set_fill_color(*self.panel_color)
        try:
            self.rect(x0, y0, w, box_h, style="F", round_corners=True, corner_radius=2)
        except TypeError:
            self.rect(x0, y0, w, box_h, style="F")
        # Header: logo + name (brand primary) + soft type·sector line.
        cy = y0 + pad
        tx = x0 + pad
        if logo_bytes:
            try:
                self.image(io.BytesIO(logo_bytes), x=x0 + pad, y=cy, w=9, h=9)
                tx = x0 + pad + 12
            except Exception:
                pass
        self.set_xy(tx, cy + 0.4)
        self._sf(11.5, "semibold")
        self.set_text_color(*self.primary_color)
        self.cell(x0 + pad + inner_w - tx, 5.5, self._safe(long_name))
        if subtitle:
            self.set_xy(tx, cy + 6.2)
            self._sf(8, "regular")
            self.set_text_color(*_TEXT_SOFT)
            self.cell(x0 + pad + inner_w - tx, 4, self._safe(subtitle))
        cy += header_h
        # Metric chips — white rounded boxes, label over value (like rating chips).
        chip_w = (inner_w - (n_chips - 1) * gap) / n_chips
        cx = x0 + pad
        for lbl, val in metrics:
            self.set_fill_color(*_WHITE)
            try:
                self.rect(cx, cy, chip_w, chip_h, style="F", round_corners=True, corner_radius=1.5)
            except TypeError:
                self.rect(cx, cy, chip_w, chip_h, style="F")
            # Label (auto-shrunk to the chip width).
            self.set_text_color(*_TEXT_SOFT)
            self._fit_font(lbl.upper(), chip_w - 2, 6.5, "semibold", min_size=5.0)
            self.set_xy(cx, cy + 1.8)
            self.cell(chip_w, 3, self._safe(lbl.upper()), align="C")
            # Value (brand primary, auto-shrunk).
            self.set_text_color(*self.primary_color)
            self._fit_font(str(val), chip_w - 3, 11.0, "bold", min_size=7.0)
            self.set_xy(cx, cy + 6.0)
            self.cell(chip_w, 5, self._safe(str(val)), align="C")
            cx += chip_w + gap
        cy += chip_h
        # Analyst consensus (optional): a thin rounded buy/hold/sell pill on a
        # light track + a dot legend, matching the web card.
        if analyst:
            cy += 3.5
            self.set_xy(x0 + pad, cy)
            self._sf(6.5, "semibold")
            self.set_text_color(*_TEXT_SOFT)
            self.cell(inner_w, 3, self._safe(analyst_title.upper()))
            cy += 4.2
            bar_h = 2.6
            rad = bar_h / 2
            self.set_fill_color(*_blend(_TEXT_SOFT, _WHITE, 0.84))     # rounded track
            try:
                self.rect(x0 + pad, cy, inner_w, bar_h, style="F", round_corners=True, corner_radius=rad)
            except TypeError:
                self.rect(x0 + pad, cy, inner_w, bar_h, style="F")
            segs = [(c, inner_w * max(0.0, f)) for (_l, f, c) in analyst if f > 0.001]
            bx = x0 + pad
            for _i, (_col, _w) in enumerate(segs):
                self.set_fill_color(*_col)
                _corn = (True if len(segs) == 1 else
                         ("TOP_LEFT", "BOTTOM_LEFT") if _i == 0 else
                         ("TOP_RIGHT", "BOTTOM_RIGHT") if _i == len(segs) - 1 else None)
                try:
                    if _corn is True:
                        self.rect(bx, cy, _w, bar_h, style="F", round_corners=True, corner_radius=rad)
                    elif _corn:
                        self.rect(bx, cy, _w, bar_h, style="F", round_corners=_corn, corner_radius=rad)
                    else:
                        self.rect(bx, cy, _w, bar_h, style="F")
                except TypeError:
                    self.rect(bx, cy, _w, bar_h, style="F")
                bx += _w
            cy += bar_h + 2.4
            self._sf(7, "regular")
            lx = x0 + pad
            for _lbl, _frac, _col in analyst:
                self.set_fill_color(*_col)
                self.ellipse(lx, cy - 1.9, 1.8, 1.8, style="F")
                self.set_xy(lx + 2.8, cy - 2.6)
                self.set_text_color(*_TEXT_SOFT)
                _txt = f"{_lbl} {_frac:.0%}"
                self.cell(self.get_string_width(_txt) + 1, 3.2, self._safe(_txt))
                lx += 2.8 + self.get_string_width(_txt) + 6
            cy += 3.0
        # Company description (optional — blank hides it, like the issuer blurb).
        if description:
            self.set_xy(x0 + pad, cy + 3)
            self._sf(8.5, "regular")
            self.set_text_color(*_TEXT_SOFT)
            self.multi_cell(inner_w, 4.3, self._safe(description))
            cy = self.get_y()
        # Trailing-1Y chart: caption + the transparent PNG directly on the panel.
        if chart_png:
            cy += 4
            self.set_xy(x0 + pad, cy)
            self._sf(8.5, "semibold")
            self.set_text_color(*self.primary_color)
            self.cell(inner_w, cap_h, self._safe(chart_caption), align="C")
            cy += cap_h
            try:
                self.image(io.BytesIO(chart_png), x=x0 + pad, y=cy, w=chart_w, h=chart_h)
            except Exception:
                pass
        self.set_y(y0 + box_h + 5)


# ──────────────────────────────────────────────────────────────────────────────
# Logo fetching
# ──────────────────────────────────────────────────────────────────────────────

# fpdf2 can only embed PNG, JPEG and GIF. Favicon services frequently hand back
# ICO (Google s2/favicons, duckduckgo), and some CDNs return WEBP — both make
# pdf.image() raise, which previously silently dropped the logo. We normalise
# *every* logo byte string through Pillow to a clean RGBA PNG before it ever
# reaches pdf.image(): the format is guaranteed embeddable, the alpha channel is
# preserved, and a multi-resolution ICO is collapsed to its largest frame.
_EMBEDDABLE_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8")  # PNG / JPEG / GIF


def _to_embeddable_png(raw: bytes | None) -> bytes | None:
    """Return PNG bytes fpdf2 can embed, or None.

    If `raw` is already a PNG/JPEG/GIF it is returned unchanged (cheap path).
    Otherwise — ICO, WEBP, BMP, TIFF, multi-frame favicon … — it is decoded by
    Pillow and re-encoded as a single RGBA PNG. Any decode failure returns None
    so a bad image is dropped rather than crashing the report.
    """
    if not raw:
        return None
    if raw[:4] in _EMBEDDABLE_MAGIC:
        return raw
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        # ICO files carry several sizes; Pillow opens the first — pick the
        # largest available frame for the crispest logo.
        sizes = getattr(im, "ico", None)
        if sizes is not None:
            try:
                biggest = max(im.ico.sizes())
                im = im.ico.getimage(biggest)
            except Exception:
                pass
        im = im.convert("RGBA")
        out = io.BytesIO()
        im.save(out, format="PNG")
        data = out.getvalue()
        print(f"[PDF logo] converted {len(raw):,}b -> PNG {len(data):,}b ({im.size[0]}x{im.size[1]})")
        return data
    except Exception as exc:
        print(f"[PDF logo] convert FAIL ({len(raw)}b): {exc}")
        return None


def _logo_aspect(png: bytes | None, default: float = 1.0) -> float:
    """Width/height aspect ratio of a logo, so it can be sized without squashing
    a wide wordmark into a square box. Falls back to `default` on any error."""
    if not png:
        return default
    try:
        from PIL import Image
        w, h = Image.open(io.BytesIO(png)).size
        return (w / h) if h else default
    except Exception:
        return default


def _fetch_image_bytes(url: str, timeout: int = 8) -> bytes | None:
    """Download an image from a URL. Returns raw bytes or None on failure.

    Uses a browser-like User-Agent so Google Favicon and other CDNs don't
    redirect or block the request.  Validates that the response body is
    non-empty before returning.
    """
    if not url:
        return None
    # Upgrade Google favicon requests to sz=256 for crisper logos
    if "google.com/s2/favicons" in url:
        import re as _re
        url = _re.sub(r"sz=\d+", "sz=256", url)
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept": "image/png,image/jpeg,image/webp,image/*,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if not data:
            print(f"[PDF logo] Empty response from {url}")
            return None
        print(f"[PDF logo] OK  {len(data):,} bytes  {url}")
        return data
    except Exception as exc:
        print(f"[PDF logo] FAIL {url!r}: {exc}")
        return None


def _read_local_image(path: Path) -> bytes | None:
    """Read a local image file as raw bytes. fpdf2 cannot render SVG natively,
    so SVG files are skipped (returns None) with a diagnostic. Any failure is
    swallowed and returns None so a missing/bad file never crashes the PDF."""
    try:
        if not path.exists() or not path.is_file():
            return None
        if path.suffix.lower() == ".svg":
            print(f"[PDF logo] SKIP SVG (not renderable by fpdf2): {path}")
            return None
        data = path.read_bytes()
        if not data:
            return None
        print(f"[PDF logo] OK  {len(data):,} bytes  {path}")
        return data
    except Exception as exc:
        print(f"[PDF logo] FAIL local {path!r}: {exc}")
        return None


def _resolve_local_path(spec: str) -> Path:
    """Resolve a branding logo_file spec to an absolute path. Absolute paths are
    honoured as-is; relative paths resolve against the repo root."""
    p = Path(spec)
    return p if p.is_absolute() else (_REPO_ROOT / p)


def _load_logo(branding: dict | None) -> bytes | None:
    """Resolve the firm/issuer branding logo, local-file-first.

    Order of preference (first that yields bytes wins):
      1. branding['logo_file']   — path to a local image (relative to repo root)
      2. branding['logo_base64'] — a base64 string or data: URI
      3. branding['logo_url']    — remote URL (last-resort network fetch)

    Returns image bytes or None. Never raises — a failure simply omits the logo.
    """
    if not branding:
        return None
    # 1. Local file
    spec = branding.get("logo_file")
    if spec:
        data = _to_embeddable_png(_read_local_image(_resolve_local_path(spec)))
        if data:
            return data
        print(f"[PDF logo] logo_file unusable ({spec}); trying next source")
    # 2. Base64 / data URI
    b64 = branding.get("logo_base64")
    if b64:
        try:
            payload = b64.split(",", 1)[1] if b64.strip().startswith("data:") else b64
            data = _to_embeddable_png(base64.b64decode(payload))
            if data:
                print(f"[PDF logo] OK  base64 -> embeddable PNG")
                return data
        except Exception as exc:
            print(f"[PDF logo] FAIL base64: {exc}")
    # 3. Remote URL
    url = branding.get("logo_url")
    if url:
        return _to_embeddable_png(_fetch_image_bytes(url))
    return None


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


def _blend(rgb: tuple, target: tuple, f: float) -> tuple:
    return tuple(round(rgb[i] * (1 - f) + target[i] * f) for i in range(3))


def _rgb_to_hue(rgb: tuple) -> float:
    """HSL hue in degrees [0, 360) for an (R,G,B) 0-255 tuple. Used to rotate the
    backtest's blue autocall ramp onto the brand accent's hue."""
    r, g, b = (c / 255.0 for c in rgb[:3])
    h, _l, _s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0


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
    }


def _build_scale_remap(primary: tuple, accent: tuple) -> dict:
    """Colour-scale map (heatmaps): keep the intensity ramp on-brand (primary/
    accent), never gold — the navy/blue endpoints map to the brand, red stays red."""
    return {_SRC_NAVY: primary, _SRC_BLUE: accent}


def _parse_rgb(c: str):
    """Return (r,g,b,alpha_or_None) for a hex or rgb()/rgba() string, else None."""
    if not isinstance(c, str):
        return None
    s = c.strip().lower()
    if s.startswith("#"):
        s = s[1:]
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) == 6:
            try:
                return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), None)
            except ValueError:
                return None
        return None
    m = re.match(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)", s)
    if m:
        r, g, b = (int(float(m.group(i))) for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) is not None else None
        return (r, g, b, a)
    return None


def _remap_color(c, remap: dict, ramp_hue: float):
    """Map one colour through a branding remap, preserving any alpha. Blue-family
    hsl() colours (the backtest autocall ramp) are hue-rotated to `ramp_hue` (the
    brand accent's hue); colours whose RGB isn't a known source value are returned
    unchanged."""
    if isinstance(c, str):
        h = re.match(r"hsl\(\s*(\d+(?:\.\d+)?)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)",
                     c.strip().lower())
        if h:
            hue = float(h.group(1))
            if 195 <= hue <= 255:   # blue family -> brand-accent ramp
                return f"hsl({ramp_hue:.0f},{h.group(2)}%,{h.group(3)}%)"
            return c
    p = _parse_rgb(c)
    if p is None:
        return c
    rgb, alpha = p[:3], p[3]
    tgt = remap.get(rgb)
    if tgt is None:
        return c
    if alpha is None:
        return f"rgb({tgt[0]},{tgt[1]},{tgt[2]})"
    return f"rgba({tgt[0]},{tgt[1]},{tgt[2]},{alpha})"


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


def _theme_figure(fig, primary_color: tuple, accent_color: tuple,
                  secondary_color: tuple = _DEFAULT_SECONDARY):
    """Apply the print theme to a Plotly figure before rasterising: white
    backgrounds, report typography, light gridlines, no Plotly logo — and remap
    the source navy/blue palette onto the branding colours (no-op for the default
    palette). Semantic colours (red KI line, grey autocall, orange coupon) and
    the fan-chart band alpha hierarchy are preserved by `_rebrand_figure`.
    """
    try:
        _rebrand_figure(fig, primary_color, accent_color, secondary_color)
    except Exception:
        pass
    try:
        fig.update_layout(
            # Transparent so the chart blends into its brand-tinted figure card
            # instead of stamping an opaque white rectangle that clashes with the
            # panel. fpdf2 composites the PNG's alpha over the card fill, so the
            # panel colour shows through the plot area and margins.
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="IBM Plex Sans, Arial, sans-serif", size=10, color="#1a1a2e"),
            modebar_remove=["logo", "toImage", "sendDataToCloud"],
        )
        # Clean, understated legend: a single horizontal strip along the bottom
        # (clears the P1/P2.. observation labels pinned to the top of the path/fan
        # charts), no "variable" group title, muted slate text at a readable-but-
        # not-shouty size, no box. Replaces the heavy 13pt bold navy legend.
        # Only for charts that actually show a legend — a legend-less chart (the
        # correlation heatmap, the per-underlying price line) keeps its own tight
        # margins instead of reserving 78mm of empty space at the bottom.
        if getattr(fig.layout, "showlegend", None) is not False:
            fig.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="top", y=-0.18, xanchor="center", x=0.5,
                    title=dict(text=""),
                    font=dict(family="IBM Plex Sans, Arial, sans-serif",
                              size=11, color="#5b6675"),
                    bgcolor="rgba(0,0,0,0)", borderwidth=0,
                    itemsizing="constant",
                ),
                margin=dict(b=78),
            )
        # Axes: cool-grey, semi-transparent so gridlines stay legible on the
        # tinted card now that the opaque white plot background is gone (a near-
        # white grid would vanish against the panel). Per-axis ranges/tickformats
        # set in charts.py are untouched.
        fig.update_xaxes(linecolor="rgba(71,85,105,0.35)",
                         gridcolor="rgba(71,85,105,0.14)",
                         zerolinecolor="rgba(71,85,105,0.35)")
        fig.update_yaxes(linecolor="rgba(71,85,105,0.35)",
                         gridcolor="rgba(71,85,105,0.14)",
                         zerolinecolor="rgba(71,85,105,0.35)")
    except Exception:
        pass


# Kaleido v1 drives an external Chrome/Chromium (unlike the self-contained
# v0.2.x). On a headless host with no browser — e.g. Streamlit Community Cloud
# without a `packages.txt` that installs `chromium` — every export raises and
# the report silently drops all figures. We attempt a one-time runtime Chrome
# download as a fallback so the report still renders charts when the system
# package is missing. Guarded so we only try once per process.
_CHROME_FETCH_TRIED = False


def _ensure_chrome() -> None:
    """Best-effort: make sure Kaleido has a Chrome to drive. No-op on failure.

    Tries kaleido.get_chrome_sync() once (downloads Chromium into Kaleido's
    cache). Only runs once per process; safe when a system Chromium already
    exists (Kaleido prefers it and this is skipped after the first attempt)."""
    global _CHROME_FETCH_TRIED
    if _CHROME_FETCH_TRIED:
        return
    _CHROME_FETCH_TRIED = True
    try:
        import kaleido
        get_chrome = getattr(kaleido, "get_chrome_sync", None)
        if get_chrome is not None:
            get_chrome()
            print("[PDF figure] fetched Chromium for Kaleido")
    except Exception as exc:
        print(f"[PDF figure] Chrome fetch unavailable: {exc}")


# Persistent Kaleido server. Plotly's pio.to_image boots a fresh headless
# Chrome on EVERY call (~3s of startup each); a full report exports ~13 figures,
# so cold-booting per figure is ~40s of pure overhead. Starting Kaleido's sync
# server once keeps a single Chrome alive for the whole build — pio.to_image
# auto-detects the running server, so _fig_to_png itself needs no change — and
# the export collapses to one ~2.7s boot plus ~0.2s per figure (~5s total).
# generate_pdf_report starts it before rendering and tears it down in a finally,
# so the Chrome subprocess never lingers past a build. Best-effort: if the
# server can't start (no Chrome on a headless host), exports fall back to the
# per-call path in _fig_to_png unchanged.
def _start_kaleido_server() -> bool:
    """Start Kaleido's persistent sync server. Returns True on success."""
    try:
        import kaleido
        kaleido.start_sync_server()
        return True
    except Exception as exc:
        print(f"[PDF figure] persistent Kaleido server unavailable "
              f"({type(exc).__name__}: {exc}); exporting per figure")
        return False


def _stop_kaleido_server() -> None:
    """Tear down the persistent Kaleido server (and its Chrome subprocess)."""
    try:
        import kaleido
        kaleido.stop_sync_server()
    except Exception:
        pass


def _fig_to_png(fig, width: int = 900, height: int = 500,
                primary_color: tuple = _DEFAULT_PRIMARY,
                accent_color: tuple = _DEFAULT_ACCENT,
                secondary_color: tuple = _DEFAULT_SECONDARY) -> bytes | None:
    """Rasterise a Plotly figure to PNG bytes at 3× scale (~300 dpi equivalent).

    Applies `_theme_figure` before rendering so all charts use the report's
    branded color scheme and white background regardless of app theme.

    Returns None on failure, but logs why first — a swallowed exception here
    silently empties the whole report of charts, which is near-impossible to
    diagnose after the fact. The most common cause is a missing Chrome for
    Kaleido v1 on a headless deploy; we retry once after fetching one.
    """
    import plotly.io as pio
    import plotly.graph_objects as go
    fig = go.Figure(fig)
    fig.update_layout(title=None, margin=dict(t=24, b=40))
    _theme_figure(fig, primary_color, accent_color, secondary_color)
    # When the persistent server is running, plotly warns once per figure that
    # "kopts is ignored if using a server" — harmless (width/height/scale are
    # respected via the figure layout) but it floods the logs. Mute just that.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*kopts.*", category=UserWarning)
        try:
            return pio.to_image(fig, format="png", width=width, height=height, scale=3)
        except Exception as exc:
            print(f"[PDF figure] to_image failed ({type(exc).__name__}: {exc}); "
                  "retrying after Chrome fetch")
            _ensure_chrome()
            try:
                return pio.to_image(fig, format="png", width=width, height=height, scale=3)
            except Exception as exc2:
                print(f"[PDF figure] to_image failed again: {type(exc2).__name__}: {exc2}")
                return None


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


def _term_rows(terms, lang: str) -> list[tuple[str, str]]:
    rows = [
        (_t("maturity",         lang), f"{terms.maturity:g}Y ({terms.n_obs} {_t('observations_word', lang)}, {_fmt_freq(terms.payment_freq, lang)})"),
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
            b.append(
                f"La probabilidad de autocall anticipado es {results.get('prob_autocall', 0):.0%}; "
                f"la probabilidad de pérdida de capital a vencimiento (knock-in sin rescate) es "
                f"{results.get('prob_knock_in_total', 0):.1%} con barrera al {terms.knock_in_barrier:.1%}.")
        if bt_summary:
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
            b.append(
                f"The probability of early redemption (autocall) is {results.get('prob_autocall', 0):.0%}; "
                f"the probability of capital loss at maturity (knock-in without rescue) is "
                f"{results.get('prob_knock_in_total', 0):.1%} against a {terms.knock_in_barrier:.1%} barrier.")
        if bt_summary:
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


def _front_cover_page(pdf: _NotePDF, terms, lang: str, report_title: str, website: str):
    """Full-bleed branded cover (page 1, toggleable): brand-colour background, the
    centred firm logo, a 'Nota Estructurada' eyebrow, the note name and the report
    month — modelled on the CADIEM cover. Uses the brand palette + logo; a brand
    may also supply `cover_image_base64` for a full-bleed background photo."""
    import re
    pdf.set_auto_page_break(auto=False)
    pdf._is_cover = True
    pdf.add_page()
    pdf._cover_pages.add(pdf.page_no())
    W, H = pdf.w, pdf.h
    cx = W / 2

    # Full-bleed background: brand primary colour, or an optional photo with a
    # colour overlay at the configured opacity (so text stays legible over it).
    pdf.set_fill_color(*pdf.primary_color)
    pdf.rect(0, 0, W, H, style="F")
    if getattr(pdf, "cover_image_bytes", None):
        try:
            pdf.image(io.BytesIO(pdf.cover_image_bytes), x=0, y=0, w=W, h=H)
        except Exception:
            pass
        _op = getattr(pdf, "cover_overlay_opacity", 0.0)
        if _op and _op > 0:
            pdf.set_fill_color(*getattr(pdf, "cover_overlay_color", pdf.primary_color))
            try:
                with pdf.local_context(fill_opacity=_op):
                    pdf.rect(0, 0, W, H, style="F")
            except Exception:
                pass

    # Logo (white wordmark), centred in the upper third. A brand may supply a
    # white knockout logo (`cover_logo_base64`) for the coloured cover; otherwise
    # the normal logo is used (which may be low-contrast on a brand background).
    logo_b = getattr(pdf, "cover_logo_bytes", None) or pdf.firm_logo_bytes
    if logo_b:
        try:
            lh = 22.0
            lw = min(lh * pdf.firm_logo_aspect, 96.0)
            pdf.image(io.BytesIO(logo_b), x=cx - lw / 2, y=H * 0.17, w=lw, h=lh)
        except Exception:
            pass

    # Eyebrow ("NOTA ESTRUCTURADA"), letter-spaced, white.
    eb = (report_title or _t("report_eyebrow", lang)).upper()
    pdf.set_xy(0, H * 0.17 + 30)
    pdf._sf(15, "light")
    pdf.set_text_color(255, 255, 255)
    try:
        pdf.set_char_spacing(3.2)
    except Exception:
        pass
    pdf.cell(W, 8, _safe(eb), align="C")
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass
    # Accent rule under the eyebrow.
    pdf.set_draw_color(*pdf.section_rule_color)
    pdf.set_line_width(0.9)
    pdf.line(cx - 38, H * 0.17 + 46, cx + 38, H * 0.17 + 46)

    # Note name — split into a bold title + an optional subtitle on a separator.
    _parts = re.split(r"\s+[—\-/:]\s+", terms.name or "", maxsplit=1)
    _title = _safe((_parts[0] or "").upper())
    _subt  = _safe((_parts[1] if len(_parts) > 1 else "").upper())
    pdf.set_xy(0, H * 0.64)
    pdf._sf(21, "bold")
    pdf.set_text_color(255, 255, 255)
    pdf.cell(W, 9, _title, align="C", new_x="LMARGIN", new_y="NEXT")
    if _subt:
        pdf.set_x(0)
        pdf._sf(12, "semibold")
        pdf.cell(W, 6, _subt, align="C", new_x="LMARGIN", new_y="NEXT")

    # Report month (accent colour).
    pdf.ln(7)
    pdf.set_x(0)
    pdf._sf(14, "bold")
    pdf.set_text_color(*pdf.section_rule_color)
    pdf.cell(W, 8, _safe(_fmt_month_year(datetime.date.today(), lang).upper()),
             align="C", new_x="LMARGIN", new_y="NEXT")

    # Website at the foot.
    if website:
        pdf.set_xy(0, H - 20)
        pdf._sf(9, "regular")
        pdf.set_text_color(255, 255, 255)
        try:
            pdf.set_char_spacing(1.6)
        except Exception:
            pass
        pdf.cell(W, 5, _safe(website), align="C")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
    pdf._is_cover = False


def _full_bleed_disclaimer(pdf: _NotePDF, lang: str, text: str, website: str = ""):
    """Disclaimer as a branded full-bleed back page — white text on the brand
    colour with the logo header and a footer, pairing the branded front cover."""
    pdf.set_auto_page_break(auto=False)
    pdf._is_cover = True
    pdf.add_page()
    pdf._cover_pages.add(pdf.page_no())
    W, H = pdf.w, pdf.h
    pdf.set_fill_color(*pdf.primary_color)
    pdf.rect(0, 0, W, H, style="F")

    logo_b = getattr(pdf, "cover_logo_bytes", None) or pdf.firm_logo_bytes
    if logo_b:
        try:
            lh = 12.0
            lw = min(lh * pdf.firm_logo_aspect, 58.0)
            pdf.image(io.BytesIO(logo_b), x=pdf.l_margin, y=15, w=lw, h=lh)
        except Exception:
            pass
    pdf.set_draw_color(*pdf.section_rule_color)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, 33, W - pdf.r_margin, 33)

    pdf.set_xy(pdf.l_margin, 41)
    pdf._sf(16, "bold")
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, _safe(_t("disclaimer_title", lang)), new_x="LMARGIN", new_y="NEXT")

    pdf.set_xy(pdf.l_margin, 54)
    inner = W - pdf.l_margin - pdf.r_margin
    _paras = (text or "").split("\n\n")
    for _i, _para in enumerate(_paras):
        pdf.set_x(pdf.l_margin)
        pdf._sf(7.6, "bold" if _i == len(_paras) - 1 else "regular")
        pdf.set_text_color(255, 255, 255)
        pdf.multi_cell(inner, 4.0, _safe(_para), align="J")
        pdf.ln(2.6)

    if website:
        pdf.set_xy(0, H - 22)
        pdf._sf(8.5, "regular")
        pdf.set_text_color(255, 255, 255)
        pdf.cell(W, 5, _safe(website), align="C")
    pdf.set_xy(0, H - 14)
    pdf._sf(7, "light")
    pdf.set_text_color(*_blend(pdf.primary_color, _WHITE, 0.65))
    pdf.cell(W, 4, _safe(f"© {datetime.date.today().year} {pdf.firm_name} — All Rights Reserved."), align="C")
    pdf._is_cover = False


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
):
    # inc(section_key) -> bool: which optional sections are included, so the
    # cover "In this report" list matches the body. Defaults to all-on.
    if inc is None:
        inc = lambda _k: True
    pdf._is_cover = True
    # Disable auto-page-break for the cover so overflowing content (long note
    # names, many bullets) does NOT automatically insert a blank page 2.
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    # Remember which page is the cover so footer() suppresses the running footer
    # there even after _is_cover is reset (footer fires lazily on the next
    # add_page, by which point _is_cover is already False).
    pdf._cover_pages.add(pdf.page_no())

    # ── Clean header — the real logo on white, no colored band ────────────
    # A full-width brand band forced a white-knockout of the logo, which flattens
    # a multi-colour wordmark (e.g. a navy mark with a coloured glyph) to a solid
    # white silhouette. Instead the cover header is white and shows the logo in
    # its own colours; brand presence comes from a thin accent rule beneath it
    # plus the note name, sidebar accent stripe and table headers throughout.
    band_h = _COVER_BAND_H
    logo_x   = pdf.l_margin
    has_logo = False
    if pdf.firm_logo_bytes:
        try:
            lh = 14.0
            lw = min(lh * pdf.firm_logo_aspect, 66.0)
            pdf.image(io.BytesIO(pdf.firm_logo_bytes),
                      x=logo_x, y=(band_h - lh) / 2 - 2, w=lw, h=lh)
            has_logo = True
        except Exception:
            has_logo = False

    _today_long = _fmt_long_date(datetime.date.today(), lang)
    # B5: a branding report_title overrides the default eyebrow / subtitle.
    _eyebrow = (pdf.report_title or _t("report_eyebrow", lang)).upper()
    if has_logo:
        # Logo carries identity on the left; eyebrow (brand colour) + date (grey)
        # form a clean right-aligned block, vertically centred against the logo.
        rx, rw = pdf.w - pdf.r_margin - 100, 100
        pdf.set_xy(rx, 12)
        pdf._sf(8, "semibold")
        pdf.set_text_color(*pdf.primary_color)
        try:
            pdf.set_char_spacing(1.4)
        except Exception:
            pass
        pdf.cell(rw, 5, _eyebrow, align="R")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        pdf.set_xy(rx, 18.5)
        pdf._sf(8, "light")
        pdf.set_text_color(*_TEXT_SOFT)
        pdf.cell(rw, 5, _today_long, align="R")
    else:
        # No logo: firm wordmark in brand colour, eyebrow + date in grey.
        pdf.set_xy(pdf.l_margin, 8)
        pdf._sf(8, "semibold")
        pdf.set_text_color(*_TEXT_SOFT)
        try:
            pdf.set_char_spacing(1.2)
        except Exception:
            pass
        pdf.cell(120, 5, _eyebrow)
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        pdf.set_xy(pdf.w - pdf.r_margin - 55, 8)
        pdf._sf(7.5, "light")
        pdf.set_text_color(*_TEXT_SOFT)
        pdf.cell(55, 5, _today_long, align="R")
        pdf.set_xy(pdf.l_margin, 15)
        pdf._sf(15, "bold")
        pdf.set_text_color(*pdf.primary_color)
        pdf.cell(140, 8, _safe(pdf.firm_name))

    # Thin rule at the base of the header — section_rule_color (in line with the
    # section bands), full width, 0.6mm.
    pdf.set_draw_color(*pdf.section_rule_color)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, band_h - 3, pdf.w - pdf.r_margin, band_h - 3)

    # ── Sidebar panel (right column) ──────────────────────────────────────
    sb_x, sb_w = 138, pdf.w - pdf.r_margin - 138
    sb_y_top   = band_h + 4
    sb_h       = 170

    pdf.set_fill_color(*pdf.panel_color)
    try:
        pdf.rect(sb_x, sb_y_top, sb_w, sb_h, style="F",
                 round_corners=True, corner_radius=3)
    except TypeError:
        pdf.rect(sb_x, sb_y_top, sb_w, sb_h, style="F")

    # Solid top stripe (rounded top corners to match the panel)
    pdf.set_fill_color(*pdf.sidebar_bar_color)
    try:
        pdf.rect(sb_x, sb_y_top, sb_w, 3.0, style="F",
                 round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=3)
    except TypeError:
        pdf.rect(sb_x, sb_y_top, sb_w, 1.5, style="F")

    def _sb_label(y, txt):
        pdf.set_xy(sb_x + 5, y)
        pdf._sf(7, "semibold")
        pdf.set_text_color(*pdf.primary_color)
        try:
            pdf.set_char_spacing(0.8)
        except Exception:
            pass
        pdf.cell(sb_w - 10, 4, txt.upper())
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        return pdf.get_y() + 4

    def _sb_text(y, txt, weight="regular", size=8, color=_TEXT):
        pdf.set_xy(sb_x + 5, y)
        pdf._sf(size, weight)
        pdf.set_text_color(*color)
        pdf.multi_cell(sb_w - 10, 4.2, _safe(txt), align="L")
        return pdf.get_y()

    y = sb_y_top + 5
    y = _sb_label(y, _t("underlyings", lang))

    _LOGO_H = 8.0
    _LOGO_W = 8.0
    _ROW_H  = 11.0
    for nm in asset_names:
        logo_url  = (logo_urls or {}).get(nm, "")
        sym       = (logo_tickers or {}).get(nm)
        logo_data = (logo_overrides or {}).get(nm) or _load_ticker_logo(nm, logo_url, sym)
        row_y  = y + 1.0
        text_x = sb_x + 4
        if logo_data:
            try:
                pdf.image(io.BytesIO(logo_data), x=sb_x + 4, y=row_y,
                          w=_LOGO_W, h=_LOGO_H)
                text_x = sb_x + 4 + _LOGO_W + 2
            except Exception:
                text_x = sb_x + 4
        # Name on a single line next to the logo: fit the font to the available
        # width (never wrap/justify, which produced glitched gaps for long names).
        _nm_w = (sb_x + sb_w - 5) - text_x
        pdf.set_xy(text_x, row_y + (_LOGO_H - 4.5) / 2)
        pdf._fit_font(nm, _nm_w, 8.5, "semibold")
        pdf.set_text_color(*_TEXT)
        pdf.cell(_nm_w, 4.5, _safe(nm))
        y = row_y + _ROW_H

    y = _sb_label(y + 3, _t("key_terms", lang))
    mini = [
        (_t("maturity", lang),        f"{terms.maturity:g}Y {_fmt_freq(terms.payment_freq, lang)}"),
        (_t("coupon_pa", lang),        f"{terms.coupon_pa*100:.2f}%"),
        (_t("autocall_barrier", lang), f"{terms.autocall_barrier:.0%}"),
        (_t("ki_barrier", lang).split(" (")[0], f"{terms.knock_in_barrier:.1%}"),
    ]
    if getattr(terms, "issue_date", None):
        mini.append((_t("issue_date", lang), terms.issue_date))
    for k, v in mini:
        pdf.set_xy(sb_x + 5, y + 0.8)
        pdf._sf(7, "light")
        pdf.set_text_color(*_TEXT_SOFT)
        pdf.cell(sb_w - 10, 3.4, _safe(k))
        pdf.set_xy(sb_x + 5, y + 4.2)
        pdf._sf(8.5, "semibold")
        pdf.set_text_color(*_TEXT)
        pdf.cell(sb_w - 10, 4, _safe(v))
        y += 9.5

    # ── Main column ───────────────────────────────────────────────────────
    main_w = sb_x - pdf.l_margin - 8
    y_main = band_h + 6

    # Issuer logo + name block
    pdf.set_xy(pdf.l_margin, y_main)
    if issuer_logo_bytes:
        try:
            pdf.image(io.BytesIO(issuer_logo_bytes),
                      x=pdf.l_margin, y=y_main, w=11, h=11)
            pdf.set_xy(pdf.l_margin + 14, y_main + 1.5)
            pdf._sf(10, "semibold")
            pdf.set_text_color(*_TEXT_SOFT)
            pdf.cell(main_w - 14, 6, _safe(pdf.issuer.upper()))
        except Exception:
            if pdf.issuer:
                pdf._sf(10, "semibold")
                pdf.set_text_color(*_TEXT_SOFT)
                pdf.cell(main_w, 6, _safe(pdf.issuer.upper()),
                         new_x="LMARGIN", new_y="NEXT")
    elif pdf.issuer:
        pdf._sf(10, "semibold")
        pdf.set_text_color(*_TEXT_SOFT)
        pdf.cell(main_w, 6, _safe(pdf.issuer.upper()),
                 new_x="LMARGIN", new_y="NEXT")

    # Note name — large, primary color
    y_name = y_main + 14
    pdf.set_xy(pdf.l_margin, y_name)
    pdf._sf(18, "bold")
    pdf.set_text_color(*pdf.primary_color)
    # Left-align: multi_cell defaults to justified, which stretches the word
    # spacing of a short wrapped title into ugly gaps (e.g. "Autocall — 12M").
    pdf.multi_cell(main_w, 9, _safe(terms.name), align="L")

    # Report type subtitle (branding report_title overrides the default)
    pdf.set_x(pdf.l_margin)
    pdf._sf(9.5, "light")
    pdf.set_text_color(*_TEXT_SOFT)
    pdf.cell(main_w, 6, _safe(pdf.report_title or _t("series_title", lang)),
             new_x="LMARGIN", new_y="NEXT")

    # Optional firm contact line (B5): website · contact, small and muted.
    _contact_bits = [b for b in (pdf.website, pdf.contact) if b]
    if _contact_bits:
        pdf.set_x(pdf.l_margin)
        pdf._sf(7.5, "light")
        pdf.set_text_color(*_TEXT_SOFT)
        pdf.cell(main_w, 4.5, _safe("  ·  ".join(_contact_bits)),
                 new_x="LMARGIN", new_y="NEXT")

    # Thin divider
    pdf.set_draw_color(*_HAIRLINE)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y() + 1,
             pdf.l_margin + main_w, pdf.get_y() + 1)
    pdf.ln(5)

    # Executive summary bullets — only when there ARE bullets (e.g. a terms-only
    # report has no simulation results, so the title would otherwise sit empty).
    _exec = list(_exec_bullets(terms, results, bt_summary, live_data, lang))
    if _exec:
        pdf._sf(8.5, "semibold")
        pdf.set_text_color(*pdf.primary_color)
        try:
            pdf.set_char_spacing(0.4)
        except Exception:
            pass
        pdf.cell(main_w, 5, _t("exec_summary", lang).upper(), new_x="LMARGIN", new_y="NEXT")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        pdf.set_draw_color(*pdf.accent_color)
        pdf.set_line_width(0.25)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + main_w, pdf.get_y())
        pdf.ln(2.5)

        for txt in _exec:
            pdf.set_x(pdf.l_margin)
            pdf._sf(8.5, "regular")
            pdf.set_text_color(*_TEXT)
            pdf.cell(5, 5.5, "•" if pdf._use_unicode else chr(149))
            pdf.multi_cell(main_w - 5, 5.5, _safe(txt), align="J")
            pdf.ln(2)

    # About this report blurb
    pdf.ln(3)
    pdf.set_x(pdf.l_margin)
    pdf._sf(8, "semibold")
    pdf.set_text_color(*pdf.primary_color)
    try:
        pdf.set_char_spacing(0.4)
    except Exception:
        pass
    pdf.cell(main_w, 5, _t("about_report_head", lang).upper(),
             new_x="LMARGIN", new_y="NEXT")
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass
    pdf.set_draw_color(*_RULE_LIGHT)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + main_w, pdf.get_y())
    pdf.ln(2)
    pdf.set_x(pdf.l_margin)
    pdf._sf(7.5, "light")
    pdf.set_text_color(*_TEXT_SOFT)
    pdf.multi_cell(main_w, 4, _safe(_about_this_report(
        lang, inc, results, bt_summary, live_data, len(asset_names or []))))

    # Contents block
    pdf.ln(3)
    pdf.set_x(pdf.l_margin)
    pdf._sf(8, "semibold")
    pdf.set_text_color(*pdf.primary_color)
    try:
        pdf.set_char_spacing(0.4)
    except Exception:
        pass
    pdf.cell(main_w, 5, _t("in_this_report", lang).upper(), new_x="LMARGIN", new_y="NEXT")
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass
    pdf.set_draw_color(*_HAIRLINE)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y() + 0.5, pdf.l_margin + main_w, pdf.get_y() + 0.5)
    pdf.ln(2)
    # The contents mirror the body's three-lens structure: a lens lists as a
    # group header (Monte Carlo / Backtest / Live) with its sub-sections indented
    # beneath, so the map matches the part dividers in the body. A lens appears
    # only when at least one of its items is included. The opening (Note Terms /
    # Issuer) and closing (Glossary / Disclaimer) groups are flat.
    _n_assets = len(asset_names or [])
    _any_fan  = any(inc(f"mc_fan_{i}") for i in range(_n_assets))
    toc_groups = []  # (header|None, [leaf titles])

    _top = []
    if inc("note_terms"):
        _top.append(_t("note_terms", lang))
    if getattr(terms, "issuer", "") and inc("issuer_info"):
        _top.append(_t("issuer_info", lang))
    if inc("underlying_breakdown"):
        _top.append(_t("underlying_breakdown", lang))
    if _top:
        toc_groups.append((None, _top))

    _mc = []
    if inc("mc_metrics") or inc("mc_irr") or inc("mc_autocall"):
        _mc.append(_t("mc_subtab_payoff", lang))
    if inc("mc_wof") or _any_fan:
        _mc.append(_t("mc_subtab_paths", lang))
    if inc("mc_single_wof"):
        _mc.append(_t("mc_subtab_explorer", lang))
    if results.get("params") and (inc("calib_table") or inc("calib_corr")):
        _mc.append(_t("calibration", lang))
    if _mc:
        toc_groups.append((_t("lens_mc", lang), _mc))

    _bt = []
    if bt_summary and (inc("bt_metrics") or inc("bt_outcome") or inc("bt_pie") or inc("bt_irr")):
        _bt.append(_t("bt_subtab_outcomes", lang))
    if bt_summary and inc("bt_prices"):
        _bt.append(_t("bt_subtab_prices", lang))
    if _bt:
        toc_groups.append((_t("lens_bt", lang), _bt))

    if live_data and (inc("live_metrics") or inc("live_asset_table")
                      or inc("live_obs_table") or inc("live_chart")):
        _live = []
        if inc("live_asset_table"):
            _live.append(_t("live_asset_perf", lang))
        if inc("live_obs_table"):
            _live.append(_t("live_obs_history", lang))
        toc_groups.append((_t("lens_live", lang), _live))

    toc_groups.append((None, [_t("glossary_title", lang), _t("disclaimer_title", lang)]))

    # The contents must fit between here and the fixed micro-disclaimer near the
    # page foot. A full report (all three lenses + every sub-section) is ~15 rows
    # and overflows at the default 5.5 mm row height, so compress rows to fit the
    # available band when needed. Common (partial) reports stay at full height.
    _toc_top    = pdf.get_y()
    _toc_bottom = pdf.h - 22 - 4.0          # keep clear of the micro-disclaimer
    _toc_avail  = _toc_bottom - _toc_top
    _gap        = 1.2                        # extra space before each lens header
    _n_heads    = sum(1 for nm, _ in toc_groups if nm is not None)
    _n_rows     = sum(len(lv) for _, lv in toc_groups) + _n_heads
    _row_h      = 5.5
    if _n_rows > 0 and (_n_rows * _row_h + _n_heads * _gap) > _toc_avail:
        _scale = max(0.0, _toc_avail - _n_heads * _gap) / (_n_rows * _row_h)
        _scale = min(1.0, _scale)
        _row_h = max(3.9, _row_h * _scale)
        _gap   = _gap * _scale

    def _toc_leaf(text, indent=0.0):
        pdf.set_x(pdf.l_margin + indent)
        pdf._sf(8.5, "regular")
        pdf.set_text_color(*_TEXT)
        pdf.cell(main_w - indent, _row_h, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*_RULE_LIGHT)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + main_w, pdf.get_y())

    def _toc_head(name):
        pdf.ln(_gap)
        pdf.set_x(pdf.l_margin)
        pdf._sf(8.5, "semibold")
        pdf.set_text_color(*pdf.primary_color)
        pdf.cell(main_w, _row_h, name, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*_RULE_LIGHT)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + main_w, pdf.get_y())

    for name, leaves in toc_groups:
        if name is not None:
            _toc_head(name)
            for leaf in leaves:
                _toc_leaf(leaf, indent=7.0)
        else:
            for leaf in leaves:
                _toc_leaf(leaf)

    # (The cover's "this document was generated by an automated simulation tool"
    # micro-disclaimer was removed at the client's request; the Important
    # Information section at the end still carries the full disclaimer.)

    pdf._is_cover = False
    # Re-enable auto-page-break for all content pages that follow
    pdf.set_auto_page_break(auto=True, margin=28)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def _table_room(n_rows: int, row_h: float = 8.0, head_h: float = 9.0) -> float:
    """Approx mm a filled-header table occupies. Capped so a long (multi-page)
    table doesn't make its sub-header demand a whole empty page — the header plus
    the start of the table is enough to keep them together; the rest flows."""
    return min(head_h + n_rows * row_h + 6.0, 130.0)


def _draw_note_diagram(pdf, terms, lang: str) -> None:
    """Draw the note-structure schematic (the React NoteTimeline, server-side):
    an observation timeline at the autocall level, the coupon / knock-in / One-Star
    barriers as dashed reference lines, and a floating value label for each. Pure
    fpdf primitives — wrapped so a drawing glitch can never abort the report."""
    try:
        from datetime import date, timedelta
        C_COUPON, C_KI, C_OS = (8, 145, 178), (220, 38, 38), (22, 163, 74)
        C_PROT, C_RISK = (22, 163, 74), (220, 38, 38)
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

        # x-axis time: real dates when the note has an issue date, else the tenor
        _mat_yrs = terms.maturity
        _tenor = (f"{int(round(_mat_yrs * 12)) // 12}y" if round(_mat_yrs * 12) % 12 == 0
                  else f"{int(round(_mat_yrs * 12))}m")
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

        # autocall window: above the autocall barrier, over the callable periods
        if start <= n:
            pdf.set_fill_color(*_blend(pdf.accent_color, _WHITE, 0.82))
            pdf.rect(acX, top, max(0.0, x1 - acX), max(0.0, ac_y - top), style="F")
            pdf.set_font(pdf._font_family, "B", 8)
            pdf.set_text_color(*pdf.accent_color)
            _wl = _t("diag_window", lang)
            pdf.text((acX + x1) / 2 - pdf.get_string_width(_wl) / 2, top + 4.0, _wl)

        # y gridlines + tick labels (0 / 50 / 100%)
        pdf.set_font(pdf._font_family, "", 6.8)
        for lvl in (0.0, 0.5, 1.0):
            gy = mapY(lvl)
            pdf.set_draw_color(223, 229, 237)
            pdf.set_line_width(0.2)
            pdf.line(x0, gy, x1, gy)
            pdf.set_text_color(150, 162, 180)
            _tl = f"{lvl:.0%}"
            pdf.text(x0 - 2 - pdf.get_string_width(_tl), gy + 1.0, _tl)

        # zone captions
        pdf.set_font(pdf._font_family, "B", 8)
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

        # axes — extended past the data with arrowheads so it doesn't end abruptly
        pdf.set_draw_color(150, 162, 180)
        pdf.set_line_width(0.4)
        pdf.line(x0, bottom, x0, top - 4)
        pdf.line(x0, bottom, x1 + 6, bottom)
        pdf.set_fill_color(150, 162, 180)
        pdf.polygon([(x0 - 1.4, top - 3), (x0 + 1.4, top - 3), (x0, top - 6)], style="F")
        pdf.polygon([(x1 + 4, bottom - 1.4), (x1 + 4, bottom + 1.4), (x1 + 7, bottom)], style="F")
        pdf.set_font(pdf._font_family, "B", 6.5)
        pdf.set_text_color(150, 162, 180)
        pdf.text(x0 - 3, top - 5.5, _t("diag_axis_level", lang))

        # observation dots on the par line + per-period coupon above
        def _dot(cx, r, fill):
            pdf.set_fill_color(*fill)
            pdf.ellipse(cx - r, par_y - r, 2 * r, 2 * r, style="F")
        _dot(x0, 1.5, pdf.accent_color)
        for i, f in enumerate(fracs):
            is_mat = (i + 1 == n)
            is_ac = (i + 1 >= start)
            col = pdf.primary_color if is_mat else (pdf.accent_color if is_ac else (205, 214, 228))
            _dot(mapX(f), 1.7 if is_mat else 1.5, col)
            if show_coupon:
                pdf.set_font(pdf._font_family, "", 6.5)
                pdf.set_text_color(*C_COUPON)
                _ct = f"+{coupon_per:.2%}"
                pdf.text(mapX(f) - pdf.get_string_width(_ct) / 2, par_y - 3.5, _ct)
            if show_yr_ticks and not is_mat:
                _yt = (f"{f * _mat_yrs:g}").rstrip(".") + "y"
                pdf.set_font(pdf._font_family, "", 6)
                pdf.set_text_color(170, 180, 195)
                pdf.text(mapX(f) - pdf.get_string_width(_yt) / 2, bottom + 4.6, _yt)

        # issue / maturity captions (below the x-axis) + the real date or tenor
        pdf.set_font(pdf._font_family, "", 7.5)
        pdf.set_text_color(110, 122, 145)
        _iss, _mat = _t("diag_issue", lang), _t("diag_maturity", lang)
        pdf.text(x0 - pdf.get_string_width(_iss) / 2, bottom + 4.6, _iss)
        pdf.text(x1 - pdf.get_string_width(_mat) / 2, bottom + 4.6, _mat)
        pdf.set_font(pdf._font_family, "", 6.5)
        pdf.set_text_color(150, 162, 180)
        if issue_lbl:
            pdf.text(x0 - pdf.get_string_width(issue_lbl) / 2, bottom + 8.6, issue_lbl)
        pdf.set_text_color(110, 122, 145)
        pdf.text(x1 - pdf.get_string_width(mat_lbl) / 2, bottom + 8.6, mat_lbl)

        # floating barrier labels (right gutter): name over value on two lines so
        # they stay narrow and the plot box can sit centred on the page.
        lx = x1 + 4
        entries = [(ac_y, pdf.accent_color, _t("diag_autocall", lang), f"{ac:.0%}")]
        if barriers_equal:
            entries.append((ki_y, C_COUPON, f"{_t('diag_coupon', lang)} / {_t('diag_knockin', lang)}", f"{cp:.0%}"))
        else:
            entries.append((mapY(cp), C_COUPON, _t("diag_coupon", lang), f"{cp:.0%}"))
            entries.append((ki_y, C_KI, _t("diag_knockin", lang), f"{ki:.0%}"))
        if os_lvl is not None:
            entries.append((mapY(os_lvl), C_OS, _t("diag_onestar", lang), f"{os_lvl:.0%}"))
        entries.sort(key=lambda e: e[0])
        prev_y = -100.0
        for ty, color, name, val in entries:
            ly = max(ty, prev_y + 7.4)
            prev_y = ly
            pdf.set_draw_color(190, 198, 210)
            pdf.set_line_width(0.2)
            pdf.line(x1 + 1, ty, lx - 1, ly - 1.0)
            pdf.set_font(pdf._font_family, "", 7)
            pdf.set_text_color(*color)
            pdf.text(lx, ly, name)
            pdf.set_font(pdf._font_family, "B", 8.5)
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


def generate_pdf_report(*args, **kwargs) -> bytes:
    """Public entry point — see _build_pdf_report for the full signature/docs.

    Wraps the build in a single persistent Kaleido server so every Plotly figure
    export shares one Chrome instead of cold-booting one per figure (~40s → ~5s
    of export for a full report), and tears the Chrome subprocess down in a
    finally so it never outlives the build. The server is best-effort: if it
    can't start, figure export silently falls back to the per-call path."""
    _server = _start_kaleido_server()
    try:
        return _build_pdf_report(*args, **kwargs)
    finally:
        if _server:
            _stop_kaleido_server()


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
) -> bytes:
    """
    Build the full institutional-style PDF report.

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

    issuer  = getattr(terms, "issuer", "") or ""
    # Issuer logo: a user-uploaded image wins (normalised to an embeddable PNG);
    # otherwise try a local branding/ticker_logos/{issuer}.png, else the favicon URL.
    if issuer_logo_override:
        issuer_logo_bytes = _to_embeddable_png(issuer_logo_override)
    else:
        issuer_logo_bytes = _load_ticker_logo(issuer, issuer_logo_url) if (issuer or issuer_logo_url) else None

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
    )
    # Custom brand typography (title_font / body_font) — no-op + IBM Plex fallback
    # when the brand ships no fonts or the TTF files are absent.
    _register_brand_fonts(pdf, branding)
    # Usable content width — a page-geometry constant used by every table. Defined
    # here (not inside the Note-Terms block) so later sections never hit an unbound
    # `usable` when Note details is toggled off.
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    # Optional full-bleed background photo for the branded cover (base64 / data URI).
    def _decode_b64_img(_v):
        if not _v:
            return None
        try:
            _pl = _v.split(",", 1)[1] if _v.strip().startswith("data:") else _v
            return _to_embeddable_png(base64.b64decode(_pl))
        except Exception as _e:
            print(f"[PDF cover] image skipped: {_e}")
            return None
    pdf.cover_image_bytes = _decode_b64_img(_b.get("cover_image_base64"))
    pdf.cover_logo_bytes  = _decode_b64_img(_b.get("cover_logo_base64"))
    pdf.cover_overlay_color = _branding_color(branding, "cover_overlay_color", primary_color)
    try:
        pdf.cover_overlay_opacity = float(_b.get("cover_overlay_opacity", 0.55))
    except Exception:
        pdf.cover_overlay_opacity = 0.55

    # ── 0. Front cover (toggleable, default on) ────────────────────────────
    if _inc("cover"):
        _front_cover_page(pdf, terms, lang, report_title, website)

    # ── 1. Summary / contents page ─────────────────────────────────────────
    _cover_page(pdf, terms, results, asset_names, bt_summary, live_data, lang,
                logo_urls, issuer_logo_bytes, logo_tickers, inc=_inc,
                logo_overrides=_logo_ovr)

    # ── 2. Note terms + observation schedule (each toggleable) ──────────────
    # The first content page. Note Terms, the Observation Schedule, the Issuer
    # block and the Underlying Breakdown are all toggleable from the Build-report
    # panel's "Note details" category; with include_sections=None (programmatic
    # callers) every one renders, so existing callers are unaffected.
    _show_terms = _inc("note_terms")
    _show_obs   = _inc("obs_schedule")
    _show_diag  = _inc("note_diagram")
    _show_desc  = _inc("note_description")
    if _show_terms or _show_obs or _show_diag or _show_desc:
        pdf.add_page()
        usable = pdf.w - pdf.l_margin - pdf.r_margin
        if _show_desc:
            # Systematic prose blurb (override or auto-generated from the terms).
            from core.note_description import describe_note
            _nd = (getattr(terms, "note_description", "") or "").strip() or describe_note(terms, lang)
            pdf.section_title(_t("note_desc_title", lang))
            pdf.set_font(pdf._font_family, "", 9.5)
            pdf.set_text_color(70, 84, 105)
            pdf.multi_cell(usable, 5.0, pdf._safe(_nd))
            pdf.ln(3)
        if _show_diag:
            pdf.section_title(_t("note_diagram", lang))
            _draw_note_diagram(pdf, terms, lang)
            pdf.ln(2)
        if _show_terms:
            pdf.section_title(_t("note_terms", lang))
            _term_data = _term_rows(terms, lang)
            pdf.data_table(
                [_t("key_terms_col_characteristic", lang), _t("key_terms_col_description", lang)],
                [[k, v] for k, v in _term_data],
                col_widths=[usable * 0.40, usable * 0.60],
                aligns=["L", "L"],
                rounded=True,
            )
        if _show_obs:
            # A sub-header under Note Terms, or its own section title when Note
            # Terms is toggled off so the schedule isn't left unlabelled.
            if _show_terms:
                pdf.subsection(_t("obs_schedule", lang), min_room=14 + _table_room(terms.n_obs))
            else:
                pdf.section_title(_t("obs_schedule", lang))
            obs_times = terms.obs_times()
            sched     = terms.autocall_barrier_schedule()
            ac_rows = []
            for i, t_obs in enumerate(obs_times):
                eligible = _t("yes", lang) if (i + 1) >= terms.autocall_start_period else _t("no", lang)
                ac_rows.append([f"P{i+1}", f"{t_obs:.3g}", f"{sched[i]:.0%}", eligible])
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
                    "mc_single_wof", "calib_table", "calib_corr"}
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
        pdf.start_section(_t("issuer_info", lang), min_room=70.0)
        pdf.issuer_info_block(pdf.issuer, issuer_logo_bytes, _issuer_desc, _ratings)

    # ── 2c. Underlying Breakdown (per-underlying summary + 1Y price chart) ───
    # Toggleable; renders when underlying metrics were supplied. Metric values
    # come from the live pull; a per-field JSON override in terms.underlyings
    # wins, and 'description' is the curated company blurb.
    if underlying_metrics and _inc("underlying_breakdown"):
        _uls = getattr(terms, "underlyings", {}) or {}
        # The section title is drawn by the FIRST card (section_title=...) so it
        # stays glued to that card instead of being stranded above one that breaks
        # to the next page. Each card is atomic — see underlying_block.
        _ul_first = True
        for _nm in asset_names:
            _m  = underlying_metrics.get(_nm, {}) or {}
            _ov = _uls.get(_nm, {}) or {}

            def _g(k, _m=_m, _ov=_ov):
                v = _ov.get(k)
                return v if v not in (None, "") else _m.get(k)

            _long = _g("long_name") or _nm
            _sub  = " · ".join(s for s in (_g("type"), _g("sector")) if s)
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
            # Analyst consensus (buy/hold/sell) — only when the user loaded it.
            _an_ov = _ov.get("analyst")
            _analyst = None
            if isinstance(_an_ov, dict):
                _tot = sum(float(_an_ov.get(k, 0) or 0) for k in ("buy", "hold", "sell"))
                if _tot > 0:
                    _analyst = [
                        (_t("sent_buy",  lang), float(_an_ov.get("buy", 0)  or 0) / _tot, (22, 163, 74)),
                        (_t("sent_hold", lang), float(_an_ov.get("hold", 0) or 0) / _tot, (245, 158, 11)),
                        (_t("sent_sell", lang), float(_an_ov.get("sell", 0) or 0) / _tot, (220, 38, 38)),
                    ]
            pdf.underlying_block(
                _long, _logo, _sub, _band, _desc, _png, _cap,
                section_title=(_t("underlying_breakdown", lang) if _ul_first else None),
                analyst=_analyst, analyst_title=_t("u_analyst", lang))
            _ul_first = False

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

    def _lazy_divider(name, question):
        """Emit a three-lens part divider at most once, when the lens's first
        included item is drawn — so a fully-toggled-off lens leaves no divider."""
        state = {"done": False}
        def ensure():
            if not state["done"]:
                pdf.section_divider(name, question)
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
    _mc_div = _lazy_divider(_t("lens_mc", lang), _t("lens_q_mc", lang))

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
        pdf.metric_band([
            (_t("expected_irr",       lang), f"{results.get('expected_irr', 0):.2%}"),
            (_t("total_return_short", lang), f"{results.get('expected_total_return', 0):.2%}"),
            (_t("prob_autocall",      lang), f"{results.get('prob_autocall', 0):.1%}"),
            (_t("prob_knock_in",      lang), f"{_p_ki:.2%}"),
            (_t("loss_given_ki",      lang), _lgki_str),
            (_t("n_paths",            lang), f"{n_paths_val:,}"),
        ])
    if _inc("mc_outcome") and figures.get("outcome") is not None:
        _sec()
        pdf.figure(_fig_to_png(figures.get("outcome"), width=900, height=300, **_kw),
                   _t("fig_outcome", lang), src_mc)
    if _inc("mc_irr"):
        _sec()
        pdf.figure(_fig_to_png(figures.get("irr_dist"), **_kw), _t("fig_irr", lang), src_mc)
    prob_by_period = results.get("prob_autocall_by_period", [])
    if _inc("mc_autocall") and prob_by_period:
        _sec()
        pdf.subsection(_t("autocall_by_period", lang),
                       min_room=14 + _table_room(len(prob_by_period)))
        rows = []
        for i, (t_obs, p_ac) in enumerate(zip(obs_times, prob_by_period)):
            eligible = _t("yes", lang) if (i + 1) >= terms.autocall_start_period else _t("no", lang)
            rows.append([f"P{i+1}", f"{t_obs:.3g}", f"{p_ac:.2%}", eligible])
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
        pdf.figure(_fig_to_png(figures.get("wof_fan"), **_kw), _t("fig_wof", lang), src_mc)
    for i, (nm, fig) in enumerate(figures.get("individual") or []):
        if _inc(f"mc_fan_{i}"):
            _sec()
            pdf.figure(_fig_to_png(fig, **_kw),
                       _t("fig_individual", lang).format(name=nm), src_mc)

    # 3c. Path Explorer — the simulated path(s) the user last viewed. One worst-of
    # chart per comparison panel, captioned with the user's panel title (or the
    # default "Worst-of path #N"). The per-asset price chart was removed from the
    # explorer, so it is no longer in the report either.
    _sec = _lazy_section(_t("mc_subtab_explorer", lang), before=_mc_div)
    _pn = figures.get("single_path_num", 0)
    # Back-compat: sessions from before multi-panel only stored one wof figure.
    _panels = figures.get("panels")
    if not _panels and figures.get("single_path_wof") is not None:
        _panels = [{"title": None, "wof": figures.get("single_path_wof"), "num": _pn}]
    if _inc("mc_single_wof") and _panels:
        for _p in _panels:
            if _p.get("wof") is None:
                continue
            _sec()
            _cap = _p.get("title") or _t("fig_single_wof", lang).format(n=_p.get("num", 0))
            pdf.figure(_fig_to_png(_p["wof"], **_kw), _cap, src_mc)

    # ── 4. Calibration ─────────────────────────────────────────────────────
    # Still part of the Monte Carlo lens (the model behind the simulation), so it
    # carries the same "01" divider rather than opening a new part.
    params = results.get("params", [])
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
    bt_figures = bt_figures or {}
    # Lens 2 of 3 — the realised-history lens.
    _bt_div = _lazy_divider(_t("lens_bt", lang), _t("lens_q_bt", lang))
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
        pdf.metric_band([
            (_t("bt_mean_irr",        lang), f"{bt_summary.get('mean_irr', 0):.2%}"),
            (_t("total_return_short", lang), f"{bt_summary.get('expected_total_return', 0):.2%}"),
            (_t("bt_autocalled_pct",  lang), f"{bt_summary.get('prob_called', 0):.1%}"),
            (_t("bt_knock_in_pct",    lang), f"{bt_summary.get('prob_knock_in', 0):.1%}"),
            (_t("bt_loss_given_ki",   lang), _bt_lgki_pdf),
            (_t("bt_n_issues",        lang), str(bt_summary.get("n_issues", 0))),
        ])
    if bt_summary and _inc("bt_outcome") and bt_figures.get("outcome") is not None:
        _sec()
        pdf.figure(_fig_to_png(bt_figures.get("outcome"), **_kw),
                   _t("fig_bt_outcome", lang), _t("src_hist", lang))
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
    _bt_panels = bt_figures.get("panels") or []
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
        _live_div = _lazy_divider(_t("lens_live", lang), _t("lens_q_live", lang))
        if _inc("live_metrics"):
            _live_div()
            pdf.metric_band([
                (_t("live_wof_today",   lang), f"{live_data.get('wof_today', 0):.1%}"),
                (_t("live_worst_asset", lang), str(live_data.get("worst_asset", ""))),
                (_t("live_irr_to_date", lang), f"{live_data.get('irr_to_date', 0):.2%}"),
                (_t("live_elapsed",     lang), f"{live_data.get('elapsed_years', 0):.2f}"),
            ])

        perf_today = live_data.get("perf_today", {})
        if perf_today and _inc("live_asset_table"):
            _live_div()
            pdf.subsection(_t("live_asset_perf", lang),
                           min_room=14 + _table_room(len(perf_today), row_h=10.0))
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
                           min_room=14 + _table_room(len(obs_rows)))
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
    if getattr(terms, "memory", False):                 _g_active.add("mem")
    if getattr(terms, "one_star_level", None) is not None: _g_active.add("os")
    if results:                                         _g_active.add("mc")
    if bt_summary:                                      _g_active.add("bt")
    if underlying_metrics:                              _g_active.add("ul")
    _glos = _GLOSSARY.get(lang, _GLOSSARY["en"])
    for _i, (_term, _defn) in enumerate(_glos):
        _tags = _GLOSSARY_TAGS[_i] if _i < len(_GLOSSARY_TAGS) else {"core"}
        if _g_active.isdisjoint(_tags):
            continue
        if pdf.get_y() > pdf.h - 34:
            pdf.add_page()
        pdf._sf(8, "semibold")
        pdf.set_text_color(*pdf.primary_color)
        pdf.write(4.4, pdf._safe(f"{_term} — "))
        pdf._sf(8, "regular")
        pdf.set_text_color(*_TEXT)
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

    return bytes(pdf.output())
