"""
app/app.py  —  Streamlit entry point.
Run with:  streamlit run app/app.py
"""

import os
import random
import sys
import pathlib

_ROOT = pathlib.Path(__file__).parent.parent
_APP  = pathlib.Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

# ── Path-count ceiling ───────────────────────────────────────────────────────
# The MC peak memory scales with n_paths × n_steps × n_assets. On Streamlit
# Community Cloud (~1 GB), a 50K-path 5Y note can OOM-kill the container. Cap
# the slider on the hosted instance; allow the full range locally.
# Override explicitly with the SNSIM_MAX_PATHS env var (set it in the app's
# "Advanced settings → Secrets/env" on Streamlit Cloud to tune the ceiling).
_ON_STREAMLIT_CLOUD = os.getcwd().startswith("/mount/src") or "STREAMLIT_CLOUD" in os.environ
_MAX_PATHS = int(os.environ.get("SNSIM_MAX_PATHS", 15000 if _ON_STREAMLIT_CLOUD else 50000))

import numpy as np
import pandas as pd
import streamlit as st

from core            import NoteTerms, price_note, replay_note
from core.calibrator import HestonCalibrator
from core.simulator  import HestonMultiSimulator
from core.backtest   import run_backtest, snapped_obs_dates
from data.loader     import load_prices, load_dividends, build_dividend_schedule

from translations import Translator
from charts import (
    build_irr_distribution, build_fan_chart, build_wof_fan,
    build_path_price_chart, build_path_wof_chart, build_corr_heatmap,
    build_backtest_outcome_bar, build_worst_asset_pie,
    build_backtest_irr_scatter, build_historical_prices,
    build_historical_wof_path, build_live_performance_chart,
)

# ==========================================================================
# Page config
# ==========================================================================
st.set_page_config(
    page_title = "Structured Note Simulator",
    page_icon  = ":chart_with_upwards_trend:",
    layout     = "wide",
)

# ── Institutional CSS theme (IBM Plex Sans + navy/blue, matches PDF report) ──
_CSS_PATH = _APP / "style.css"
try:
    _css = _CSS_PATH.read_text()
    st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)
except Exception:
    pass

# ==========================================================================
# Issuer logo helper
# ==========================================================================
_ISSUER_DOMAINS = {
    "bbva":             "bbva.com",
    "hsbc":             "hsbc.com",
    "bnp":              "bnpparibas.com",
    "bnp paribas":      "bnpparibas.com",
    "barclays":         "barclays.com",
    "deutsche bank":    "db.com",
    "societe generale": "societegenerale.com",
    "ubs":              "ubs.com",
    "credit suisse":    "credit-suisse.com",
    "jpmorgan":         "jpmorgan.com",
    "jp morgan":        "jpmorgan.com",
    "goldman sachs":    "goldmansachs.com",
    "morgan stanley":   "morganstanley.com",
    "citi":             "citi.com",
    "citigroup":        "citi.com",
    "unicredit":        "unicredit.eu",
    "intesa":           "intesasanpaolo.com",
    "natixis":          "natixis.com",
    "ing":              "ing.com",
    "rabobank":         "rabobank.com",
    "commerzbank":      "commerzbank.com",
}


def get_issuer_logo_url(issuer: str) -> str | None:
    """Return a favicon URL for a known structured note issuer, or None if issuer is empty."""
    if not issuer:
        return None
    key    = issuer.strip().lower()
    domain = _ISSUER_DOMAINS.get(key) or f"{key.replace(' ', '')}.com"
    return f"https://www.google.com/s2/favicons?sz=64&domain={domain}"


# ==========================================================================
# Available underlyings
# ==========================================================================
UNDERLYING_OPTIONS = {
    # ── Equity indices — US ──────────────────────────────────────────────
    "SPX — S&P 500":            "^GSPC",
    "NDX — Nasdaq 100":         "^NDX",
    "RUT — Russell 2000":       "^RUT",
    # ── Equity indices — Europe ──────────────────────────────────────────
    "SX5E — Euro Stoxx 50":     "^STOXX50E",
    "DAX — DAX 40":             "^GDAXI",
    "FTSE — FTSE 100":          "^FTSE",
    "CAC — CAC 40":             "^FCHI",
    "SMI — Swiss Market":       "^SSMI",
    "IBEX — Spain":             "^IBEX",
    "MIB — Italy":              "FTSEMIB.MI",
    # ── Equity indices — Asia / EM ───────────────────────────────────────
    "NKY — Nikkei 225":         "^N225",
    "HSI — Hang Seng":          "^HSI",
    "KOSPI — Korea":            "^KS11",
    "ASX — Australia":          "^AXJO",
    "TWII — Taiwan":            "^TWII",
    "NSEI — India Nifty 50":    "^NSEI",
    "STI — Singapore":          "^STI",
    "BVSP — Brazil Bovespa":    "^BVSP",
    "MXX — Mexico IPC":         "^MXX",
    # ── US Banks & Financials ────────────────────────────────────────────
    "GS — Goldman Sachs":       "GS",
    "JPM — J.P. Morgan":        "JPM",
    "MS — Morgan Stanley":      "MS",
    "BAC — Bank of America":    "BAC",
    "C — Citigroup":            "C",
    "WFC — Wells Fargo":        "WFC",
    "BLK — BlackRock":          "BLK",
    "SCHW — Charles Schwab":    "SCHW",
    "V — Visa":                 "V",
    "MA — Mastercard":          "MA",
    # ── US Tech ─────────────────────────────────────────────────────────
    "AAPL — Apple":             "AAPL",
    "MSFT — Microsoft":         "MSFT",
    "NVDA — NVIDIA":            "NVDA",
    "AMZN — Amazon":            "AMZN",
    "META — Meta":              "META",
    "GOOGL — Alphabet":         "GOOGL",
    "TSLA — Tesla":             "TSLA",
    "AVGO — Broadcom":          "AVGO",
    "PLTR — Palantir":          "PLTR",
    "AMD — AMD":                "AMD",
    "INTC — Intel":             "INTC",
    "CRM — Salesforce":         "CRM",
    "NFLX — Netflix":           "NFLX",
    "SPOT — Spotify":           "SPOT",
    "UBER — Uber":              "UBER",
    # ── US Healthcare & Other ────────────────────────────────────────────
    "LLY — Eli Lilly":          "LLY",
    "UNH — UnitedHealth":       "UNH",
    "BRK-B — Berkshire":        "BRK-B",
    # ── European stocks ──────────────────────────────────────────────────
    "ASML — ASML":              "ASML",
    "SAP — SAP":                "SAP",
    "NVO — Novo Nordisk":       "NVO",
    "AZN — AstraZeneca":        "AZN",
    "SHEL — Shell":             "SHEL",
    "NESN — Nestlé":            "NESN.SW",
    "NOVN — Novartis":          "NOVN.SW",
    "ROG — Roche":              "ROG.SW",
    "SIE — Siemens":            "SIE.DE",
    "AIR — Airbus":             "AIR.PA",
    "TTE — TotalEnergies":      "TTE.PA",
    "BNP — BNP Paribas":        "BNP.PA",
    "MC — LVMH":                "MC.PA",
    "OR — L'Oréal":             "OR.PA",
    "SAN — Santander":          "SAN.MC",
    # ── Commodities & Equity ETFs ────────────────────────────────────────
    "GLD — Gold ETF":           "GLD",
    "SLV — Silver ETF":         "SLV",
    "GDX — Gold Miners ETF":    "GDX",
    "USO — Oil ETF":            "USO",
    "XLE — Energy ETF":         "XLE",
    "XLF — Financials ETF":     "XLF",
    "EEM — EM ETF":             "EEM",
    "ARKK — ARK Innovation":    "ARKK",
    # ── Fixed Income ETFs ────────────────────────────────────────────────
    "TLT — 20Y Treasury ETF":   "TLT",
    "IEF — 7-10Y Treasury ETF": "IEF",
    "HYG — High Yield ETF":     "HYG",
    "LQD — Investment Grade ETF": "LQD",
    # ── Crypto ETFs ──────────────────────────────────────────────────────
    "IBIT — iShares Bitcoin ETF": "IBIT",
    "FBTC — Fidelity Bitcoin ETF": "FBTC",
}
UNDERLYING_LABELS  = list(UNDERLYING_OPTIONS.keys())

# Logo URLs for all tickers.
# Stocks/ETFs: parqet CDN (accepts yfinance symbols directly).
# Indices: Google favicon service using the exchange/provider domain — reliable and free.
_LOGO_BASE = "https://assets.parqet.com/logos/symbol/{sym}?format=png"
_GF = "https://www.google.com/s2/favicons?sz=64&domain={domain}"
TICKER_LOGOS: dict[str, str] = {
    **{sym: _LOGO_BASE.format(sym=sym) for sym in [
        # US Banks & Financials
        "GS", "JPM", "MS", "BAC", "C", "WFC", "BLK", "SCHW", "V", "MA",
        # US Tech
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
        "AVGO", "PLTR", "AMD", "INTC", "CRM", "NFLX", "SPOT", "UBER",
        # US Healthcare & Other
        "LLY", "UNH", "BRK-B",
        # European (clean symbols / ADRs)
        "ASML", "SAP", "NVO", "AZN", "SHEL",
        # Commodity & Equity ETFs
        "GLD", "SLV", "GDX", "USO", "XLE", "XLF", "EEM", "ARKK",
        # Fixed Income ETFs
        "TLT", "IEF", "HYG", "LQD",
        # Crypto ETFs
        "IBIT", "FBTC",
    ]},
    # Indices — exchange / index-provider favicon via Google
    "^GSPC":      _GF.format(domain="spglobal.com"),
    "^NDX":       _GF.format(domain="nasdaq.com"),
    "^RUT":       _GF.format(domain="ftserussell.com"),
    "^STOXX50E":  _GF.format(domain="stoxx.com"),
    "^GDAXI":     _GF.format(domain="deutsche-boerse.com"),
    "^FTSE":      _GF.format(domain="ftserussell.com"),
    "^FCHI":      _GF.format(domain="euronext.com"),
    "^SSMI":      _GF.format(domain="six-group.com"),
    "^IBEX":      _GF.format(domain="bolsademadrid.es"),
    "FTSEMIB.MI": _GF.format(domain="borsaitaliana.it"),
    "^N225":      _GF.format(domain="jpx.co.jp"),
    "^HSI":       _GF.format(domain="hsi.com.hk"),
    "^KS11":      _GF.format(domain="krx.co.kr"),
    "^AXJO":      _GF.format(domain="asx.com.au"),
    "^TWII":      _GF.format(domain="twse.com.tw"),
    "^NSEI":      _GF.format(domain="nseindia.com"),
    "^STI":       _GF.format(domain="sgx.com"),
    "^BVSP":      _GF.format(domain="b3.com.br"),
    "^MXX":       _GF.format(domain="bmv.com.mx"),
}
# Map by yfinance symbol → label for JSON loading
_TICKER_TO_LABEL   = {v: k for k, v in UNDERLYING_OPTIONS.items()}

