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
  - Typography: Inter variable font (Regular / SemiBold / Bold / Light /
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
    "primary_color":         "#003366",           # headers, bands, table fills
    "accent_color":          "#00A0DC",           # rules, hero data series, median
    "chart_secondary_color": "#C69426",           # 2nd chart category (default: gold)
    "logo_file":             "branding/acme.png", # local path, repo-root relative (preferred)
    "logo_base64":           "",                  # OR a base64 / data: URI
    "logo_url":              "https://...",        # OR a remote URL (last resort)
    "report_title":          "Structured Note Analytics",  # cover eyebrow + subtitle
    "website":               "www.acme.com",      # cover identity line
    "contact":               "research@acme.com", # cover identity line
    "footer_note":           "..."                # overrides the default footer disclaimer line
  }

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
import functools
import urllib.request
import warnings
import numpy as np
from pathlib import Path
from fpdf import FPDF

_REPO_ROOT       = Path(__file__).parent.parent
_TICKER_LOGO_DIR = _REPO_ROOT / "branding" / "ticker_logos"
_FONT_DIR        = _REPO_ROOT / "fonts"
_INTER_TTC       = _FONT_DIR / "Inter.ttc"
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
_TEXT             = (33,  33, 33)   # near-black
_TEXT_SOFT        = (107, 114, 128) # warm grey  #6b7280
_HAIRLINE         = (203, 213, 225) # cool grey  #cbd5e1
_RULE_LIGHT       = (226, 232, 240) # slate-100  #e2e8f0
_PANEL            = (241, 245, 249) # slate-100  #f1f5f9
_ROW_ALT          = (248, 250, 252) # slate-50   #f8fafc — zebra rows
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
}
_HEX_KEYS = ("primary_color", "accent_color", "chart_secondary_color")


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
    tuple[int, int, int], tuple[int, int, int], tuple[int, int, int], str
]:
    """Return (primary, accent, secondary, firm_name) from the branding dict.
    Malformed hex values fall back to defaults with a warning; never raises."""
    if not branding:
        return _DEFAULT_PRIMARY, _DEFAULT_ACCENT, _DEFAULT_SECONDARY, "Structured Note Analytics"
    primary   = _branding_color(branding, "primary_color",         _DEFAULT_PRIMARY)
    accent    = _branding_color(branding, "accent_color",          _DEFAULT_ACCENT)
    secondary = _branding_color(branding, "chart_secondary_color", _DEFAULT_SECONDARY)
    firm      = branding.get("firm_name", "Structured Note Analytics") or "Structured Note Analytics"
    return primary, accent, secondary, firm


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
    "obs_schedule":          {"en": "Observation Schedule",              "es": "Calendario de Observaciones"},
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
    "disclaimer_title":      {"en": "Important Information",             "es": "Información Importante"},
    "maturity":              {"en": "Maturity",                          "es": "Vencimiento"},
    "freq":                  {"en": "Payment frequency",                 "es": "Frecuencia de pago"},
    "coupon_pa":             {"en": "Coupon p.a.",                       "es": "Cupón anual"},
    "coupon_barrier":        {"en": "Coupon barrier",                    "es": "Barrera de cupón"},
    "autocall_barrier":      {"en": "Autocall barrier",                  "es": "Barrera de autocall"},
    "autocall_start":        {"en": "First autocall observation",        "es": "Primera observación autocall"},
    "ki_barrier":            {"en": "Knock-in barrier (European)",       "es": "Barrera knock-in (europea)"},
    "memory":                {"en": "Memory coupon",                     "es": "Cupón con memoria"},
    "coupon_basket":         {"en": "Coupon basket",                     "es": "Cesta de cupón"},
    "autocall_basket":       {"en": "Autocall basket",                   "es": "Cesta de autocall"},
    "final_basket":          {"en": "Final redemption basket",           "es": "Cesta de redención final"},
    "rescue_barrier":        {"en": "Final redemption barrier",          "es": "Barrera de redención final"},
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
    "prob_knock_in":         {"en": "P(capital loss)",                   "es": "P(pérdida de capital)"},
    "n_paths":               {"en": "Simulated paths",                   "es": "Caminos simulados"},
    "autocall_by_period":    {"en": "Autocall Probability by Period",    "es": "Probabilidad de Autocall por Período"},
    "period":                {"en": "Period",                            "es": "Período"},
    "time_y":                {"en": "Time (yrs)",                        "es": "Tiempo (años)"},
    "p_autocall":            {"en": "P(autocall)",                       "es": "P(autocall)"},
    "ac_level":              {"en": "Barrier",                           "es": "Barrera"},
    "eligible":              {"en": "Eligible",                          "es": "Elegible"},
    "yes":                   {"en": "Yes",                               "es": "Sí"},
    "no":                    {"en": "No",                                "es": "No"},
    "fig_irr":               {"en": "Distribution of simple annualised IRR across simulated paths",
                              "es": "Distribución de TIR anual simple en los caminos simulados"},
    "fig_wof":               {"en": "Worst-of basket performance fan with barrier levels",
                              "es": "Abanico de la cesta worst-of con niveles de barrera"},
    "fig_corr":              {"en": "Calibrated return correlation matrix",
                              "es": "Matriz de correlaciones de retorno calibrada"},
    "fig_bt_outcome":        {"en": "Distribution of historical outcomes by issue date",
                              "es": "Distribución de resultados históricos por fecha de emisión"},
    "fig_bt_irr":            {"en": "Realised simple annualised IRR by historical issue date",
                              "es": "TIR anual simple realizada por fecha de emisión histórica"},
    "fig_live":              {"en": "Underlying performance since issue date with observation outcomes",
                              "es": "Rendimiento de los subyacentes desde emisión con resultados de observación"},
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
    "live_wof_today":        {"en": "Worst-of today",                    "es": "Worst-of hoy"},
    "live_worst_asset":      {"en": "Worst asset",                       "es": "Peor activo"},
    "live_irr_to_date":      {"en": "Coupon IRR to date (ann.)",         "es": "TIR de cupones a fecha (anual)"},
    "live_elapsed":          {"en": "Elapsed (years)",                   "es": "Transcurrido (años)"},
    "live_asset_perf":       {"en": "Current Asset Performance",         "es": "Rendimiento Actual por Activo"},
    "live_obs_history":      {"en": "Observation History",               "es": "Historial de Observaciones"},
    "performance":           {"en": "Performance",                       "es": "Rendimiento"},
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


