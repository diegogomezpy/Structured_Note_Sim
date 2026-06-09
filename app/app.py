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

from core            import NoteTerms, price_note
from core.calibrator import HestonCalibrator
from core.simulator  import HestonMultiSimulator
from core.backtest   import run_backtest
from data.loader     import load_prices

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
    page_icon  = "📈",
    layout     = "wide",
)
st.markdown("""<style>
[data-testid="stMetricValue"]{font-weight:700}
[data-testid="stSidebar"] .stButton>button{width:100%}
.stTabs [data-baseweb="tab-list"]{border-bottom:2px solid #1a6b1a}
.stTabs [aria-selected="true"]{border-bottom:2px solid #1a6b1a!important;font-weight:600}
[data-testid="stExpander"]{border:1px solid #c8e6c8!important;border-radius:6px}
hr{border-color:#c8e6c8}
</style>""", unsafe_allow_html=True)

# ==========================================================================
# Available underlyings
# ==========================================================================
UNDERLYING_OPTIONS = {
    # ── Equity indices ───────────────────────────────────────────────────
    "SPX — S&P 500":            "^GSPC",
    "NDX — Nasdaq 100":         "^NDX",
    "RUT — Russell 2000":       "^RUT",
    "SX5E — Euro Stoxx 50":     "^STOXX50E",
    "DAX — DAX 40":             "^GDAXI",
    "FTSE — FTSE 100":          "^FTSE",
    "CAC — CAC 40":             "^FCHI",
    "SMI — Swiss Market":       "^SSMI",
    "NKY — Nikkei 225":         "^N225",
    "HSI — Hang Seng":          "^HSI",
    "KOSPI — Korea":            "^KS11",
    "ASX — Australia":          "^AXJO",
    "IBEX — Spain":             "^IBEX",
    "MIB — Italy":              "FTSEMIB.MI",
    # ── US Banks & Financials ────────────────────────────────────────────
    "GS — Goldman Sachs":       "GS",
    "JPM — J.P. Morgan":        "JPM",
    "MS — Morgan Stanley":      "MS",
    "BAC — Bank of America":    "BAC",
    "C — Citigroup":            "C",
    "WFC — Wells Fargo":        "WFC",
    "BLK — BlackRock":          "BLK",
    # ── US Tech ─────────────────────────────────────────────────────────
    "AAPL — Apple":             "AAPL",
    "MSFT — Microsoft":         "MSFT",
    "NVDA — NVIDIA":            "NVDA",
    "AMZN — Amazon":            "AMZN",
    "META — Meta":              "META",
    "GOOGL — Alphabet":         "GOOGL",
    "TSLA — Tesla":             "TSLA",
    "PLTR — Palantir":          "PLTR",
    "AMD — AMD":                "AMD",
    "INTC — Intel":             "INTC",
    "CRM — Salesforce":         "CRM",
    "NFLX — Netflix":           "NFLX",
    # ── European stocks ──────────────────────────────────────────────────
    "ASML — ASML":              "ASML",
    "SAP — SAP":                "SAP",
    "NESN — Nestlé":            "NESN.SW",
    "NOVN — Novartis":          "NOVN.SW",
    "ROG — Roche":              "ROG.SW",
    "MC — LVMH":                "MC.PA",
    "OR — L'Oréal":             "OR.PA",
    "SAN — Santander":          "SAN.MC",
    # ── Commodities & ETFs ───────────────────────────────────────────────
    "GLD — Gold ETF":           "GLD",
    "SLV — Silver ETF":         "SLV",
    "USO — Oil ETF":            "USO",
    "XLE — Energy ETF":         "XLE",
    "XLF — Financials ETF":     "XLF",
    "EEM — EM ETF":             "EEM",
}
UNDERLYING_LABELS  = list(UNDERLYING_OPTIONS.keys())
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
    "history_years":    5.0,     # None = max history
    "calib_years":      5.0,     # years of recent data used for Heston calibration
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==========================================================================
# Cached helpers
# ==========================================================================
@st.cache_data
def _load_prices(tickers_tuple, years=5.0):
    return load_prices(source="yfinance", tickers=dict(tickers_tuple), years=years)

