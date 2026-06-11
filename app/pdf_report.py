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
                    logo_bytes, issuer_logo_bytes,
                    branding=None) -> bytes

Branding dict schema (all keys optional):
  {
    "firm_name":     "Acme Capital",
    "primary_color": "#003366",
    "accent_color":  "#00A0DC",
    "logo_url":      "https://..."
  }
"""

from __future__ import annotations

import io
import datetime
import urllib.request
import numpy as np
from pathlib import Path
from fpdf import FPDF

_FONT_DIR  = Path(__file__).parent.parent / "fonts"
_INTER_TTC = _FONT_DIR / "Inter.ttc"

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


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' to (R, G, B) integer tuple."""
    h = hex_str.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _resolve_palette(branding: dict | None) -> tuple[
    tuple[int, int, int], tuple[int, int, int], str
]:
    """Return (primary_color, accent_color, firm_name) from branding dict."""
    if not branding:
        return _DEFAULT_PRIMARY, _DEFAULT_ACCENT, "Structured Note Analytics"
    primary = _hex_to_rgb(branding["primary_color"]) if branding.get("primary_color") else _DEFAULT_PRIMARY
    accent  = _hex_to_rgb(branding["accent_color"])  if branding.get("accent_color")  else _DEFAULT_ACCENT
    firm    = branding.get("firm_name", "Structured Note Analytics") or "Structured Note Analytics"
    return primary, accent, firm


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
# TTC indices used from Inter.ttc:
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
                 firm_logo_bytes: bytes | None = None):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.lang          = lang
        self.issuer        = issuer
        self.doc_ref       = doc_ref
        self.primary_color = primary_color
        self.accent_color  = accent_color
        self.firm_name     = firm_name
        self.firm_logo_bytes = firm_logo_bytes
        self._is_cover     = False
        self._fig_no       = 0
        self._gen_dt       = datetime.datetime.now().strftime("%d %b %Y  %H:%M")
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(auto=True, margin=28)
        self.alias_nb_pages()
        self._use_inter = _register_inter(self)

    # ------------------------------------------------------------------
    # Font helpers
    # ------------------------------------------------------------------
    def _sf(self, size: float, weight: str = "regular") -> None:
        """Set font by semantic weight."""
        if self._use_inter:
            _map = {
                "regular":    ("Inter",      ""),
                "bold":       ("Inter",      "B"),
                "bold_italic":("Inter",      "BI"),
                "italic":     ("Inter",      "I"),
                "semibold":   ("InterSB",    ""),
                "light":      ("InterLight", ""),
            }
            family, style = _map.get(weight, ("Inter", ""))
            self.set_font(family, style, size)
        else:
            _hmap = {
                "regular":    ("Helvetica", ""),
                "bold":       ("Helvetica", "B"),
                "bold_italic":("Helvetica", "BI"),
                "italic":     ("Helvetica", "I"),
                "semibold":   ("Helvetica", "B"),
                "light":      ("Helvetica", ""),
            }
            family, style = _hmap.get(weight, ("Helvetica", ""))
            self.set_font(family, style, size)

    def _safe(self, text: object) -> str:
        return _safe(text, latin1=not self._use_inter)

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

        # ── Firm logo (top-left) ─────────────────────────────────────
        logo_w = 0.0
        if self.firm_logo_bytes:
            try:
                self.image(io.BytesIO(self.firm_logo_bytes),
                           x=self.l_margin, y=8, w=8, h=8)
                logo_w = 10.0
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
        # ── Thin rule above footer ────────────────────────────────────
        self.set_draw_color(*_HAIRLINE)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.h - 22, self.w - self.r_margin, self.h - 22)

        # ── Disclaimer line ───────────────────────────────────────────
        self.set_y(-20)
        self._sf(6, "light")
        self.set_text_color(*_TEXT_SOFT)
        self.multi_cell(0, 2.9, _t("footer_line", self.lang), align="L")

        # ── Page number + generation datetime ────────────────────────
        self.set_y(-11)
        self._sf(6.5, "light")
        self.set_text_color(*_TEXT_SOFT)
        self.cell(0, 4.5, self._safe(self._gen_dt), align="L")
        self.set_y(-11)
        self.cell(0, 4.5, f"Page {self.page_no()} of {{nb}}", align="R")
        self.set_text_color(*_TEXT)

    # ------------------------------------------------------------------
    # Building blocks
    # ------------------------------------------------------------------
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
        self.cell(5, 5, "•" if self._use_inter else chr(149))
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
               w: float = 172, h: float = 80):
        if img_bytes is None:
            return
        self._fig_no += 1
        needed = h + 18
        if self.get_y() + needed > self.h - 28:
            self.add_page()
        # Caption above figure — SemiBold 8.5pt in accent color
        self._sf(8.5, "semibold")
        self.set_text_color(*self.accent_color)
        self.multi_cell(0, 4.5, f"Figure {self._fig_no}: {caption}", align="C")
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

def _fetch_image_bytes(url: str, timeout: int = 5) -> bytes | None:
    """Download an image from a URL. Returns raw bytes or None on failure."""
    if not url:
        return None
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; PDF-report/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Figure export helper
# ──────────────────────────────────────────────────────────────────────────────

