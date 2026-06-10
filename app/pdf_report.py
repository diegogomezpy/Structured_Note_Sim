"""
app/pdf_report.py
-----------------
PDF report generator for the Structured Note Simulator.

Public API
----------
generate_pdf_report(terms, results, asset_names, figures, lang) -> bytes
"""

from __future__ import annotations

import io
import datetime
import numpy as np
from fpdf import FPDF

# ──────────────────────────────────────────────────────────────────────────────
# Colour palette (matching app theme)
# ──────────────────────────────────────────────────────────────────────────────
_GREEN_DARK   = (26,  107, 26)    # #1a6b1a
_GREEN_LIGHT  = (198, 239, 198)   # light green for alt rows
_WHITE        = (255, 255, 255)
_LIGHT_GREY   = (245, 245, 245)
_MID_GREY     = (170, 170, 170)
_TEXT_DARK    = (30,  30,  30)

# ──────────────────────────────────────────────────────────────────────────────
# Translations
# ──────────────────────────────────────────────────────────────────────────────
_LABELS: dict[str, dict[str, str]] = {
    "report_title":          {"en": "Structured Note Report",           "es": "Informe de Nota Estructurada"},
    "generated":             {"en": "Generated",                        "es": "Generado"},
    "note_terms":            {"en": "Note Terms",                       "es": "Términos de la Nota"},
    "sim_summary":           {"en": "Simulation Summary",               "es": "Resumen de Simulación"},
    "autocall_by_period":    {"en": "Autocall Probability by Period",   "es": "Probabilidad de Autocall por Período"},
    "irr_dist":              {"en": "IRR Distribution",                 "es": "Distribución de TIR"},
    "wof_fan":               {"en": "Worst-of Fan Chart",               "es": "Gráfico de Abanico Worst-of"},
    "corr_heatmap":          {"en": "Correlation Heatmap",              "es": "Mapa de Calor de Correlaciones"},
    "heston_params":         {"en": "Heston Parameters",               "es": "Parámetros de Heston"},
    "underlyings":           {"en": "Underlyings",                      "es": "Subyacentes"},
    # Term labels
    "maturity":              {"en": "Maturity",                         "es": "Vencimiento"},
    "freq":                  {"en": "Payment Frequency",                "es": "Frecuencia de Pago"},
    "coupon_pa":             {"en": "Coupon p.a.",                      "es": "Cupón anual"},
    "coupon_barrier":        {"en": "Coupon Barrier",                   "es": "Barrera de Cupón"},
    "autocall_barrier":      {"en": "Autocall Barrier",                 "es": "Barrera de Autocall"},
    "ki_barrier":            {"en": "Knock-in Barrier",                 "es": "Barrera Knock-in"},
    "memory":                {"en": "Memory",                           "es": "Memoria"},
    "coupon_basket":         {"en": "Coupon Basket",                    "es": "Cesta de Cupón"},
    "autocall_basket":       {"en": "Autocall Basket",                  "es": "Cesta de Autocall"},
    "final_basket":          {"en": "Final Basket",                     "es": "Cesta Final"},
    # Simulation labels
    "expected_irr":          {"en": "Expected IRR p.a. (simple)",       "es": "TIR Esperada anual (simple)"},
    "expected_total_return": {"en": "Expected Total Return",            "es": "Retorno Total Esperado"},
    "expected_coupon":       {"en": "Expected Coupon",                  "es": "Cupón Esperado"},
    "prob_autocall":         {"en": "P(Autocall)",                      "es": "P(Autocall)"},
    "prob_knock_in":         {"en": "P(Knock-in)",                      "es": "P(Knock-in)"},
    "n_paths":               {"en": "Paths",                            "es": "Caminos"},
    "seed":                  {"en": "Seed",                             "es": "Semilla"},
    # Autocall table
    "period":                {"en": "Period",                           "es": "Período"},
    "time_y":                {"en": "Time (Y)",                         "es": "Tiempo (A)"},
    "p_autocall":            {"en": "P(autocall)",                      "es": "P(autocall)"},
    "eligible":              {"en": "Eligible",                         "es": "Elegible"},
    "yes":                   {"en": "Yes",                              "es": "Sí"},
    "no":                    {"en": "No",                               "es": "No"},
    # Heston table
    "asset":                 {"en": "Asset",                            "es": "Activo"},
    "feller":                {"en": "Feller",                           "es": "Feller"},
}


def _t(key: str, lang: str) -> str:
    return _LABELS.get(key, {}).get(lang, _LABELS.get(key, {}).get("en", key))


# ──────────────────────────────────────────────────────────────────────────────
# FPDF subclass with helpers
# ──────────────────────────────────────────────────────────────────────────────