# ──────────────────────────────────────────────────────────────────────────────
# Text sanitisation
# Inter covers all Latin/Greek/punctuation/math Unicode natively, so we only
# need to neutralise emojis and a handful of symbols Inter omits.
# ──────────────────────────────────────────────────────────────────────────────
_EMOJI_STRIP = {
    "✅": "OK", "⚠️": "!", "❌": "x", "🚀": ">>", "⏳": "...",
    "®": "", "™": "", "©": "",
}


def _safe(text: object, *, latin1: bool = False) -> str:
    """Sanitise text for the PDF.

    With Inter (Unicode font) only emojis need neutralising.
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
# Primary: IBM Plex Sans individual TTF files (institutional quality).
# Fallback 1: Inter TTC collection (if IBM files are missing).
# Fallback 2: Helvetica (built-in, Latin-1 only).
#
# TTC indices used from Inter.ttc (fallback):
#   0  = Inter Regular       14 = Inter Bold
#   3  = Inter Italic        15 = Inter Bold Italic
#   6  = Inter Light         12 = Inter SemiBold
# ──────────────────────────────────────────────────────────────────────────────
_TTC_IDX = {
    ("Inter",      ""):   0,
    ("Inter",      "I"):  3,
    ("Inter",      "B"):  14,
    ("Inter",      "BI"): 15,
    ("InterSB",    ""):   12,
    ("InterLight", ""):   6,
}

# Font family name exposed to _sf() — switches based on what is available
_FONT_FAMILY = "IBMPlexSans"   # overridden to "Inter" if IBM files absent


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


def _register_inter(pdf: FPDF) -> bool:
    """Register Inter variants from the TTC collection. Returns True on success."""
    if not _INTER_TTC.exists():
        return False
    try:
        ttc = str(_INTER_TTC)
        for (family, style), idx in _TTC_IDX.items():
            pdf.add_font(family, style, ttc, collection_font_number=idx)
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# FPDF subclass
# ──────────────────────────────────────────────────────────────────────────────

class _NotePDF(FPDF):
    """A4 portrait document with QIS-publication styling and Inter typography."""

    def __init__(self, lang: str = "en", issuer: str = "", doc_ref: str = "",
                 primary_color: tuple = _DEFAULT_PRIMARY,
                 accent_color: tuple = _DEFAULT_ACCENT,
                 firm_name: str = "Structured Note Analytics",
                 firm_logo_bytes: bytes | None = None,
                 report_title: str | None = None,
                 website: str = "", contact: str = "",
                 footer_note: str | None = None):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.lang          = lang
        self.issuer        = issuer
        self.doc_ref       = doc_ref
        self.primary_color = primary_color
        self.accent_color  = accent_color
        self.firm_name     = firm_name
        self.firm_logo_bytes = firm_logo_bytes
        # Optional branding content (B5). report_title overrides the default
        # "Structured Note Analytics" eyebrow/subtitle; footer_note overrides the
        # default footer disclaimer line; website/contact print on the cover.
        self.report_title  = report_title
        self.website       = website or ""
        self.contact       = contact or ""
        self.footer_note   = footer_note
        # Aspect ratio (so a wide wordmark isn't squashed into a square box) and a
        # white knockout for legible placement on the coloured cover band.
        self.firm_logo_aspect = _logo_aspect(firm_logo_bytes, default=1.0)
        self.firm_logo_white_bytes = _white_knockout(firm_logo_bytes)
        self._is_cover     = False
        self._cover_page_no = None   # page number that holds the cover (no running footer)
        self._fig_no       = 0
        # Locale-neutral numeric timestamp so the footer never shows an English
        # month abbreviation in a Spanish report.
        self._gen_dt       = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M")
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(auto=True, margin=28)
        self.alias_nb_pages()
        # Try IBM Plex Sans first; fall back to Inter TTC; last resort Helvetica
        if _register_ibm_plex(self):
            self._font_family = "IBMPlexSans"
            self._use_unicode = True
            print("[PDF font] Using IBM Plex Sans")
        elif _register_inter(self):
            self._font_family = "Inter"
            self._use_unicode = True
            print("[PDF font] Using Inter (IBM Plex Sans files missing)")
        else:
            self._font_family = "Helvetica"
            self._use_unicode = False
            print("[PDF font] Using Helvetica fallback")
        # Legacy flag — kept so external code referencing _use_inter still works
        self._use_inter = self._use_unicode

    # ------------------------------------------------------------------
    # Font helpers
    # ------------------------------------------------------------------
    def _sf(self, size: float, weight: str = "regular") -> None:
        """Set font by semantic weight.

        Dispatches to IBM Plex Sans, Inter, or Helvetica depending on which
        was successfully registered at construction time.
        """
        ff = self._font_family
        if ff == "IBMPlexSans":
            _map = {
                "regular":     ("IBMPlexSans",      ""),
                "bold":        ("IBMPlexSans",      "B"),
                "bold_italic": ("IBMPlexSans",      "BI"),
                "italic":      ("IBMPlexSans",      "I"),
                "semibold":    ("IBMPlexSansSB",    ""),
                "light":       ("IBMPlexSansLight", ""),
            }
            family, style = _map.get(weight, ("IBMPlexSans", ""))
        elif ff == "Inter":
            _map = {
                "regular":     ("Inter",      ""),
                "bold":        ("Inter",      "B"),
                "bold_italic": ("Inter",      "BI"),
                "italic":      ("Inter",      "I"),
                "semibold":    ("InterSB",    ""),
                "light":       ("InterLight", ""),
            }
            family, style = _map.get(weight, ("Inter", ""))
        else:
            _hmap = {
                "regular":     ("Helvetica", ""),
                "bold":        ("Helvetica", "B"),
                "bold_italic": ("Helvetica", "BI"),
                "italic":      ("Helvetica", "I"),
                "semibold":    ("Helvetica", "B"),
                "light":       ("Helvetica", ""),
            }
            family, style = _hmap.get(weight, ("Helvetica", ""))
        self.set_font(family, style, size)

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
        self.set_xy(self.l_margin + logo_w, 9.5)
        self._sf(7.5, "semibold")
        self.set_text_color(*self.primary_color)
        firm_label = self._safe(self.firm_name.upper())
        self.cell(100, 4.5, firm_label)

        self._sf(7, "light")
        self.set_text_color(*_TEXT_SOFT)
        self.set_xy(self.w - self.r_margin - 85, 9.5)
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
        if self._is_cover or self.page_no() == self._cover_page_no:
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
    def start_section(self, text: str, min_room: float = 110.0):
        """Begin a major section, breaking to a new page only when needed.

        Sections used to each call an unconditional ``add_page()``, which left
        big voids whenever a section had little content (a 1-row observation
        table dropped onto an otherwise-blank page). Instead we keep flowing on
        the current page and only break when fewer than ``min_room`` mm remain
        below the cursor — enough for the title plus a meaningful chunk of the
        section. The result fills pages naturally without orphan sections.
        """
        if self.page_no() == 0:
            self.add_page()
        elif self.get_y() > self.h - self.b_margin - min_room:
            self.add_page()
        else:
            self.ln(6)   # generous separation between stacked sections
        self.section_title(text)

    def section_title(self, text: str):
        """SemiBold 11pt section header with micro-space above and thin rule below."""
        if self.get_y() > self.h - 60:
            self.add_page()
        self.ln(4)                          # breathing room above
        self._sf(11, "semibold")
        self.set_text_color(*self.primary_color)
        self.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        # Thin rule directly below
        self.set_draw_color(*self.primary_color)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_text_color(*_TEXT)
        self.ln(3)

    def subsection(self, text: str):
        """SemiBold 9pt sub-header with rule below."""
        if self.get_y() > self.h - 55:
            self.add_page()
        self.ln(2)
        self._sf(9, "semibold")
        self.set_text_color(*_TEXT)
        self.cell(0, 6, text.upper(), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_RULE_LIGHT)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
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
                self.rect(self.l_margin, y0, col_w[0] + col_w[1], 6.4, style="F")
            self._sf(8.5, "semibold")
            self.set_text_color(*_TEXT)
            self.cell(col_w[0], 6.4, k)
            self._sf(8.5, "regular")
            self.cell(col_w[1], 6.4, v, new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*_RULE_LIGHT)
            self.set_line_width(0.15)
            self.line(self.l_margin, self.get_y(),
                      self.l_margin + col_w[0] + col_w[1], self.get_y())
        self.ln(3)

    def data_table(self, headers: list[str], rows: list[list[str]],
                   col_widths: list[float] | None = None,
                   aligns: list[str] | None = None):
        """Filled-header table with zebra rows and proper number alignment."""
        n = len(headers)
        usable = self.w - self.l_margin - self.r_margin
        if col_widths is None:
            col_widths = [usable / n] * n
        if aligns is None:
            aligns = ["L"] + ["R"] * (n - 1)

        def _header_row():
            self.set_fill_color(*self.primary_color)
            self.set_text_color(*_WHITE)
            self._sf(7.5, "semibold")
            for h, w, a in zip(headers, col_widths, aligns):
                self.cell(w, 7, f" {h} ", border=0, fill=True, align=a)
            self.ln()
            # Thin separator between header and data
            self.set_draw_color(*self.accent_color)
            self.set_line_width(0.25)
            self.line(self.l_margin, self.get_y(),
                      self.l_margin + sum(col_widths), self.get_y())
            self.set_text_color(*_TEXT)
            self._sf(8, "regular")

        if self.get_y() > self.h - 55:
            self.add_page()
        _header_row()

        for i, row in enumerate(rows):
            if self.get_y() > self.h - 30:
                self.add_page()
                _header_row()
            fill_color = _ROW_ALT if i % 2 == 0 else _WHITE
            self.set_fill_color(*fill_color)
            for cell_val, w, a in zip(row, col_widths, aligns):
                self.cell(w, 6, f" {cell_val} ", border=0, fill=True, align=a)
            self.ln()

        # Bottom rule
        self.set_draw_color(*_HAIRLINE)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(),
                  self.l_margin + sum(col_widths), self.get_y())

    def logo_row_table(self, headers: list[str], rows: list[list[str]],
                       logos: dict, col_widths: list[float] | None = None,
                       aligns: list[str] | None = None):
        """Like data_table but draws a small inline ticker logo to the left of the
        first-column name. `rows[i][0]` is the asset name and `logos[name]` its
        PNG bytes (or None). Mirrors the calibration table's inline-logo style."""
        n = len(headers)
        usable = self.w - self.l_margin - self.r_margin
        if col_widths is None:
            col_widths = [usable / n] * n
        if aligns is None:
            aligns = ["L"] + ["R"] * (n - 1)
        LW = LH = 6.0
        ROW_H = 8.0

        def _header_row():
            self.set_fill_color(*self.primary_color)
            self.set_text_color(*_WHITE)
            self._sf(7.5, "semibold")
            for h, w, a in zip(headers, col_widths, aligns):
                self.cell(w, 7, f" {h} ", border=0, fill=True, align=a)
            self.ln()
            self.set_draw_color(*self.accent_color)
            self.set_line_width(0.25)
            self.line(self.l_margin, self.get_y(),
                      self.l_margin + sum(col_widths), self.get_y())
            self.set_text_color(*_TEXT)
            self._sf(8, "regular")

        if self.get_y() > self.h - 55:
            self.add_page()
        _header_row()

        for i, row in enumerate(rows):
            if self.get_y() > self.h - 30:
                self.add_page()
                _header_row()
            name = str(row[0])
            fill = _ROW_ALT if i % 2 == 0 else _WHITE
            row_y = self.get_y()
            # First column: zebra fill, inline logo, then name
            self.set_fill_color(*fill)
            self.rect(self.l_margin, row_y, col_widths[0], ROW_H, style="F")
            ldata = (logos or {}).get(name)
            text_x = self.l_margin + 2
            if ldata:
                try:
                    self.image(io.BytesIO(ldata), x=self.l_margin + 1,
                               y=row_y + (ROW_H - LH) / 2, w=LW, h=LH)
                    text_x = self.l_margin + LW + 3
                except Exception:
                    pass
            self.set_xy(text_x, row_y + (ROW_H - 4) / 2)
            self._sf(8, "semibold")
            self.set_text_color(*_TEXT)
            self.cell(col_widths[0] - (text_x - self.l_margin) - 1, 4, self._safe(name))
            # Remaining columns
            self._sf(8, "regular")
            self.set_xy(self.l_margin + col_widths[0], row_y)
            for cell_val, w, a in zip(row[1:], col_widths[1:], aligns[1:]):
                self.set_fill_color(*fill)
                self.cell(w, ROW_H, f" {cell_val} ", border=0, fill=True, align=a)
            self.set_y(row_y + ROW_H)

        self.set_draw_color(*_HAIRLINE)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(),
                  self.l_margin + sum(col_widths), self.get_y())
        self.ln(4)

    def metric_band(self, metrics: list[tuple[str, str]]):
        """Horizontal band of key metrics with accent top rule."""
        n = len(metrics)
        usable = self.w - self.l_margin - self.r_margin
        w = usable / n
        y0 = self.get_y()

        # Accent top rule
        self.set_draw_color(*self.accent_color)
        self.set_line_width(0.6)
        self.line(self.l_margin, y0, self.w - self.r_margin, y0)
        self.ln(2.5)

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

            self.set_xy(x, y0 + 8.5)
            self._sf(13, "bold")
            self.set_text_color(*self.primary_color)
            self.cell(w - 2, 7, value)
            x += w

        self.set_y(y0 + 18)
        self.set_draw_color(*_RULE_LIGHT)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
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
        needed = h + 18
        if self.get_y() + needed > self.h - 28:
            self.add_page()
        # Caption above figure — SemiBold 8.5pt in accent color
        self._sf(8.5, "semibold")
        self.set_text_color(*self.accent_color)
        self.multi_cell(0, 4.5, f"{_t('figure_word', self.lang)} {self._fig_no}: {caption}", align="C")
        self.ln(1)
        x = (self.w - w) / 2
        self.image(io.BytesIO(img_bytes), x=x, w=w, h=h)
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
        self.set_fill_color(*_PANEL)
        try:
            self.rect(x0, y0, w, box_h, style="F", round_corners=True, corner_radius=2)
        except TypeError:
            self.rect(x0, y0, w, box_h, style="F")
        # Left accent bar
        self.set_fill_color(*self.accent_color)
        self.rect(x0, y0, 2, box_h, style="F")
        self.set_xy(x0 + 6, y0 + 3.5)
        self._sf(8.5, "semibold")
        self.set_text_color(*self.primary_color)
        self.cell(w - 10, 5, title)
        self.set_xy(x0 + 6, y0 + 10)
        self._sf(8, "regular")
        self.set_text_color(*_TEXT)
        self.multi_cell(w - 10, 4.3, text)
        self.set_y(y0 + box_h + 4)


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