def _fig_to_png(fig, width: int = 900, height: int = 420) -> bytes | None:
    try:
        import plotly.io as pio
        import plotly.graph_objects as go
        fig = go.Figure(fig)
        fig.update_layout(title=None, margin=dict(t=24, b=40))
        return pio.to_image(fig, format="png", width=width, height=height,
                            scale=2, engine="kaleido")
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Page builders
# ──────────────────────────────────────────────────────────────────────────────

def _term_rows(terms, lang: str) -> list[tuple[str, str]]:
    rows = [
        (_t("maturity",         lang), f"{terms.maturity:g}Y ({terms.n_obs} observations, {terms.payment_freq})"),
        (_t("coupon_pa",        lang), f"{terms.coupon_pa * 100:.2f}%  ({terms.coupon_rate * 100:.4f}% per period)"),
        (_t("coupon_barrier",   lang), f"{terms.coupon_barrier:.1%}" if terms.coupon_barrier > 0 else
                                       ("Guaranteed (0%)" if lang == "en" else "Garantizado (0%)")),
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
                     f"{_t('yes', lang)} ({terms.coupon_pa * 100:.2f}% p.a.)"))
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
):
    pdf._is_cover = True
    pdf.add_page()

    # ── Full-width colored top band ───────────────────────────────────────
    band_h = _COVER_BAND_H
    pdf.set_fill_color(*pdf.primary_color)
    pdf.rect(0, 0, pdf.w, band_h, style="F")

    # Firm logo (top-left in band)
    logo_x = pdf.l_margin
    if pdf.firm_logo_bytes:
        try:
            pdf.image(io.BytesIO(pdf.firm_logo_bytes),
                      x=logo_x, y=(band_h - 9) / 2, w=9, h=9)
            logo_x += 12
        except Exception:
            pass

    # Report title (white, in band)
    pdf.set_xy(logo_x, 7)
    pdf._sf(8.5, "semibold")
    pdf.set_text_color(*_WHITE)
    try:
        pdf.set_char_spacing(1.2)
    except Exception:
        pass
    pdf.cell(140, 5, _t("report_eyebrow", lang).upper())
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass

    # Generation date (right-aligned in band)
    pdf.set_xy(pdf.w - pdf.r_margin - 55, 7)
    pdf._sf(7.5, "light")
    pdf.set_text_color(220, 230, 245)
    pdf.cell(55, 5, datetime.date.today().strftime("%-d %B %Y"), align="R")

    # Firm name (second line in band)
    pdf.set_xy(logo_x, 14)
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
        logo_data = _fetch_image_bytes(logo_url) if logo_url else None
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
        (_t("maturity", lang),        f"{terms.maturity:g}Y {terms.payment_freq}"),
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

    # Report type subtitle
    pdf.set_x(pdf.l_margin)
    pdf._sf(9.5, "light")
    pdf.set_text_color(*_TEXT_SOFT)
    pdf.cell(main_w, 6, _safe(_t("series_title", lang)),
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
        pdf.cell(5, 5.5, "•" if pdf._use_inter else chr(149))
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
    pdf.cell(main_w, 5, ("ABOUT THIS REPORT" if lang == "en" else "ACERCA DE ESTE INFORME"),
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
) -> bytes:
    """
    Build the full institutional-style PDF report.

    logo_urls       — {display_name: url} for underlying ticker logos.
    issuer_logo_url — favicon / logo URL for the issuer (shown on cover).
    branding        — optional dict with firm_name, primary_color, accent_color,
                      logo_url. See module docstring for full schema.
    All optional parameters default to None; existing callers are unaffected.
    """
    # ── Resolve branding ──────────────────────────────────────────────
    primary_color, accent_color, firm_name = _resolve_palette(branding)
    brand_logo_bytes = None
    if branding and branding.get("logo_url"):
        brand_logo_bytes = _fetch_image_bytes(branding["logo_url"])

    issuer_logo_bytes = _fetch_image_bytes(issuer_logo_url) if issuer_logo_url else None

    issuer  = getattr(terms, "issuer", "") or ""
    doc_ref = f"{_t('series_title', lang)} | {terms.name}"
    pdf = _NotePDF(
        lang            = lang,
        issuer          = issuer,
        doc_ref         = doc_ref,
        primary_color   = primary_color,
        accent_color    = accent_color,
        firm_name       = firm_name,
        firm_logo_bytes = brand_logo_bytes,
    )

    # ── 1. Cover ───────────────────────────────────────────────────────────
    _cover_page(pdf, terms, results, asset_names, bt_summary, live_data, lang,
                logo_urls, issuer_logo_bytes)

    # ── 2. Note terms ──────────────────────────────────────────────────────
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
    pdf.add_page()
    pdf.section_title(_t("sim_summary", lang))
    n_paths_val = int(np.asarray(results.get("annualized_returns", np.array([]))).shape[0])
    pdf.metric_band([
        (_t("expected_irr",       lang), f"{results.get('expected_irr', 0):.2%}"),
        (_t("total_return_short", lang), f"{results.get('expected_total_return', 0):.2%}"),
        (_t("prob_autocall",      lang), f"{results.get('prob_autocall', 0):.1%}"),
        (_t("prob_knock_in",      lang), f"{results.get('prob_knock_in_total', 0):.2%}"),
        (_t("n_paths",            lang), f"{n_paths_val:,}"),
    ])

    src_mc = f"{_t('src_mc', lang)}, {n_paths_val:,} paths"
    pdf.figure(_fig_to_png(figures.get("irr_dist")), _t("fig_irr", lang), src_mc)
    pdf.figure(_fig_to_png(figures.get("wof_fan")),  _t("fig_wof", lang), src_mc)

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
        pdf.add_page()
        pdf.section_title(_t("calibration", lang))

        logo_strip_y = pdf.get_y()
        n_assets = len(params)
        strip_w  = usable / max(n_assets, 1)
        any_logo = False
        for i, p in enumerate(params):
            nm    = str(p.name)
            url   = (logo_urls or {}).get(nm, "")
            ldata = _fetch_image_bytes(url) if url else None
            cx    = pdf.l_margin + i * strip_w + (strip_w - 10) / 2
            if ldata:
                try:
                    pdf.image(io.BytesIO(ldata), x=cx, y=logo_strip_y, w=10, h=10)
                    any_logo = True
                except Exception:
                    pass
        if any_logo:
            pdf.set_y(logo_strip_y + 12)
        else:
            pdf.set_y(logo_strip_y)

        hp_rows = []
        for p in params:
            try:
                ok, _ = p.feller_condition()
            except Exception:
                ok = False
            hp_rows.append([
                str(p.name), f"{p.S0:,.2f}", f"{p.mu * 100:.1f}%",
                f"{np.sqrt(p.V0) * 100:.1f}%", f"{np.sqrt(p.theta) * 100:.1f}%",
                f"{p.kappa:.2f}", f"{p.xi:.2f}", f"{p.rho:.2f}",
                "OK" if ok else "!",
            ])
        pdf.data_table(
            [_t("asset", lang), "S0", "mu p.a.", "Vol (V0)", "Vol (theta)",
             "kappa", "xi", "rho", _t("feller", lang)],
            hp_rows,
            col_widths=[usable * 0.18] + [usable * 0.1025] * 8,
        )
        pdf.figure(_fig_to_png(figures.get("corr"), width=560, height=460),
                   _t("fig_corr", lang), _t("src_hist", lang), w=105, h=86)

    # ── 5. Historical backtest ─────────────────────────────────────────────
    if bt_summary:
        pdf.add_page()
        pdf.section_title(_t("backtest", lang))
        pdf.metric_band([
            (_t("bt_n_issues",       lang), str(bt_summary.get("n_issues", 0))),
            (_t("bt_mean_irr",       lang), f"{bt_summary.get('mean_irr', 0):.2%}"),
            (_t("bt_median_irr",     lang), f"{bt_summary.get('median_irr', 0):.2%}"),
            (_t("bt_autocalled_pct", lang), f"{bt_summary.get('prob_called', 0):.1%}"),
            (_t("bt_knock_in_pct",   lang), f"{bt_summary.get('prob_knock_in', 0):.1%}"),
        ])
        if bt_figures:
            pdf.figure(_fig_to_png(bt_figures.get("outcome")),
                       _t("fig_bt_outcome", lang), _t("src_hist", lang))
            pdf.figure(_fig_to_png(bt_figures.get("irr_scatter")),
                       _t("fig_bt_irr", lang), _t("src_hist", lang))

    # ── 6. Current performance ─────────────────────────────────────────────
    if live_data:
        pdf.add_page()
        pdf.section_title(_t("live", lang))
        pdf.metric_band([
            (_t("live_wof_today",   lang), f"{live_data.get('wof_today', 0):.1%}"),
            (_t("live_worst_asset", lang), str(live_data.get("worst_asset", ""))),
            (_t("live_irr_to_date", lang), f"{live_data.get('irr_to_date', 0):.2%}"),
            (_t("live_elapsed",     lang), f"{live_data.get('elapsed_years', 0):.2f}"),
        ])

        perf_today = live_data.get("perf_today", {})
        if perf_today:
            pdf.subsection(_t("live_asset_perf", lang))
            pdf.data_table(
                [_t("asset", lang), _t("performance", lang)],
                [[name, f"{perf:.2%}"] for name, perf in perf_today.items()],
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

        pdf.figure(_fig_to_png(live_figure), _t("fig_live", lang), _t("src_hist", lang))

    # ── 7. Disclaimers ─────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title(_t("disclaimer_title", lang))
    pdf._sf(7.5, "regular")
    pdf.set_text_color(*_TEXT_SOFT)
    for para in _t("disclaimer_body", lang).split("\n\n"):
        pdf.multi_cell(0, 3.8, _safe(para))
        pdf.ln(2.5)
    pdf.set_text_color(*_TEXT)

    return bytes(pdf.output())