@st.cache_data
def _run_backtest_cached(tickers_tuple, terms_json,
                         bt_start_str=None, bt_end_str=None):
    # Always pull max history for backtesting: the user-selected history_years
    # controls Heston calibration only.  The backtest needs the full available
    # price series to maximise the number of valid issue dates.
    prices   = _load_prices(tickers_tuple, years=None)
    t        = NoteTerms.from_json(terms_json)
    bt_start = pd.Timestamp(bt_start_str) if bt_start_str else None
    bt_end   = pd.Timestamp(bt_end_str)   if bt_end_str   else None
    return run_backtest(prices, t, bt_start=bt_start, bt_end=bt_end)

# ==========================================================================
# Language toggle (always in sidebar)
# ==========================================================================
lang_choice = st.sidebar.radio("🌐 Language / Idioma", ["English", "Español"],
                                horizontal=True)
tr = Translator("es" if lang_choice == "Español" else "en")

# ==========================================================================
# ─────────────────────────────────────────────────────────────────────────
#  PAGE 1 — SETUP
# ─────────────────────────────────────────────────────────────────────────
# ==========================================================================
if st.session_state["page"] == "setup":

    st.title("📈 Structured Note Simulator")
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
    default_ul = st.session_state["setup_ul_default"] or                  ["SPX — S&P 500", "SX5E — Euro Stoxx 50", "SMI — Swiss Market"]
    # Filter to only valid options
    default_ul = [d for d in default_ul if d in all_labels]

    selected_labels = st.multiselect(
        "Select underlyings (2–5)", all_labels,
        default=default_ul,
        key="setup_underlyings",
    )

    # ── Custom ticker input ───────────────────────────────────────────────
    with st.expander("➕ Add a custom ticker (not in the list above)"):
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

    st.divider()

    # ── Note terms ────────────────────────────────────────────────────────
    st.subheader("Note Terms")

    col1, col2, col3 = st.columns(3)

    maturity_opts = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
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
        coupon_bar_pct = st.slider("Coupon barrier (%)", 0, 100,
                                    int(base.coupon_barrier * 100))
        memory = st.toggle("Memory coupon", value=base.memory)

    with col3:
        autocall_bar_pct = st.slider("Autocall barrier (%)", 50, 120,
                                      int(base.autocall_barrier * 100))
        ki_bar_pct = st.slider("Knock-in barrier (%)", 0, 100,
                                int(base.knock_in_barrier * 100))

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
        final_basket = st.selectbox("Final redemption check", basket_opts,
                                     index=basket_opts.index(base.final_basket))

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
    _hist_opts   = [1.0, 2.0, 3.0, 5.0, 10.0, None]
    _hist_labels = ["1 Year", "2 Years", "3 Years", "5 Years", "10 Years", "Max (all available)"]
    _hy = st.session_state.get("history_years", 5.0)
    _hist_default_idx = _hist_opts.index(_hy) if _hy in _hist_opts else 3
    _hist_choice = st.radio(
        "Price history to download (used for calibration & backtest)",
        _hist_labels,
        index=_hist_default_idx,
        horizontal=True,
    )
    history_years = _hist_opts[_hist_labels.index(_hist_choice)]

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
    if len(selected_labels) < 2:
        st.warning("Select at least 2 underlyings to continue.")
    else:
        if st.button("✅ Confirm & Load Dashboard", type="primary",
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
                name                  = base.name if loaded_terms else "Custom Note",
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
                call_steepness        = 100.0,
                tickers               = selected_tickers,
                issue_date            = issue_date_input.isoformat() if _issue_is_live else None,
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
    st.sidebar.header("📋 Note")
    st.sidebar.markdown(f"**{terms.name}**")
    st.sidebar.markdown(
        f"{', '.join(selected_tickers.values())}  \n"
        f"{int(terms.maturity*12)}M · {terms.n_obs} obs · {terms.payment_freq} · "
        f"{terms.coupon_pa*100:.2g}% p.a."
    )
    st.sidebar.download_button(
        "⬇ Download config (JSON)",
        data=terms.to_json(),
        file_name="note_config.json",
        mime="application/json",
    )
    st.sidebar.divider()
    if st.sidebar.button("⚙️ Reconfigure Note"):
        st.session_state["page"]             = "setup"
        st.session_state["results"]          = None
        st.session_state["loaded_terms_dict"] = None
        st.rerun()
    run_button = st.sidebar.button("🚀 Run Simulation", type="primary")

    # ── Title ─────────────────────────────────────────────────────────────
    st.title("📈 Multi-Asset Structured Note Simulator")
    st.markdown(
        f"**{terms.name}** — "
        f"{', '.join(selected_tickers.values())} · "
        f"{int(terms.maturity*12)}M · {terms.n_obs} obs · "
        f"Coupon {terms.coupon_pa*100:.2g}% p.a. · "
        f"{'Memory' if terms.memory else 'No memory'} · "
        f"KI {terms.knock_in_barrier:.0%} · Autocall {terms.autocall_barrier:.0%}"
    )

    with st.expander("📖 Note Structure Summary", expanded=False):
        # Underlyings table
        st.markdown("**Underlyings**")
        ul_df = pd.DataFrame([
            {"Display Name": disp, "yfinance Symbol": sym}
            for sym, disp in selected_tickers.items()
        ])
        st.dataframe(ul_df, use_container_width=True, hide_index=True)

        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Maturity", f"{terms.maturity}Y")
        c1.metric("Observations", f"{terms.n_obs}")
        c1.metric("Frequency", terms.payment_freq.capitalize())
        c2.metric("Coupon p.a.", f"{terms.coupon_pa*100:.2g}%")
        c2.metric("Coupon / period", f"{terms.coupon_rate*100:.4f}%")
        c2.metric("Memory", "Yes" if terms.memory else "No")
        c3.metric("Coupon barrier", f"{terms.coupon_barrier:.0%}")
        c3.metric("Autocall barrier", f"{terms.autocall_barrier:.0%}")
        c3.metric("Knock-in barrier", f"{terms.knock_in_barrier:.0%}")
        obs_df = pd.DataFrame({
            "Period": range(1, terms.n_obs + 1),
            "Time (Y)": [f"{t:.4g}" for t in terms.obs_times()],
            "Autocall eligible": ["✅" if i + 1 >= terms.autocall_start_period else "❌ coupon only"
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
            prices = _load_prices(tickers_tuple, years=st.session_state.get("history_years", 5.0))
            cal    = HestonCalibrator(
                prices_df   = prices,
                calib_years = st.session_state.get("calib_years", 5.0),
            )
            cal_result = cal.calibrate()

            N_steps = max(252, round(252 * terms.maturity))
            sim = HestonMultiSimulator(
                params  = cal_result.params,
                corr_SS = cal_result.corr_SS,
                corr_VV = cal_result.corr_VV,
                corr_SV = cal_result.corr_SV,
                T       = terms.maturity,
                N       = N_steps,
                n_paths = n_paths,
                seed    = seed,
                t_dof   = cal_result.t_dof,
            )
            sim_results = sim.run()

            n_assets   = len(cal_result.params)
            sim_prices = np.stack(sim_results["S_paths"], axis=2)
            S0_vec     = np.array([p.S0 for p in cal_result.params]).reshape(1, 1, n_assets)
            perf_paths = sim_prices / S0_vec
            wof_paths  = perf_paths.min(axis=2)

            note_results = price_note(perf_paths, terms, seed=seed + 1)
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
    _has_live = bool(_live_issue_date)

    # Build run_terms (needed inside MC tab — falls back to terms when no sim yet)
    if _has_sim:
        run_terms = NoteTerms.from_dict(R["terms_snapshot"])
        if _live_issue_date and run_terms.issue_date != _live_issue_date:
            run_terms = NoteTerms.from_dict({**R["terms_snapshot"], "issue_date": _live_issue_date})
        asset_names = R.get("asset_names") or st.session_state.get("last_asset_names") or list(selected_tickers.values())
        wof_paths   = R["worst_of_paths"]
        sim_prices  = R["sim_prices"]
        N           = wof_paths.shape[1] - 1
        t_grid      = np.linspace(0, run_terms.maturity, N + 1)
        obs_steps_i = run_terms.obs_steps(N)
        obs_times_l = run_terms.obs_times()
        obs_pairs   = [(f"P{i+1}", t) for i, t in enumerate(obs_times_l)]
    else:
        run_terms = terms

    if _has_live:
        tab_mc, tab_bt, tab_live = st.tabs(["📊 Monte Carlo", "📅 Historical Backtest", "📍 Current Performance"])
    else:
        tab_mc, tab_bt = st.tabs(["📊 Monte Carlo", "📅 Historical Backtest"])
        tab_live = None

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — MONTE CARLO
    # ══════════════════════════════════════════════════════════════════
    with tab_mc:
        if not _has_sim:
            st.info("Click **🚀 Run Simulation** in the sidebar to run the Monte Carlo engine.")
            with st.spinner(f"Pre-fetching market data for {', '.join(selected_tickers.values())}…"):
                try:
                    _load_prices(tickers_tuple, years=st.session_state.get("history_years", 5.0))
                    st.success("Market data ready. Click **🚀 Run Simulation** in the sidebar.")
                except Exception as e:
                    st.error(f"Failed to fetch prices: {e}")
        else:
            st.success("Simulation complete.")
            # ── Summary metrics ───────────────────────────────────────
            st.header("Summary Statistics")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Expected IRR p.a. (simple)",  f"{R['expected_irr']:.2%}")
            c2.metric("Expected Total Return", f"{R['expected_total_return']:.2%}")
            c3.metric("Expected Coupon",       f"{R['expected_coupon']:.2%}")
            c4.metric("P(Autocalled)",         f"{R['prob_autocall']:.2%}")
            c5.metric("P(Knock-in)",           f"{R['prob_knock_in_total']:.2%}")

            with st.expander("Autocall probability by period", expanded=False):
                prob_by_period = R["prob_autocall_by_period"]
                ac_df = pd.DataFrame({
                    "Period":      range(1, run_terms.n_obs + 1),
                    "Time (Y)":    [f"{t:.3g}" for t in obs_times_l],
                    "P(autocall)": [f"{p:.2%}" for p in prob_by_period],
                    "Eligible":    ["✅" if i + 1 >= run_terms.autocall_start_period else "❌"
                                     for i in range(run_terms.n_obs)],
                })
                st.dataframe(ac_df, use_container_width=True, hide_index=True)

            st.markdown("---")

            mc_tab1, mc_tab2, mc_tab3, mc_tab4 = st.tabs([
                "📊 Payoff & Distribution", "📈 Price Paths",
                "🔍 Path Explorer",         "🔗 Correlation Diagnostics",
            ])

            with mc_tab1:
                st.subheader("IRR Distribution — All Simulated Paths")
                coupon_pa = run_terms.coupon_pa
                st.plotly_chart(
                    build_irr_distribution(
                        R["annualized_returns"], R["autocall_events"],
                        R["expected_irr"], coupon_pa, tr,
                    ),
                    use_container_width=True,
                )
                if R["prob_knock_in_total"] > 0:
                    st.info(f"**{R['prob_knock_in_total']:.1%}** of paths trigger the "
                            f"knock-in barrier ({run_terms.knock_in_barrier:.0%}) at maturity.")

            with mc_tab2:
                st.subheader("Simulated Price Path Fan Charts")
                st.markdown("#### Worst-of Basket Performance")
                st.plotly_chart(
                    build_wof_fan(wof_paths, t_grid, run_terms.knock_in_barrier, obs_pairs, tr),
                    use_container_width=True,
                )
                st.markdown("#### Individual Underlying Paths")
                for i, name in enumerate(asset_names):
                    st.plotly_chart(
                        build_fan_chart(sim_prices[:, :, i], name, t_grid, obs_pairs, tr),
                        use_container_width=True,
                    )

            with mc_tab3:
                st.subheader("Single Path Explorer")
                max_path = sim_prices.shape[0] - 1
                pc1, pc2, pc3 = st.columns(3)
                if pc1.button("🎲 Random"):
                    st.session_state["path_num"] = random.randint(0, max_path)
                if pc2.button("⬅ Prev"):
                    st.session_state["path_num"] = max(0, st.session_state["path_num"] - 1)
                if pc3.button("Next ➡"):
                    st.session_state["path_num"] = min(max_path, st.session_state["path_num"] + 1)

                pn = st.session_state["path_num"]
                st.caption(f"Path #{pn} of {max_path}")
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
                    st.markdown(f"### ✅ Autocalled at period {autocall_q} ({t_q:.3g}Y)")
                elif ki:
                    st.markdown(f"### ⚠️ Maturity — Knock-in (worst-of: {worst_f:.1%})")
                else:
                    st.markdown(f"### 📈 Maturity — No knock-in (worst-of: {worst_f:.1%})")

                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Principal", f"{principal:.2%}")
                mc2.metric("Coupons",   f"{coupons:.2%}")
                mc3.metric("IRR p.a.",  f"{irr:.2%}")

            with mc_tab4:
                st.subheader("Correlation Diagnostics")
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
                    f"Max off-diagonal error: **{max_err:.4f}**"
                )
                st.markdown("---")
                st.subheader("Calibrated Heston Parameters")
                rows = []
                for p in R["params"]:
                    ok, _ = p.feller_condition()
                    rows.append({
                        "Asset": p.name, "S₀": f"{p.S0:.1f}",
                        "μ p.a.": f"{p.mu*100:.1f}%",
                        "V₀ σ":   f"{np.sqrt(p.V0)*100:.1f}%",
                        "θ σ LR": f"{np.sqrt(p.theta)*100:.1f}%",
                        "κ": f"{p.kappa:.3f}", "ξ": f"{p.xi:.3f}", "ρ": f"{p.rho:.3f}",
                        "Feller": "✅" if ok else "⚠️",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.info(f"**Student-t Copula:** ν = {R.get('t_dof','N/A')} d.f.")

    # ══════════════════════════════════════════════════════════════════
    # TAB 2 — HISTORICAL BACKTEST
    # ══════════════════════════════════════════════════════════════════
    with tab_bt:
        st.header("📅 Historical Backtest")
        st.markdown("Evaluates this note on every valid issue date using actual realized prices.")

        # ── Load full price history (max) for path explorer ───────────
        _history_years = st.session_state.get("history_years", 5.0)
        try:
            _all_prices = _load_prices(tickers_tuple, years=None)
            _min_date   = _all_prices.index.min().date()
            _max_date   = _all_prices.index.max().date()
        except Exception:
            _all_prices = None
            _min_date   = None
            _max_date   = None

        import datetime as _dt

        # ── Date range pickers ────────────────────────────────────────
        _bt_start_default = st.session_state.get("bt_start_default", _min_date)
        _bt_end_default   = st.session_state.get("bt_end_default",   _max_date)

        if _min_date and _bt_start_default and _bt_start_default < _min_date:
            _bt_start_default = _min_date
        if _max_date and _bt_end_default and _bt_end_default > _max_date:
            _bt_end_default = _max_date

        bdc1, bdc2, bdc3 = st.columns([2, 2, 1])
        with bdc1:
            bt_start_val = st.date_input(
                "Backtest start (issue dates from)",
                value=_bt_start_default,
                min_value=_min_date,
                max_value=_max_date,
                key="bt_start_picker",
            )
        with bdc2:
            bt_end_val = st.date_input(
                "Backtest end (issue dates until)",
                value=_bt_end_default,
                min_value=_min_date,
                max_value=_max_date,
                key="bt_end_picker",
            )
        with bdc3:
            st.markdown("<br>", unsafe_allow_html=True)
            apply_bt = st.button("Apply", key="bt_apply_btn", use_container_width=True)

        # Only commit the new date range when the user clicks Apply.
        # This prevents an expensive backtest rerun on every keystroke.
        if apply_bt:
            st.session_state["bt_start_default"] = bt_start_val
            st.session_state["bt_end_default"]   = bt_end_val

        # Use the last confirmed values (not the live picker state) as the
        # actual filter passed to the backtest.
        _confirmed_start = st.session_state.get("bt_start_default", _min_date)
        _confirmed_end   = st.session_state.get("bt_end_default",   _max_date)
        bt_start_str = str(_confirmed_start) if _confirmed_start else None
        bt_end_str   = str(_confirmed_end)   if _confirmed_end   else None

        with st.spinner("Running historical backtest…"):
            try:
                bt, bt_summary = _run_backtest_cached(
                    tickers_tuple, terms.to_json(),
                    bt_start_str=bt_start_str,
                    bt_end_str=bt_end_str,
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
            bt.loc[(bt["Call Quarter"] == 0) & (bt["Worst Final Perf"] < terms.knock_in_barrier),
                   "Outcome"] = "Knock-in"
            color_map = {
                "Maturity": "#3498db", "Knock-in": "#e74c3c",
                **{f"Autocalled P{i}": f"hsl({120 - i*4},55%,38%)" for i in range(1, terms.n_obs + 1)},
            }

            b1, b2, b3, b4, b5 = st.columns(5)
            b1.metric("Issue Dates",  str(bt_summary.get("n_issues", 0)))
            b2.metric("Mean IRR",     f"{bt_summary.get("mean_irr", 0):.2%}")
            b3.metric("Median IRR",   f"{bt_summary.get("median_irr", 0):.2%}")
            b4.metric("Knock-in %",   f"{bt_summary.get("prob_knock_in", 0):.1%}")
            b5.metric("Autocalled %", f"{bt_summary.get("prob_called", 0):.1%}")

            col1, col2 = st.columns(2)
            col1.plotly_chart(build_backtest_outcome_bar(bt, color_map, tr), use_container_width=True)
            col2.plotly_chart(build_worst_asset_pie(bt, tr),                 use_container_width=True)
            st.plotly_chart(build_backtest_irr_scatter(bt, color_map, tr),   use_container_width=True)

            try:
                _hist_chart_prices = _load_prices(tickers_tuple, years=None)
                bt_start_mark = bt["Issue Date"].min()
                bt_end_mark   = bt["Issue Date"].max()
                st.plotly_chart(build_historical_prices(_hist_chart_prices, bt_start_mark, bt_end_mark, tr),
                                use_container_width=True)
            except Exception:
                pass

            st.subheader("📅 Historical Path Explorer")
            st.caption("Select any issue date from the backtest to see the actual "
                       "per-asset performance and worst-of path over the note's life.")

            issue_dates = sorted(bt["Issue Date"].unique())

            _prev_dates = st.session_state.get("bt_issue_dates_list", [])
            if list(issue_dates) != list(_prev_dates):
                st.session_state["bt_issue_dates_list"] = list(issue_dates)
                st.session_state["bt_issue_idx"] = 0

            _issue_idx = min(st.session_state.get("bt_issue_idx", 0), len(issue_dates) - 1)

            selected_issue = st.selectbox(
                "Issue date",
                issue_dates,
                index=_issue_idx,
                format_func=lambda d: d.strftime("%Y-%m-%d"),
                key="bt_issue_selector",
            )

            if selected_issue is not None:
                row = bt[bt["Issue Date"] == selected_issue].iloc[0]
                st.markdown(
                    f"**Outcome:** {row['Outcome']} &nbsp;|&nbsp; "
                    f"**IRR:** {row['IRR']:.2%} &nbsp;|&nbsp; "
                    f"**Worst asset:** {row['Worst Asset']} "
                    f"({row['Worst Final Perf']:.1%})"
                )
                try:
                    if _all_prices is not None:
                        maturity_days   = round(terms.maturity * 252)
                        obs_day_offsets = [round(t / terms.maturity * maturity_days)
                                           for t in terms.obs_times()]
                        st.plotly_chart(
                            build_historical_wof_path(
                                _all_prices,
                                issue_date        = selected_issue,
                                maturity_days     = maturity_days,
                                obs_day_offsets   = obs_day_offsets,
                                knock_in_barrier  = terms.knock_in_barrier,
                                autocall_barrier  = terms.autocall_barrier,
                                call_quarter      = int(row["Call Quarter"]),
                                tr                = tr,
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
            _mat_ts    = _issue_ts + pd.Timedelta(days=round(run_terms.maturity * 365.25))
            _mat_days  = round(run_terms.maturity * 252)
            _obs_offsets = [round(t / run_terms.maturity * _mat_days) for t in obs_times_l]

            # How far through the note's life are we?
            _elapsed_days = (_today_ts - _issue_ts).days
            _elapsed_years = _elapsed_days / 365.25
            _remaining_years = run_terms.maturity - _elapsed_years
            _pct_elapsed = min(_elapsed_years / run_terms.maturity, 1.0)

            st.markdown(
                f"**Issue date:** {_issue_ts.date()} &nbsp;·&nbsp; "
                f"**Maturity:** {_mat_ts.date()} &nbsp;·&nbsp; "
                f"**Elapsed:** {_elapsed_years:.2f}Y &nbsp;·&nbsp; "
                f"**Remaining:** {max(_remaining_years, 0):.2f}Y"
            )
            st.progress(min(_pct_elapsed, 1.0))

            # Fetch live prices from issue date to today
            try:
                _live_prices = _load_prices(tickers_tuple, years=None)
                _live_prices = _live_prices[_live_prices.index >= _issue_ts]

                if len(_live_prices) < 2:
                    st.warning("Not enough live price data since issue date.")
                else:
                    _issue_idx   = _live_prices.index.searchsorted(_issue_ts)
                    _S0          = _live_prices.iloc[_issue_idx].values.astype(float)
                    _today_slice = _live_prices[_live_prices.index <= _today_ts]
                    _perf_today  = _today_slice.iloc[-1].values / _S0
                    _wof_today   = float(_perf_today.min())
                    _worst_asset_today = asset_names[int(_perf_today.argmin())]

                    # ── Live summary metrics ──────────────────────────
                    _lc1, _lc2, _lc3, _lc4 = st.columns(4)
                    _lc1.metric("Worst-of Today",  f"{_wof_today:.1%}",
                                delta=f"{_wof_today - 1.0:.1%} vs strike")
                    _lc2.metric("Worst Asset",     _worst_asset_today)
                    _lc3.metric("vs KI Barrier",
                                f"{_wof_today / run_terms.knock_in_barrier:.1%}",
                                delta=f"{_wof_today - run_terms.knock_in_barrier:.1%}",
                                delta_color="normal")
                    _lc4.metric("vs Autocall",
                                f"{_wof_today / run_terms.autocall_barrier:.1%}",
                                delta=f"{_wof_today - run_terms.autocall_barrier:.1%}",
                                delta_color="normal")

                    # ── Per-asset current performance ─────────────────
                    st.markdown("#### Current Asset Performance")
                    _asset_cols = st.columns(len(asset_names))
                    for _i, (_aname, _acol) in enumerate(zip(asset_names, _asset_cols)):
                        _ap = float(_perf_today[_i])
                        _acol.metric(_aname, f"{_ap:.1%}", f"{_ap - 1.0:.1%} vs strike")

                    # ── Coupon status replay ──────────────────────────
                    st.markdown("#### Observation History")
                    _pending_coupons = 0
                    _total_coupons_paid = 0.0
                    _obs_rows = []
                    for _q, (_offset, _label) in enumerate(zip(_obs_offsets, obs_labels)):
                        _obs_abs_idx = _issue_idx + _offset
                        if _obs_abs_idx >= len(_live_prices):
                            _obs_rows.append({
                                "Period": _label, "Date": "—", "Status": "⏳ Upcoming",
                                "Worst-of": "—", "Coupon": "—", "Cumulative": "—",
                            })
                            continue
                        _obs_date = _live_prices.index[_obs_abs_idx]
                        if _obs_date > _today_ts:
                            _obs_rows.append({
                                "Period": _label,
                                "Date": str(_obs_date.date()),
                                "Status": "⏳ Upcoming",
                                "Worst-of": "—", "Coupon": "—", "Cumulative": "—",
                            })
                            continue
                        _obs_perf = _live_prices.iloc[_obs_abs_idx].values / _S0
                        _obs_wof  = float(_obs_perf.min())
                        _coupon_met = _obs_wof >= run_terms.coupon_barrier
                        _autocall_eligible = (_q + 1) >= run_terms.autocall_start_period
                        _autocall_fired = _autocall_eligible and _obs_wof >= run_terms.autocall_barrier

                        if _coupon_met:
                            _period_coupon = run_terms.coupon_rate * (_pending_coupons + 1) if run_terms.memory else run_terms.coupon_rate
                            _pending_coupons = 0
                            _total_coupons_paid += _period_coupon
                            _status = "🚀 AUTOCALLED" if _autocall_fired else "✅ Coupon paid"
                        else:
                            _period_coupon = 0.0
                            if run_terms.memory:
                                _pending_coupons += 1
                            _status = "❌ Coupon missed"

                        _obs_rows.append({
                            "Period":     _label,
                            "Date":       str(_obs_date.date()),
                            "Status":     _status,
                            "Worst-of":   f"{_obs_wof:.1%}",
                            "Coupon":     f"{_period_coupon:.4%}" if _period_coupon > 0 else "—",
                            "Cumulative": f"{_total_coupons_paid:.4%}",
                        })
                        if _autocall_fired:
                            break

                    _obs_df = pd.DataFrame(_obs_rows)
                    st.dataframe(_obs_df, use_container_width=True, hide_index=True)

                    if _pending_coupons > 0:
                        st.info(
                            f"**{_pending_coupons} coupon(s) pending** in memory — "
                            f"worth **{_pending_coupons * run_terms.coupon_rate:.4%}** "
                            f"(paid when worst-of next exceeds {run_terms.coupon_barrier:.0%})."
                        )

                    _irr_to_date = _total_coupons_paid / max(_elapsed_years, 1/252)
                    st.metric("Coupon IRR to date (annualised)", f"{_irr_to_date:.2%}")

                    # ── Live performance chart ────────────────────────
                    st.plotly_chart(
                        build_live_performance_chart(
                            hist_prices        = _live_prices,
                            issue_date         = _issue_ts,
                            today              = _today_ts,
                            maturity_date      = _mat_ts,
                            obs_day_offsets    = _obs_offsets,
                            obs_labels         = obs_labels,
                            knock_in_barrier   = run_terms.knock_in_barrier,
                            autocall_barrier   = run_terms.autocall_barrier,
                            coupon_barrier     = run_terms.coupon_barrier,
                            coupon_rate        = run_terms.coupon_rate,
                            memory             = run_terms.memory,
                            autocall_start_period = run_terms.autocall_start_period,
                            tr                 = tr,
                        ),
                        use_container_width=True,
                    )

            except Exception as _e:
                st.error(f"Could not load live price data: {_e}")