# ==========================================================================
# Session state defaults
# ==========================================================================
_DEFAULTS = {
    "page":             "setup",   # "setup" | "dashboard"
    "run_terms":        None,
    "selected_tickers": None,
    "n_paths":          10000,
    "seed":             42,
    "results":          None,
    "path_num":         0,
    "setup_ul_default": None,    # set when JSON is loaded to override multiselect
    "custom_tickers":   {},      # {symbol: display_name} for user-entered tickers
    "loaded_terms_dict": None,   # persists NoteTerms from JSON upload across reruns
    "history_years":    None,    # always max history
    "calib_years":      5.0,     # years of recent data used for Heston calibration
    "branding":         None,    # parsed branding JSON dict (firm_name, colors, logo_url)
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==========================================================================
# Cached helpers
# ==========================================================================
# ttl: refresh hourly so the Current Performance tab doesn't serve stale
# prices in a long-running session.
@st.cache_data(ttl=3600)
def _load_prices(tickers_tuple, years=5.0, field="close"):
    # field="close"     → raw official closes (barrier observation: backtest/live)
    # field="adj_close" → dividend-adjusted (calibration of drift/vol/corr ONLY)
    return load_prices(source="yfinance", tickers=dict(tickers_tuple),
                       years=years, field=field)

@st.cache_data(ttl=24 * 3600)
def _load_dividends_cached(tickers_tuple):
    return load_dividends(dict(tickers_tuple))

@st.cache_data(ttl=3600)
def _run_backtest_cached(tickers_tuple, terms_json,
                         bt_start_str=None, bt_end_str=None,
                         history_years=None):
    # history_years=None → pull maximum available history (best for backtesting).
    # Pass a float (e.g. 5.0) to limit to that window — useful when one underlying
    # has a short history (e.g. PLTR IPO Sept 2020) and period='max' causes issues.
    prices   = _load_prices(tickers_tuple, years=history_years)
    t        = NoteTerms.from_json(terms_json)
    bt_start = pd.Timestamp(bt_start_str) if bt_start_str else None
    bt_end   = pd.Timestamp(bt_end_str)   if bt_end_str   else None
    return run_backtest(prices, t, bt_start=bt_start, bt_end=bt_end)

# ==========================================================================
# Language toggle (always in sidebar)
# ==========================================================================
lang_choice = st.sidebar.radio("Language / Idioma", ["English", "Español"],
                                horizontal=True)
tr = Translator("es" if lang_choice == "Español" else "en")


def _safe_load_prices(tickers_tuple, **kw):
    """Wrap _load_prices so a Yahoo outage shows a clean message and halts the
    run, instead of surfacing a raw traceback to the user. The underlying
    load_prices already raises a friendly ValueError on empty/rate-limited
    responses; we render it and st.stop() to abort this script run cleanly."""
    try:
        return _load_prices(tickers_tuple, **kw)
    except Exception as exc:  # noqa: BLE001 — any data-layer failure is user-facing
        st.error(tr("data_load_error", msg=str(exc)))
        st.info(tr("data_load_retry"))
        st.stop()


def _detect_note_type(t: NoteTerms) -> str:
    """Infer which setup-form template a loaded config corresponds to, so the
    note-type picker can show only the relevant fields. Order matters: the two
    standalone payoff branches (capital-protected, bonus) are checked first
    because they set fields the Phoenix tests would otherwise match."""
    if getattr(t, "capital_guarantee", None) is not None:
        return "capital_protected"
    if getattr(t, "min_return", 0.0) and t.min_return > 0:
        return "bonus_cert"
    if getattr(t, "coupon_at_autocall_only", False) or getattr(t, "autocall_step_down", 0.0) > 0:
        return "growth_autocall"
    if t.coupon_barrier == 0.0 and not t.memory:
        return "reverse_conv"
    return "phoenix"


# ==========================================================================
# ─────────────────────────────────────────────────────────────────────────
#  PAGE 1 — SETUP
# ─────────────────────────────────────────────────────────────────────────
# ==========================================================================
if st.session_state["page"] == "setup":

    st.title(tr("setup_title"))
    st.markdown(tr("setup_intro"))
    st.divider()

    # ── JSON upload ───────────────────────────────────────────────────────
    uploaded = st.file_uploader(tr("setup_upload_label"),
                                 type=["json"], key="setup_upload")
    if uploaded is not None:
        try:
            raw = uploaded.read().decode()
            _parsed = NoteTerms.from_json(raw)
            # Only process if this is a newly uploaded file (different from what's stored)
            _parsed_dict = _parsed.to_dict()
            if st.session_state["loaded_terms_dict"] != _parsed_dict:
                st.session_state["loaded_terms_dict"] = _parsed_dict
                # Fresh upload → set the note-type picker to the detected template.
                # This is the ONLY place we force the picker, so a manual override
                # on later reruns is never clobbered (this block runs once per file).
                st.session_state["setup_note_type"] = _detect_note_type(_parsed)
                # Resolve tickers to known labels (or register as custom)
                if _parsed.tickers:
                    # Auto-correct inverted ticker dicts: if values look like yfinance symbols
                    # and keys look like display names, swap them.
                    # Heuristic: a yfinance symbol is short (<= 6 chars), uppercase, no spaces.
                    _t = _parsed.tickers
                    _vals_look_like_symbols = all(
                        len(v) <= 6 and v == v.upper() and " " not in v
                        for v in _t.values()
                    )
                    _keys_look_like_symbols = all(
                        len(k) <= 6 and k == k.upper() and " " not in k
                        for k in _t.keys()
                    )
                    if _vals_look_like_symbols and not _keys_look_like_symbols:
                        # Inverted: swap so keys are symbols, values are display names
                        _t = {v: k for k, v in _t.items()}
                        # Also fix in the stored dict so NoteTerms has correct format
                        _parsed_dict["tickers"] = _t
                        st.session_state["loaded_terms_dict"] = _parsed_dict

                    resolved = []
                    custom_from_json = {}
                    for sym, disp in _t.items():
                        if sym in _TICKER_TO_LABEL:
                            resolved.append(_TICKER_TO_LABEL[sym])
                        else:
                            custom_lbl = f"{disp} — {sym} (custom)"
                            custom_from_json[sym] = disp
                            resolved.append(custom_lbl)
                    st.session_state["custom_tickers"] = custom_from_json
                    # Write directly to the widget key so the multiselect reflects it
                    st.session_state["setup_underlyings"] = resolved
                    st.session_state["setup_ul_default"]  = resolved
        except Exception as e:
            st.error(tr("setup_invalid_json", e=e))

    # Restore loaded_terms from session state so it survives reruns
    loaded_terms = (
        NoteTerms.from_dict(st.session_state["loaded_terms_dict"])
        if st.session_state["loaded_terms_dict"] is not None
        else None
    )
    if loaded_terms is not None:
        st.success(tr("setup_config_loaded", name=loaded_terms.name))

    base = loaded_terms or NoteTerms()

    st.divider()

    # ── Underlyings ───────────────────────────────────────────────────────
    st.subheader(tr("setup_underlyings_header"))

    # Build full option list including any custom tickers from session state
    custom_tickers = st.session_state.get("custom_tickers", {})
    all_labels = UNDERLYING_LABELS + [
        f"{disp} — {sym} (custom)" for sym, disp in custom_tickers.items()
    ]

    # Default: session state override (from JSON) or fallback
    default_ul = (
        st.session_state["setup_ul_default"]
        or ["SPX — S&P 500", "SX5E — Euro Stoxx 50", "SMI — Swiss Market"]
    )
    # Filter to only valid options
    default_ul = [d for d in default_ul if d in all_labels]

    selected_labels = st.multiselect(
        tr("setup_select_underlyings"), all_labels,
        default=default_ul,
        key="setup_underlyings",
    )

    # ── Custom ticker input ───────────────────────────────────────────────
    with st.expander(tr("setup_add_custom_expander")):
        st.caption(tr("setup_custom_caption"))
        cc1, cc2, cc3 = st.columns([2, 2, 1])
        with cc1:
            custom_sym = st.text_input(tr("setup_custom_symbol"), placeholder="e.g. UBER",
                                        key="custom_sym_input").strip().upper()
        with cc2:
            custom_name = st.text_input(tr("setup_display_name"), placeholder="e.g. Uber",
                                         key="custom_name_input").strip()
        with cc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(tr("setup_add_btn"), key="add_custom_btn"):
                if custom_sym and custom_name:
                    ct = dict(st.session_state.get("custom_tickers", {}))
                    ct[custom_sym] = custom_name
                    st.session_state["custom_tickers"] = ct
                    # Auto-select the new ticker
                    new_lbl = f"{custom_name} — {custom_sym} (custom)"
                    current = list(st.session_state.get("setup_underlyings", default_ul))
                    if new_lbl not in current:
                        current.append(new_lbl)
                    st.session_state["setup_ul_default"] = current
                    st.rerun()
                else:
                    st.warning(tr("setup_enter_both"))

    # ── Logo row for selected tickers ─────────────────────────────────────
    if selected_labels:
        _lbl_to_sym = {k: v for k, v in UNDERLYING_OPTIONS.items()}
        _lbl_to_sym.update({
            f"{disp} — {sym} (custom)": sym
            for sym, disp in custom_tickers.items()
        })
        logo_cols = st.columns(min(len(selected_labels), 5))
        for _i, _lbl in enumerate(selected_labels[:5]):
            _sym = _lbl_to_sym.get(_lbl)
            _logo_url = (TICKER_LOGOS.get(_sym) or _LOGO_BASE.format(sym=_sym)) if _sym else None
            _short = _lbl.split(" — ")[0]
            with logo_cols[_i]:
                if _logo_url:
                    # onerror hides the element if the URL fails instead of showing a broken icon
                    st.markdown(
                        f'<img src="{_logo_url}" width="48" height="48" '
                        f'style="object-fit:contain;border-radius:4px;" '
                        f'onerror="this.style.display=\'none\'">',
                        unsafe_allow_html=True,
                    )
                st.caption(_short)

    st.divider()

    # ── Note type ─────────────────────────────────────────────────────────
    st.subheader(tr("setup_note_type_header"))
    _nt_opts = ["phoenix", "reverse_conv", "growth_autocall",
                "bonus_cert", "capital_protected", "custom"]
    _nt_label = {
        "phoenix": tr("nt_phoenix"), "reverse_conv": tr("nt_reverse_conv"),
        "growth_autocall": tr("nt_growth_autocall"), "bonus_cert": tr("nt_bonus_cert"),
        "capital_protected": tr("nt_capital_protected"), "custom": tr("nt_custom"),
    }
    _nt_desc = {
        "phoenix": tr("nt_phoenix_desc"), "reverse_conv": tr("nt_reverse_conv_desc"),
        "growth_autocall": tr("nt_growth_autocall_desc"), "bonus_cert": tr("nt_bonus_cert_desc"),
        "capital_protected": tr("nt_capital_protected_desc"), "custom": tr("nt_custom_desc"),
    }
    note_type = st.radio(
        tr("setup_note_type"), _nt_opts,
        format_func=lambda k: _nt_label[k],
        horizontal=True,
        key="setup_note_type",
        help=tr("setup_note_type_help"),
    )
    st.info(_nt_desc[note_type])

    # Per-template field visibility
    _is_phoenix = note_type == "phoenix"
    _is_revconv = note_type == "reverse_conv"
    _is_growth  = note_type == "growth_autocall"
    _is_bonus   = note_type == "bonus_cert"
    _is_capprot = note_type == "capital_protected"
    _is_custom  = note_type == "custom"

    _show_coupon         = note_type in ("phoenix", "reverse_conv", "growth_autocall", "custom")
    _show_coupon_barrier = note_type in ("phoenix", "custom")
    _show_memory         = note_type in ("phoenix", "custom")
    _show_coupon_basket  = note_type in ("phoenix", "custom")
    _show_autocall       = note_type in ("phoenix", "reverse_conv", "growth_autocall", "custom")
    _show_growth         = note_type in ("growth_autocall", "custom")
    _show_ki             = note_type in ("phoenix", "reverse_conv", "growth_autocall", "bonus_cert", "custom")
    _show_min_return     = _is_bonus
    _show_capprot        = _is_capprot
    _show_rescue         = note_type in ("phoenix", "custom")

    basket_opts = ["worst_of", "best_of", "average"]
    _basket_label = {
        "worst_of": tr("basket_worst_of"),
        "best_of":  tr("basket_best_of"),
        "average":  tr("basket_average"),
    }
    from core.note import _FREQ_TO_PERIODS

    # ── Field defaults ─────────────────────────────────────────────────────
    # Seed every field from the loaded/base config, then force the
    # template-canonical values for whatever this structure hard-codes — so
    # switching type from a Phoenix base still builds a correct note even for
    # the fields this template hides.
    coupon_pa_pct    = round(base.coupon_pa * 100, 4)
    coupon_bar_pct   = round(base.coupon_barrier * 100, 4)
    memory           = base.memory
    coupon_basket    = base.coupon_basket
    autocall_basket  = base.autocall_basket
    _ac_val          = round(base.autocall_barrier * 100, 4)
    autocall_bar_pct = min(max(_ac_val, 50.0), 300.0)
    ki_bar_pct       = round(base.knock_in_barrier * 100, 4)
    step_down_pct    = round(getattr(base, "autocall_step_down", 0.0) * 100, 4)
    _base_floor      = getattr(base, "autocall_floor", None)
    floor_pct        = round((_base_floor if _base_floor is not None else 0.0) * 100, 4)
    premium_at_call  = bool(getattr(base, "coupon_at_autocall_only", False))
    min_return_pct   = round(getattr(base, "min_return", 0.0) * 100, 4)
    rescue_on        = (base.final_basket == "best_of")
    rescue_bar_pct   = round(getattr(base, "final_redemption_barrier", 1.0) * 100, 4)
    capital_guarantee = getattr(base, "capital_guarantee", None)
    upside_cap        = getattr(base, "upside_cap", None)

    if _is_bonus:
        # No coupons, no autocall (barrier set unreachable); KI + floor only.
        coupon_pa_pct = 0.0; coupon_bar_pct = 0.0; memory = False
        autocall_bar_pct = 200.0; autocall_basket = "worst_of"; coupon_basket = "worst_of"
        step_down_pct = 0.0; floor_pct = 0.0; premium_at_call = False
        capital_guarantee = None; upside_cap = None; rescue_on = False
    elif _is_capprot:
        # Standalone payoff: engine ignores coupon/autocall/KI entirely.
        coupon_pa_pct = 0.0; coupon_bar_pct = 0.0; memory = False
        autocall_bar_pct = 200.0; autocall_basket = "worst_of"; coupon_basket = "worst_of"
        ki_bar_pct = 0.0; min_return_pct = 0.0
        step_down_pct = 0.0; floor_pct = 0.0; premium_at_call = False
        rescue_on = False
    elif _is_revconv:
        # Guaranteed coupon (barrier 0), no memory; standard worst-of redemption.
        coupon_bar_pct = 0.0; memory = False
        step_down_pct = 0.0; floor_pct = 0.0; premium_at_call = False
        min_return_pct = 0.0; capital_guarantee = None; upside_cap = None; rescue_on = False
    elif _is_growth:
        # Premium paid only at autocall; coupon barrier/memory n/a.
        memory = False; premium_at_call = True
        min_return_pct = 0.0; capital_guarantee = None; upside_cap = None; rescue_on = False
    elif _is_phoenix:
        step_down_pct = 0.0; floor_pct = 0.0; premium_at_call = False
        min_return_pct = 0.0; capital_guarantee = None; upside_cap = None

    # ── Schedule & Maturity ───────────────────────────────────────────────
    st.subheader(tr("setup_schedule_header"))
    maturity_opts = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    # Keep a loaded config's maturity selectable instead of silently snapping
    # it to the nearest preset (e.g. a 9M note must not become 1Y).
    if base.maturity not in maturity_opts:
        maturity_opts = sorted(set(maturity_opts + [base.maturity]))
    freq_opts = ["monthly", "quarterly", "semi-annual", "annual"]
    _freq_label = {
        "monthly":     tr("freq_monthly"),
        "quarterly":   tr("freq_quarterly"),
        "semi-annual": tr("freq_semi_annual"),
        "annual":      tr("freq_annual"),
    }
    sc_a, sc_b = st.columns(2)
    with sc_a:
        maturity = st.selectbox(
            tr("setup_maturity_years"), maturity_opts,
            index=maturity_opts.index(base.maturity)
                  if base.maturity in maturity_opts else 1,
        )
    with sc_b:
        payment_freq = st.selectbox(
            tr("setup_payment_freq"), freq_opts,
            index=freq_opts.index(base.payment_freq)
                  if base.payment_freq in freq_opts else 1,
            format_func=lambda f: _freq_label.get(f, f),
        )
    _n_obs_derived = round(maturity * _FREQ_TO_PERIODS[payment_freq])
    st.caption(tr("setup_obs_periods_caption", n=_n_obs_derived,
                  per_yr=_FREQ_TO_PERIODS[payment_freq], mat=maturity))

    # ── Coupon ────────────────────────────────────────────────────────────
    if _show_coupon:
        st.subheader(tr("setup_coupon_header"))
        cp_a, cp_b = st.columns(2)
        with cp_a:
            # Growth autocall: coupon_pa carries the premium accrual rate.
            coupon_pa_pct = st.number_input(
                tr("setup_premium_pa") if _is_growth else tr("setup_coupon_pa"),
                0.0, 50.0, value=round(base.coupon_pa * 100, 4),
                step=0.5, format="%.4f",
                help=tr("setup_premium_pa_help") if _is_growth else tr("setup_coupon_pa_help"),
            )
            if not _is_growth:
                _coupon_per_period = coupon_pa_pct / 100.0 / _FREQ_TO_PERIODS[payment_freq]
                st.caption(tr("setup_coupon_period_caption", v=_coupon_per_period * 100))
        with cp_b:
            if _show_coupon_basket:
                coupon_basket = st.selectbox(
                    tr("setup_coupon_basket_rule"), basket_opts,
                    index=basket_opts.index(base.coupon_basket),
                    format_func=lambda b: _basket_label.get(b, b),
                    help=tr("setup_basket_rule_help"),
                )
        if _show_coupon_barrier:
            cb_a, cb_b = st.columns(2)
            with cb_a:
                # number_input (not int slider): term sheets use sub-percent
                # barriers (e.g. 55.5%, 53.7%) which an int slider truncates.
                coupon_bar_pct = st.number_input(
                    tr("setup_coupon_barrier"), 0.0, 100.0,
                    value=round(base.coupon_barrier * 100, 4), step=0.5, format="%.2f",
                    help=tr("setup_coupon_barrier_help"),
                )
            with cb_b:
                st.markdown("<br>", unsafe_allow_html=True)
                memory = st.toggle(tr("setup_memory_coupon"), value=base.memory,
                                   help=tr("setup_memory_help"))

    # ── Protection / Barriers ─────────────────────────────────────────────
    if _show_ki or _show_min_return or _show_capprot or _show_rescue:
        st.subheader(tr("setup_barriers_header"))
        st.caption(tr("setup_barriers_caption"))
        if _show_ki:
            ki_bar_pct = st.number_input(
                tr("setup_ki_barrier"), 0.0, 100.0,
                value=round(base.knock_in_barrier * 100, 4), step=0.5, format="%.2f",
            )
            if _is_bonus:
                st.caption(tr("setup_ki_european_caption"))
        if _show_min_return:
            min_return_pct = st.number_input(
                tr("setup_min_return"), 0.0, 100.0,
                value=round(getattr(base, "min_return", 0.0) * 100, 4),
                step=0.5, format="%.2f", help=tr("setup_min_return_help"),
            )
        if _show_capprot:
            cg_a, cg_b = st.columns(2)
            with cg_a:
                _cg_def = getattr(base, "capital_guarantee", None)
                cap_guar_pct = st.number_input(
                    tr("setup_capital_guarantee"), 0.0, 100.0,
                    value=round((_cg_def if _cg_def is not None else 1.0) * 100, 4),
                    step=1.0, format="%.2f", help=tr("setup_capital_guarantee_help"),
                )
                capital_guarantee = cap_guar_pct / 100.0
            with cg_b:
                _uc_def = getattr(base, "upside_cap", None)
                _cap_on = st.toggle(tr("setup_cap_upside_toggle"),
                                    value=_uc_def is not None)
                if _cap_on:
                    uc_pct = st.number_input(
                        tr("setup_upside_cap"), 0.0, 200.0,
                        value=round((_uc_def if _uc_def is not None else 0.15) * 100, 4),
                        step=1.0, format="%.2f", help=tr("setup_upside_cap_help"),
                    )
                    upside_cap = uc_pct / 100.0
                else:
                    upside_cap = None
        if _show_rescue:
            # Best-of capital rescue clause (e.g. BBVA XS3378405743 Final Payout
            # xi): at maturity, capital is returned at par if the BEST performer
            # is at or above the rescue barrier, even when the KI was breached.
            rescue_on = st.toggle(
                tr("setup_rescue_toggle"),
                value=(base.final_basket == "best_of"),
                help=tr("setup_rescue_help"),
            )
            if rescue_on:
                rescue_bar_pct = st.number_input(
                    tr("setup_rescue_barrier"), 50.0, 150.0,
                    value=round(getattr(base, "final_redemption_barrier", 1.0) * 100, 4),
                    step=0.5, format="%.2f",
                    help=tr("setup_rescue_barrier_help"),
                )
    final_basket = "best_of" if rescue_on else "worst_of"

    # ── Autocall ──────────────────────────────────────────────────────────
    if _show_autocall:
        st.subheader(tr("setup_autocall_header"))
        au_a, au_b, au_c = st.columns(3)
        with au_a:
            # Bound at 300% and clamp the default so a Bonus/CP config (200%
            # barrier) loads without a ValueAboveMax crash if switched here.
            _ac_val = round(base.autocall_barrier * 100, 4)
            autocall_bar_pct = st.number_input(
                tr("setup_autocall_barrier"), 50.0, 300.0,
                value=min(max(_ac_val, 50.0), 300.0), step=0.5, format="%.2f",
            )
        with au_b:
            autocall_start = st.number_input(
                tr("setup_autocall_start"), 1, _n_obs_derived,
                value=min(base.autocall_start_period, _n_obs_derived),
                help=tr("setup_autocall_start_help"),
            )
        with au_c:
            autocall_basket = st.selectbox(
                tr("setup_autocall_basket_rule"), basket_opts,
                index=basket_opts.index(base.autocall_basket),
                format_func=lambda b: _basket_label.get(b, b),
                help=tr("setup_basket_rule_help"),
            )
        if _show_growth:
            st.markdown("**" + tr("setup_growth_subheader") + "**")
            gr_a, gr_b, gr_c = st.columns(3)
            with gr_a:
                step_down_pct = st.number_input(
                    tr("setup_step_down"), 0.0, 10.0,
                    value=round(getattr(base, "autocall_step_down", 0.0) * 100, 4),
                    step=0.5, format="%.2f", help=tr("setup_step_down_help"),
                )
            with gr_b:
                floor_pct = st.number_input(
                    tr("setup_autocall_floor"), 0.0, 100.0,
                    value=round((_base_floor if _base_floor is not None else 0.0) * 100, 4),
                    step=0.5, format="%.2f", help=tr("setup_autocall_floor_help"),
                )
            with gr_c:
                if _is_custom:
                    st.markdown("<br>", unsafe_allow_html=True)
                    premium_at_call = st.toggle(
                        tr("setup_premium_at_call"),
                        value=bool(getattr(base, "coupon_at_autocall_only", False)),
                        help=tr("setup_premium_at_call_help"),
                    )
            if step_down_pct > 0:
                _sd_preview = NoteTerms(
                    maturity=float(maturity), payment_freq=payment_freq,
                    autocall_barrier=autocall_bar_pct / 100.0,
                    autocall_start_period=int(autocall_start),
                    autocall_step_down=step_down_pct / 100.0,
                    autocall_floor=(floor_pct / 100.0) if floor_pct > 0 else None,
                ).autocall_barrier_schedule()
                st.caption(tr("setup_barrier_schedule") +
                           " → ".join(f"{lvl:.0%}" for lvl in _sd_preview))
    else:
        # Autocall hidden (Bonus / Capital-Protected): keep a valid start period.
        autocall_start = max(min(base.autocall_start_period, _n_obs_derived), 1)

    st.divider()

    # ── Metadata & identification (optional) ──────────────────────────────
    with st.expander(tr("setup_metadata_header")):
        note_name = st.text_input(
            tr("setup_note_name"),
            value=base.name if loaded_terms else "Custom Note",
            help=tr("setup_note_name_help"),
        )
        # Issuer — source of truth is loaded_terms (JSON) over widget state.
        # Push the loaded issuer into session_state before the widget renders so
        # the Streamlit keyed-widget problem (value= ignored on reruns) doesn't
        # drop it. This runs inside the expander, whose body always executes.
        _base_issuer = getattr(base, "issuer", "") or ""
        if loaded_terms is not None and _base_issuer and st.session_state.get("setup_issuer") != _base_issuer:
            st.session_state["setup_issuer"] = _base_issuer
        issuer_input = st.text_input(
            tr("setup_issuer_name"),
            value=_base_issuer,
            placeholder="e.g. BBVA, HSBC, BNP Paribas",
            key="setup_issuer",
            help=tr("setup_issuer_caption"),
        )
        if issuer_input:
            _logo_url = get_issuer_logo_url(issuer_input)
            if _logo_url:
                st.markdown(
                    f'<img src="{_logo_url}" height="32" style="margin-top:4px" '
                    f'onerror="this.style.display=\'none\'">',
                    unsafe_allow_html=True,
                )

        # Issue date — same keyed-widget guard as the issuer above.
        import datetime as _dt2
        _base_issue_str = getattr(base, "issue_date", None)
        _base_issue = None
        if _base_issue_str:
            try:
                _base_issue = _dt2.date.fromisoformat(_base_issue_str)
            except Exception:
                pass
        if _base_issue is not None and st.session_state.get("setup_issue_date") != _base_issue:
            st.session_state["setup_issue_date"] = _base_issue
        issue_date_input = st.date_input(
            tr("setup_issue_date_input"),
            value=_base_issue,
            min_value=None,
            max_value=None,
            key="setup_issue_date",
            help=tr("setup_issue_date_help"),
        )
        st.caption(tr("setup_issue_date_caption"))
        # A note is live if it has an issue date on or before today.
        _issue_is_live = bool(issue_date_input) and issue_date_input <= _dt2.date.today()
        if _issue_is_live:
            st.success(tr("setup_live_note", date=issue_date_input))
        elif issue_date_input:
            st.info(tr("setup_future_issue"))

    # ── Simulation engine settings ────────────────────────────────────────
    with st.expander(tr("setup_engine_header")):
        # Always pull the maximum available history; the calibration window
        # below controls how much is used for Heston parameter estimation.
        history_years = None
        eng_a, eng_b = st.columns(2)
        with eng_a:
            n_paths = st.slider(tr("setup_mc_paths"), 1000, _MAX_PATHS,
                                min(st.session_state["n_paths"], _MAX_PATHS), step=1000)
        with eng_b:
            seed = int(st.number_input(tr("setup_random_seed"),
                                       value=int(st.session_state["seed"])))
        st.caption(tr("setup_price_history_caption"))
        _calib_opts   = [1.0, 2.0, 3.0, 5.0, 10.0]
        _calib_labels = {
            1.0:  tr("setup_calib_1y"),  2.0: tr("setup_calib_2y"),
            3.0:  tr("setup_calib_3y"),  5.0: tr("setup_calib_5y"),
            10.0: tr("setup_calib_10y"),
        }
        _calib_cur    = st.session_state.get("calib_years", 5.0)
        _calib_default_idx = _calib_opts.index(_calib_cur) if _calib_cur in _calib_opts else 3
        calib_years = st.radio(
            tr("setup_calib_window"),
            _calib_opts,
            index=_calib_default_idx,
            horizontal=True,
            format_func=lambda y: _calib_labels.get(y, str(y)),
            help=tr("setup_calib_window_help"),
        )

    st.divider()

    # ── Confirm ───────────────────────────────────────────────────────────────────
    if len(selected_labels) < 1:
        st.warning(tr("setup_select_min_one"))
    else:
        if st.button(tr("setup_confirm_btn"), type="primary",
                     use_container_width=True):
            custom_tickers = st.session_state.get("custom_tickers", {})
            # Build reverse map including custom tickers
            all_options = dict(UNDERLYING_OPTIONS)
            all_options.update({sym: disp for sym, disp in custom_tickers.items()})
            _all_label_to_sym = {k: v for k, v in UNDERLYING_OPTIONS.items()}
            _all_label_to_sym.update({
                f"{disp} — {sym} (custom)": sym
                for sym, disp in custom_tickers.items()
            })
            selected_tickers = {}
            for lbl in selected_labels[:5]:
                sym  = _all_label_to_sym.get(lbl)
                disp = lbl.split(" — ")[0]
                if sym:
                    selected_tickers[sym] = disp
            terms = NoteTerms(
                name                  = note_name.strip() or "Custom Note",
                issuer                = issuer_input.strip(),
                maturity              = float(maturity),
                payment_freq          = payment_freq,
                coupon_pa             = coupon_pa_pct / 100.0,
                coupon_barrier        = coupon_bar_pct / 100.0,
                autocall_barrier      = autocall_bar_pct / 100.0,
                autocall_start_period = int(autocall_start),
                knock_in_barrier      = ki_bar_pct / 100.0,
                principal_protection  = 1.0,
                memory                = memory,
                coupon_basket         = coupon_basket,
                autocall_basket       = autocall_basket,
                final_basket          = final_basket,
                final_redemption_barrier = rescue_bar_pct / 100.0,
                call_steepness        = None,   # hard trigger (deterministic)
                # Growth autocall fields (Growth / Custom templates).
                autocall_step_down      = step_down_pct / 100.0,
                autocall_floor          = (floor_pct / 100.0) if (step_down_pct > 0 and floor_pct > 0) else None,
                coupon_at_autocall_only = bool(premium_at_call),
                # Bonus Certificate / Capital Protected fields — exposed by the
                # Bonus / Capital-Protected templates; default to a no-op for the
                # Phoenix family so plain notes are unaffected.
                min_return              = min_return_pct / 100.0,
                capital_guarantee       = capital_guarantee,
                upside_cap              = upside_cap,
                tickers               = selected_tickers,
                # Keep the issue date even when it is in the future, so a
                # config round-trip through the setup form doesn't drop it;
                # the dashboard only shows the live tab once it is <= today.
                issue_date            = issue_date_input.isoformat() if issue_date_input else None,
            )
            st.session_state["run_terms"]        = terms
            st.session_state["selected_tickers"] = selected_tickers
            st.session_state["n_paths"]          = n_paths
            st.session_state["seed"]             = int(seed)
            st.session_state["history_years"]    = history_years
            st.session_state["calib_years"]      = calib_years
            st.session_state["results"]          = None
            st.session_state["page"]             = "dashboard"
            st.session_state["setup_ul_default"] = None   # clear for next reconfigure
            st.session_state["loaded_terms_dict"] = None  # clear for next reconfigure
            st.rerun()

# ==========================================================================
# ─────────────────────────────────────────────────────────────────────────
#  PAGE 2 — DASHBOARD
# ─────────────────────────────────────────────────────────────────────────
# ==========================================================================
elif st.session_state["page"] == "dashboard":

    terms            = st.session_state["run_terms"]
    selected_tickers = st.session_state["selected_tickers"]
    n_paths          = st.session_state["n_paths"]
    seed             = st.session_state["seed"]
    tickers_tuple    = tuple(selected_tickers.items())

    # ── Sidebar ───────────────────────────────────────────────────────────
    st.sidebar.header(tr("sidebar_note"))
    st.sidebar.markdown(f"**{terms.name}**")
    if getattr(terms, "issuer", ""):
        _sb_logo = get_issuer_logo_url(terms.issuer)
        _sb_issuer_html = f"**{terms.issuer}**"
        if _sb_logo:
            _sb_issuer_html = (
                f'<img src="{_sb_logo}" height="20" style="vertical-align:middle;margin-right:6px" '
                f'onerror="this.style.display=\'none\'">'
                f"<span>{terms.issuer}</span>"
            )
        st.sidebar.markdown(_sb_issuer_html, unsafe_allow_html=True)
    st.sidebar.markdown(
        f"{', '.join(selected_tickers.values())}  \n"
        f"{int(terms.maturity*12)}M · {terms.n_obs} obs · {terms.payment_freq} · "
        f"{terms.coupon_pa*100:.2g}% p.a."
    )
    st.sidebar.download_button(
        tr("sidebar_download_config"),
        data=terms.to_json(),
        file_name="note_config.json",
        mime="application/json",
    )
    # ── Branding JSON uploader ────────────────────────────────────────────
    # Persist the parsed branding dict in session state so it survives reruns.
    _branding_upload = st.sidebar.file_uploader(
        tr("sidebar_branding_label"),
        type=["json"],
        key="branding_upload",
        help=tr("sidebar_branding_help"),
    )
    if _branding_upload is not None:
        try:
            import json as _json
            _branding_raw = _branding_upload.read().decode()
            st.session_state["branding"] = _json.loads(_branding_raw)
        except Exception as _be:
            st.sidebar.warning(tr("sidebar_branding_invalid", e=_be))
    _branding_dict = st.session_state.get("branding")
    if _branding_dict:
        _bfirm = _branding_dict.get("firm_name", "")
        _bcolor = _branding_dict.get("primary_color", "")
        st.sidebar.caption(tr("sidebar_branding_caption", firm=_bfirm, color=_bcolor))
        if st.sidebar.button(tr("sidebar_clear_branding"), key="clear_branding"):
            st.session_state["branding"] = None
            st.rerun()

    _pdf_btn = st.sidebar.button(
        tr("sidebar_generate_pdf"),
        disabled=not bool(st.session_state.get("results")),
        help=tr("sidebar_generate_pdf_help"),
    )
    # Placeholder so the generated download button appears right here, directly
    # under the trigger button — not buried at the bottom of the sidebar.
    _pdf_slot = st.sidebar.empty()
    st.sidebar.divider()
    if st.sidebar.button(tr("sidebar_reconfigure")):
        st.session_state["page"]             = "setup"
        st.session_state["results"]          = None
        st.session_state["loaded_terms_dict"] = None
        st.rerun()
    run_button = st.sidebar.button(tr("run_simulation"), type="primary")

    # ── Title ─────────────────────────────────────────────────────────────
    st.title(tr("page_title"))
    _issuer_str = getattr(terms, "issuer", "") or ""
    _issuer_logo = get_issuer_logo_url(_issuer_str) if _issuer_str else None
    if _issuer_str:
        _issuer_badge = (
            f'<img src="{_issuer_logo}" height="20" style="vertical-align:middle;margin-right:5px;border-radius:3px" '
            f'onerror="this.style.display=\'none\'">'
            if _issuer_logo else ""
        ) + f"<span style='vertical-align:middle'>{_issuer_str}</span> &nbsp;·&nbsp; "
        st.markdown(
            f"<div style='margin-bottom:4px'>{_issuer_badge}"
            f"<b>{terms.name}</b> — "
            f"{', '.join(selected_tickers.values())} · "
            f"{int(terms.maturity*12)}M · {terms.n_obs} obs · "
            f"{tr('metric_coupon_pa')} {terms.coupon_pa*100:.2g}% · "
            f"{tr('dash_memory') if terms.memory else tr('dash_no_memory')} · "
            f"KI {terms.knock_in_barrier:.0%} · Autocall {terms.autocall_barrier:.0%}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"**{terms.name}** — "
            f"{', '.join(selected_tickers.values())} · "
            f"{int(terms.maturity*12)}M · {terms.n_obs} obs · "
            f"{tr('metric_coupon_pa')} {terms.coupon_pa*100:.2g}% · "
            f"{tr('dash_memory') if terms.memory else tr('dash_no_memory')} · "
            f"KI {terms.knock_in_barrier:.0%} · Autocall {terms.autocall_barrier:.0%}"
        )

    with st.expander(tr("note_structure_expander"), expanded=False):
        # Issuer row (if set)
        if getattr(terms, "issuer", ""):
            _exp_logo = get_issuer_logo_url(terms.issuer)
            _exp_issuer_html = (
                f'<img src="{_exp_logo}" height="24" style="vertical-align:middle;margin-right:8px" '
                f'onerror="this.style.display=\'none\'">'
                f"<strong>{tr('structure_issuer_label')}</strong> {terms.issuer}"
            ) if _exp_logo else f"<strong>{tr('structure_issuer_label')}</strong> {terms.issuer}"
            st.markdown(_exp_issuer_html, unsafe_allow_html=True)

        # Underlyings table with logos
        st.markdown(tr("underlyings_header"))
        _ul_rows_html = "".join(
            "<tr>"
            "<td style='padding:4px 8px;vertical-align:middle;'>"
            + (
                f"<img src='{TICKER_LOGOS.get(sym) or _LOGO_BASE.format(sym=sym)}' "
                f"width='24' height='24' "
                f"style='border-radius:4px;vertical-align:middle;' "
                f"onerror=\"this.style.display='none'\"/>"
            )
            + f"</td>"
            f"<td style='padding:4px 8px;vertical-align:middle;'>{disp}</td>"
            f"<td style='padding:4px 8px;vertical-align:middle;font-family:monospace;'>{sym}</td>"
            "</tr>"
            for sym, disp in selected_tickers.items()
        )
        st.markdown(
            "<table style='border-collapse:collapse;width:100%'>"
            "<thead><tr>"
            "<th style='padding:4px 8px;text-align:left;border-bottom:1px solid #ddd;width:36px;'></th>"
            f"<th style='padding:4px 8px;text-align:left;border-bottom:1px solid #ddd;'>{tr('col_display_name')}</th>"
            f"<th style='padding:4px 8px;text-align:left;border-bottom:1px solid #ddd;'>{tr('col_yf_symbol')}</th>"
            "</tr></thead>"
            f"<tbody>{_ul_rows_html}</tbody>"
            "</table>",
            unsafe_allow_html=True,
        )

        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric(tr("metric_maturity"), f"{terms.maturity}Y")
        c1.metric(tr("metric_observations"), f"{terms.n_obs}")
        c1.metric(tr("metric_frequency"), terms.payment_freq.capitalize())
        c2.metric(tr("metric_coupon_pa"), f"{terms.coupon_pa*100:.2g}%")
        c2.metric(tr("metric_coupon_period"), f"{terms.coupon_rate*100:.4f}%")
        c2.metric(tr("metric_memory"), tr("yes") if terms.memory else tr("no_str"))
        c3.metric(tr("metric_coupon_barrier"), f"{terms.coupon_barrier:.0%}")
        c3.metric(tr("metric_autocall_barrier"), f"{terms.autocall_barrier:.0%}")
        c3.metric(tr("metric_ki_barrier"), f"{terms.knock_in_barrier:.0%}")
        if terms.final_basket == "best_of":
            st.info(tr("best_of_rescue_info", barrier=terms.final_redemption_barrier))
        obs_df = pd.DataFrame({
            tr("col_period"): range(1, terms.n_obs + 1),
            tr("col_time_y"): [f"{t:.4g}" for t in terms.obs_times()],
            tr("col_autocall_eligible"): [tr("autocall_eligible_yes") if i + 1 >= terms.autocall_start_period else tr("autocall_eligible_coupon_only")
                                   for i in range(terms.n_obs)],
        })
        st.dataframe(obs_df, use_container_width=True, hide_index=True)

    # ── Shared derived values (always available from terms) ─────────────
    obs_times_l = terms.obs_times()
    obs_pairs   = [(f"P{i+1}", t) for i, t in enumerate(obs_times_l)]
    obs_labels  = [f"P{i+1}" for i in range(len(obs_times_l))]
    # asset_names available before simulation runs (falls back to selected_tickers)
    _R_pre = st.session_state["results"]
    asset_names = (
        _R_pre.get("asset_names") or st.session_state.get("last_asset_names")
        or list(selected_tickers.values())
    ) if _R_pre is not None else list(selected_tickers.values())

    # ── Run simulation (triggered by sidebar button) ──────────────────────
    if run_button:
        with st.spinner(tr("mc_run_spinner")):
            _hist_years = st.session_state.get("history_years", None)
            # Calibrate drift/vol/correlations on ADJUSTED closes (total-return
            # dynamics — ex-date jumps must not pollute the estimates) ...
            prices_adj = _safe_load_prices(tickers_tuple, years=_hist_years, field="adj_close")
            # ... but barriers, S0, and dividend jumps live in RAW price space.
            prices_raw = _safe_load_prices(tickers_tuple, years=_hist_years, field="close")
            cal    = HestonCalibrator(
                prices_df   = prices_adj,
                calib_years = st.session_state.get("calib_years", 5.0),
            )
            cal_result = cal.calibrate()

            # Spot override: the simulation starts at the actual market price
            # (raw close), not the dividend-adjusted level.
            _raw_last = prices_raw.iloc[-1]
            for p in cal_result.params:
                if p.name in _raw_last.index:
                    p.S0 = float(_raw_last[p.name])

            # ── Trading-day simulation grid ────────────────────────────────
            # One step per future trading day from the last close to maturity;
            # dt = calendar gap in years (a Fri→Mon step diffuses 3 days of
            # variance). Observation dates and dividend ex-dates land on real
            # grid rows shared with the backtest/live-tab date logic.
            _anchor    = prices_raw.index[-1]
            _mat_date  = pd.offsets.BDay().rollforward(
                _anchor + pd.DateOffset(months=round(terms.maturity * 12)))
            _grid      = pd.bdate_range(_anchor, _mat_date)
            _dt_grid   = np.diff(_grid.values).astype("timedelta64[D]").astype(float) / 365.0
            N_steps    = len(_grid) - 1
            _obs_steps = [min(int(_grid.searchsorted(d)), N_steps)
                          for d in terms.obs_calendar_dates(_anchor)]
            _obs_times = [(_grid[s] - _grid[0]).days / 365.0 for s in _obs_steps]

            # ── Pre-programmed dividend jumps ──────────────────────────────
            # Trailing-12M cash dividends repeated on anniversary ex-dates,
            # as proportional drops vs the current spot. Indices/non-payers
            # contribute zeros.
            try:
                _divs = _load_dividends_cached(tickers_tuple)
            except Exception as _div_e:
                st.warning(tr("mc_div_warning", e=_div_e))
                _divs = {}
            _div_sched = build_dividend_schedule(
                [_divs.get(p.name, pd.Series(dtype=float)) for p in cal_result.params],
                [p.S0 for p in cal_result.params],
                _grid,
            )

            sim = HestonMultiSimulator(
                params       = cal_result.params,
                corr_SS      = cal_result.corr_SS,
                corr_VV      = cal_result.corr_VV,
                corr_SV      = cal_result.corr_SV,
                n_paths      = n_paths,
                seed         = seed,
                t_dof        = cal_result.t_dof,
                dt_grid      = _dt_grid,
                div_schedule = _div_sched,
            )
            sim_results = sim.run()

            n_assets   = len(cal_result.params)
            sim_prices = np.stack(sim_results["S_paths"], axis=2)
            S0_vec     = np.array([p.S0 for p in cal_result.params]).reshape(1, 1, n_assets)
            perf_paths = sim_prices / S0_vec
            wof_paths  = perf_paths.min(axis=2)

            note_results = price_note(perf_paths, terms, seed=seed + 1,
                                      obs_steps=_obs_steps, obs_times=_obs_times)
            s0_values    = [p.S0 for p in cal_result.params]

            # Memory: store the display arrays as float32 (halves the footprint).
            # All payoff statistics in note_results were already computed at
            # float64 by price_note above, and everything downstream (percentile
            # fans, path explorer, per-asset perf) is display-level. Keep only
            # realized_corr from sim_results — the sole field the dashboard reads;
            # the rest of sim_results held S_paths (a duplicate of sim_prices)
            # plus V_paths, ~2/3 of the run's memory for data never read again.
            # grid_dates / div_schedule were write-only and are dropped too.
            st.session_state["results"] = {
                **note_results,
                "worst_of_paths": wof_paths.astype(np.float32),
                "sim_prices":     sim_prices.astype(np.float32),
                "asset_names":    list(selected_tickers.values()),
                "s0_values":      s0_values,
                "params":         cal_result.params,
                "corr_SS":        cal_result.corr_SS,
                "realized_corr":  sim_results["realized_corr"],
                "t_dof":          cal_result.t_dof,
                "terms_snapshot": terms.to_dict(),
                # Real-calendar grid metadata (drives charts + obs tables)
                "t_grid_years":   np.concatenate([[0.0], np.cumsum(_dt_grid)]),
                "obs_steps":      _obs_steps,
                "obs_times":      _obs_times,
            }
            st.session_state["last_asset_names"] = list(selected_tickers.values())
            st.session_state["path_num"] = 0
            st.rerun()

    # ── Tab structure (always rendered) ──────────────────────────────────
    R        = st.session_state["results"]   # None until simulation runs
    _has_sim = R is not None

    # Resolve live issue date
    _live_issue_date = terms.issue_date
    if not _live_issue_date and _has_sim:
        _live_issue_date = NoteTerms.from_dict(R["terms_snapshot"]).issue_date
    # Live tracking only makes sense once the note has actually started
    # trading; a future issue date is stored but doesn't get the tab yet.
    _has_live = bool(_live_issue_date) and pd.Timestamp(_live_issue_date) <= pd.Timestamp.today()

    # Build run_terms (needed inside MC tab — falls back to terms when no sim yet)
    if _has_sim:
        run_terms = NoteTerms.from_dict(R["terms_snapshot"])
        if _live_issue_date and run_terms.issue_date != _live_issue_date:
            run_terms = NoteTerms.from_dict({**R["terms_snapshot"], "issue_date": _live_issue_date})
        asset_names = R.get("asset_names") or st.session_state.get("last_asset_names") or list(selected_tickers.values())
        wof_paths   = R["worst_of_paths"]
        sim_prices  = R["sim_prices"]
        N           = wof_paths.shape[1] - 1
        # Real-calendar grid (stored by the run block); fall back to the old
        # uniform grid for results cached before this feature.
        t_grid      = R.get("t_grid_years")
        if t_grid is None:
            t_grid = np.linspace(0, run_terms.maturity, N + 1)
        obs_steps_i = R.get("obs_steps") or run_terms.obs_steps(N)
        obs_times_l = R.get("obs_times") or run_terms.obs_times()
        obs_pairs   = [(f"P{i+1}", t) for i, t in enumerate(obs_times_l)]
        # Step-down autocall barrier: pass the per-observation schedule to charts
        # so the line follows the decline (None for constant-barrier notes).
        _ac_levels   = run_terms.autocall_barrier_schedule()
        _ac_sched_t  = list(zip(obs_times_l, _ac_levels)) if run_terms.autocall_step_down else None
        _ac_sched_st = list(zip(obs_steps_i, _ac_levels)) if run_terms.autocall_step_down else None
    else:
        run_terms = terms
        _ac_sched_t = _ac_sched_st = None

    if _has_live:
        tab_mc, tab_bt, tab_live = st.tabs([tr("tab_monte_carlo"), tr("tab_historical_backtest"), tr("tab_current_performance")])
    else:
        tab_mc, tab_bt = st.tabs([tr("tab_monte_carlo"), tr("tab_historical_backtest")])
        tab_live = None

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — MONTE CARLO
    # ══════════════════════════════════════════════════════════════════
    with tab_mc:
        if not _has_sim:
            st.info(tr("mc_click_run_info"))
            with st.spinner(tr("mc_prefetch_spinner", tickers=', '.join(selected_tickers.values()))):
                try:
                    _load_prices(tickers_tuple, years=st.session_state.get("history_years", None))
                    st.success(tr("mc_market_ready"))
                except Exception as e:
                    st.error(tr("mc_fetch_failed", e=e))
        else:
            st.success(tr("sim_complete"))
            # Build the three headline MC figures ONCE per rerun and reuse the
            # same objects for both the on-screen tabs and the PDF cache. Each
            # of these runs np.percentile over the full (2·n_paths × N) array,
            # so building them twice (once here, once for display) doubled that
            # cost every rerun. They must still rebuild each rerun because the
            # Translator language can change. _fig_to_png copies the figure
            # before rasterising, so sharing the object with st.plotly_chart is
            # safe. (Language change → full script rerun → figures rebuilt.)
            _fig_irr = build_irr_distribution(
                R["annualized_returns"], R["autocall_events"],
                R["expected_irr"], run_terms.coupon_pa, tr,
            )
            _fig_wof = build_wof_fan(
                wof_paths, t_grid, run_terms.knock_in_barrier, obs_pairs, tr,
                autocall_barrier=run_terms.autocall_barrier,
                autocall_schedule=_ac_sched_t,
            )
            _fig_corr_input = build_corr_heatmap(R["corr_SS"], asset_names, tr("corr_input"))
            # Cache MC figures for PDF generation (used by sidebar PDF button)
            st.session_state["_pdf_mc_figures"] = {
                "irr_dist": _fig_irr,
                "wof_fan":  _fig_wof,
                "corr":     _fig_corr_input,
            }
            # ── Summary metrics (two rows of 3) ──────────────────────
            st.header(tr("summary_stats_header"))
            _ki_mask = R.get("knock_in_triggered")
            _lgki_str = (
                f"{float(R['annualized_returns'][_ki_mask].mean()):.2%}"
                if _ki_mask is not None and _ki_mask.any()
                else "—"
            )
            c1, c2, c3 = st.columns(3)
            c1.metric(tr("expected_irr_pa"),        f"{R['expected_irr']:.2%}",
                      help=tr("mc_help_expected_irr"))
            c2.metric(tr("expected_total_return"),  f"{R['expected_total_return']:.2%}",
                      help=tr("mc_help_expected_return"))
            c3.metric(tr("expected_coupon_metric"), f"{R['expected_coupon']:.2%}",
                      help=tr("mc_help_expected_coupon"))
            c4, c5, c6 = st.columns(3)
            c4.metric(tr("prob_autocalled"),        f"{R['prob_autocall']:.2%}",
                      help=tr("mc_help_prob_autocall"))
            c5.metric(tr("prob_knock_in_metric"),   f"{R['prob_knock_in_total']:.2%}",
                      help=tr("mc_help_prob_knock_in"))
            c6.metric(tr("loss_given_ki_metric"),   _lgki_str,
                      help=tr("mc_help_loss_given_ki"))
            if R.get("prob_rescued", 0) > 0:
                st.caption(
                    tr("barrier_rescued_caption",
                       barrier=R['prob_barrier_event'],
                       rescued=R['prob_rescued'],
                       basket=terms.final_basket.replace('_', '-'),
                       level=terms.final_redemption_barrier)
                )

            with st.expander(tr("autocall_by_period_expander"), expanded=False):
                prob_by_period = R["prob_autocall_by_period"]
                ac_df = pd.DataFrame({
                    tr("col_period"):    range(1, run_terms.n_obs + 1),
                    tr("col_time_y"):    [f"{t:.3g}" for t in obs_times_l],
                    tr("col_p_autocall"): [f"{p:.2%}" for p in prob_by_period],
                    tr("col_eligible"): [tr("yes") if i + 1 >= run_terms.autocall_start_period else tr("no_str")
                                     for i in range(run_terms.n_obs)],
                })
                st.dataframe(ac_df, use_container_width=True, hide_index=True)

            st.markdown("---")

            mc_tab1, mc_tab2, mc_tab3, mc_tab4 = st.tabs([
                tr("mc_subtab_payoff"), tr("mc_subtab_paths"),
                tr("mc_subtab_explorer"), tr("mc_subtab_corr"),
            ])

            with mc_tab1:
                st.subheader(tr("irr_dist_subheader"))
                st.plotly_chart(_fig_irr, use_container_width=True)
                if R["prob_knock_in_total"] > 0:
                    st.info(tr("knock_in_info", pct=R['prob_knock_in_total'],
                               barrier=run_terms.knock_in_barrier))

            with mc_tab2:
                st.subheader(tr("price_paths_subheader"))
                st.markdown(tr("wof_basket_md"))
                st.plotly_chart(_fig_wof, use_container_width=True)
                st.markdown(tr("individual_paths_md"))
                for i, name in enumerate(asset_names):
                    st.plotly_chart(
                        build_fan_chart(sim_prices[:, :, i], name, t_grid, obs_pairs, tr),
                        use_container_width=True,
                    )

            # P2: isolate the path explorer in a fragment so its Random/Prev/Next
            # buttons rerun ONLY this block, not every tab (the backtest + live
            # tabs no longer rebuild on a path step). It closes over the last
            # full run's arrays, which are stable until the next Run Simulation.
            @st.fragment
            def _mc_path_explorer():
                st.subheader(tr("single_path_subheader"))
                max_path = sim_prices.shape[0] - 1
                pc1, pc2, pc3 = st.columns(3)
                if pc1.button(tr("btn_random")):
                    st.session_state["path_num"] = random.randint(0, max_path)
                if pc2.button(tr("btn_prev")):
                    st.session_state["path_num"] = max(0, st.session_state["path_num"] - 1)
                if pc3.button(tr("btn_next")):
                    st.session_state["path_num"] = min(max_path, st.session_state["path_num"] + 1)

                pn = st.session_state["path_num"]
                st.caption(tr("path_caption", n=pn, total=max_path))
                obs_labels = [lbl for lbl, _ in obs_pairs]

                path_df = pd.DataFrame(
                    {n: sim_prices[pn, :, i] for i, n in enumerate(asset_names)}
                )
                st.plotly_chart(
                    build_path_price_chart(path_df, pn, obs_steps_i, obs_labels, tr),
                    use_container_width=True,
                )
                autocall_q    = int(R["autocall_events"][pn])
                s0_arr        = np.array(R.get("s0_values") or [p.S0 for p in R["params"]])
                asset_perf_pn = sim_prices[pn] / s0_arr[np.newaxis, :]
                st.plotly_chart(
                    build_path_wof_chart(
                        wof_paths[pn], autocall_q, obs_steps_i, obs_labels,
                        run_terms.knock_in_barrier, pn, tr,
                        asset_paths=asset_perf_pn, asset_names=asset_names,
                        autocall_barrier=run_terms.autocall_barrier,
                        autocall_schedule=_ac_sched_st,
                    ),
                    use_container_width=True,
                )

                principal = float(R["principal_payoffs"][pn])
                coupons   = float(R["coupon_payoffs"][pn])
                irr       = float(R["annualized_returns"][pn])
                worst_f   = float(wof_paths[pn, -1])
                ki        = bool(R["knock_in_triggered"][pn])

                if autocall_q > 0:
                    t_q = obs_times_l[autocall_q - 1]
                    st.markdown(tr("autocalled_at_md", q=autocall_q, t=t_q))
                elif ki:
                    st.markdown(tr("maturity_knock_in_md", wof=worst_f))
                else:
                    st.markdown(tr("maturity_no_knock_in_md", wof=worst_f))

                mc1, mc2, mc3 = st.columns(3)
                mc1.metric(tr("metric_principal"), f"{principal:.2%}",
                           help=tr("mc_help_principal"))
                mc2.metric(tr("metric_coupons"),   f"{coupons:.2%}",
                           help=tr("mc_help_coupons"))
                mc3.metric(tr("metric_irr_pa"),    f"{irr:.2%}",
                           help=tr("mc_help_irr_pa"))

                # Per-asset final performance with logos
                _disp_to_sym_pe = {disp: sym for sym, disp in selected_tickers.items()}
                _pe_cols = st.columns(len(asset_names))
                for _pe_i, (_pe_name, _pe_col) in enumerate(zip(asset_names, _pe_cols)):
                    _pe_sym = _disp_to_sym_pe.get(_pe_name, "")
                    _pe_logo = TICKER_LOGOS.get(_pe_sym, "")
                    _pe_logo_html = (
                        f"<img src='{_pe_logo}' width='24' height='24' "
                        f"style='border-radius:4px;vertical-align:middle;margin-right:4px;' "
                        f"onerror=\"this.style.display='none'\"/>"
                        if _pe_logo else ""
                    )
                    _pe_final = float(asset_perf_pn[-1, _pe_i])
                    _pe_col.markdown(
                        f"{_pe_logo_html}<b style='vertical-align:middle;'>{_pe_name}</b>",
                        unsafe_allow_html=True,
                    )
                    _pe_col.metric(tr("mc_final_perf"), f"{_pe_final:.1%}")

            with mc_tab3:
                _mc_path_explorer()

            with mc_tab4:
                st.subheader(tr("corr_diag_subheader"))
                corr_SS       = R["corr_SS"]
                # realized_corr is the only field kept from the simulator's full
                # output (P1); fall back to the legacy nested key for any results
                # dict cached in session before that change.
                realized_corr = R.get("realized_corr")
                if realized_corr is None:
                    realized_corr = R["sim_results"]["realized_corr"]
                diff          = realized_corr - corr_SS
                hm1, hm2, hm3 = st.columns(3)
                hm1.plotly_chart(_fig_corr_input,                                                     use_container_width=True)
                hm2.plotly_chart(build_corr_heatmap(realized_corr, asset_names, tr("corr_realized")), use_container_width=True)
                hm3.plotly_chart(build_corr_heatmap(diff, asset_names, tr("corr_difference"),
                                                      zmin=-0.1, zmax=0.1),                  use_container_width=True)
                max_err = float(np.max(np.abs(diff - np.diag(np.diag(diff)))))
                _corr_quality = (tr("corr_quality_good") if max_err < 0.02
                                 else tr("corr_quality_acceptable") if max_err < 0.05
                                 else tr("corr_quality_elevated"))
                (st.success if max_err < 0.05 else st.warning)(
                    tr("corr_max_err_message", err=max_err, quality=_corr_quality)
                )
                st.markdown("---")
                st.subheader(tr("calib_heston_subheader"))
                _disp_to_sym = {disp: sym for sym, disp in selected_tickers.items()}
                rows = []
                for p in R["params"]:
                    ok, _ = p.feller_condition()
                    _sym = _disp_to_sym.get(p.name, "")
                    _logo_url = TICKER_LOGOS.get(_sym, "")
                    _logo_html = (
                        f"<img src='{_logo_url}' width='24' height='24' "
                        f"style='border-radius:4px;vertical-align:middle;margin-right:6px;' "
                        f"onerror=\"this.style.display='none'\"/>"
                        if _logo_url else ""
                    )
                    rows.append({
                        tr("asset"): f"{_logo_html}{p.name}", "S₀": f"{p.S0:.1f}",
                        "μ p.a.": f"{p.mu*100:.1f}%",
                        "V₀ σ":   f"{np.sqrt(p.V0)*100:.1f}%",
                        "θ σ LR": f"{np.sqrt(p.theta)*100:.1f}%",
                        "κ": f"{p.kappa:.3f}", "ξ": f"{p.xi:.3f}", "ρ": f"{p.rho:.3f}",
                        tr("heston_col_feller"): tr("heston_feller_pass") if ok else tr("heston_feller_warn"),
                    })
                _heston_cols = [tr("asset"), "S₀", "μ p.a.", "V₀ σ", "θ σ LR", "κ", "ξ", "ρ", tr("heston_col_feller")]
                _th_cells = "".join(
                    f"<th style='padding:4px 8px;text-align:left;border-bottom:1px solid #ddd;white-space:nowrap;'>{c}</th>"
                    for c in _heston_cols
                )
                _heston_rows_html = "".join(
                    "<tr>" + "".join(
                        f"<td style='padding:4px 8px;vertical-align:middle;white-space:nowrap;'>{row[c]}</td>"
                        for c in _heston_cols
                    ) + "</tr>"
                    for row in rows
                )
                st.markdown(
                    f"<div style='overflow-x:auto'><table style='border-collapse:collapse;width:100%'>"
                    f"<thead><tr>{_th_cells}</tr></thead>"
                    f"<tbody>{_heston_rows_html}</tbody>"
                    f"</table></div>",
                    unsafe_allow_html=True,
                )
                st.caption(tr("heston_column_guide"))
                st.info(tr("t_copula_dof", v=R.get('t_dof', 'N/A')))


    # ══════════════════════════════════════════════════════════════════
    # TAB 2 — HISTORICAL BACKTEST
    # ══════════════════════════════════════════════════════════════════
    with tab_bt:
        st.header(tr("bt_tab_header"))
        st.markdown(tr("bt_tab_intro"))

        # ── Load full price history for backtest path explorer ────────────
        # Use the same history_years that the user selected — avoids pulling
        # period='max' when an underlying (e.g. PLTR) has a short history and
        # a max-history download returns fewer rows than the backtest needs.
        _history_years = st.session_state.get("history_years", None)
        try:
            _all_prices = _load_prices(tickers_tuple, years=_history_years)
        except Exception:
            _all_prices = None

        import datetime as _dt

        # ── Feasibility check ─────────────────────────────────────────
        # run_backtest needs one full CALENDAR maturity window of realized
        # prices after the first issue date. Surface this up-front instead of
        # letting run_backtest raise into a red error box. NOTE: do not use
        # st.stop() here — it would abort the whole script and kill the
        # Current Performance tab that renders after this one.
        _mat_months   = round(terms.maturity * 12)
        _bt_feasible  = (
            _all_prices is not None
            and _all_prices.index[0] + pd.DateOffset(months=_mat_months) <= _all_prices.index[-1]
        )

        if _all_prices is None:
            st.warning(tr("bt_no_price_history"))
        elif not _bt_feasible:
            st.warning(
                tr("bt_not_enough_history", mat=terms.maturity,
                   start=_all_prices.index[0].date(),
                   end=_all_prices.index[-1].date())
            )

        if not _bt_feasible:
            bt, bt_summary = pd.DataFrame(), {}
        else:
            # ── Valid issue-date bounds ───────────────────────────────────
            # Bound the pickers by the range run_backtest will actually accept,
            # NOT the raw price range — otherwise selections in the invalid head/
            # tail are silently clamped and 'Apply' appears to do nothing.
            _min_date = _all_prices.index[0].date()
            _max_date = (_all_prices.index[-1] - pd.DateOffset(months=_mat_months)).date()
            st.caption(
                tr("bt_valid_dates_caption",
                   start=_min_date, end=_max_date, mat=terms.maturity,
                   hist_start=_all_prices.index[0].date(),
                   hist_end=_all_prices.index[-1].date())
            )

            # ── Reset picker state when the note / data context changes ──────
            # The date pickers are keyed widgets: Streamlit ignores value= after
            # the first render and keeps the old state in session. Switching note
            # (e.g. HSBC banks → BBVA with PLTR's short history) changes min/max,
            # and a stale out-of-range value raises StreamlitAPIException. Reset
            # all backtest date state whenever the context fingerprint changes.
            _bt_fingerprint = (tickers_tuple, _history_years, terms.maturity, terms.payment_freq)
            if st.session_state.get("bt_fingerprint") != _bt_fingerprint:
                st.session_state["bt_fingerprint"] = _bt_fingerprint
                for _k in ("bt_start_picker", "bt_end_picker",
                           "bt_start_default", "bt_end_default"):
                    st.session_state.pop(_k, None)

            def _clamp_date(d):
                if d is None:
                    return None
                if d < _min_date:
                    return _min_date
                if d > _max_date:
                    return _max_date
                return d

            # ── Date range pickers ────────────────────────────────────────
            _bt_start_default = _clamp_date(st.session_state.get("bt_start_default", _min_date))
            _bt_end_default   = _clamp_date(st.session_state.get("bt_end_default",   _max_date))

            bdc1, bdc2, bdc3 = st.columns([2, 2, 1])
            with bdc1:
                bt_start_val = st.date_input(
                    tr("bt_start_label"),
                    value=_bt_start_default,
                    min_value=_min_date,
                    max_value=_max_date,
                    key="bt_start_picker",
                )
            with bdc2:
                bt_end_val = st.date_input(
                    tr("bt_end_label"),
                    value=_bt_end_default,
                    min_value=_min_date,
                    max_value=_max_date,
                    key="bt_end_picker",
                )
            with bdc3:
                st.markdown("<br>", unsafe_allow_html=True)
                apply_bt = st.button(tr("bt_apply_btn"), key="bt_apply_btn", use_container_width=True)

            # Only commit the new date range when the user clicks Apply.
            # This prevents an expensive backtest rerun on every keystroke.
            if apply_bt:
                if bt_start_val > bt_end_val:
                    st.warning(tr("bt_date_order_warning"))
                else:
                    st.session_state["bt_start_default"] = bt_start_val
                    st.session_state["bt_end_default"]   = bt_end_val

            # Use the last confirmed values (clamped to the current valid range)
            # as the actual filter passed to the backtest.
            _confirmed_start = _clamp_date(st.session_state.get("bt_start_default", _min_date))
            _confirmed_end   = _clamp_date(st.session_state.get("bt_end_default",   _max_date))
            bt_start_str = str(_confirmed_start) if _confirmed_start else None
            bt_end_str   = str(_confirmed_end)   if _confirmed_end   else None

            with st.spinner(tr("bt_running")):
                try:
                    bt, bt_summary = _run_backtest_cached(
                        tickers_tuple, terms.to_json(),
                        bt_start_str=bt_start_str,
                        bt_end_str=bt_end_str,
                        history_years=st.session_state.get("history_years", None),
                    )
                except Exception as e:
                    st.error(tr("bt_failed", e=e))
                    bt, bt_summary = pd.DataFrame(), {}

        if bt.empty:
            st.warning(tr("bt_no_results"))
        else:
            # Outcome labels are localized for display; the color_map keys use the
            # same translated strings so the chart legend and palette stay aligned.
            _bt_maturity   = tr("bt_outcome_maturity")
            _bt_knock_in   = tr("bt_outcome_knock_in")
            bt["Outcome"] = bt["Call Quarter"].map(
                {0: _bt_maturity, **{i: tr("bt_outcome_autocalled_p", i=i) for i in range(1, terms.n_obs + 1)}}
            )
            bt.loc[(bt["Call Quarter"] == 0) & bt["Knock-in"], "Outcome"] = _bt_knock_in
            # Navy/blue institutional palette (matches charts.py + PDF):
            # Maturity = warm grey, Knock-in = red, Autocalls = navy→light-blue ramp.
            color_map = {
                _bt_maturity: "#6b7280", _bt_knock_in: "#dc2626",
                **{tr("bt_outcome_autocalled_p", i=i):
                   f"hsl(217,{max(35, 70 - i*3)}%,{min(70, 28 + i*5)}%)"
                   for i in range(1, terms.n_obs + 1)},
            }

            _bt_ki_rows = bt[bt["Knock-in"]] if not bt.empty else pd.DataFrame()
            _bt_lgki_str = (
                f"{float(_bt_ki_rows['IRR'].mean()):.2%}"
                if not _bt_ki_rows.empty
                else "—"
            )
            b1, b2, b3 = st.columns(3)
            b1.metric(tr("bt_metric_issue_dates"),    str(bt_summary.get("n_issues", 0)),
                      help=tr("bt_help_issue_dates"))
            b2.metric(tr("bt_metric_mean_irr"),       f"{bt_summary.get('mean_irr', 0):.2%}",
                      help=tr("bt_help_mean_irr"))
            b3.metric(tr("bt_metric_median_irr"),     f"{bt_summary.get('median_irr', 0):.2%}",
                      help=tr("bt_help_median_irr"))
            b4, b5, b6 = st.columns(3)
            b4.metric(tr("bt_metric_knock_in_pct"),   f"{bt_summary.get('prob_knock_in', 0):.1%}",
                      help=tr("bt_help_knock_in_pct"))
            b5.metric(tr("bt_metric_autocalled_pct"), f"{bt_summary.get('prob_called', 0):.1%}",
                      help=tr("bt_help_autocalled_pct"))
            b6.metric(tr("loss_given_ki_metric"),     _bt_lgki_str,
                      help=tr("bt_help_loss_given_ki"))

            _bt_outcome_fig = build_backtest_outcome_bar(bt, color_map, tr)
            _bt_irr_fig     = build_backtest_irr_scatter(bt, color_map, tr)
            col1, col2 = st.columns(2)
            col1.plotly_chart(_bt_outcome_fig,                   use_container_width=True)
            col2.plotly_chart(build_worst_asset_pie(bt, tr),     use_container_width=True)
            st.plotly_chart(_bt_irr_fig,                         use_container_width=True)
            # Cache for PDF — augment bt_summary with loss-given-KI
            _pdf_bt_summary = dict(bt_summary)
            if not _bt_ki_rows.empty:
                _pdf_bt_summary["loss_given_ki"] = float(_bt_ki_rows["IRR"].mean())
            st.session_state["_pdf_bt_summary"] = _pdf_bt_summary
            st.session_state["_pdf_bt_figures"] = {"outcome": _bt_outcome_fig, "irr_scatter": _bt_irr_fig}

            try:
                # P4: this chart plots max-history daily closes (decades ×
                # n_assets points) and re-serialises to the browser every rerun.
                # Downsample to weekly for DISPLAY only — visually identical at
                # this scale, a fraction of the JSON payload. Raw daily prices are
                # still used everywhere the payoff is evaluated.
                _hist_chart_prices = (
                    _load_prices(tickers_tuple, years=None)
                    .resample("W-FRI").last().dropna()
                )
                bt_start_mark = bt["Issue Date"].min()
                bt_end_mark   = bt["Issue Date"].max()
                st.plotly_chart(build_historical_prices(_hist_chart_prices, bt_start_mark, bt_end_mark, tr),
                                use_container_width=True)
            except Exception:
                pass

            # P2: the issue-date selector reruns ONLY this fragment, so picking
            # a different historical issue no longer rebuilds the MC tab, the
            # backtest summary charts, or the live tab. Closes over bt /
            # _all_prices / terms from the last full run (stable until rerun).
            @st.fragment
            def _bt_path_explorer():
                st.subheader(tr("bt_path_explorer_header"))
                st.caption(tr("bt_path_explorer_caption"))

                issue_dates = sorted(bt["Issue Date"].unique())

                _prev_dates = st.session_state.get("bt_issue_dates_list", [])
                if list(issue_dates) != list(_prev_dates):
                    st.session_state["bt_issue_dates_list"] = list(issue_dates)
                    st.session_state["bt_issue_idx"] = 0

                _issue_idx = min(st.session_state.get("bt_issue_idx", 0), len(issue_dates) - 1)

                selected_issue = st.selectbox(
                    tr("bt_issue_date_select"),
                    issue_dates,
                    index=_issue_idx,
                    format_func=lambda d: d.strftime("%Y-%m-%d"),
                    key="bt_issue_selector",
                )

                if selected_issue is not None:
                    row = bt[bt["Issue Date"] == selected_issue].iloc[0]
                    st.markdown(
                        f"{tr('bt_outcome_label', outcome=row['Outcome'])} &nbsp;|&nbsp; "
                        f"{tr('bt_irr_label', irr=row['IRR'])} &nbsp;|&nbsp; "
                        f"{tr('bt_worst_asset_label', asset=row['Worst Asset'], perf=row['Worst Final Perf'])}"
                    )
                    try:
                        if _all_prices is not None:
                            # Same calendar-first snapping run_backtest uses, so the
                            # chart markers sit exactly on the evaluated dates.
                            _pe_anchor, _pe_obs_dates = snapped_obs_dates(
                                _all_prices, terms, selected_issue)
                            _pe_sched = (
                                list(zip(_pe_obs_dates, terms.autocall_barrier_schedule()))
                                if terms.autocall_step_down else None
                            )
                            st.plotly_chart(
                                build_historical_wof_path(
                                    _all_prices,
                                    issue_date        = _pe_anchor,
                                    obs_dates         = _pe_obs_dates,
                                    knock_in_barrier  = terms.knock_in_barrier,
                                    autocall_barrier  = terms.autocall_barrier,
                                    coupon_barrier    = terms.coupon_barrier,
                                    call_quarter      = int(row["Call Quarter"]),
                                    tr                = tr,
                                    autocall_schedule = _pe_sched,
                                    coupon_at_autocall_only = terms.coupon_at_autocall_only,
                                ),
                                use_container_width=True,
                            )
                    except Exception as e:
                        st.error(tr("bt_could_not_build_path", e=e))

            _bt_path_explorer()


    # ══════════════════════════════════════════════════════════════════
    # TAB 3 — CURRENT PERFORMANCE (only if issue_date is set)
    # ══════════════════════════════════════════════════════════════════
    if tab_live is not None:
        with tab_live:
            import datetime as _dt
            _issue_ts  = pd.Timestamp(run_terms.issue_date)
            _today_ts  = pd.Timestamp(_dt.date.today())
            # Calendar maturity: issue + tenor in months (term-sheet convention)
            _mat_ts    = _issue_ts + pd.DateOffset(months=round(run_terms.maturity * 12))

            # How far through the note's life are we?
            _elapsed_days = (_today_ts - _issue_ts).days
            _elapsed_years = _elapsed_days / 365.25
            _remaining_years = run_terms.maturity - _elapsed_years
            _pct_elapsed = min(_elapsed_years / run_terms.maturity, 1.0)

            st.markdown(
                tr("live_tab_header_md",
                   issue=_issue_ts.date(), mat=_mat_ts.date(),
                   elapsed=_elapsed_years, remaining=max(_remaining_years, 0))
            )
            st.progress(min(_pct_elapsed, 1.0))

            # Fetch live prices (raw closes — what the term sheet observes)
            try:
                _full_prices = _load_prices(tickers_tuple, years=None)
                # Snap the issue date to the trading calendar; observation
                # dates follow the same calendar-first rule as the backtest.
                _issue_idx_full = int(_full_prices.index.searchsorted(_issue_ts))
                if _issue_idx_full >= len(_full_prices):
                    _issue_idx_full = len(_full_prices) - 1
                _anchor_live = _full_prices.index[_issue_idx_full]
                if (_anchor_live - _issue_ts).days > 7:
                    st.warning(
                        tr("live_history_warning",
                           anchor=_anchor_live.date(), issue=_issue_ts.date())
                    )
                _live_prices = _full_prices.iloc[_issue_idx_full:]

                if len(_live_prices) < 2:
                    st.warning(tr("live_not_enough_data"))
                else:
                    _S0          = _full_prices.iloc[_issue_idx_full].values.astype(float)
                    _today_slice = _live_prices[_live_prices.index <= _today_ts]
                    _perf_today  = _today_slice.iloc[-1].values / _S0
                    _wof_today   = float(_perf_today.min())
                    _worst_asset_today = asset_names[int(_perf_today.argmin())]
                    # Calendar observation dates (unsnapped) + snap where data exists
                    _obs_cal     = run_terms.obs_calendar_dates(_anchor_live)
                    _ac_sched_lv = run_terms.autocall_barrier_schedule()

                    # ── Live summary metrics ──────────────────────────
                    _lc1, _lc2, _lc3, _lc4 = st.columns(4)
                    _lc1.metric(tr("live_metric_wof_today"),  f"{_wof_today:.1%}",
                                delta=tr("live_metric_vs_strike", v=_wof_today - 1.0),
                                help=tr("live_help_wof_today"))
                    _lc2.metric(tr("live_metric_worst_asset"), _worst_asset_today,
                                help=tr("live_help_worst_asset"))
                    # Autocall buffer uses the barrier for the next upcoming
                    # observation period, not the flat initial barrier — for
                    # step-down notes these differ after the first callable period.
                    _next_obs_idx = next(
                        (i for i, d in enumerate(_obs_cal)
                         if pd.Timestamp(d) > _today_ts),
                        len(_ac_sched_lv) - 1,
                    )
                    _next_ac_barrier = float(_ac_sched_lv[_next_obs_idx])
                    _ki_buf  = _wof_today - run_terms.knock_in_barrier
                    _ac_buf  = _wof_today - _next_ac_barrier
                    _lc3.metric(tr("live_metric_ki_buffer"),
                                f"{_ki_buf:+.1%}",
                                delta=tr("live_delta_barrier_ref",
                                         barrier=run_terms.knock_in_barrier),
                                delta_color="off",
                                help=tr("live_help_ki_buffer", barrier=run_terms.knock_in_barrier))
                    _lc4.metric(tr("live_metric_ac_buffer"),
                                f"{_ac_buf:+.1%}",
                                delta=tr("live_delta_autocall_ref",
                                         barrier=_next_ac_barrier),
                                delta_color="off",
                                help=tr("live_help_ac_buffer", barrier=_next_ac_barrier))

                    # ── Per-asset current performance ─────────────────
                    st.markdown(tr("live_asset_perf_header"))
                    _live_disp_to_sym = {disp: sym for sym, disp in selected_tickers.items()}
                    _asset_cols = st.columns(len(asset_names))
                    for _i, (_aname, _acol) in enumerate(zip(asset_names, _asset_cols)):
                        _ap = float(_perf_today[_i])
                        _live_sym = _live_disp_to_sym.get(_aname, "")
                        _live_logo = (TICKER_LOGOS.get(_live_sym) or _LOGO_BASE.format(sym=_live_sym)) if _live_sym else None
                        if _live_logo:
                            _acol.markdown(
                                f"<img src='{_live_logo}' width='24' height='24' "
                                f"style='border-radius:4px;vertical-align:middle;margin-right:4px;' "
                                f"onerror=\"this.style.display='none'\"/>"
                                f"<b style='vertical-align:middle;'>{_aname}</b>",
                                unsafe_allow_html=True,
                            )
                            _acol.metric("", f"{_ap:.1%}", tr("live_metric_vs_strike", v=_ap - 1.0))
                        else:
                            _acol.metric(_aname, f"{_ap:.1%}", tr("live_metric_vs_strike", v=_ap - 1.0))

                    # ── Coupon status replay (shared engine logic) ────────
                    # All payoff semantics (memory, step-down autocall
                    # schedule, coupon_at_autocall_only) come from
                    # core.note.replay_note — never reimplement them here.
                    st.markdown(tr("live_obs_history_header"))
                    _k_period     = tr("live_col_period")
                    _k_date       = tr("live_col_date")
                    _k_status     = tr("live_col_status")
                    _k_wof        = tr("live_col_wof")
                    _k_coupon     = tr("live_col_coupon")
                    _k_cumulative = tr("live_col_cumulative")

                    # Snap each calendar obs date to the trading calendar;
                    # collect the ones that have already happened.
                    _obs_snapped: list = []          # (date or None, is_past)
                    for _d in _obs_cal:
                        _j = int(_full_prices.index.searchsorted(_d))
                        if _j < len(_full_prices) and _full_prices.index[_j] <= _today_ts:
                            _obs_snapped.append(_full_prices.index[_j])
                        else:
                            _obs_snapped.append(None)   # upcoming (show calendar date)

                    _past_dates = [d for d in _obs_snapped if d is not None]
                    if _past_dates:
                        _perf_obs = np.vstack(
                            [_full_prices.loc[d].values / _S0 for d in _past_dates])
                    else:
                        _perf_obs = np.empty((0, len(_S0)))
                    _replay = replay_note(_perf_obs, run_terms)

                    _obs_rows = []
                    _obs_markers = []        # for the live chart
                    _running_total = 0.0
                    for _q, _label in enumerate(obs_labels):
                        _snap = _obs_snapped[_q] if _q < len(_obs_snapped) else None
                        if _q >= len(_replay["rows"]) or _snap is None:
                            # Upcoming — or after an autocall terminated the note
                            if _replay["autocall_period"] and _q + 1 > _replay["autocall_period"]:
                                break                       # note no longer exists
                            _est = _obs_cal[_q].date() if _q < len(_obs_cal) else tr("live_obs_dash")
                            _obs_rows.append({
                                _k_period: _label, _k_date: str(_est),
                                _k_status: tr("live_status_upcoming"),
                                _k_wof: tr("live_obs_dash"), _k_coupon: tr("live_obs_dash"),
                                _k_cumulative: tr("live_obs_dash"),
                            })
                            continue

                        _r        = _replay["rows"][_q]
                        _obs_wof  = float(_perf_obs[_q].min())
                        _running_total += _r["coupon_amount"]
                        if _r["autocalled"]:
                            _status = tr("live_status_autocalled")
                        elif run_terms.coupon_at_autocall_only:
                            _status = tr("live_status_no_coupon")
                        elif _r["coupon_met"]:
                            _status = tr("live_status_coupon_paid")
                        else:
                            _status = tr("live_status_coupon_missed")
                        _obs_rows.append({
                            _k_period:     _label,
                            _k_date:       str(_snap.date()),
                            _k_status:     _status,
                            _k_wof:        f"{_obs_wof:.1%}",
                            _k_coupon:     f"{_r['coupon_amount']:.4%}" if _r["coupon_amount"] > 0 else tr("live_obs_dash"),
                            _k_cumulative: f"{_running_total:.4%}",
                        })
                        _obs_markers.append({
                            "date":       _snap,
                            "label":      _label,
                            "wof":        _obs_wof,
                            "autocalled": _r["autocalled"],
                            "paid":       _r["coupon_met"] or _r["coupon_amount"] > 0,
                            "amount":     _r["coupon_amount"],
                        })
                        if _r["autocalled"]:
                            break

                    _obs_df = pd.DataFrame(_obs_rows)
                    st.dataframe(_obs_df, use_container_width=True, hide_index=True)

                    _pending_coupons    = _replay["pending_coupons"]
                    _total_coupons_paid = _replay["total_coupons"]
                    if _pending_coupons > 0:
                        st.info(
                            tr("live_pending_coupons_info",
                               n=_pending_coupons,
                               val=_pending_coupons * run_terms.coupon_rate,
                               barrier=run_terms.coupon_barrier)
                        )
                    if run_terms.coupon_at_autocall_only and not _replay["autocall_period"]:
                        st.info(
                            tr("live_growth_premium_info",
                               rate=run_terms.coupon_rate,
                               pa=run_terms.coupon_pa,
                               next_premium=run_terms.coupon_rate * (len(_replay['rows']) + 1))
                        )

                    _irr_to_date = _total_coupons_paid / max(_elapsed_years, 1/252)
                    st.metric(tr("live_coupon_irr_metric"), f"{_irr_to_date:.2%}",
                              help=tr("live_help_coupon_irr"))

                    # ── Live performance chart ────────────────────────
                    # Future observation reference lines (calendar dates),
                    # only while the note is still alive.
                    if _replay["autocall_period"]:
                        _future_obs = []
                    else:
                        _future_obs = [
                            (obs_labels[_q], _obs_cal[_q])
                            for _q in range(len(_replay["rows"]), run_terms.n_obs)
                        ]
                    _live_sched = (
                        [(d, _ac_sched_lv[_q]) for _q, d in enumerate(_obs_cal)]
                        if run_terms.autocall_step_down else None
                    )
                    _live_fig = build_live_performance_chart(
                        hist_prices        = _live_prices,
                        issue_date         = _anchor_live,
                        today              = _today_ts,
                        maturity_date      = _mat_ts,
                        obs_markers        = _obs_markers,
                        future_obs         = _future_obs,
                        knock_in_barrier   = run_terms.knock_in_barrier,
                        autocall_barrier   = run_terms.autocall_barrier,
                        coupon_barrier     = run_terms.coupon_barrier,
                        tr                 = tr,
                        autocall_schedule  = _live_sched,
                    )
                    st.plotly_chart(_live_fig, use_container_width=True)
                    # Cache for PDF
                    st.session_state["_pdf_live_data"] = {
                        "wof_today":    _wof_today,
                        "worst_asset":  _worst_asset_today,
                        "perf_today":   {n: float(p) for n, p in zip(asset_names, _perf_today)},
                        "irr_to_date":  _irr_to_date,
                        "elapsed_years": _elapsed_years,
                        "obs_rows":     _obs_rows,
                    }
                    st.session_state["_pdf_live_figure"] = _live_fig

            except Exception as _e:
                st.error(tr("live_could_not_load", e=_e))

    # ══════════════════════════════════════════════════════════════════
    # PDF GENERATION (sidebar button — runs after all tab content)
    # ══════════════════════════════════════════════════════════════════
    if _pdf_btn and _has_sim:
        with st.spinner(tr("building_pdf")):
            from pdf_report import generate_pdf_report
            # Build logo URL maps from the already-populated TICKER_LOGOS dict
            _pdf_logo_urls = {
                name: (TICKER_LOGOS.get(sym) or _LOGO_BASE.format(sym=sym))
                for sym, name in run_terms.tickers.items()
            }
            # display name -> ticker symbol, so the PDF can look for a local
            # branding/ticker_logos/{SYMBOL}.png before fetching a URL.
            _pdf_logo_tickers = {name: sym for sym, name in run_terms.tickers.items()}
            _pdf_issuer_logo_url = get_issuer_logo_url(getattr(run_terms, "issuer", "") or "")
            _pdf_bytes = generate_pdf_report(
                terms            = run_terms,
                results          = R,
                asset_names      = asset_names,
                figures          = st.session_state.get("_pdf_mc_figures", {}),
                lang             = "es" if lang_choice == "Español" else "en",
                bt_summary       = st.session_state.get("_pdf_bt_summary"),
                bt_figures       = st.session_state.get("_pdf_bt_figures"),
                live_data        = st.session_state.get("_pdf_live_data"),
                live_figure      = st.session_state.get("_pdf_live_figure"),
                logo_urls        = _pdf_logo_urls,
                issuer_logo_url  = _pdf_issuer_logo_url,
                branding         = st.session_state.get("branding"),
                logo_tickers     = _pdf_logo_tickers,
            )
        _pdf_slot.download_button(
            tr("sidebar_download_pdf"),
            data=_pdf_bytes,
            file_name=f"{run_terms.name.replace(' ', '_')}_report.pdf",
            mime="application/pdf",
            key="dl_pdf_sidebar",
        )