def _white_knockout(png: bytes | None) -> bytes | None:
    """Recolour every opaque pixel of a logo to white, preserving the alpha mask.
    Used to render a (typically dark/coloured) firm wordmark legibly on the
    coloured cover band, where the original colour would clash or vanish. Returns
    None if the source is missing or can't be processed (caller falls back)."""
    if not png:
        return None
    try:
        from PIL import Image
        import numpy as np
        im = Image.open(io.BytesIO(png)).convert("RGBA")
        arr = np.array(im)
        opaque = arr[..., 3] > 0
        arr[opaque, 0] = 255
        arr[opaque, 1] = 255
        arr[opaque, 2] = 255
        out = io.BytesIO()
        Image.fromarray(arr, "RGBA").save(out, format="PNG")
        return out.getvalue()
    except Exception as exc:
        print(f"[PDF logo] white-knockout FAIL: {exc}")
        return None


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


@functools.lru_cache(maxsize=256)
def _load_ticker_logo(display_name: str, url: str | None,
                      symbol: str | None = None) -> bytes | None:
    """Resolve a single underlying/ticker logo, local-folder-first.

    Looks for branding/ticker_logos/{STEM}.{png,jpg,...} where STEM is tried as
    the ticker symbol first, then the display name. Falls back to the supplied
    URL. Never raises; returns None if nothing yields usable bytes.

    Memoised (P5): the same ticker is resolved for the cover, the calibration
    table and the performance table — without the cache each call re-did the
    local-file probe and, when no file exists, a fresh ≤8s network fetch per
    call. Keyed on (display_name, url, symbol), all hashable; None results are
    cached too so a missing logo isn't re-fetched three times. The set of ticker
    logos is independent of branding, so sharing the cache across reports in a
    long-running session is safe and beneficial.
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
    """Colour-scale map (heatmaps): keep the intensity ramp on-brand (green),
    never gold — the navy/blue endpoints map to the brand, red stays red."""
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
    try:
        if getattr(fig.layout, "colorway", None):
            fig.layout.colorway = tuple(rc(c) for c in fig.layout.colorway)
    except Exception:
        pass
    for tr in fig.data:
        for path in ("line.color", "fillcolor", "marker.color", "marker.line.color"):
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
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(family="IBM Plex Sans, Arial, sans-serif", size=10, color="#1a1a2e"),
            modebar_remove=["logo", "toImage", "sendDataToCloud"],
        )
        # Style axes without disturbing any explicit per-axis ranges/tickformats
        fig.update_xaxes(linecolor="#e5e7eb", gridcolor="#f3f4f6",
                         zerolinecolor="#e5e7eb")
        fig.update_yaxes(linecolor="#e5e7eb", gridcolor="#f3f4f6",
                         zerolinecolor="#e5e7eb")
    except Exception:
        pass


def _fig_to_png(fig, width: int = 900, height: int = 500,
                primary_color: tuple = _DEFAULT_PRIMARY,
                accent_color: tuple = _DEFAULT_ACCENT,
                secondary_color: tuple = _DEFAULT_SECONDARY) -> bytes | None:
    """Rasterise a Plotly figure to PNG bytes at 3× scale (~300 dpi equivalent).

    Applies `_theme_figure` before rendering so all charts use the report's
    branded color scheme and white background regardless of app theme.
    """
    try:
        import plotly.io as pio
        import plotly.graph_objects as go
        fig = go.Figure(fig)
        fig.update_layout(title=None, margin=dict(t=24, b=40))
        _theme_figure(fig, primary_color, accent_color, secondary_color)
        return pio.to_image(fig, format="png", width=width, height=height,
                            scale=3, engine="kaleido")
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Page builders
# ──────────────────────────────────────────────────────────────────────────────

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
        (_t("final_basket",     lang), f"{terms.final_basket.replace('_', '-')}"
                                       + (f"  ({_t('rescue_barrier', lang)} {terms.final_redemption_barrier:.0%})"
                                          if terms.final_basket == "best_of" else "")),
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


def _exec_bullets(terms, results, bt_summary, live_data, lang: str) -> list[str]:
    b = []
    if lang == "es":
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
                f"Since issue, the worst-of basket trades at {live_data.get('wof_today', 0):.1%} of strike "
                f"({live_data.get('worst_asset', '')} is the worst performer); coupon IRR to date is "
                f"{live_data.get('irr_to_date', 0):.1%} annualised.")
    return b


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
):
    pdf._is_cover = True
    # Disable auto-page-break for the cover so overflowing content (long note
    # names, many bullets) does NOT automatically insert a blank page 2.
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    # Remember which page is the cover so footer() suppresses the running footer
    # there even after _is_cover is reset (footer fires lazily on the next
    # add_page, by which point _is_cover is already False).
    pdf._cover_page_no = pdf.page_no()

    # ── Full-width colored top band ───────────────────────────────────────
    band_h = _COVER_BAND_H
    pdf.set_fill_color(*pdf.primary_color)
    pdf.rect(0, 0, pdf.w, band_h, style="F")

    # Firm logo (white knockout, left, vertically centred in the band). When a
    # logo is present it carries the firm identity, so the redundant firm-name
    # text line is suppressed; the eyebrow + date sit to its right.
    logo_x   = pdf.l_margin
    has_logo = False
    band_logo = pdf.firm_logo_white_bytes or pdf.firm_logo_bytes
    if band_logo:
        try:
            lh = 12.0
            lw = min(lh * pdf.firm_logo_aspect, 60.0)
            pdf.image(io.BytesIO(band_logo),
                      x=logo_x, y=(band_h - lh) / 2, w=lw, h=lh)
            has_logo = True
        except Exception:
            has_logo = False

    _today_long = _fmt_long_date(datetime.date.today(), lang)
    # B5: a branding report_title overrides the default eyebrow / subtitle.
    _eyebrow = (pdf.report_title or _t("report_eyebrow", lang)).upper()
    if has_logo:
        # Logo carries identity on the left; eyebrow + date form a clean
        # right-aligned block, vertically centred against the logo.
        rx, rw = pdf.w - pdf.r_margin - 100, 100
        pdf.set_xy(rx, 14)
        pdf._sf(8, "semibold")
        pdf.set_text_color(*_WHITE)
        try:
            pdf.set_char_spacing(1.4)
        except Exception:
            pass
        pdf.cell(rw, 5, _eyebrow, align="R")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        pdf.set_xy(rx, 20.5)
        pdf._sf(8, "light")
        pdf.set_text_color(220, 230, 245)
        pdf.cell(rw, 5, _today_long, align="R")
    else:
        # No logo: eyebrow top-left, date top-right, firm wordmark below.
        pdf.set_xy(pdf.l_margin, 7)
        pdf._sf(8.5, "semibold")
        pdf.set_text_color(*_WHITE)
        try:
            pdf.set_char_spacing(1.2)
        except Exception:
            pass
        pdf.cell(120, 5, _eyebrow)
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        pdf.set_xy(pdf.w - pdf.r_margin - 55, 7)
        pdf._sf(7.5, "light")
        pdf.set_text_color(220, 230, 245)
        pdf.cell(55, 5, _today_long, align="R")
        pdf.set_xy(pdf.l_margin, 14)
        pdf._sf(13, "bold")
        pdf.set_text_color(*_WHITE)
        pdf.cell(140, 7, _safe(pdf.firm_name))

    # ── Sidebar panel (right column) ──────────────────────────────────────
    sb_x, sb_w = 138, pdf.w - pdf.r_margin - 138
    sb_y_top   = band_h + 4
    sb_h       = 170

    pdf.set_fill_color(*_PANEL)
    pdf.rect(sb_x, sb_y_top, sb_w, sb_h, style="F")

    # Accent top stripe on sidebar
    pdf.set_fill_color(*pdf.accent_color)
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
        pdf.multi_cell(sb_w - 10, 4.2, _safe(txt))
        return pdf.get_y()

    y = sb_y_top + 5
    y = _sb_label(y, _t("underlyings", lang))

    _LOGO_H = 8.0
    _LOGO_W = 8.0
    _ROW_H  = 11.0
    for nm in asset_names:
        logo_url  = (logo_urls or {}).get(nm, "")
        sym       = (logo_tickers or {}).get(nm)
        logo_data = _load_ticker_logo(nm, logo_url, sym)
        row_y = y + 1.0
        if logo_data:
            try:
                pdf.image(io.BytesIO(logo_data), x=sb_x + 4, y=row_y,
                          w=_LOGO_W, h=_LOGO_H)
                text_x = sb_x + 4 + _LOGO_W + 2
                pdf.set_xy(text_x, row_y + (_LOGO_H - 4.5) / 2)
                pdf._sf(8.5, "semibold")
                pdf.set_text_color(*_TEXT)
                pdf.cell(sb_w - (_LOGO_W + 12), 4.5, _safe(nm))
            except Exception:
                _sb_text(y + 1, nm, "semibold", 8.5)
        else:
            _sb_text(y + 1, nm, "semibold", 8.5)
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
    pdf.multi_cell(main_w, 9, _safe(terms.name))

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

    # Executive summary bullets
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

    for txt in _exec_bullets(terms, results, bt_summary, live_data, lang):
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
    pdf.multi_cell(main_w, 4, _safe(_t("about_this_report", lang)))

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
    toc = [_t("note_terms", lang), _t("sim_summary", lang), _t("calibration", lang)]
    if bt_summary:
        toc.append(_t("backtest", lang))
    if live_data:
        toc.append(_t("live", lang))
    toc.append(_t("disclaimer_title", lang))
    for item in toc:
        pdf.set_x(pdf.l_margin)
        pdf._sf(8.5, "regular")
        pdf.set_text_color(*_TEXT)
        pdf.cell(main_w, 5.5, item, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*_RULE_LIGHT)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + main_w, pdf.get_y())

    # Micro-disclaimer at very bottom of cover
    pdf.set_xy(pdf.l_margin, pdf.h - 22)
    pdf.set_draw_color(*_HAIRLINE)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.h - 22, pdf.l_margin + main_w + sb_w + 8, pdf.h - 22)
    pdf.set_xy(pdf.l_margin, pdf.h - 20)
    pdf._sf(6, "light")
    pdf.set_text_color(*_TEXT_SOFT)
    pdf.multi_cell(0, 2.8, _safe(_t("cover_topline", lang)), align="C")

    pdf._is_cover = False
    # Re-enable auto-page-break for all content pages that follow
    pdf.set_auto_page_break(auto=True, margin=28)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def generate_pdf_report(
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
    branding: dict | None = None,
    logo_tickers: dict[str, str] | None = None,
) -> bytes:
    """
    Build the full institutional-style PDF report.

    logo_urls       — {display_name: url} for underlying ticker logos.
    issuer_logo_url — favicon / logo URL for the issuer (shown on cover).
    branding        — optional dict; see the module docstring for the full schema
                      (firm_name, primary/accent/chart_secondary colours, a
                      logo_file/logo_base64/logo_url, and report_title / website /
                      contact / footer_note content keys). Unknown keys warn and
                      malformed hex falls back to defaults.
    All optional parameters default to None; existing callers are unaffected.
    """
    # ── Resolve + validate branding ───────────────────────────────────
    _validate_branding(branding)
    primary_color, accent_color, secondary_color, firm_name = _resolve_palette(branding)
    # Local-file-first: logo_file -> logo_base64 -> logo_url
    brand_logo_bytes = _load_logo(branding)
    # Optional content keys (B5)
    _b = branding or {}
    report_title = _b.get("report_title") or None
    website      = _b.get("website", "") or ""
    contact      = _b.get("contact", "") or ""
    footer_note  = _b.get("footer_note") or None

    issuer  = getattr(terms, "issuer", "") or ""
    # Issuer logo: try a local branding/ticker_logos/{issuer}.png first, else URL.
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
    )

    # ── 1. Cover ───────────────────────────────────────────────────────────
    _cover_page(pdf, terms, results, asset_names, bt_summary, live_data, lang,
                logo_urls, issuer_logo_bytes, logo_tickers)

    # ── 2. Note terms ──────────────────────────────────────────────────────
    # First content section — always on a fresh page after the cover.
    pdf.add_page()
    pdf.section_title(_t("note_terms", lang))
    pdf.kv_table(_term_rows(terms, lang))

    pdf.subsection(_t("obs_schedule", lang))
    obs_times = terms.obs_times()
    sched     = terms.autocall_barrier_schedule()
    ac_rows = []
    for i, t_obs in enumerate(obs_times):
        eligible = _t("yes", lang) if (i + 1) >= terms.autocall_start_period else _t("no", lang)
        ac_rows.append([f"P{i+1}", f"{t_obs:.3g}", f"{sched[i]:.0%}", eligible])
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.data_table(
        [_t("period", lang), _t("time_y", lang), _t("ac_level", lang), _t("eligible", lang)],
        ac_rows,
        col_widths=[usable * 0.2, usable * 0.25, usable * 0.3, usable * 0.25],
        aligns=["L", "R", "R", "R"],
    )

    pdf.callout(_t("model_box_title", lang), _t("model_box_body", lang))

    # ── 3. Monte Carlo ─────────────────────────────────────────────────────
    # Low min_room: the metric band + first figure caption pack onto the Note
    # Terms page if there is room; figure() then moves any figure that won't fit
    # to the next page on its own. This keeps page 2 full instead of breaking
    # the whole MC block to a fresh page and leaving Note Terms half-empty.
    pdf.start_section(_t("sim_summary", lang), min_room=55.0)
    n_paths_val = int(np.asarray(results.get("annualized_returns", np.array([]))).shape[0])
    pdf.metric_band([
        (_t("expected_irr",       lang), f"{results.get('expected_irr', 0):.2%}"),
        (_t("total_return_short", lang), f"{results.get('expected_total_return', 0):.2%}"),
        (_t("prob_autocall",      lang), f"{results.get('prob_autocall', 0):.1%}"),
        (_t("prob_knock_in",      lang), f"{results.get('prob_knock_in_total', 0):.2%}"),
        (_t("n_paths",            lang), f"{n_paths_val:,}"),
    ])

    src_mc = f"{_t('src_mc', lang)}, {n_paths_val:,} {_t('paths_word', lang)}"
    _kw = dict(primary_color=primary_color, accent_color=accent_color,
               secondary_color=secondary_color)
    pdf.figure(_fig_to_png(figures.get("irr_dist"), **_kw), _t("fig_irr", lang), src_mc)
    pdf.figure(_fig_to_png(figures.get("wof_fan"),  **_kw), _t("fig_wof", lang), src_mc)

    prob_by_period = results.get("prob_autocall_by_period", [])
    if prob_by_period:
        pdf.subsection(_t("autocall_by_period", lang))
        rows = []
        for i, (t_obs, p_ac) in enumerate(zip(obs_times, prob_by_period)):
            eligible = _t("yes", lang) if (i + 1) >= terms.autocall_start_period else _t("no", lang)
            rows.append([f"P{i+1}", f"{t_obs:.3g}", f"{p_ac:.2%}", eligible])
        pdf.data_table(
            [_t("period", lang), _t("time_y", lang), _t("p_autocall", lang), _t("eligible", lang)],
            rows,
            col_widths=[usable * 0.2, usable * 0.25, usable * 0.3, usable * 0.25],
            aligns=["L", "R", "R", "R"],
        )

    # ── 4. Calibration ─────────────────────────────────────────────────────
    params = results.get("params", [])
    if params:
        pdf.start_section(_t("calibration", lang))

        # Build the calibration table.  The "Asset" column uses an inline logo +
        # name approach: we draw the table row-by-row so we can interleave the
        # small logo image at the left edge of each asset row.
        n_assets   = len(params)
        col_w_asset = usable * 0.18
        col_w_rest  = usable * 0.1025
        col_widths  = [col_w_asset] + [col_w_rest] * 8
        headers     = [_t("asset", lang), _t("calib_s0", lang), _t("calib_mu", lang),
                       _t("calib_v0", lang), _t("calib_theta", lang),
                       "kappa", "xi", "rho", _t("feller", lang)]
        aligns      = ["L"] + ["R"] * 8

        # Prefetch all logos so we know row height before drawing
        _LOGO_INLINE_W = 6.0
        _LOGO_INLINE_H = 6.0
        _ROW_H_CALIB   = 8.0   # slightly taller than the default 6 to fit logos

        logo_cache: dict[str, bytes | None] = {}
        for p in params:
            nm  = str(p.name)
            url = (logo_urls or {}).get(nm, "")
            sym = (logo_tickers or {}).get(nm)
            logo_cache[nm] = _load_ticker_logo(nm, url, sym)

        # ── Draw filled header row ──
        if pdf.get_y() > pdf.h - 55:
            pdf.add_page()
        pdf.set_fill_color(*pdf.primary_color)
        pdf.set_text_color(*_WHITE)
        pdf._sf(7.5, "semibold")
        for h, w, a in zip(headers, col_widths, aligns):
            pdf.cell(w, 7, f" {h} ", border=0, fill=True, align=a)
        pdf.ln()
        pdf.set_draw_color(*pdf.accent_color)
        pdf.set_line_width(0.25)
        pdf.line(pdf.l_margin, pdf.get_y(),
                 pdf.l_margin + sum(col_widths), pdf.get_y())
        pdf.set_text_color(*_TEXT)
        pdf._sf(8, "regular")

        for i, p in enumerate(params):
            if pdf.get_y() > pdf.h - 30:
                pdf.add_page()
                # Repeat header
                pdf.set_fill_color(*pdf.primary_color)
                pdf.set_text_color(*_WHITE)
                pdf._sf(7.5, "semibold")
                for h, w, a in zip(headers, col_widths, aligns):
                    pdf.cell(w, 7, f" {h} ", border=0, fill=True, align=a)
                pdf.ln()
                pdf.set_text_color(*_TEXT)
                pdf._sf(8, "regular")

            nm = str(p.name)
            try:
                ok, _ = p.feller_condition()
            except Exception:
                ok = False
            data_cells = [
                f"{p.S0:,.2f}", f"{p.mu * 100:.1f}%",
                f"{np.sqrt(p.V0) * 100:.1f}%", f"{np.sqrt(p.theta) * 100:.1f}%",
                f"{p.kappa:.2f}", f"{p.xi:.2f}", f"{p.rho:.2f}",
                "OK" if ok else "!",
            ]
            fill_color = _ROW_ALT if i % 2 == 0 else _WHITE
            pdf.set_fill_color(*fill_color)

            row_y = pdf.get_y()

            # ── Asset cell with inline logo ──
            pdf.set_fill_color(*fill_color)
            pdf.rect(pdf.l_margin, row_y, col_w_asset, _ROW_H_CALIB, style="F")
            ldata = logo_cache.get(nm)
            text_x = pdf.l_margin + 2
            if ldata:
                try:
                    logo_y = row_y + (_ROW_H_CALIB - _LOGO_INLINE_H) / 2
                    pdf.image(io.BytesIO(ldata),
                              x=pdf.l_margin + 1, y=logo_y,
                              w=_LOGO_INLINE_W, h=_LOGO_INLINE_H)
                    text_x = pdf.l_margin + _LOGO_INLINE_W + 3
                except Exception:
                    pass  # logo failed; just print the name
            pdf.set_xy(text_x, row_y + (_ROW_H_CALIB - 4) / 2)
            pdf._sf(8, "semibold")
            pdf.set_text_color(*_TEXT)
            avail_w = col_w_asset - (text_x - pdf.l_margin) - 1
            pdf.cell(avail_w, 4, pdf._safe(nm))

            # ── Remaining data cells ──
            pdf._sf(8, "regular")
            for cell_val, w, a in zip(data_cells, col_widths[1:], aligns[1:]):
                pdf.set_xy(pdf.get_x(), row_y)
                pdf.set_fill_color(*fill_color)
                pdf.cell(w, _ROW_H_CALIB, f" {cell_val} ", border=0, fill=True, align=a)
            pdf.ln(_ROW_H_CALIB - (pdf.get_y() - row_y))
            pdf.set_y(row_y + _ROW_H_CALIB)

        # Bottom rule
        pdf.set_draw_color(*_HAIRLINE)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, pdf.get_y(),
                 pdf.l_margin + sum(col_widths), pdf.get_y())
        pdf.ln(4)
        pdf.figure(_fig_to_png(figures.get("corr"), width=560, height=460, **_kw),
                   _t("fig_corr", lang), _t("src_hist", lang), w=105, h=86)

    # ── 5. Historical backtest ─────────────────────────────────────────────
    if bt_summary:
        pdf.start_section(_t("backtest", lang))
        pdf.metric_band([
            (_t("bt_n_issues",       lang), str(bt_summary.get("n_issues", 0))),
            (_t("bt_mean_irr",       lang), f"{bt_summary.get('mean_irr', 0):.2%}"),
            (_t("bt_median_irr",     lang), f"{bt_summary.get('median_irr', 0):.2%}"),
            (_t("bt_autocalled_pct", lang), f"{bt_summary.get('prob_called', 0):.1%}"),
            (_t("bt_knock_in_pct",   lang), f"{bt_summary.get('prob_knock_in', 0):.1%}"),
        ])
        if bt_figures:
            pdf.figure(_fig_to_png(bt_figures.get("outcome"), **_kw),
                       _t("fig_bt_outcome", lang), _t("src_hist", lang))
            pdf.figure(_fig_to_png(bt_figures.get("irr_scatter"), **_kw),
                       _t("fig_bt_irr", lang), _t("src_hist", lang))

    # ── 6. Current performance ─────────────────────────────────────────────
    if live_data:
        pdf.start_section(_t("live", lang))
        pdf.metric_band([
            (_t("live_wof_today",   lang), f"{live_data.get('wof_today', 0):.1%}"),
            (_t("live_worst_asset", lang), str(live_data.get("worst_asset", ""))),
            (_t("live_irr_to_date", lang), f"{live_data.get('irr_to_date', 0):.2%}"),
            (_t("live_elapsed",     lang), f"{live_data.get('elapsed_years', 0):.2f}"),
        ])

        perf_today = live_data.get("perf_today", {})
        if perf_today:
            pdf.subsection(_t("live_asset_perf", lang))
            _perf_logos = {
                nm: _load_ticker_logo(nm, (logo_urls or {}).get(nm, ""),
                                      (logo_tickers or {}).get(nm))
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
        if obs_rows:
            pdf.subsection(_t("live_obs_history", lang))
            obs_headers = list(obs_rows[0].keys())
            obs_data    = [[str(r.get(h, "")) for h in obs_headers] for r in obs_rows]
            n_cols = len(obs_headers)
            if n_cols == 6:
                obs_w = [usable * f for f in (0.08, 0.13, 0.37, 0.14, 0.13, 0.15)]
            else:
                obs_w = [usable / n_cols] * n_cols
            pdf.data_table(obs_headers, obs_data, col_widths=obs_w,
                           aligns=["L"] * n_cols)

        pdf.figure(_fig_to_png(live_figure, **_kw), _t("fig_live", lang), _t("src_hist", lang))

    # ── 7. Disclaimers ─────────────────────────────────────────────────────
    # The full legal block is ~80mm tall; only break if it would otherwise be
    # split awkwardly. Flowing it after the previous section avoids a near-empty
    # page before the disclaimer.
    pdf.start_section(_t("disclaimer_title", lang), min_room=90.0)
    pdf._sf(7.5, "regular")
    pdf.set_text_color(*_TEXT_SOFT)
    for para in _t("disclaimer_body", lang).split("\n\n"):
        pdf.multi_cell(0, 3.8, _safe(para))
        pdf.ln(2.5)
    pdf.set_text_color(*_TEXT)

    return bytes(pdf.output())