class _NotePDF(FPDF):
    """FPDF2 document with branded header bar and convenience helpers."""

    def __init__(self, lang: str = "en"):
        super().__init__()
        self.lang = lang
        self.set_auto_page_break(auto=True, margin=18)

    # ------------------------------------------------------------------
    # Page header / footer
    # ------------------------------------------------------------------
    def header(self):
        # Dark green bar at the top
        self.set_fill_color(*_GREEN_DARK)
        self.rect(0, 0, self.w, 14, "F")
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*_WHITE)
        self.set_xy(10, 2)
        self.cell(0, 10, _t("report_title", self.lang))
        self.set_text_color(*_TEXT_DARK)
        self.ln(18)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_MID_GREY)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")
        self.set_text_color(*_TEXT_DARK)

    # ------------------------------------------------------------------
    # Section heading
    # ------------------------------------------------------------------
    def section_title(self, text: str):
        self.set_fill_color(*_GREEN_DARK)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, f"  {text}", ln=True, fill=True)
        self.set_text_color(*_TEXT_DARK)
        self.ln(2)

    # ------------------------------------------------------------------
    # Two-column key-value table
    # ------------------------------------------------------------------
    def kv_table(self, rows: list[tuple[str, str]], col_w: tuple[float, float] = (80, 100)):
        self.set_font("Helvetica", "", 9)
        for i, (k, v) in enumerate(rows):
            fill_color = _LIGHT_GREY if i % 2 == 0 else _WHITE
            self.set_fill_color(*fill_color)
            self.set_font("Helvetica", "B", 9)
            self.cell(col_w[0], 7, f"  {k}", border=0, fill=True)
            self.set_font("Helvetica", "", 9)
            self.cell(col_w[1], 7, f"  {v}", border=0, fill=True, ln=True)
        self.ln(3)

    # ------------------------------------------------------------------
    # Generic multi-column table
    # ------------------------------------------------------------------
    def data_table(
        self,
        headers: list[str],
        rows: list[list[str]],
        col_widths: list[float] | None = None,
    ):
        n = len(headers)
        if col_widths is None:
            usable = self.w - self.l_margin - self.r_margin
            col_widths = [usable / n] * n

        # Header row
        self.set_fill_color(*_GREEN_DARK)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 8)
        for h, w in zip(headers, col_widths):
            self.cell(w, 7, f"  {h}", border=0, fill=True)
        self.ln()
        self.set_text_color(*_TEXT_DARK)

        # Data rows
        self.set_font("Helvetica", "", 8)
        for i, row in enumerate(rows):
            fill_color = _LIGHT_GREY if i % 2 == 0 else _WHITE
            self.set_fill_color(*fill_color)
            for cell_val, w in zip(row, col_widths):
                self.cell(w, 6.5, f"  {str(cell_val)}", border=0, fill=True)
            self.ln()
        self.ln(3)

    # ------------------------------------------------------------------
    # Embedded image from bytes
    # ------------------------------------------------------------------
    def embed_image(self, img_bytes: bytes, w: float = 180, h: float = 90):
        buf = io.BytesIO(img_bytes)
        x = (self.w - w) / 2
        self.image(buf, x=x, w=w, h=h)
        self.ln(4)


# ──────────────────────────────────────────────────────────────────────────────
# Figure export helper
# ──────────────────────────────────────────────────────────────────────────────

