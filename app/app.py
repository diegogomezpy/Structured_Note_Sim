"""
app/app.py  —  Streamlit entry point.
Run with:  streamlit run app/app.py
"""

import random
import sys
import pathlib

_ROOT = pathlib.Path(__file__).parent.parent
_APP  = pathlib.Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

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
_DISPLAY_TO_LABEL  = {k.split(" — ")[0]: k for k in UNDERLYING_OPTIONS.keys()}
# Also map by yfinance symbol → label for JSON loading
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

# ==========================================================================
# ─────────────────────────────────────────────────────────────────────────
#  PAGE 1 — SETUP
# ─────────────────────────────────────────────────────────────────────────
# ==========================================================================
if st.session_state["page"] == "setup":

    st.title("Structured Note Simulator")
    st.markdown("Configure the note below, then click **Confirm & Run** to load the dashboard.")
    st.divider()

    # ── JSON upload ───────────────────────────────────────────────────────
    uploaded = st.file_uploader("Upload note config (JSON) — optional",
                                 type=["json"], key="setup_upload")
    if uploaded is not None:
        try:
            raw = uploaded.read().decode()
            _parsed = NoteTerms.from_json(raw)
            # Only process if this is a newly uploaded file (different from what's stored)
            _parsed_dict = _parsed.to_dict()
            if st.session_state["loaded_terms_dict"] != _parsed_dict:
                st.session_state["loaded_terms_dict"] = _parsed_dict
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
            st.error(f"Invalid JSON: {e}")

    # Restore loaded_terms from session state so it survives reruns
    loaded_terms = (
        NoteTerms.from_dict(st.session_state["loaded_terms_dict"])
        if st.session_state["loaded_terms_dict"] is not None
        else None
    )
    if loaded_terms is not None:
        st.success(f"Config loaded: **{loaded_terms.name}**")

    base = loaded_terms or NoteTerms()

    st.divider()

    # ── Underlyings ───────────────────────────────────────────────────────
    st.subheader("Underlyings")

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
        "Select underlyings (2–5)", all_labels,
        default=default_ul,
        key="setup_underlyings",
    )

    # ── Custom ticker input ───────────────────────────────────────────────
    with st.expander("Add a custom ticker (not in the list above)"):
        st.caption("Enter any valid yfinance symbol, e.g. UBER, 2222.SR, BTC-USD")
        cc1, cc2, cc3 = st.columns([2, 2, 1])
        with cc1:
            custom_sym = st.text_input("yfinance symbol", placeholder="e.g. UBER",
                                        key="custom_sym_input").strip().upper()
        with cc2:
            custom_name = st.text_input("Display name", placeholder="e.g. Uber",
                                         key="custom_name_input").strip()
        with cc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Add", key="add_custom_btn"):
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
                    st.warning("Enter both a symbol and a display name.")

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

    # ── Note terms ────────────────────────────────────────────────────────
    st.subheader("Note Terms")

    note_name = st.text_input(
        "Note name",
        value=base.name if loaded_terms else "Custom Note",
        help="Display name used in the dashboard and PDF report.",
    )

    col1, col2, col3 = st.columns(3)

    maturity_opts = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    # Keep a loaded config's maturity selectable instead of silently snapping
    # it to the nearest preset (e.g. a 9M note must not become 1Y).
    if base.maturity not in maturity_opts:
        maturity_opts = sorted(set(maturity_opts + [base.maturity]))
    freq_opts     = ["monthly", "quarterly", "semi-annual", "annual"]
    from core.note import _FREQ_TO_PERIODS

    with col1:
        maturity = st.selectbox(
            "Maturity (years)", maturity_opts,
            index=maturity_opts.index(base.maturity)
                  if base.maturity in maturity_opts else 1,
        )
        payment_freq = st.selectbox(
            "Payment frequency", freq_opts,
            index=freq_opts.index(base.payment_freq)
                  if base.payment_freq in freq_opts else 1,
        )
        _n_obs_derived = round(maturity * _FREQ_TO_PERIODS[payment_freq])
        st.caption(f"→ **{_n_obs_derived} observation periods** "
                   f"({_FREQ_TO_PERIODS[payment_freq]}×/yr × {maturity}Y)")
        autocall_start = st.number_input(
            "Autocall start period", 1, _n_obs_derived,
            value=min(base.autocall_start_period, _n_obs_derived),
            help="First N periods are coupon-only (no autocall trigger).",
        )

    with col2:
        coupon_pa_pct = st.number_input(
            "Coupon p.a. (%)", 0.0, 50.0,
            value=round(base.coupon_pa * 100, 4),
            step=0.5, format="%.4f",
            help="Annualised coupon rate. Per-period rate is derived automatically.",
        )
        _coupon_per_period = coupon_pa_pct / 100.0 / _FREQ_TO_PERIODS[payment_freq]
        st.caption(f"→ **{_coupon_per_period*100:.4f}% per period**")
        # number_input (not int slider): term sheets use sub-percent barriers
        # (e.g. 55.5%, 53.7%) which an int slider silently truncates.
        coupon_bar_pct = st.number_input(
            "Coupon barrier (%)", 0.0, 100.0,
            value=round(base.coupon_barrier * 100, 4), step=0.5, format="%.2f",
        )
        memory = st.toggle("Memory coupon", value=base.memory)

    with col3:
        autocall_bar_pct = st.number_input(
            "Autocall barrier (%)", 50.0, 150.0,
            value=round(base.autocall_barrier * 100, 4), step=0.5, format="%.2f",
        )
        ki_bar_pct = st.number_input(
            "Knock-in barrier (%)", 0.0, 100.0,
            value=round(base.knock_in_barrier * 100, 4), step=0.5, format="%.2f",
        )

    st.divider()

    # ── Basket types ──────────────────────────────────────────────────────
    st.subheader("Basket Types")
    basket_opts = ["worst_of", "best_of", "average"]
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        coupon_basket = st.selectbox("Coupon barrier check", basket_opts,
                                      index=basket_opts.index(base.coupon_basket))
    with bc2:
        autocall_basket = st.selectbox("Autocall trigger check", basket_opts,
                                        index=basket_opts.index(base.autocall_basket))
    with bc3:
        # Best-of capital rescue clause (e.g. BBVA XS3378405743 Final Payout xi):
        # at maturity, capital is returned at par if the BEST performer is at or
        # above the rescue barrier, even when the knock-in barrier was breached.
        # Off = standard worst-of note: knock-in alone determines the loss.
        rescue_on = st.toggle(
            "Best-of capital rescue at maturity",
            value=(base.final_basket == "best_of"),
            help="If ON: even when the knock-in barrier is breached, capital is "
                 "returned at 100% as long as the best-performing underlying "
                 "finishes at or above the rescue barrier (BBVA-style 'Barrier "
                 "and Knock-in' clause). If OFF: standard worst-of redemption — "
                 "a knock-in always results in delivery of the worst performer.",
        )
        if rescue_on:
            rescue_bar_pct = st.number_input(
                "Rescue barrier (% of initial)", 50.0, 150.0,
                value=round(getattr(base, "final_redemption_barrier", 1.0) * 100, 4),
                step=0.5, format="%.2f",
                help="Best performer must finish at or above this level for the "
                     "rescue to apply. Term sheets typically use 100%.",
            )
        else:
            rescue_bar_pct = 100.0
        final_basket = "best_of" if rescue_on else "worst_of"

    st.divider()

    # ── Advanced — Growth / Classic Autocall ─────────────────────────────
    # Every JSON-loadable field is editable here; nothing is silently
    # pass-through-only anymore.
    _adv_active = bool(getattr(base, "autocall_step_down", 0.0)
                       or getattr(base, "coupon_at_autocall_only", False))
    with st.expander("Advanced — Growth / Classic Autocall (step-down barrier, premium at call)",
                     expanded=_adv_active):
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            step_down_pct = st.number_input(
                "Autocall step-down per period (%)", 0.0, 10.0,
                value=round(getattr(base, "autocall_step_down", 0.0) * 100, 4),
                step=0.5, format="%.2f",
                help="The autocall barrier declines by this amount each period "
                     "from the first callable observation. 0 = constant barrier "
                     "(plain Phoenix).",
            )
        with ac2:
            _base_floor = getattr(base, "autocall_floor", None)
            floor_pct = st.number_input(
                "Autocall barrier floor (%)", 0.0, 100.0,
                value=round((_base_floor if _base_floor is not None else 0.0) * 100, 4),
                step=0.5, format="%.2f",
                help="Minimum barrier level under step-down. 0 = no floor. "
                     "Ignored when step-down is 0.",
            )
        with ac3:
            st.markdown("<br>", unsafe_allow_html=True)
            premium_at_call = st.toggle(
                "Premium only at autocall",
                value=bool(getattr(base, "coupon_at_autocall_only", False)),
                help="Growth autocall: no periodic coupon — an accrued premium of "
                     "coupon p.a. × elapsed periods is paid as a lump only when "
                     "the note autocalls (zero if held to maturity). "
                     "E.g. Citi XS3096699163.",
            )
        if step_down_pct > 0:
            _sd_preview = NoteTerms(
                maturity=float(maturity), payment_freq=payment_freq,
                autocall_barrier=autocall_bar_pct / 100.0,
                autocall_start_period=int(autocall_start),
                autocall_step_down=step_down_pct / 100.0,
                autocall_floor=(floor_pct / 100.0) if floor_pct > 0 else None,
            ).autocall_barrier_schedule()
            st.caption("Barrier schedule: " +
                       " → ".join(f"{lvl:.0%}" for lvl in _sd_preview))

    st.divider()

    # ── Issuer (optional) ────────────────────────────────────────────────
    st.subheader("Issuer (optional)")
    st.caption("Name of the bank or institution that issued this note — used for display only.")
    # Source of truth: loaded_terms (from JSON) takes priority over widget state.
    # Push the loaded issuer into session_state before the widget renders, so the
    # Streamlit keyed-widget problem (value= is ignored on reruns) doesn't drop it.
    _base_issuer = getattr(base, "issuer", "") or ""
    if loaded_terms is not None and _base_issuer and st.session_state.get("setup_issuer") != _base_issuer:
        st.session_state["setup_issuer"] = _base_issuer
    issuer_input = st.text_input(
        "Issuer name",
        value=_base_issuer,
        placeholder="e.g. BBVA, HSBC, BNP Paribas",
        key="setup_issuer",
    )
    if issuer_input:
        _logo_url = get_issuer_logo_url(issuer_input)
        if _logo_url:
            st.markdown(
                f'<img src="{_logo_url}" height="32" style="margin-top:4px" '
                f'onerror="this.style.display=\'none\'">',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Issue Date (optional) ─────────────────────────────────────────────
    st.subheader("Issue Date (optional)")
    st.caption("If set to today or earlier, a **Current Performance** tab will appear on the dashboard.")
    import datetime as _dt2

    # Source of truth: loaded_terms (from JSON) takes priority over widget state.
    # This avoids the Streamlit keyed-widget problem where value= is ignored on reruns.
    _base_issue_str = getattr(base, "issue_date", None)
    _base_issue = None
    if _base_issue_str:
        try:
            _base_issue = _dt2.date.fromisoformat(_base_issue_str)
        except Exception:
            pass

    # Clear the widget key when a new JSON is loaded so value= takes effect
    if _base_issue is not None and st.session_state.get("setup_issue_date") != _base_issue:
        st.session_state["setup_issue_date"] = _base_issue

    issue_date_input = st.date_input(
        "Note issue date (leave blank for hypothetical notes)",
        value=_base_issue,
        min_value=None,
        max_value=None,
        key="setup_issue_date",
        help="Populated automatically from JSON config. Set to a past or current date to enable live tracking.",
    )

    # A note is live if it has an issue date on or before today
    _issue_is_live = bool(issue_date_input) and issue_date_input <= _dt2.date.today()
    if _issue_is_live:
        st.success(f"Live note · issued {issue_date_input} · **Current Performance** tab will appear on the dashboard.")
    elif issue_date_input:
        st.info("Issue date is in the future — Current Performance tab will appear once trading begins.")

    st.divider()

    # ── Simulation ────────────────────────────────────────────────────────
    st.subheader("Simulation")
    sc1, sc2 = st.columns(2)
    with sc1:
        n_paths = st.slider("Monte Carlo paths", 1000, 50000,
                             st.session_state["n_paths"], step=1000)
    with sc2:
        seed = int(st.number_input("Random seed", value=int(st.session_state["seed"])))

    st.divider()

    # ── Historical Data ───────────────────────────────────────────────────────────────
    st.subheader("Historical Data")
    # Always pull the maximum available history. The backtest benefits from
    # every available issue date, and the calibration window below controls
    # how much of it is actually used for Heston parameter estimation.
    history_years = None
    st.caption("Price history: **Max (all available)** — aligned across underlyings, "
               "so the common start is set by the shortest-history asset (e.g. latest IPO).")

    _calib_opts   = [1.0, 2.0, 3.0, 5.0, 10.0]
    _calib_labels = ["1 Year", "2 Years", "3 Years", "5 Years", "10 Years"]
    _calib_cur    = st.session_state.get("calib_years", 5.0)
    _calib_default_idx = _calib_opts.index(_calib_cur) if _calib_cur in _calib_opts else 3
    _calib_choice = st.radio(
        "Calibration window (Heston params estimated on this recent period only)",
        _calib_labels,
        index=_calib_default_idx,
        horizontal=True,
        help="Keep short (2–5Y) for forward-looking drift and vol. "
             "Longer windows drag mu negative when they include major crashes (e.g. 2008 for bank stocks).",
    )
    calib_years = _calib_opts[_calib_labels.index(_calib_choice)]

    st.divider()

    # ── Confirm ───────────────────────────────────────────────────────────────────
    if len(selected_labels) < 1:
        st.warning("Select at least 1 underlying to continue.")
    else:
        if st.button("Confirm & Load Dashboard", type="primary",
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
                # Growth/classic autocall fields from the Advanced expander
                autocall_step_down      = step_down_pct / 100.0,
                autocall_floor          = (floor_pct / 100.0) if (step_down_pct > 0 and floor_pct > 0) else None,
                coupon_at_autocall_only = bool(premium_at_call),
                # Bonus Certificate / Capital Protected fields — not exposed in the
                # setup form UI; preserved from the loaded JSON config across round-trips.
                min_return              = getattr(base, "min_return", 0.0),
                capital_guarantee       = getattr(base, "capital_guarantee", None),
                upside_cap              = getattr(base, "upside_cap", None),
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
    st.sidebar.header("Note")
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
        "Download config (JSON)",
        data=terms.to_json(),
        file_name="note_config.json",
        mime="application/json",
    )
    # ── Branding JSON uploader ────────────────────────────────────────────
    # Persist the parsed branding dict in session state so it survives reruns.
    _branding_upload = st.sidebar.file_uploader(
        "Corporate branding (JSON) — optional",
        type=["json"],
        key="branding_upload",
        help="Upload a branding JSON to customise the PDF with your firm's colors and logo. "
             "Schema: {firm_name, primary_color, accent_color, logo_url}",
    )
    if _branding_upload is not None:
        try:
            import json as _json
            _branding_raw = _branding_upload.read().decode()
            st.session_state["branding"] = _json.loads(_branding_raw)
        except Exception as _be:
            st.sidebar.warning(f"Branding JSON invalid: {_be}")
    _branding_dict = st.session_state.get("branding")
    if _branding_dict:
        _bfirm = _branding_dict.get("firm_name", "")
        _bcolor = _branding_dict.get("primary_color", "")
        st.sidebar.caption(f"Branding: **{_bfirm}** {_bcolor}")
        if st.sidebar.button("Clear branding", key="clear_branding"):
            st.session_state["branding"] = None
            st.rerun()

    _pdf_btn = st.sidebar.button(
        "Generate PDF Report",
        disabled=not bool(st.session_state.get("results")),
        help="Builds the report, then a download button appears below. "
             "Run a simulation first to enable it.",
    )
    # Placeholder so the generated download button appears right here, directly
    # under the trigger button — not buried at the bottom of the sidebar.
    _pdf_slot = st.sidebar.empty()
    st.sidebar.divider()
    if st.sidebar.button("Reconfigure Note"):
        st.session_state["page"]             = "setup"
        st.session_state["results"]          = None
        st.session_state["loaded_terms_dict"] = None
        st.rerun()
    run_button = st.sidebar.button("Run Simulation", type="primary")

    # ── Title ─────────────────────────────────────────────────────────────
    st.title("Multi-Asset Structured Note Simulator")
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
            f"Coupon {terms.coupon_pa*100:.2g}% p.a. · "
            f"{'Memory' if terms.memory else 'No memory'} · "
            f"KI {terms.knock_in_barrier:.0%} · Autocall {terms.autocall_barrier:.0%}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"**{terms.name}** — "
            f"{', '.join(selected_tickers.values())} · "
            f"{int(terms.maturity*12)}M · {terms.n_obs} obs · "
            f"Coupon {terms.coupon_pa*100:.2g}% p.a. · "
            f"{'Memory' if terms.memory else 'No memory'} · "
            f"KI {terms.knock_in_barrier:.0%} · Autocall {terms.autocall_barrier:.0%}"
        )

    with st.expander(tr("note_structure_expander"), expanded=False):
        # Issuer row (if set)
        if getattr(terms, "issuer", ""):
            _exp_logo = get_issuer_logo_url(terms.issuer)
            _exp_issuer_html = (
                f'<img src="{_exp_logo}" height="24" style="vertical-align:middle;margin-right:8px" '
                f'onerror="this.style.display=\'none\'">'
                f"<strong>Issuer:</strong> {terms.issuer}"
            ) if _exp_logo else f"<strong>Issuer:</strong> {terms.issuer}"
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
            "<th style='padding:4px 8px;text-align:left;border-bottom:1px solid #ddd;'>Display Name</th>"
            "<th style='padding:4px 8px;text-align:left;border-bottom:1px solid #ddd;'>yfinance Symbol</th>"
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
            tr("col_autocall_eligible"): ["Yes" if i + 1 >= terms.autocall_start_period else "Coupon only"
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
        with st.spinner("Running Heston calibration and Monte Carlo simulation…"):
            _hist_years = st.session_state.get("history_years", None)
            # Calibrate drift/vol/correlations on ADJUSTED closes (total-return
            # dynamics — ex-date jumps must not pollute the estimates) ...
            prices_adj = _load_prices(tickers_tuple, years=_hist_years, field="adj_close")
            # ... but barriers, S0, and dividend jumps live in RAW price space.
            prices_raw = _load_prices(tickers_tuple, years=_hist_years, field="close")
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
                st.warning(f"Could not load dividend history ({_div_e}) — "
                           "simulating without dividend jumps.")
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

            st.session_state["results"] = {
                **note_results,
                "worst_of_paths": wof_paths,
                "sim_prices":     sim_prices,
                "asset_names":    list(selected_tickers.values()),
                "s0_values":      s0_values,
                "params":         cal_result.params,
                "corr_SS":        cal_result.corr_SS,
                "sim_results":    sim_results,
                "t_dof":          cal_result.t_dof,
                "terms_snapshot": terms.to_dict(),
                # Real-calendar grid metadata (drives charts + obs tables)
                "t_grid_years":   np.concatenate([[0.0], np.cumsum(_dt_grid)]),
                "obs_steps":      _obs_steps,
                "obs_times":      _obs_times,
                "grid_dates":     _grid,
                "div_schedule":   _div_sched,
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
        tab_mc, tab_bt, tab_live = st.tabs(["Monte Carlo", "Historical Backtest", "Current Performance"])
    else:
        tab_mc, tab_bt = st.tabs(["Monte Carlo", "Historical Backtest"])
        tab_live = None

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — MONTE CARLO
    # ══════════════════════════════════════════════════════════════════
    with tab_mc:
        if not _has_sim:
            st.info("Click **Run Simulation** in the sidebar to run the Monte Carlo engine.")
            with st.spinner(f"Pre-fetching market data for {', '.join(selected_tickers.values())}…"):
                try:
                    _load_prices(tickers_tuple, years=st.session_state.get("history_years", None))
                    st.success("Market data ready. Click **Run Simulation** in the sidebar.")
                except Exception as e:
                    st.error(f"Failed to fetch prices: {e}")
        else:
            st.success(tr("sim_complete"))
            # Cache MC figures for PDF generation (used by sidebar PDF button)
            st.session_state["_pdf_mc_figures"] = {
                "irr_dist": build_irr_distribution(
                    R["annualized_returns"], R["autocall_events"],
                    R["expected_irr"], run_terms.coupon_pa, tr,
                ),
                "wof_fan": build_wof_fan(
                    wof_paths, t_grid, run_terms.knock_in_barrier, obs_pairs, tr,
                    autocall_barrier=run_terms.autocall_barrier,
                    autocall_schedule=_ac_sched_t,
                ),
                "corr": build_corr_heatmap(R["corr_SS"], asset_names, "Input"),
            }
            # ── Summary metrics ───────────────────────────────────────
            st.header(tr("summary_stats_header"))
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric(tr("expected_irr_pa"),  f"{R['expected_irr']:.2%}",
                      help="Average of per-path annualized returns: mean(return ÷ holding time). "
                           "Early autocalls divide a small gain by a short holding period, so they "
                           "contribute large positive IRRs; knock-in losses are spread over the full "
                           "maturity. This can be positive even when Expected Total Return is "
                           "negative (average of ratios ≠ ratio of averages), and implicitly assumes "
                           "autocall proceeds are reinvested at similar rates.")
            c2.metric(tr("expected_total_return"), f"{R['expected_total_return']:.2%}",
                      help="Average money outcome per 1.00 invested over the note's life: "
                           "mean(payout − 1) = coupons received + principal returned − 1. "
                           "Not annualized. The more conservative headline number.")
            c3.metric(tr("expected_coupon_metric"), f"{R['expected_coupon']:.2%}",
                      help="Average total coupon income received over the note's life, per path "
                           "(coupons across all periods, including memory catch-up payments). "
                           "Expressed as a fraction of par. Does not include principal redemption.")
            c4.metric(tr("prob_autocalled"),   f"{R['prob_autocall']:.2%}",
                      help="Probability the issuer exercises the call at any observation date "
                           "before (or at) maturity. An autocall terminates the note early, "
                           "returning principal plus the period coupon. Higher autocall barriers "
                           "reduce this probability; the autocall start period locks out early "
                           "observations from triggering.")
            c5.metric(tr("prob_knock_in_metric"), f"{R['prob_knock_in_total']:.2%}",
                      help="Probability of capital loss at maturity: knock-in barrier breached "
                           "AND the final redemption condition not met. For notes with a best-of "
                           "final basket (e.g. BBVA XS3378405743), paths where the best performer "
                           "finishes ≥ the redemption barrier are 'rescued' to par even if the "
                           "worst breached the KI level — those are excluded here.")
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
                    tr("col_eligible"): ["Yes" if i + 1 >= run_terms.autocall_start_period else "No"
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
                coupon_pa = run_terms.coupon_pa
                st.plotly_chart(
                    build_irr_distribution(
                        R["annualized_returns"], R["autocall_events"],
                        R["expected_irr"], coupon_pa, tr,
                    ),
                    use_container_width=True,
                )
                if R["prob_knock_in_total"] > 0:
                    st.info(tr("knock_in_info", pct=R['prob_knock_in_total'],
                               barrier=run_terms.knock_in_barrier))

            with mc_tab2:
                st.subheader(tr("price_paths_subheader"))
                st.markdown(tr("wof_basket_md"))
                st.plotly_chart(
                    build_wof_fan(wof_paths, t_grid, run_terms.knock_in_barrier, obs_pairs, tr,
                                  autocall_barrier=run_terms.autocall_barrier,
                                  autocall_schedule=_ac_sched_t),
                    use_container_width=True,
                )
                st.markdown(tr("individual_paths_md"))
                for i, name in enumerate(asset_names):
                    st.plotly_chart(
                        build_fan_chart(sim_prices[:, :, i], name, t_grid, obs_pairs, tr),
                        use_container_width=True,
                    )

            with mc_tab3:
                st.subheader(tr("single_path_subheader"))
                max_path = sim_prices.shape[0] - 1
                pc1, pc2, pc3 = st.columns(3)
                if pc1.button("Random"):
                    st.session_state["path_num"] = random.randint(0, max_path)
                if pc2.button("Prev"):
                    st.session_state["path_num"] = max(0, st.session_state["path_num"] - 1)
                if pc3.button("Next"):
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
                           help="Principal returned on this path as a fraction of par: 100% if "
                                "the note autocalled or matured without a knock-in; the worst-of "
                                "final performance if knock-in was triggered without a best-of "
                                "rescue.")
                mc2.metric(tr("metric_coupons"),   f"{coupons:.2%}",
                           help="Total coupon income received on this single path as a fraction "
                                "of par, summing all paid periods (including memory catch-up "
                                "payments if applicable).")
                mc3.metric(tr("metric_irr_pa"),    f"{irr:.2%}",
                           help="Simple annualised return for this single path: "
                                "(principal + coupons − 1) ÷ holding time. "
                                "Short autocall paths can show very high IRRs because the same "
                                "coupon income is divided by a small holding period.")

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
                    _pe_col.metric("Final perf.", f"{_pe_final:.1%}")

            with mc_tab4:
                st.subheader(tr("corr_diag_subheader"))
                corr_SS       = R["corr_SS"]
                realized_corr = R["sim_results"]["realized_corr"]
                diff          = realized_corr - corr_SS
                hm1, hm2, hm3 = st.columns(3)
                hm1.plotly_chart(build_corr_heatmap(corr_SS,       asset_names, "Input"),    use_container_width=True)
                hm2.plotly_chart(build_corr_heatmap(realized_corr, asset_names, "Realized"), use_container_width=True)
                hm3.plotly_chart(build_corr_heatmap(diff, asset_names, "Difference",
                                                      zmin=-0.1, zmax=0.1),                  use_container_width=True)
                max_err = float(np.max(np.abs(diff - np.diag(np.diag(diff)))))
                (st.success if max_err < 0.05 else st.warning)(
                    f"Max off-diagonal error: **{max_err:.4f}** "
                    f"({'good' if max_err < 0.02 else 'acceptable' if max_err < 0.05 else 'elevated — consider more paths'}). "
                    f"This is the largest absolute difference between a target and realized "
                    f"pairwise correlation. Values < 0.05 are acceptable for pricing; "
                    f"> 0.05 suggests the Cholesky decomposition is not well converged — "
                    f"try increasing Monte Carlo paths."
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
                        "Asset": f"{_logo_html}{p.name}", "S₀": f"{p.S0:.1f}",
                        "μ p.a.": f"{p.mu*100:.1f}%",
                        "V₀ σ":   f"{np.sqrt(p.V0)*100:.1f}%",
                        "θ σ LR": f"{np.sqrt(p.theta)*100:.1f}%",
                        "κ": f"{p.kappa:.3f}", "ξ": f"{p.xi:.3f}", "ρ": f"{p.rho:.3f}",
                        "Feller": "Pass" if ok else "Warn",
                    })
                _heston_cols = ["Asset", "S₀", "μ p.a.", "V₀ σ", "θ σ LR", "κ", "ξ", "ρ", "Feller"]
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
                st.caption(
                    "**Column guide:** "
                    "**μ** = arithmetic drift (annualised); "
                    "**V₀ σ** = current implied vol (√V₀); "
                    "**θ σ LR** = long-run vol mean (√θ, the level V reverts toward); "
                    "**κ** = mean-reversion speed (higher → vol snaps back faster; typical equity: 1–5); "
                    "**ξ** = vol-of-vol, volatility of the variance process (higher → fatter tails; typical: 0.1–0.8); "
                    "**ρ** = leverage effect, correlation between spot and variance shocks "
                    "(negative for equities — down moves spike vol; typical: −0.7 to −0.3); "
                    "**Feller** = 'Pass' if 2κθ > ξ² (Feller condition), ensuring variance stays positive; "
                    "'Warn' means variance can touch zero, which is a known Heston model artefact and "
                    "generally has negligible pricing impact."
                )
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
            st.warning("Could not load price history for the backtest.")
        elif not _bt_feasible:
            st.warning(
                f"**Not enough history for this note.** A {terms.maturity:g}Y note needs "
                f"one full {terms.maturity:g}-year calendar window of realized prices after "
                f"the first issue date, but the aligned history across all underlyings only "
                f"spans {_all_prices.index[0].date()} → {_all_prices.index[-1].date()}."
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

            with st.spinner("Running historical backtest…"):
                try:
                    bt, bt_summary = _run_backtest_cached(
                        tickers_tuple, terms.to_json(),
                        bt_start_str=bt_start_str,
                        bt_end_str=bt_end_str,
                        history_years=st.session_state.get("history_years", None),
                    )
                except Exception as e:
                    st.error(f"Backtest failed: {e}")
                    bt, bt_summary = pd.DataFrame(), {}

        if bt.empty:
            st.warning("No backtest results. Check underlyings have sufficient history.")
        else:
            bt["Outcome"] = bt["Call Quarter"].map(
                {0: "Maturity", **{i: f"Autocalled P{i}" for i in range(1, terms.n_obs + 1)}}
            )
            bt.loc[(bt["Call Quarter"] == 0) & bt["Knock-in"], "Outcome"] = "Knock-in"
            # Navy/blue institutional palette (matches charts.py + PDF):
            # Maturity = warm grey, Knock-in = red, Autocalls = navy→light-blue ramp.
            color_map = {
                "Maturity": "#6b7280", "Knock-in": "#dc2626",
                **{f"Autocalled P{i}":
                   f"hsl(217,{max(35, 70 - i*3)}%,{min(70, 28 + i*5)}%)"
                   for i in range(1, terms.n_obs + 1)},
            }

            b1, b2, b3, b4, b5 = st.columns(5)
            b1.metric(tr("bt_metric_issue_dates"),    str(bt_summary.get("n_issues", 0)),
                      help="Number of distinct historical issue dates tested. Each date seeds "
                           "an independent note life using the actual realized price path of "
                           "the underlyings. The backtest slides a window of length = maturity "
                           "across the full price history, one issue date per trading day.")
            b2.metric(tr("bt_metric_mean_irr"),       f"{bt_summary.get('mean_irr', 0):.2%}",
                      help="Average of per-issue simple annualised returns: "
                           "mean((payout − 1) ÷ holding time). Simple annualisation — not "
                           "compound. Skewed upward by early autocalls that divide coupon "
                           "income by a short holding period.")
            b3.metric(tr("bt_metric_median_irr"),     f"{bt_summary.get('median_irr', 0):.2%}",
                      help="Median simple annualised return across all historical issue dates. "
                           "Less sensitive than the mean to the skew introduced by very early "
                           "autocalls; a better central-tendency estimate for most note structures.")
            b4.metric(tr("bt_metric_knock_in_pct"),   f"{bt_summary.get('prob_knock_in', 0):.1%}",
                      help="Fraction of historical issue dates where the knock-in barrier was "
                           "breached AND the final redemption condition was not met, resulting "
                           "in a capital loss. Notes with a best-of rescue clause show a lower "
                           "figure here than the raw barrier-breach rate.")
            b5.metric(tr("bt_metric_autocalled_pct"), f"{bt_summary.get('prob_called', 0):.1%}",
                      help="Fraction of historical issue dates where the note was called early "
                           "at an autocall observation date before maturity.")

            _bt_outcome_fig = build_backtest_outcome_bar(bt, color_map, tr)
            _bt_irr_fig     = build_backtest_irr_scatter(bt, color_map, tr)
            col1, col2 = st.columns(2)
            col1.plotly_chart(_bt_outcome_fig,                   use_container_width=True)
            col2.plotly_chart(build_worst_asset_pie(bt, tr),     use_container_width=True)
            st.plotly_chart(_bt_irr_fig,                         use_container_width=True)
            # Cache for PDF
            st.session_state["_pdf_bt_summary"] = bt_summary
            st.session_state["_pdf_bt_figures"] = {"outcome": _bt_outcome_fig, "irr_scatter": _bt_irr_fig}

            try:
                _hist_chart_prices = _load_prices(tickers_tuple, years=None)
                bt_start_mark = bt["Issue Date"].min()
                bt_end_mark   = bt["Issue Date"].max()
                st.plotly_chart(build_historical_prices(_hist_chart_prices, bt_start_mark, bt_end_mark, tr),
                                use_container_width=True)
            except Exception:
                pass

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
                    st.error(f"Could not build path: {e}")


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
                        f"Aligned price history only starts {_anchor_live.date()} — after the "
                        f"stated issue date {_issue_ts.date()}. The initial fixing uses the "
                        f"first available close, so levels may not match the term sheet."
                    )
                _live_prices = _full_prices.iloc[_issue_idx_full:]

                if len(_live_prices) < 2:
                    st.warning("Not enough live price data since issue date.")
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
                                help="Current level of the worst-performing underlying relative "
                                     "to its initial fixing price (strike = 100%). This is the "
                                     "key risk indicator: coupon and autocall eligibility, and "
                                     "knock-in exposure, are all measured against this figure.")
                    _lc2.metric(tr("live_metric_worst_asset"), _worst_asset_today,
                                help="The underlying currently dragging the worst-of basket — "
                                     "i.e. the one with the lowest performance relative to its "
                                     "initial fixing. This asset sets the barrier observation level.")
                    _lc3.metric(tr("live_metric_vs_ki"),
                                f"{_wof_today / run_terms.knock_in_barrier:.1%}",
                                delta=f"{_wof_today - run_terms.knock_in_barrier:.1%}",
                                delta_color="normal",
                                help=f"Worst-of level as a percentage of the knock-in barrier "
                                     f"({run_terms.knock_in_barrier:.0%}). "
                                     f"Values > 100% mean the worst-of is above the KI barrier "
                                     f"(no knock-in risk yet). The delta shows distance to the "
                                     f"barrier in percentage-point terms.")
                    _lc4.metric(tr("live_metric_vs_autocall"),
                                f"{_wof_today / run_terms.autocall_barrier:.1%}",
                                delta=f"{_wof_today - run_terms.autocall_barrier:.1%}",
                                delta_color="normal",
                                help=f"Worst-of level as a percentage of the autocall barrier "
                                     f"({run_terms.autocall_barrier:.0%}). "
                                     f"Values ≥ 100% at an eligible observation date would "
                                     f"trigger an early call. The delta shows distance to the "
                                     f"barrier in percentage-point terms.")

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
                            _est = _obs_cal[_q].date() if _q < len(_obs_cal) else "—"
                            _obs_rows.append({
                                _k_period: _label, _k_date: str(_est),
                                _k_status: "Upcoming",
                                _k_wof: "—", _k_coupon: "—", _k_cumulative: "—",
                            })
                            continue

                        _r        = _replay["rows"][_q]
                        _obs_wof  = float(_perf_obs[_q].min())
                        _running_total += _r["coupon_amount"]
                        if _r["autocalled"]:
                            _status = "Autocalled"
                        elif run_terms.coupon_at_autocall_only:
                            _status = "— No periodic coupon (premium at call)"
                        elif _r["coupon_met"]:
                            _status = "Coupon paid"
                        else:
                            _status = "Coupon missed"
                        _obs_rows.append({
                            _k_period:     _label,
                            _k_date:       str(_snap.date()),
                            _k_status:     _status,
                            _k_wof:        f"{_obs_wof:.1%}",
                            _k_coupon:     f"{_r['coupon_amount']:.4%}" if _r["coupon_amount"] > 0 else "—",
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
                            f"Growth autocall: no periodic coupons — an accrued premium of "
                            f"{run_terms.coupon_rate:.2%} per period "
                            f"({run_terms.coupon_pa:.0%} p.a.) is paid only if the note "
                            f"autocalls. Premium if called at the next eligible observation: "
                            f"{run_terms.coupon_rate * (len(_replay['rows']) + 1):.2%}."
                        )

                    _irr_to_date = _total_coupons_paid / max(_elapsed_years, 1/252)
                    st.metric(tr("live_coupon_irr_metric"), f"{_irr_to_date:.2%}",
                              help="Total coupons paid so far ÷ elapsed time in years — a simple "
                                   "(not compound) annualisation of income received. Does not "
                                   "include any accrued-but-unpaid memory coupons or the principal "
                                   "return at maturity. Comparable to a running yield on a bond, "
                                   "but note it overstates the realized return for notes where "
                                   "coupons cluster toward the end of the life.")

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
                st.error(f"Could not load live price data: {_e}")

    # ══════════════════════════════════════════════════════════════════
    # PDF GENERATION (sidebar button — runs after all tab content)
    # ══════════════════════════════════════════════════════════════════
    if _pdf_btn and _has_sim:
        with st.spinner("Building PDF report…"):
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
            "Download PDF",
            data=_pdf_bytes,
            file_name=f"{run_terms.name.replace(' ', '_')}_report.pdf",
            mime="application/pdf",
            key="dl_pdf_sidebar",
        )