def _fig_to_png(fig, width: int = 700, height: int = 350) -> bytes | None:
    """Export a Plotly figure to PNG bytes. Returns None on failure."""
    try:
        import plotly.io as pio
        return pio.to_image(fig, format="png", width=width, height=height, engine="kaleido")
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def generate_pdf_report(
    terms,
    results: dict,
    asset_names: list[str],
    figures: dict,
    lang: str = "en",
) -> bytes:
    """
    Build a PDF report for a completed Monte Carlo simulation and return raw bytes.

    Parameters
    ----------
    terms       : NoteTerms instance
    results     : st.session_state["results"]
    asset_names : list of display names for the underlyings
    figures     : dict with keys "irr_dist", "wof_fan", "corr" (go.Figure values)
    lang        : "en" or "es"
    """
    pdf = _NotePDF(lang=lang)
    pdf.add_page()

    # ── 1. Header info block ───────────────────────────────────────────────
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 9, terms.name, ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"{_t('underlyings', lang)}: {', '.join(asset_names)}", ln=True)
    pdf.cell(0, 6, f"{_t('generated', lang)}: {now_str}", ln=True)
    pdf.ln(4)

    # ── 2. Note Terms table ────────────────────────────────────────────────
    pdf.section_title(_t("note_terms", lang))
    term_rows = [
        (_t("maturity",         lang), f"{terms.maturity}Y"),
        (_t("freq",             lang), terms.payment_freq.capitalize()),
        (_t("coupon_pa",        lang), f"{terms.coupon_pa * 100:.2f}%"),
        (_t("coupon_barrier",   lang), f"{terms.coupon_barrier:.0%}"),
        (_t("autocall_barrier", lang), f"{terms.autocall_barrier:.0%}"),
        (_t("ki_barrier",       lang), f"{terms.knock_in_barrier:.0%}"),
        (_t("memory",           lang), _t("yes", lang) if terms.memory else _t("no", lang)),
        (_t("coupon_basket",    lang), terms.coupon_basket.replace("_", "-")),
        (_t("autocall_basket",  lang), terms.autocall_basket.replace("_", "-")),
        (_t("final_basket",     lang), terms.final_basket.replace("_", "-")),
    ]
    pdf.kv_table(term_rows)

    # ── 3. Simulation Summary table ────────────────────────────────────────
    pdf.section_title(_t("sim_summary", lang))
    n_paths_val = int(results.get("annualized_returns", np.array([])).shape[0])
    sim_rows = [
        (_t("expected_irr",          lang), f"{results.get('expected_irr', 0):.2%}"),
        (_t("expected_total_return", lang), f"{results.get('expected_total_return', 0):.2%}"),
        (_t("expected_coupon",       lang), f"{results.get('expected_coupon', 0):.2%}"),
        (_t("prob_autocall",         lang), f"{results.get('prob_autocall', 0):.2%}"),
        (_t("prob_knock_in",         lang), f"{results.get('prob_knock_in_total', 0):.2%}"),
        (_t("n_paths",               lang), f"{n_paths_val:,}"),
    ]
    pdf.kv_table(sim_rows)

    # ── 4. Autocall probability by period ──────────────────────────────────
    pdf.section_title(_t("autocall_by_period", lang))
    prob_by_period = results.get("prob_autocall_by_period", [])
    obs_times = terms.obs_times()
    ac_headers = [
        _t("period",    lang),
        _t("time_y",    lang),
        _t("p_autocall", lang),
        _t("eligible",  lang),
    ]
    ac_rows = []
    for i, (t_obs, p_ac) in enumerate(zip(obs_times, prob_by_period)):
        eligible = _t("yes", lang) if (i + 1) >= terms.autocall_start_period else _t("no", lang)
        ac_rows.append([f"P{i+1}", f"{t_obs:.3g}", f"{p_ac:.2%}", eligible])
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.data_table(ac_headers, ac_rows, col_widths=[usable * 0.15, usable * 0.2, usable * 0.35, usable * 0.3])

    # ── 5. IRR Distribution chart ──────────────────────────────────────────
    _irr_fig = figures.get("irr_dist")
    if _irr_fig is not None:
        pdf.add_page()
        pdf.section_title(_t("irr_dist", lang))
        img = _fig_to_png(_irr_fig, width=700, height=350)
        if img is not None:
            pdf.embed_image(img, w=180, h=90)

    # ── 6. Worst-of Fan Chart ──────────────────────────────────────────────
    _wof_fig = figures.get("wof_fan")
    if _wof_fig is not None:
        pdf.section_title(_t("wof_fan", lang))
        img = _fig_to_png(_wof_fig, width=700, height=350)
        if img is not None:
            pdf.embed_image(img, w=180, h=90)

    # ── 7. Correlation heatmap ─────────────────────────────────────────────
    _corr_fig = figures.get("corr")
    if _corr_fig is not None:
        pdf.section_title(_t("corr_heatmap", lang))
        img = _fig_to_png(_corr_fig, width=500, height=400)
        if img is not None:
            pdf.embed_image(img, w=120, h=96)

    # ── 8. Heston Parameters table ─────────────────────────────────────────
    params = results.get("params", [])
    if params:
        pdf.add_page()
        pdf.section_title(_t("heston_params", lang))
        hp_headers = [
            _t("asset", lang), "S0", "mu", "V0 sigma",
            "theta sLR", "kappa", "xi", "rho", _t("feller", lang),
        ]
        hp_rows = []
        for p in params:
            try:
                ok, _ = p.feller_condition()
            except Exception:
                ok = False
            hp_rows.append([
                str(p.name),
                f"{p.S0:.1f}",
                f"{p.mu * 100:.1f}%",
                f"{np.sqrt(p.V0) * 100:.1f}%",
                f"{np.sqrt(p.theta) * 100:.1f}%",
                f"{p.kappa:.3f}",
                f"{p.xi:.3f}",
                f"{p.rho:.3f}",
                "OK" if ok else "warn",
            ])
        usable = pdf.w - pdf.l_margin - pdf.r_margin
        pdf.data_table(
            hp_headers, hp_rows,
            col_widths=[
                usable * 0.14, usable * 0.09, usable * 0.09,
                usable * 0.10, usable * 0.10, usable * 0.09,
                usable * 0.09, usable * 0.09, usable * 0.11,
            ],
        )

    return bytes(pdf.output())
