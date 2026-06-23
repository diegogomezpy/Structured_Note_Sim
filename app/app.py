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
from data.loader     import (load_prices, load_dividends, build_dividend_schedule,
                             load_underlying_metrics, resolve_issuer_summary,
                             fetch_business_summary, translate_text)

from translations import Translator
from charts import (
    build_irr_distribution, build_fan_chart, build_wof_fan,
    build_path_wof_chart, build_corr_heatmap,
    build_backtest_outcome_bar, build_worst_asset_pie,
    build_backtest_irr_scatter, build_historical_prices,
    build_historical_wof_path, build_live_performance_chart,
    build_underlying_price_chart,
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
    "julius baer":      "juliusbaer.com",
    "bank julius baer": "juliusbaer.com",
    "bank julius baer & co. ltd.": "juliusbaer.com",
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
from underlyings import (  # shared ticker universe + logo maps + label helper
    UNDERLYING_OPTIONS, UNDERLYING_LABELS, _LOGO_BASE, TICKER_LOGOS,
    _TICKER_TO_LABEL, _label_to_name,
)


def _logo_src(sym: str | None) -> str:
    """<img src> for a ticker logo: a user-uploaded custom logo (as a base64
    data URI) when one exists for this symbol, else the favicon/CDN URL. Returns
    '' when there is no symbol, so callers can guard on truthiness."""
    if not sym:
        return ""
    custom = st.session_state.get("custom_logos", {}).get(sym)
    if custom:
        import base64
        return "data:image/png;base64," + base64.b64encode(custom).decode("ascii")
    return TICKER_LOGOS.get(sym) or _LOGO_BASE.format(sym=sym)


def _live_card(label: str, value: str, *, delta: str | None = None,
               delta_kind: str = "neutral", help_text: str | None = None,
               logo: str | None = None, logo_with_value: bool = False,
               value_text: bool = False) -> str:
    """Build one '.snsim-metric-card' (a metric card that can carry a logo).
    Used for every live-tab card so a row stays uniform height with logos inside
    the box. `logo_with_value=True` puts the logo beside the value (name cards);
    otherwise it sits in the label (per-asset cards). `value_text=True` marks the
    value as free text (e.g. an asset name) so it wraps at a smaller size instead
    of the big numeric style that overflows. delta_kind: neg/pos/neutral."""
    import html as _html
    logo_img = (f"<img src='{logo}' class='smc-logo' onerror=\"this.style.display='none'\"/>"
                if logo else "")
    label_logo = logo_img if (logo and not logo_with_value) else ""
    value_logo = logo_img if (logo and logo_with_value) else ""
    help_html = (f"<span class='smc-help' title=\"{_html.escape(str(help_text), quote=True)}\">?</span>"
                 if help_text else "")
    delta_html = f"<div class='smc-delta {delta_kind}'>{delta}</div>" if delta else ""
    value_cls = "smc-value smc-value--text" if value_text else "smc-value"
    return (
        "<div class='snsim-metric-card'>"
        f"<div class='smc-label'>{label_logo}<span>{label}</span>{help_html}</div>"
        f"<div class='{value_cls}'>{value_logo}<span>{value}</span></div>"
        f"{delta_html}</div>"
    )


def _asset_chip(name: str, sym: str) -> str:
    """A compact underlying chip: logo + display name + ticker symbol."""
    import html as _html
    logo = _logo_src(sym)
    logo_img = (f"<img src='{logo}' class='ac-logo' onerror=\"this.style.display='none'\"/>"
                if logo else "")
    return (
        "<div class='snsim-asset-chip'>"
        f"{logo_img}"
        f"<span class='ac-text'><span class='ac-name'>{_html.escape(str(name))}</span>"
        f"<span class='ac-sym'>{_html.escape(str(sym))}</span></span></div>"
    )


def _fmt_market_cap(v) -> str:
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


def _render_underlying_card(name, sym, metrics, override, prices_1y, tr) -> None:
    """One underlying's breakdown for the note-structure expander: logo + long
    name + type/sector, a metric row (market cap / 3M IV / last price / RSI), the
    company description, and a trailing-12-month price chart. `metrics` is the
    live data pull; `override` are per-field JSON values from terms.underlyings
    (a present override wins over the live value)."""
    import html as _html
    metrics  = metrics or {}
    override = override or {}

    def _f(key):
        ov = override.get(key)
        return ov if ov not in (None, "") else metrics.get(key)

    long_name = _f("long_name") or name
    sub = " · ".join(s for s in (_f("type"), _f("sector")) if s) or "—"
    logo = _logo_src(sym)
    logo_img = (f"<img src='{logo}' style='height:26px;border-radius:5px;"
                f"vertical-align:middle;margin-right:8px' "
                f"onerror=\"this.style.display='none'\"/>" if logo else "")
    st.markdown(
        f"<div style='margin-top:8px'>{logo_img}"
        f"<span style='font-weight:600;font-size:1.02rem;vertical-align:middle'>"
        f"{_html.escape(str(long_name))}</span>&nbsp;"
        f"<span style='color:#6b7280;font-size:0.85rem'>{_html.escape(sub)}</span></div>",
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4 = st.columns(4)
    iv, lp, rsi = _f("iv_3m"), _f("last_price"), _f("rsi_14")
    _realized = _f("iv_source") == "realized"
    _iv_lbl  = tr("ul_vol_3m_realized") if _realized else tr("ul_iv_3m")
    _iv_help = tr("ul_vol_3m_realized_help") if _realized else tr("ul_iv_3m_help")
    m1.metric(tr("ul_market_cap"), _fmt_market_cap(_f("market_cap")))
    m2.metric(_iv_lbl, f"{float(iv)*100:.1f}%" if iv not in (None, "") else "—",
              help=_iv_help)
    m3.metric(tr("ul_last_price"), f"{float(lp):,.2f}" if lp not in (None, "") else "—")
    m4.metric(tr("ul_rsi"),    f"{float(rsi):.0f}"     if rsi not in (None, "") else "—")

    # A user-entered description wins as-is; otherwise show the full Yahoo
    # business summary. In Spanish mode, auto-translate it for display (cached;
    # idempotent for text that is already Spanish) so a loaded note's English
    # descriptions follow the UI language without re-prefilling.
    desc = override.get("description") or metrics.get("business_summary") or ""
    if desc and getattr(tr, "lang", "en") == "es":
        desc = _translate_cached(desc, "es")
    if desc:
        st.caption(desc)

    cols = getattr(prices_1y, "columns", [])
    if prices_1y is not None and name in cols:
        try:
            fig = build_underlying_price_chart(prices_1y[name], name, tr)
            fig.update_layout(height=200, margin=dict(l=44, r=12, t=6, b=24))
            st.plotly_chart(fig, use_container_width=True, key=f"ulchart_{sym}")
        except Exception:
            pass


def _setup_header(num: int, title: str) -> None:
    """Render a numbered setup-section header (a step badge + title)."""
    import html as _html
    st.markdown(
        f"<div class='setup-h'><span class='setup-h-num'>{num}</span>"
        f"<span class='setup-h-title'>{_html.escape(str(title))}</span></div>",
        unsafe_allow_html=True,
    )


def _tab_intro(kind: str, number: str, eyebrow: str, question: str) -> None:
    """Render a top-level tab's intro band — the shared opener for the three
    analysis lenses. `kind` ('mc' | 'bt' | 'live') selects the badge accent so
    each lens is distinct but structurally identical (number badge + tense
    eyebrow + the question the lens answers). Mirrors the PDF part dividers."""
    import html as _html
    st.markdown(
        f"<div class='snsim-tab-intro {kind}'>"
        f"<span class='sti-num'>{_html.escape(str(number))}</span>"
        f"<span class='sti-text'>"
        f"<span class='sti-eyebrow'>{_html.escape(str(eyebrow))}</span>"
        f"<span class='sti-q'>{_html.escape(str(question))}</span></span></div>",
        unsafe_allow_html=True,
    )

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
    "issuer_logo_bytes": None,   # user-uploaded custom issuer logo (overrides favicon)
    "custom_logos":     {},      # {yf_symbol: bytes} — uploaded underlying logos (override favicons)
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Auto-load a local firm branding file (branding/branding_<firm>.json — the
# convention documented in .gitignore) ONCE per session, so the user's branding
# stays "logged in" without re-uploading on every restart. A one-shot flag means
# an explicitly cleared branding stays cleared on later reruns.
if not st.session_state.get("_branding_autoloaded"):
    st.session_state["_branding_autoloaded"] = True
    if st.session_state.get("branding") is None:
        import glob as _glob_b, json as _json_b, os as _os_b
        for _bpath in sorted(_glob_b.glob("branding/branding_*.json")):
            if _os_b.path.basename(_bpath) == "branding_example.json":
                continue
            try:
                with open(_bpath, encoding="utf-8") as _bf:
                    st.session_state["branding"] = _json_b.load(_bf)
                break
            except Exception:
                pass

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

@st.cache_data(ttl=3600, show_spinner=False)
def _load_underlying_metrics_cached(tickers_tuple):
    """Per-underlying summary metrics for the Underlying Breakdown (market cap,
    sector, type, last price, RSI, 3M IV, business summary). Cached 1h; reuses
    the 1Y close series for RSI / last price so it costs one info + options call
    per ticker. Returns {} on a hard failure so the dashboard degrades cleanly."""
    try:
        prices = _load_prices(tickers_tuple, years=1.0)
        closes = {name: prices[name] for name in prices.columns}
    except Exception:
        closes = None
    try:
        return load_underlying_metrics(dict(tickers_tuple), closes=closes)
    except Exception as e:
        print(f"[app] underlying metrics failed: {e}")
        return {}

# Issuer-summary cache keyed on name. Only SUCCESSFUL resolutions are cached;
# a None (transient Yahoo blip, or a subsidiary name that didn't resolve) is NOT,
# so a single failure doesn't pin "no description" for the rest of the session —
# same bug class as the logo / translation caches. Not st.cache_data (which would
# cache the None for 24h).
_ISSUER_SUMMARY_CACHE: dict[str, str] = {}


def _resolve_issuer_summary_cached(name):
    """Issuer business summary resolved from its name via Yahoo search (for the
    issuer-description prefill). Caches only real summaries; retries after a miss."""
    if not name:
        return None
    if name in _ISSUER_SUMMARY_CACHE:
        return _ISSUER_SUMMARY_CACHE[name]
    try:
        out = resolve_issuer_summary(name)
    except Exception:
        out = None
    if out:
        _ISSUER_SUMMARY_CACHE[name] = out
    return out


# Per-underlying business-summary cache keyed on symbol. Same "cache only real
# hits" policy as the issuer cache. Uses the lightweight fetch_business_summary
# (one .info read, no option-chain IV / RSI work) so the prefill button doesn't
# wait on the full metrics bundle it would only throw away.
_UL_SUMMARY_CACHE: dict[str, str] = {}


def _fetch_ul_summary_cached(sym):
    """Business summary for one underlying symbol, for the description prefill."""
    if not sym:
        return None
    if sym in _UL_SUMMARY_CACHE:
        return _UL_SUMMARY_CACHE[sym]
    try:
        out = fetch_business_summary(sym)
    except Exception:
        out = None
    if out:
        _UL_SUMMARY_CACHE[sym] = out
    return out

# Translation cache keyed on (text, target). Only SUCCESSFUL translations are
# cached; a failure (returns the input unchanged) is NOT, so a transient blip —
# or a click made before deep-translator was installed — doesn't pin the English
# fallback for the rest of the session (same bug class as the logo cache). Not
# st.cache_data, which would cache the failed result too.
_TRANSLATION_CACHE: dict[tuple, str] = {}


def _translate_cached(text, target_lang):
    """Best-effort translation of a (Yahoo) description into the UI language for
    the prefill buttons. Caches only real translations; retries after a failure."""
    if not text or target_lang in (None, "", "en"):
        return text
    key = (text, target_lang)
    if key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[key]
    try:
        out = translate_text(text, target_lang)
    except Exception:
        out = text
    if out and out != text:          # a genuine translation — cache it
        _TRANSLATION_CACHE[key] = out
    return out


def _path_filter_matches(autocall_events, knock_in, total_returns, coupon_amounts,
                         outcome="any", ac_periods=None, ki_choice="any",
                         ret_lo=None, ret_hi=None, coupon_periods=None):
    """Return the sorted indices of paths matching the path-explorer query.

    Operates on the per-path arrays price_note already returns, so the same
    filter logic serves the Monte Carlo explorer (and, fed the backtest's
    per-issue arrays, the backtest explorer). All clauses are AND-combined:

      outcome        "any" | "autocalled" | "maturity" | "loss" (maturity + KI)
      ac_periods     restrict autocalls to these 1-indexed periods (None = any)
      ki_choice      "any" | "yes" | "no"   (knock-in actually cost capital)
      ret_lo/ret_hi  inclusive total-return band (None = unbounded that side)
      coupon_periods path must have paid a coupon at EACH listed 1-indexed period
                     (needs the coupon matrix; ignored when it's unavailable —
                     e.g. a results dict cached before the matrix was exposed)
    """
    ac   = np.asarray(autocall_events)
    ki   = np.asarray(knock_in, dtype=bool)
    ret  = np.asarray(total_returns, dtype=float)
    mask = np.ones(ac.shape[0], dtype=bool)

    if outcome == "autocalled":
        mask &= ac > 0
        if ac_periods:
            mask &= np.isin(ac, list(ac_periods))
    elif outcome == "maturity":
        mask &= ac == 0
    elif outcome == "loss":
        mask &= (ac == 0) & ki

    if ki_choice == "yes":
        mask &= ki
    elif ki_choice == "no":
        mask &= ~ki

    if ret_lo is not None:
        mask &= ret >= ret_lo
    if ret_hi is not None:
        mask &= ret <= ret_hi

    if coupon_periods and coupon_amounts is not None:
        ca = np.asarray(coupon_amounts)
        for p in coupon_periods:
            if 1 <= int(p) <= ca.shape[1]:
                mask &= ca[:, int(p) - 1] > 0

    return np.nonzero(mask)[0]


def _build_path_marker_info(rows, autocall_q, n_obs, wof_levels, knock_in, terms, tr):
    """Per-observation legend entries for the path-explorer worst-of chart.

    `rows` are replay_note(...)['rows'] (the canonical per-period facts);
    `wof_levels[i]` is the worst-of at observation i. Returns one {text, kind}
    per LIVE observation (the list stops at the autocall — the note is gone
    after). Each label states the full note state at that date: worst-of level,
    the coupon outcome (paid amount, memory multiplier or pending count, or an
    accruing / paid premium for growth autocalls), the autocall, and at maturity
    the knock-in vs par-redemption result.
    """
    info = []
    n_live = autocall_q if autocall_q > 0 else n_obs
    rate = terms.coupon_rate
    for i in range(n_live):
        period       = i + 1
        row          = rows[i] if i < len(rows) else None
        amt          = float(row["coupon_amount"]) if row else 0.0
        pending      = int(row["pending_after"]) if row else 0
        called       = (autocall_q == period)
        reached_mat  = (autocall_q == 0 and period == n_obs)

        parts = [f"P{period}", tr("leg_wof", v=f"{wof_levels[i]:.0%}")]
        if called:
            parts.append(tr("leg_called"))
        elif reached_mat:
            parts.append(tr("leg_maturity"))

        if terms.coupon_at_autocall_only:                 # growth autocall premium
            if amt > 0:
                parts.append(tr("leg_premium", v=f"{amt:.2%}", k=period))
            elif not called and not reached_mat:
                parts.append(tr("leg_accruing"))
        elif amt > 0:                                     # coupon paid
            released = round(amt / rate) if rate else 1
            if terms.memory and released > 1:
                parts.append(tr("leg_coupon_memory", v=f"{amt:.2%}", k=released))
            else:
                parts.append(tr("leg_coupon", v=f"{amt:.2%}"))
        else:                                             # coupon missed
            if terms.memory and pending > 0:
                parts.append(tr("leg_no_coupon_pending", k=pending))
            else:
                parts.append(tr("leg_no_coupon"))

        if reached_mat:
            parts.append(tr("leg_knock_in") if knock_in else tr("leg_redeemed_par"))

        if reached_mat and knock_in:
            kind = "knock_in"
        elif called:
            kind = "call_coupon" if amt > 0 else "call"
        else:
            kind = "coupon" if amt > 0 else "missed"
        info.append({"text": " · ".join(parts), "kind": kind})
    return info


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


# Build-report panel tree: category -> (category label key, [sub-items]).
# Each sub-item is (widget_id, label_key, [fine PDF keys it maps to]). The fine
# keys are what generate_pdf_report gates on via include_sections; "__mc_fans__"
# Path-explorer filter vocabularies. MODULE-level so BOTH the Monte Carlo and the
# backtest explorer panels can reference them — the backtest tab renders (and its
# explorer fragment reruns) independently of whether the MC sim has run, so these
# must never be scoped to the MC results block.
_OUTCOMES   = ["any", "autocalled", "maturity", "loss"]
_KI_CHOICES = ["any", "yes", "no"]

# expands to one mc_fan_{i} per underlying. A category master toggle ticks/clears
# all of its sub-items at once.
_REPORT_TREE = {
    "note": ("report_cat_note", [
        ("note_terms",  "rep_note_terms",  ["note_terms"]),
        ("note_obs",    "rep_note_obs",    ["obs_schedule"]),
        ("note_issuer", "rep_note_issuer", ["issuer_info"]),
        ("note_uls",    "rep_note_uls",    ["underlying_breakdown"]),
    ]),
    "mc": ("report_cat_mc", [
        ("mc_summary",  "rep_mc_summary",  ["mc_metrics"]),
        ("mc_autocall", "rep_mc_autocall", ["mc_autocall"]),
        ("mc_irr",      "rep_mc_irr",      ["mc_irr"]),
        ("mc_wof",      "rep_mc_wof",      ["mc_wof"]),
        ("mc_fans",     "rep_mc_fans",     ["__mc_fans__"]),
        ("mc_explorer", "rep_mc_explorer", ["mc_single_wof"]),
        ("mc_corr",     "rep_mc_corr",     ["calib_corr"]),
        ("mc_calib",    "rep_mc_calib",    ["calib_table"]),
    ]),
    "bt": ("report_cat_bt", [
        ("bt_summary",  "rep_bt_summary",  ["bt_metrics"]),
        ("bt_outcome",  "rep_bt_outcome",  ["bt_outcome"]),
        ("bt_pie",      "rep_bt_pie",      ["bt_pie"]),
        ("bt_irr",      "rep_bt_irr",      ["bt_irr"]),
        ("bt_prices",   "rep_bt_prices",   ["bt_prices"]),
        ("bt_path",     "rep_bt_path",     ["bt_path"]),
    ]),
    "live": ("report_cat_live", [
        ("live_metrics", "rep_live_metrics", ["live_metrics"]),
        ("live_assets",  "rep_live_assets",  ["live_asset_table"]),
        ("live_obs",     "rep_live_obs",     ["live_obs_table"]),
        ("live_chart",   "rep_live_chart",   ["live_chart"]),
    ]),
}


def _toggle_report_category(cat: str) -> None:
    """Master-toggle callback: set every sub-item in a category to the master's
    new value (ticking the master selects the whole category, unticking clears it)."""
    val = st.session_state.get(f"rep_master_{cat}", True)
    for sub_id, _lbl, _fine in _REPORT_TREE[cat][1]:
        st.session_state[f"rep_sub_{sub_id}"] = val


def _collect_pdf_sections(n_assets: int = 0, has_live: bool = True) -> set[str]:
    """Expand the Build-report panel's per-analysis checkboxes into the
    fine-grained include_sections keys the PDF gates on. Each item defaults ON."""
    sel: set[str] = set()
    for cat, (_cat_label, subs) in _REPORT_TREE.items():
        for sub_id, _lbl, fine_keys in subs:
            if not st.session_state.get(f"rep_sub_{sub_id}", True):
                continue
            for fk in fine_keys:
                if fk == "__mc_fans__":
                    sel.update(f"mc_fan_{i}" for i in range(n_assets))
                else:
                    sel.add(fk)
    return sel


def _pdf_needs_mc() -> bool:
    """True if any selected report section is sourced from the Monte Carlo sim.
    Used to skip the (slow) simulation entirely when the requested PDF only
    contains Note-details / backtest / live sections — none of which need it."""
    return any(st.session_state.get(f"rep_sub_{sub_id}", True)
               for sub_id, _lbl, _fine in _REPORT_TREE["mc"][1])


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
    _setup_header(1, tr("setup_underlyings_header"))

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
        # Selected underlyings shown as chips (matches the dashboard).
        logo_cols = st.columns(min(len(selected_labels), 5))
        for _i, _lbl in enumerate(selected_labels[:5]):
            _sym = _lbl_to_sym.get(_lbl) or ""
            logo_cols[_i].markdown(
                _asset_chip(_label_to_name(_lbl), _sym), unsafe_allow_html=True)

        # ── Custom logos (override the favicon/CDN logo per underlying) ────
        with st.expander(tr("setup_custom_logos_header")):
            st.caption(tr("setup_custom_logos_caption"))
            _cl = dict(st.session_state.get("custom_logos", {}))
            for _lbl in selected_labels[:5]:
                _sym = _lbl_to_sym.get(_lbl)
                if not _sym:
                    continue
                _ulc1, _ulc2 = st.columns([4, 1])
                with _ulc1:
                    _up = st.file_uploader(
                        _label_to_name(_lbl),
                        type=["png", "jpg", "jpeg", "gif", "webp"],
                        key=f"custom_logo_up_{_sym}",
                    )
                    if _up is not None:
                        _cl[_sym] = _up.getvalue()
                with _ulc2:
                    if _cl.get(_sym):
                        st.image(_cl[_sym], width=40)
                        if st.button(tr("setup_custom_logo_clear"),
                                     key=f"custom_logo_clear_{_sym}"):
                            _cl.pop(_sym, None)
                            st.session_state["custom_logos"] = _cl
                            st.rerun()
            st.session_state["custom_logos"] = _cl

        # ── Per-underlying company descriptions ──────────────────────────────
        # JSON-preloaded (terms.underlyings), editable here, each with a one-click
        # 'prefill from Yahoo' that drops in the business summary. The text is
        # shown in the dashboard Underlying Breakdown and the PDF (blank = hidden).
        with st.expander(tr("setup_ul_descriptions")):
            _base_uls = getattr(base, "underlyings", {}) or {}
            for _lbl in selected_labels[:5]:
                _sym = _lbl_to_sym.get(_lbl)
                if not _sym:
                    continue
                _nm  = _label_to_name(_lbl)
                _key = f"ul_desc_{_sym}"
                if _key not in st.session_state:
                    st.session_state[_key] = (_base_uls.get(_nm, {}) or {}).get("description", "") or ""
                _dc1, _dc2 = st.columns([5, 1])
                with _dc2:
                    if st.button(tr("setup_ul_prefill"), key=f"ul_prefill_{_sym}",
                                 help=tr("setup_ul_prefill_help")):
                        with st.spinner(tr("setup_ul_prefill_spinner")):
                            try:
                                _summ = _fetch_ul_summary_cached(_sym) or ""
                            except Exception:
                                _summ = ""
                        if _summ:
                            # Localise the English summary to the UI language.
                            _tgt = "es" if lang_choice == "Español" else "en"
                            _out = _translate_cached(_summ, _tgt)
                            st.session_state[_key] = _out
                            if _tgt == "es" and _out.strip() == _summ.strip():
                                st.toast(tr("ul_translate_unavailable"), icon="⚠️")
                            st.rerun()
                        else:
                            st.toast(tr("ul_metrics_failed"))
                with _dc1:
                    st.text_area(_nm, key=_key, height=80, help=tr("setup_ul_desc_help"))

    st.divider()

    # ── Note type ─────────────────────────────────────────────────────────
    _setup_header(2, tr("setup_note_type_header"))
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

    # Every section is always shown so the full set of note features is visible
    # regardless of the broad note-type picked. The picker only pre-fills
    # template-canonical defaults (see the _is_* block below); it never hides
    # fields — hiding them based on category was confusing.
    _show_coupon         = True
    _show_coupon_barrier = True
    _show_memory         = True
    _show_coupon_basket  = True
    _show_autocall       = True
    _show_growth         = True
    _show_ki             = True
    _show_min_return     = True
    _show_capprot        = True
    _show_one_star       = True

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
    _base_one_star   = getattr(base, "one_star_level", None)
    one_star_on      = _base_one_star is not None
    one_star_pct     = round((_base_one_star if _base_one_star is not None else 1.0) * 100, 4)
    capital_guarantee = getattr(base, "capital_guarantee", None)
    upside_cap        = getattr(base, "upside_cap", None)

    if _is_bonus:
        # No coupons, no autocall (barrier set unreachable); KI + floor only.
        coupon_pa_pct = 0.0; coupon_bar_pct = 0.0; memory = False
        autocall_bar_pct = 200.0; autocall_basket = "worst_of"; coupon_basket = "worst_of"
        step_down_pct = 0.0; floor_pct = 0.0; premium_at_call = False
        capital_guarantee = None; upside_cap = None; one_star_on = False
    elif _is_capprot:
        # Standalone payoff: engine ignores coupon/autocall/KI entirely.
        coupon_pa_pct = 0.0; coupon_bar_pct = 0.0; memory = False
        autocall_bar_pct = 200.0; autocall_basket = "worst_of"; coupon_basket = "worst_of"
        ki_bar_pct = 0.0; min_return_pct = 0.0
        step_down_pct = 0.0; floor_pct = 0.0; premium_at_call = False
        one_star_on = False
    elif _is_revconv:
        # Guaranteed coupon (barrier 0), no memory; standard worst-of redemption.
        coupon_bar_pct = 0.0; memory = False
        step_down_pct = 0.0; floor_pct = 0.0; premium_at_call = False
        min_return_pct = 0.0; capital_guarantee = None; upside_cap = None; one_star_on = False
    elif _is_growth:
        # Premium paid only at autocall; coupon barrier/memory n/a.
        memory = False; premium_at_call = True
        min_return_pct = 0.0; capital_guarantee = None; upside_cap = None; one_star_on = False
    elif _is_phoenix:
        step_down_pct = 0.0; floor_pct = 0.0; premium_at_call = False
        min_return_pct = 0.0; capital_guarantee = None; upside_cap = None

    # ── Schedule & Maturity ───────────────────────────────────────────────
    _setup_header(3, tr("setup_schedule_header"))
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
        _setup_header(4, tr("setup_coupon_header"))
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
    if _show_ki or _show_min_return or _show_capprot or _show_one_star:
        _setup_header(5, tr("setup_barriers_header"))
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
            # Capital protection is a mutually-exclusive payoff mode: when on,
            # the engine skips the entire Phoenix/autocall/KI waterfall. Gate it
            # behind an explicit toggle so it doesn't silently override every
            # other note type now that the section is always visible. Defaults
            # on only for a config that already has a capital guarantee.
            _capprot_on = st.toggle(
                tr("setup_capital_protected_toggle"),
                value=getattr(base, "capital_guarantee", None) is not None,
                help=tr("setup_capital_protected_toggle_help"),
            )
            if _capprot_on:
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
            else:
                capital_guarantee = None
                upside_cap = None
        if _show_one_star:
            # One Star overlay (BNP-style, also covers the BBVA XS3378405743
            # 'Barrier and Knock-in' rescue): a single underlying at or above the
            # One Star level pays the coupon, triggers the autocall, and returns
            # capital at par at maturity even when the KI was breached.
            one_star_on = st.toggle(
                tr("setup_one_star_toggle"),
                value=one_star_on,
                help=tr("setup_one_star_help"),
            )
            if one_star_on:
                one_star_pct = st.number_input(
                    tr("setup_one_star_level"), 50.0, 150.0,
                    value=one_star_pct,
                    step=0.5, format="%.2f",
                    help=tr("setup_one_star_level_help"),
                )
    one_star_level = (one_star_pct / 100.0) if one_star_on else None

    # ── Autocall ──────────────────────────────────────────────────────────
    if _show_autocall:
        _setup_header(6, tr("setup_autocall_header"))
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
                st.markdown("<br>", unsafe_allow_html=True)
                # Seed from the template-aware default (premium_at_call) so the
                # Growth template still defaults this on; always visible now.
                premium_at_call = st.toggle(
                    tr("setup_premium_at_call"),
                    value=bool(premium_at_call),
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

        # Issuer profile — powers the PDF "Issuer Information" section (on by
        # default). All optional; blanks are simply hidden in the PDF.
        # Keyed + 'prefill from Yahoo' button (resolves the issuer name to a
        # ticker and drops in its business summary), like the underlying ones.
        if "setup_issuer_desc" not in st.session_state:
            st.session_state["setup_issuer_desc"] = getattr(base, "issuer_description", "") or ""
        _idc1, _idc2 = st.columns([5, 1])
        with _idc2:
            if st.button(tr("setup_ul_prefill"), key="issuer_desc_prefill",
                         help=tr("setup_ul_prefill_help"), disabled=not issuer_input):
                with st.spinner(tr("setup_ul_prefill_spinner")):
                    _isumm = _resolve_issuer_summary_cached(issuer_input.strip()) if issuer_input else None
                if _isumm:
                    _itgt = "es" if lang_choice == "Español" else "en"
                    _iout = _translate_cached(_isumm, _itgt)
                    st.session_state["setup_issuer_desc"] = _iout
                    if _itgt == "es" and _iout.strip() == _isumm.strip():
                        st.toast(tr("ul_translate_unavailable"), icon="⚠️")
                    st.rerun()
                else:
                    st.toast(tr("ul_metrics_failed"))
        with _idc1:
            issuer_description = st.text_area(
                tr("setup_issuer_description"),
                key="setup_issuer_desc",
                height=80,
                help=tr("setup_issuer_description_help"),
            )
        _rt_a, _rt_b, _rt_c = st.columns(3)
        with _rt_a:
            issuer_rating_sp = st.text_input(
                tr("setup_rating_sp"), value=getattr(base, "issuer_rating_sp", "") or "",
                placeholder="A+",
            )
        with _rt_b:
            issuer_rating_moody = st.text_input(
                tr("setup_rating_moody"), value=getattr(base, "issuer_rating_moody", "") or "",
                placeholder="A1",
            )
        with _rt_c:
            issuer_rating_fitch = st.text_input(
                tr("setup_rating_fitch"), value=getattr(base, "issuer_rating_fitch", "") or "",
                placeholder="AA-",
            )

        # Custom issuer logo — overrides the auto-fetched favicon (e.g. when the
        # favicon can't be resolved). Bytes are kept in a non-widget session key
        # so they survive navigation between setup and dashboard.
        _iss_logo_up = st.file_uploader(
            tr("setup_issuer_logo"), type=["png", "jpg", "jpeg", "gif", "webp"],
            key="issuer_logo_upload", help=tr("setup_issuer_logo_help"),
        )
        if _iss_logo_up is not None:
            st.session_state["issuer_logo_bytes"] = _iss_logo_up.getvalue()
        if st.session_state.get("issuer_logo_bytes"):
            _il_a, _il_b = st.columns([1, 3])
            with _il_a:
                st.image(st.session_state["issuer_logo_bytes"], width=48)
            with _il_b:
                if st.button(tr("setup_issuer_logo_clear"), key="clear_issuer_logo"):
                    st.session_state["issuer_logo_bytes"] = None
                    st.rerun()

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
                disp = _label_to_name(lbl)
                if sym:
                    selected_tickers[sym] = disp
            # Per-underlying company descriptions from the setup editors, keyed by
            # display name. Any non-description override from the loaded config
            # (e.g. a hand-set sector for an index) is carried through.
            _base_uls = getattr(base, "underlyings", {}) or {}
            _uls_dict: dict = {}
            for sym, disp in selected_tickers.items():
                _d     = (st.session_state.get(f"ul_desc_{sym}", "") or "").strip()
                _extra = {k: v for k, v in (_base_uls.get(disp, {}) or {}).items()
                          if k != "description"}
                if _d or _extra:
                    _uls_dict[disp] = ({"description": _d} if _d else {}) | _extra
            terms = NoteTerms(
                name                  = note_name.strip() or "Custom Note",
                issuer                = issuer_input.strip(),
                issuer_description    = issuer_description.strip(),
                issuer_rating_sp      = issuer_rating_sp.strip(),
                issuer_rating_moody   = issuer_rating_moody.strip(),
                issuer_rating_fitch   = issuer_rating_fitch.strip(),
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
                one_star_level        = one_star_level,
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
                underlyings           = _uls_dict,
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
        f"{terms.coupon_pa*100:g}% p.a."
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

    # ── Build-report panel — choose what goes in the PDF in ONE place ─────
    # Replaces the ~20 'Include in PDF' checkboxes that used to sit next to every
    # chart. A master toggle per analysis selects/clears the whole category; each
    # analysis also has its own sub-toggle. Everything defaults ON, so the full
    # report is produced without any clicking; untick what you don't want.
    with st.sidebar.expander(tr("report_panel_header"), expanded=False):
        st.caption(tr("report_panel_caption"))
        for _cat, (_cat_label_key, _subs) in _REPORT_TREE.items():
            st.session_state.setdefault(f"rep_master_{_cat}", True)
            st.checkbox(
                f"**{tr(_cat_label_key)}**", key=f"rep_master_{_cat}",
                on_change=_toggle_report_category, args=(_cat,),
            )
            _sp, _body = st.columns([1, 14])
            with _body:
                for _sub_id, _sub_label_key, _fine in _subs:
                    st.session_state.setdefault(f"rep_sub_{_sub_id}", True)
                    st.checkbox(tr(_sub_label_key), key=f"rep_sub_{_sub_id}")
    # The button is always enabled: if the sim hasn't been run yet, clicking it
    # runs the sim first and then builds the report (see _run_for_pdf below).
    _pdf_btn = st.sidebar.button(
        tr("sidebar_generate_pdf"),
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
            f"{tr('metric_coupon_pa')} {terms.coupon_pa*100:g}% · "
            f"{tr('dash_memory') if terms.memory else tr('dash_no_memory')} · "
            f"KI {terms.knock_in_barrier:.0%} · Autocall {terms.autocall_barrier:.0%}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"**{terms.name}** — "
            f"{', '.join(selected_tickers.values())} · "
            f"{int(terms.maturity*12)}M · {terms.n_obs} obs · "
            f"{tr('metric_coupon_pa')} {terms.coupon_pa*100:g}% · "
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
            # Issuer profile (description + credit ratings) — mirrors the PDF
            # 'Issuer Information' section so it's visible in the app too.
            _iss_desc = getattr(terms, "issuer_description", "") or ""
            if _iss_desc and getattr(tr, "lang", "en") == "es":
                _iss_desc = _translate_cached(_iss_desc, "es")
            if _iss_desc:
                st.caption(_iss_desc)
            _iss_ratings = [
                ("S&P",     getattr(terms, "issuer_rating_sp", "") or ""),
                ("Moody's", getattr(terms, "issuer_rating_moody", "") or ""),
                ("Fitch",   getattr(terms, "issuer_rating_fitch", "") or ""),
            ]
            _iss_ratings = [(a, v) for a, v in _iss_ratings if v.strip()]
            if _iss_ratings:
                _rcols = st.columns(len(_iss_ratings))
                for _c, (_ag, _rv) in zip(_rcols, _iss_ratings):
                    _c.metric(_ag, _rv)

        # Underlyings — full per-underlying breakdown (metrics pulled live +
        # description + 1Y price chart), mirroring the PDF "Underlying Breakdown".
        st.markdown(tr("ul_breakdown_header"))
        _ul_overrides = getattr(terms, "underlyings", {}) or {}
        with st.spinner(tr("ul_loading")):
            _ul_metrics = _load_underlying_metrics_cached(tickers_tuple)
            try:
                _ul_prices_1y = _load_prices(tickers_tuple, years=1.0)
            except Exception:
                _ul_prices_1y = None
        if not _ul_metrics:
            st.caption(tr("ul_metrics_failed"))
        for _sym, _disp in selected_tickers.items():
            with st.container(border=True):
                _render_underlying_card(_disp, _sym, _ul_metrics.get(_disp, {}),
                                        _ul_overrides.get(_disp, {}), _ul_prices_1y, tr)

        st.divider()
        # Terms grouped (Schedule / Coupon / Barriers), mirroring the summary tabs.
        st.markdown("**" + tr("structure_group_schedule") + "**")
        s1, s2, s3 = st.columns(3)
        s1.metric(tr("metric_maturity"), f"{terms.maturity}Y")
        s2.metric(tr("metric_observations"), f"{terms.n_obs}")
        s3.metric(tr("metric_frequency"), terms.payment_freq.capitalize())
        st.markdown("**" + tr("structure_group_coupon") + "**")
        p1, p2, p3 = st.columns(3)
        p1.metric(tr("metric_coupon_pa"), f"{terms.coupon_pa*100:g}%")
        p2.metric(tr("metric_coupon_period"), f"{terms.coupon_rate*100:.4f}%")
        p3.metric(tr("metric_memory"), tr("yes") if terms.memory else tr("no_str"))
        st.markdown("**" + tr("structure_group_barriers") + "**")
        k1, k2, k3 = st.columns(3)
        k1.metric(tr("metric_coupon_barrier"), f"{terms.coupon_barrier:.0%}")
        k2.metric(tr("metric_autocall_barrier"), f"{terms.autocall_barrier:.0%}")
        k3.metric(tr("metric_ki_barrier"), f"{terms.knock_in_barrier:.0%}")
        if terms.one_star_level is not None:
            st.info(tr("one_star_info", barrier=terms.one_star_level))
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
    # Generate-report also runs the sim when none exists yet, so a PDF can be
    # produced without first clicking Run Simulation. A pending flag survives the
    # rerun so the report is built once results + figures are available.
    # ...but ONLY when the requested report actually contains a Monte Carlo
    # section. A PDF of just Note-details / backtest / live sections is built
    # straight away without running the (slow) simulation at all.
    _needs_mc    = _pdf_needs_mc()
    _run_for_pdf = _pdf_btn and st.session_state.get("results") is None and _needs_mc
    if run_button or _run_for_pdf:
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
                "effective_corr": sim_results.get("effective_corr"),
                "t_dof":          cal_result.t_dof,
                "terms_snapshot": terms.to_dict(),
                # Real-calendar grid metadata (drives charts + obs tables)
                "t_grid_years":   np.concatenate([[0.0], np.cumsum(_dt_grid)]),
                "obs_steps":      _obs_steps,
                "obs_times":      _obs_times,
            }
            st.session_state["last_asset_names"] = list(selected_tickers.values())
            st.session_state["path_num"] = 0
            # If this run was triggered by Generate-report, remember to build the
            # PDF after the rerun (once the tabs have rendered + cached figures).
            if _run_for_pdf:
                st.session_state["_pending_pdf"] = True
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
        _tab_intro("mc", "01", tr("tab_intro_mc_eyebrow"), tr("tab_intro_mc_q"))
        if not _has_sim:
            st.info(tr("mc_click_run_info"))
            with st.spinner(tr("mc_prefetch_spinner", tickers=', '.join(selected_tickers.values()))):
                try:
                    _load_prices(tickers_tuple, years=st.session_state.get("history_years", None))
                    st.success(tr("mc_market_ready"))
                except Exception as e:
                    st.error(tr("mc_fetch_failed", e=e))
        else:
            # Build the three headline MC figures ONCE per rerun and reuse the
            # same objects for both the on-screen tabs and the PDF cache. Each
            # of these runs np.percentile over the full (2·n_paths × N) array,
            # so building them twice (once here, once for display) doubled that
            # cost every rerun. They must still rebuild each rerun because the
            # Translator language can change. _fig_to_png copies the figure
            # before rasterising, so sharing the object with st.plotly_chart is
            # safe. (Language change → full script rerun → figures rebuilt.)
            _fig_irr = build_irr_distribution(
                R["annualized_returns"], R.get("total_returns"), R["autocall_events"],
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
            # Summary is now its own subtab (mirrors the Backtest tab) instead of
            # a floating metrics block + a separate autocall dropdown.
            mc_tab0, mc_tab1, mc_tab2, mc_tab3, mc_tab4 = st.tabs([
                tr("mc_subtab_summary"), tr("mc_subtab_payoff"), tr("mc_subtab_paths"),
                tr("mc_subtab_explorer"), tr("mc_subtab_corr"),
            ])

            with mc_tab0:
                # Knock-in (barrier breached at maturity), not capital loss: count
                # the knock-in event itself and average the IRR over those paths.
                _ki_mask = R.get("knock_in_mask")
                if _ki_mask is None:
                    _ki_mask = R.get("knock_in_triggered")
                _lgki = R.get("loss_given_knock_in")
                if _lgki is None and _ki_mask is not None and _ki_mask.any():
                    _lgki = float(R["annualized_returns"][_ki_mask].mean())
                _lgki_str = f"{_lgki:.2%}" if _lgki is not None and _lgki == _lgki else "—"  # nan check

                # ── Expected return ──────────────────────────────────────
                st.markdown("**" + tr("summary_returns_label") + "**")
                c1, c2, c3 = st.columns(3)
                c1.metric(tr("expected_irr_pa"),        f"{R['expected_irr']:.2%}",
                          help=tr("mc_help_expected_irr"))
                c2.metric(tr("expected_total_return"),  f"{R['expected_total_return']:.2%}",
                          help=tr("mc_help_expected_return"))
                c3.metric(tr("expected_coupon_metric"), f"{R['expected_coupon']:.2%}",
                          help=tr("mc_help_expected_coupon"))

                # ── Risk & protection ────────────────────────────────────
                st.markdown("**" + tr("summary_risk_label") + "**")
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
                           level=terms.one_star_level or 1.0)
                    )

                # ── Autocall probability by period (folded into the summary) ──
                st.divider()
                st.markdown("**" + tr("autocall_by_period_expander") + "**")
                prob_by_period = R["prob_autocall_by_period"]
                ac_df = pd.DataFrame({
                    tr("col_period"):    range(1, run_terms.n_obs + 1),
                    tr("col_time_y"):    [f"{t:.3g}" for t in obs_times_l],
                    tr("col_p_autocall"): [f"{p:.2%}" for p in prob_by_period],
                    tr("col_eligible"): [tr("yes") if i + 1 >= run_terms.autocall_start_period else tr("no_str")
                                     for i in range(run_terms.n_obs)],
                })
                st.dataframe(ac_df, use_container_width=True, hide_index=True)

            with mc_tab1:
                st.subheader(tr("irr_dist_subheader"))
                st.plotly_chart(_fig_irr, use_container_width=True)
                if R["prob_knock_in_total"] > 0:
                    st.info(tr("knock_in_info", pct=R["prob_knock_in_total"],
                               barrier=run_terms.knock_in_barrier))

            with mc_tab2:
                st.subheader(tr("price_paths_subheader"))
                st.markdown(tr("wof_basket_md"))
                st.plotly_chart(_fig_wof, use_container_width=True)
                st.markdown(tr("individual_paths_md"))
                _individual_figs = []
                for i, name in enumerate(asset_names):
                    _ind_fig = build_fan_chart(sim_prices[:, :, i], name, t_grid, obs_pairs, tr)
                    _individual_figs.append((name, _ind_fig))
                    st.plotly_chart(_ind_fig, use_container_width=True)
                # Cache per-underlying fans for the PDF (Price Paths analysis).
                st.session_state["_pdf_mc_figures"]["individual"] = _individual_figs

            # P2: isolate the path explorer in a fragment so its filter / step
            # buttons rerun ONLY this block, not every tab (the backtest + live
            # tabs no longer rebuild on a path step). It closes over the last
            # full run's arrays, which are stable until the next Run Simulation.
            #
            # The explorer renders one or more independent comparison panels. Each
            # panel queries the full set of simulated paths down to those matching
            # the user's conditions (outcome, autocall period, knock-in, total-
            # return band, coupon-paid periods) and steps through the matches. The
            # filter runs over the per-path arrays price_note already returns, so
            # there is no second payoff pass — see _path_filter_matches.
            max_path     = sim_prices.shape[0] - 1
            n_obs_mc     = len(obs_times_l)
            _mc_disp_sym = {disp: sym for sym, disp in selected_tickers.items()}
            _mc_total    = R.get("total_returns")
            if _mc_total is None:
                _mc_total = np.asarray(R["nominal_payoffs"], dtype=float) - 1.0
            _mc_total    = np.asarray(_mc_total, dtype=float)
            _mc_coupon_m = R.get("coupon_amounts")   # None for pre-feature caches
            # _OUTCOMES / _KI_CHOICES are module-level (shared with the backtest
            # explorer, which runs independently of the MC sim).

            def _render_mc_panel(pid, idx, is_primary):
                obs_labels = [lbl for lbl, _ in obs_pairs]
                with st.container(border=True, key=f"pathload_mc_{pid}"):
                    _h1, _h2 = st.columns([6, 1])
                    _h1.markdown(tr("explorer_panel_label", label=chr(65 + idx)))
                    if not is_primary and _h2.button(
                            "✕", key=f"mc_panel_rm_{pid}", help=tr("explorer_remove_panel")):
                        st.session_state["mc_panel_ids"].remove(pid)
                        st.rerun(scope="fragment")
                    _custom_title = st.text_input(
                        tr("explorer_panel_name"), key=f"mc_title_{pid}",
                        placeholder=tr("explorer_panel_name_ph")).strip()

                    # ── Filter controls ──────────────────────────────────────
                    with st.expander(tr("explorer_filter_title"), expanded=False):
                        outcome = st.radio(
                            tr("explorer_outcome_label"), _OUTCOMES,
                            format_func=lambda o: tr(f"explorer_outcome_{o}"),
                            horizontal=True, key=f"mc_outcome_{pid}")
                        ac_periods = []
                        if outcome == "autocalled":
                            ac_periods = st.multiselect(
                                tr("explorer_ac_period_label"),
                                list(range(1, n_obs_mc + 1)),
                                key=f"mc_acper_{pid}")
                        ki_choice = st.radio(
                            tr("explorer_ki_label"), _KI_CHOICES,
                            format_func=lambda k: tr(f"explorer_ki_{k}"),
                            horizontal=True, key=f"mc_ki_{pid}")
                        _rlo, _rhi = float(_mc_total.min()), float(_mc_total.max())
                        if _rhi - _rlo < 1e-9:
                            _rhi = _rlo + 0.01
                        _sl_min, _sl_max = round(_rlo * 100, 1), round(_rhi * 100, 1)
                        ret_band = st.slider(
                            tr("explorer_return_label"),
                            min_value=_sl_min, max_value=_sl_max,
                            value=(_sl_min, _sl_max),
                            format="%.1f%%", key=f"mc_ret_{pid}")
                        if _mc_coupon_m is not None:
                            coupon_periods = st.multiselect(
                                tr("explorer_coupon_label"),
                                list(range(1, n_obs_mc + 1)),
                                key=f"mc_cpnper_{pid}",
                                help=tr("explorer_coupon_help"))
                        else:
                            coupon_periods = []
                            st.caption(tr("explorer_coupon_unavailable"))

                    # At the slider extremes (untouched), apply NO bound — the 0.1%
                    # display rounding makes the rounded edge fall just inside the
                    # true data range, which would silently drop paths sitting
                    # exactly at the min/max (e.g. every path at the coupon cap).
                    matches = _path_filter_matches(
                        R["autocall_events"], R["knock_in_triggered"], _mc_total,
                        _mc_coupon_m, outcome=outcome, ac_periods=ac_periods,
                        ki_choice=ki_choice,
                        ret_lo=None if ret_band[0] <= _sl_min else ret_band[0] / 100.0,
                        ret_hi=None if ret_band[1] >= _sl_max else ret_band[1] / 100.0,
                        coupon_periods=coupon_periods)
                    M = len(matches)
                    st.caption(tr("explorer_match_count", m=M, total=max_path + 1))
                    if M == 0:
                        st.info(tr("explorer_no_matches"))
                        return

                    # ── Step through the matches ─────────────────────────────
                    pos_key = f"mc_pos_{pid}"
                    pos = min(st.session_state.get(pos_key, 0), M - 1)
                    _c1, _c2, _c3 = st.columns(3)
                    if _c1.button(tr("btn_random"), key=f"mc_rnd_{pid}"):
                        pos = random.randint(0, M - 1)
                    if _c2.button(tr("btn_prev"), key=f"mc_prev_{pid}"):
                        pos = max(0, pos - 1)
                    if _c3.button(tr("btn_next"), key=f"mc_next_{pid}"):
                        pos = min(M - 1, pos + 1)
                    st.session_state[pos_key] = pos
                    pn = int(matches[pos])
                    st.caption(tr("explorer_match_caption", k=pos + 1, m=M, n=pn))

                    autocall_q    = int(R["autocall_events"][pn])
                    s0_arr        = np.array(R.get("s0_values") or [p.S0 for p in R["params"]])
                    asset_perf_pn = sim_prices[pn] / s0_arr[np.newaxis, :]
                    _ki           = bool(R["knock_in_triggered"][pn])
                    # Rich per-observation legend entries via the canonical engine
                    # (replay_note honours memory / coupon basket / autocall-only).
                    _perf_obs_pn = asset_perf_pn[obs_steps_i, :]
                    _cpn_rows    = replay_note(_perf_obs_pn, run_terms)["rows"]
                    _wof_levels  = [float(wof_paths[pn, s]) for s in obs_steps_i]
                    _marker_info = _build_path_marker_info(
                        _cpn_rows, autocall_q, len(obs_steps_i), _wof_levels,
                        _ki, run_terms, tr)
                    # Worst-of line with the underlying asset performances behind
                    # it (dashed, like the historical explorer); the separate raw-
                    # price chart is dropped from screen. Truncates at the call.
                    _sp_wof_fig = build_path_wof_chart(
                        wof_paths[pn], autocall_q, obs_steps_i, obs_labels,
                        run_terms.knock_in_barrier, pn, tr,
                        asset_paths=asset_perf_pn, asset_names=asset_names,
                        autocall_barrier=run_terms.autocall_barrier,
                        autocall_schedule=_ac_sched_st,
                        marker_info=_marker_info,
                        title=_custom_title or None,
                    )
                    st.plotly_chart(_sp_wof_fig, use_container_width=True,
                                    key=f"mc_woffig_{pid}")
                    # Feed the PDF Path Explorer: EVERY panel contributes its worst-of
                    # chart + the user's panel title, so the report mirrors all the
                    # comparison panels. (The per-asset price chart was dropped from
                    # the explorer, so it is no longer carried into the report.)
                    if "_pdf_mc_figures" in st.session_state:
                        _pdf_figs = st.session_state["_pdf_mc_figures"]
                        _pdf_figs.setdefault("panels", []).append({
                            "title": _custom_title or None,
                            "wof":   _sp_wof_fig,
                            "num":   pn,
                        })
                        if is_primary:
                            _pdf_figs["single_path_num"] = pn

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

                    # Per-asset final performance with logos (logo inside the card)
                    _pe_cols = st.columns(len(asset_names))
                    for _pe_i, (_pe_name, _pe_col) in enumerate(zip(asset_names, _pe_cols)):
                        _pe_final = float(asset_perf_pn[-1, _pe_i])
                        _pe_d = _pe_final - 1.0
                        _pe_col.markdown(_live_card(
                            _pe_name, f"{_pe_final:.1%}",
                            delta=f"{'↓' if _pe_d < 0 else '↑'} {tr('live_metric_vs_strike', v=_pe_d)}",
                            delta_kind=("neg" if _pe_d < 0 else "pos"),
                            logo=_logo_src(_mc_disp_sym.get(_pe_name, ""))),
                            unsafe_allow_html=True)

            @st.fragment
            def _mc_path_explorer():
                st.subheader(tr("single_path_subheader"))
                st.caption(tr("explorer_intro_caption"))
                # Rebuild the per-panel PDF list from scratch each run so removed
                # panels drop out and the order (A, B, C) is preserved.
                if "_pdf_mc_figures" in st.session_state:
                    st.session_state["_pdf_mc_figures"]["panels"] = []
                ids = st.session_state.setdefault("mc_panel_ids", [0])
                if len(ids) < 3 and st.button(tr("explorer_add_panel"),
                                              key="mc_add_panel"):
                    ids.append((max(ids) + 1) if ids else 0)
                    st.rerun(scope="fragment")
                for _idx, _pid in enumerate(list(ids)):
                    _render_mc_panel(_pid, _idx, is_primary=(_idx == 0))

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
                st.caption(tr("corr_realized_caption"))
                max_err = float(np.max(np.abs(diff - np.diag(np.diag(diff)))))
                _corr_quality = (tr("corr_quality_good") if max_err < 0.02
                                 else tr("corr_quality_acceptable") if max_err < 0.05
                                 else tr("corr_quality_elevated"))
                (st.success if max_err < 0.05 else st.warning)(
                    tr("corr_max_err_message", err=max_err, quality=_corr_quality)
                )
                # Effective basket correlation — the heteroskedasticity-inflated
                # co-movement the payoff actually sees. Shown for transparency,
                # explicitly NOT compared against the input (it runs higher by
                # construction). Guarded for legacy cached results without it.
                effective_corr = R.get("effective_corr")
                if effective_corr is not None:
                    with st.expander(tr("corr_effective_header")):
                        ec1, ec2 = st.columns([1, 1])
                        ec1.plotly_chart(
                            build_corr_heatmap(effective_corr, asset_names, tr("corr_effective")),
                            use_container_width=True)
                        _eff_gap = float(np.max(np.abs(
                            (effective_corr - corr_SS) - np.diag(np.diag(effective_corr - corr_SS)))))
                        ec2.metric(tr("corr_effective_gap"), f"{_eff_gap:+.3f}")
                        ec2.caption(tr("corr_effective_caption"))
                st.divider()
                st.subheader(tr("calib_heston_subheader"))
                _disp_to_sym = {disp: sym for sym, disp in selected_tickers.items()}
                rows = []
                for p in R["params"]:
                    ok, _ = p.feller_condition()
                    _sym = _disp_to_sym.get(p.name, "")
                    _logo_url = _logo_src(_sym)
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
        _tab_intro("bt", "02", tr("tab_intro_bt_eyebrow"), tr("tab_intro_bt_q"))
        # Supplementary one-liner on the backtest method, under the intro band.
        st.caption(tr("bt_tab_intro"))

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
            # Maturity = stark dark slate (deliberately off the blue ramp so it
            # never reads as "just another autocall period"); Knock-in = red;
            # Autocalls = a smooth blue gradient that darkens monotonically with
            # the period (P1 light → final period deep blue). In the branded PDF
            # the blue ramp is hue-rotated onto the accent colour, while the slate
            # and red pass through (see _rebrand_figure).
            _n_ac = max(terms.n_obs - 1, 1)
            color_map = {
                _bt_maturity: "#334155", _bt_knock_in: "#dc2626",
                **{tr("bt_outcome_autocalled_p", i=i):
                   f"hsl(217,72%,{70 - ((i - 1) / _n_ac) * 40:.0f}%)"
                   for i in range(1, terms.n_obs + 1)},
            }

            _bt_ki_rows = bt[bt["Knock-in"]] if not bt.empty else pd.DataFrame()
            _bt_lgki_str = (
                f"{float(_bt_ki_rows['IRR'].mean()):.2%}"
                if not _bt_ki_rows.empty
                else "—"
            )

            # Subtabs mirror the Monte Carlo tab's layout so both analyses read
            # the same way instead of the backtest being one long scroll.
            bt_tab1, bt_tab2, bt_tab3 = st.tabs([
                tr("bt_subtab_outcomes"), tr("bt_subtab_prices"),
                tr("bt_subtab_explorer"),
            ])

            with bt_tab1:
                # Grouped like the Monte Carlo summary (returns vs risk), with the
                # sample size as a one-line caption above.
                # Same metric set + layout as the Monte Carlo summary (returns
                # row of three, then risk row of three), so the two tabs read in
                # parallel. Median IRR — a backtest-specific extra — sits in the
                # caption rather than as a card.
                st.caption(tr("bt_sample_caption", n=bt_summary.get("n_issues", 0))
                           + " · " + tr("bt_median_caption",
                                        v=f"{bt_summary.get('median_irr', 0):.2%}"))
                st.markdown("**" + tr("bt_returns_label") + "**")
                b1, b2, b3 = st.columns(3)
                b1.metric(tr("bt_metric_mean_irr"),       f"{bt_summary.get('mean_irr', 0):.2%}",
                          help=tr("bt_help_mean_irr"))
                b2.metric(tr("bt_metric_total_return"),   f"{bt_summary.get('expected_total_return', 0):.2%}",
                          help=tr("bt_help_total_return"))
                b3.metric(tr("bt_metric_coupon"),         f"{bt_summary.get('expected_coupon', 0):.2%}",
                          help=tr("bt_help_coupon"))
                st.markdown("**" + tr("summary_risk_label") + "**")
                b4, b5, b6 = st.columns(3)
                b4.metric(tr("bt_metric_autocalled_pct"), f"{bt_summary.get('prob_called', 0):.1%}",
                          help=tr("bt_help_autocalled_pct"))
                b5.metric(tr("bt_metric_knock_in_pct"),   f"{bt_summary.get('prob_knock_in', 0):.1%}",
                          help=tr("bt_help_knock_in_pct"))
                b6.metric(tr("loss_given_ki_metric"),     _bt_lgki_str,
                          help=tr("bt_help_loss_given_ki"))

                _bt_outcome_fig = build_backtest_outcome_bar(bt, color_map, tr)
                _bt_irr_fig     = build_backtest_irr_scatter(bt, color_map, tr)
                _bt_pie_fig     = build_worst_asset_pie(bt, tr)
                col1, col2 = st.columns(2)
                with col1:
                    st.plotly_chart(_bt_outcome_fig, use_container_width=True)
                with col2:
                    st.plotly_chart(_bt_pie_fig, use_container_width=True)
                st.plotly_chart(_bt_irr_fig, use_container_width=True)
                # Cache for PDF — augment bt_summary with loss-given-KI
                _pdf_bt_summary = dict(bt_summary)
                if not _bt_ki_rows.empty:
                    _pdf_bt_summary["loss_given_ki"] = float(_bt_ki_rows["IRR"].mean())
                st.session_state["_pdf_bt_summary"] = _pdf_bt_summary
                # Preserve any prices/path figures already cached this run.
                _bt_figs = dict(st.session_state.get("_pdf_bt_figures", {}))
                _bt_figs.update({"outcome": _bt_outcome_fig, "irr_scatter": _bt_irr_fig,
                                 "pie": _bt_pie_fig})
                st.session_state["_pdf_bt_figures"] = _bt_figs

            with bt_tab2:
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
                    _bt_prices_fig = build_historical_prices(_hist_chart_prices, bt_start_mark, bt_end_mark, tr)
                    st.plotly_chart(_bt_prices_fig, use_container_width=True)
                    st.session_state.setdefault("_pdf_bt_figures", {})["prices"] = _bt_prices_fig
                except Exception:
                    pass

            # P2: the explorer reruns ONLY its own fragment, so filtering /
            # stepping a historical issue no longer rebuilds the MC tab, the
            # backtest summary charts, or the live tab. Closes over bt /
            # bt_summary / _all_prices / terms from the last full run.
            #
            # Per-issue arrays for the explorer filter — row-aligned with `bt`
            # (RangeIndex), so a positional match index maps straight to bt.iloc.
            _bt_ac       = bt["Call Quarter"].to_numpy()
            _bt_ki       = bt["Knock-in"].to_numpy()
            _bt_irr      = bt["IRR"].to_numpy()
            _bt_coupon_m = bt_summary.get("coupon_amounts")
            n_obs_bt     = terms.n_obs

            def _render_bt_panel(pid, idx, is_primary):
                with st.container(border=True, key=f"pathload_bt_{pid}"):
                    _h1, _h2 = st.columns([6, 1])
                    _h1.markdown(tr("explorer_panel_label", label=chr(65 + idx)))
                    if not is_primary and _h2.button(
                            "✕", key=f"bt_panel_rm_{pid}", help=tr("explorer_remove_panel")):
                        st.session_state["bt_panel_ids"].remove(pid)
                        st.rerun(scope="fragment")
                    _custom_title = st.text_input(
                        tr("explorer_panel_name"), key=f"bt_title_{pid}",
                        placeholder=tr("explorer_panel_name_ph")).strip()

                    with st.expander(tr("explorer_filter_title"), expanded=False):
                        outcome = st.radio(
                            tr("explorer_outcome_label"), _OUTCOMES,
                            format_func=lambda o: tr(f"explorer_outcome_{o}"),
                            horizontal=True, key=f"bt_outcome_{pid}")
                        ac_periods = []
                        if outcome == "autocalled":
                            ac_periods = st.multiselect(
                                tr("explorer_ac_period_label"),
                                list(range(1, n_obs_bt + 1)), key=f"bt_acper_{pid}")
                        ki_choice = st.radio(
                            tr("explorer_ki_label"), _KI_CHOICES,
                            format_func=lambda k: tr(f"explorer_ki_{k}"),
                            horizontal=True, key=f"bt_ki_{pid}")
                        _rlo, _rhi = float(_bt_irr.min()), float(_bt_irr.max())
                        if _rhi - _rlo < 1e-9:
                            _rhi = _rlo + 0.01
                        _sl_min, _sl_max = round(_rlo * 100, 1), round(_rhi * 100, 1)
                        ret_band = st.slider(
                            tr("explorer_irr_label"),
                            min_value=_sl_min, max_value=_sl_max,
                            value=(_sl_min, _sl_max),
                            format="%.1f%%", key=f"bt_ret_{pid}")
                        if _bt_coupon_m is not None:
                            coupon_periods = st.multiselect(
                                tr("explorer_coupon_label"),
                                list(range(1, n_obs_bt + 1)), key=f"bt_cpnper_{pid}",
                                help=tr("explorer_coupon_help"))
                        else:
                            coupon_periods = []
                            st.caption(tr("explorer_coupon_unavailable"))

                    # At the slider extremes (untouched), apply NO bound — see the
                    # Monte Carlo panel: 0.1% display rounding otherwise drops paths
                    # sitting exactly at the min/max IRR (e.g. the coupon cap).
                    matches = _path_filter_matches(
                        _bt_ac, _bt_ki, _bt_irr, _bt_coupon_m, outcome=outcome,
                        ac_periods=ac_periods, ki_choice=ki_choice,
                        ret_lo=None if ret_band[0] <= _sl_min else ret_band[0] / 100.0,
                        ret_hi=None if ret_band[1] >= _sl_max else ret_band[1] / 100.0,
                        coupon_periods=coupon_periods)
                    M = len(matches)
                    st.caption(tr("explorer_match_count", m=M, total=len(bt)))
                    if M == 0:
                        st.info(tr("explorer_no_matches"))
                        return

                    pos_key = f"bt_pos_{pid}"
                    pos = min(st.session_state.get(pos_key, 0), M - 1)
                    _c1, _c2, _c3 = st.columns(3)
                    if _c1.button(tr("btn_random"), key=f"bt_rnd_{pid}"):
                        pos = random.randint(0, M - 1)
                    if _c2.button(tr("btn_prev"), key=f"bt_prev_{pid}"):
                        pos = max(0, pos - 1)
                    if _c3.button(tr("btn_next"), key=f"bt_next_{pid}"):
                        pos = min(M - 1, pos + 1)
                    st.session_state[pos_key] = pos

                    row = bt.iloc[int(matches[pos])]
                    selected_issue = row["Issue Date"]
                    st.caption(tr("explorer_bt_match_caption", k=pos + 1, m=M,
                                  d=selected_issue.strftime("%Y-%m-%d")))
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
                            # Engine-true coupon-paid flags per observation date
                            # (replay_note — same logic the payoff used). Built
                            # from per-asset perf vs the issue-date fixing.
                            _pe_issue_loc = _all_prices.index.searchsorted(_pe_anchor)
                            _pe_s0 = _all_prices.iloc[_pe_issue_loc].values.astype(float)
                            _pe_perf_obs = []
                            for _d in _pe_obs_dates:
                                _loc = _all_prices.index.searchsorted(_d)
                                if _loc >= len(_all_prices):
                                    break
                                _pe_perf_obs.append(_all_prices.iloc[_loc].values.astype(float) / _pe_s0)
                            _pe_flags = [
                                r["coupon_amount"] > 0
                                for r in replay_note(np.array(_pe_perf_obs), terms)["rows"]
                            ] if _pe_perf_obs else None
                            _bt_path_fig = build_historical_wof_path(
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
                                coupon_flags      = _pe_flags,
                                knock_in          = bool(row["Knock-in"]),
                                title             = _custom_title or None,
                            )
                            st.plotly_chart(_bt_path_fig, use_container_width=True,
                                            key=f"bt_pathfig_{pid}")
                            # Carry this panel's path into the PDF backtest section
                            # (one chart per comparison panel, with its title/date).
                            st.session_state.setdefault("_pdf_bt_figures", {}) \
                                .setdefault("panels", []).append({
                                    "title": _custom_title or None,
                                    "path":  _bt_path_fig,
                                    "issue": selected_issue.strftime("%Y-%m-%d"),
                                })
                    except Exception as e:
                        st.error(tr("bt_could_not_build_path", e=e))

            @st.fragment
            def _bt_path_explorer():
                st.subheader(tr("bt_path_explorer_header"))
                st.caption(tr("bt_path_explorer_caption"))
                # Rebuild the per-panel PDF list each run so removed panels drop out.
                st.session_state.setdefault("_pdf_bt_figures", {})["panels"] = []
                ids = st.session_state.setdefault("bt_panel_ids", [0])
                if len(ids) < 3 and st.button(tr("explorer_add_panel"),
                                              key="bt_add_panel"):
                    ids.append((max(ids) + 1) if ids else 0)
                    st.rerun(scope="fragment")
                for _idx, _pid in enumerate(list(ids)):
                    _render_bt_panel(_pid, _idx, is_primary=(_idx == 0))

            with bt_tab3:
                _bt_path_explorer()


    # ══════════════════════════════════════════════════════════════════
    # TAB 3 — CURRENT PERFORMANCE (only if issue_date is set)
    # ══════════════════════════════════════════════════════════════════
    if tab_live is not None:
        with tab_live:
            _tab_intro("live", "03", tr("tab_intro_live_eyebrow"), tr("tab_intro_live_q"))
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

                    # ── Live summary metrics (grouped: Today / Barriers) ──
                    _live_disp_to_sym = {disp: sym for sym, disp in selected_tickers.items()}
                    # Buffers use the barrier for the next upcoming observation
                    # (step-down notes differ after the first callable period).
                    _next_obs_idx = next(
                        (i for i, d in enumerate(_obs_cal)
                         if pd.Timestamp(d) > _today_ts),
                        len(_ac_sched_lv) - 1,
                    )
                    _next_ac_barrier = float(_ac_sched_lv[_next_obs_idx])
                    _ki_buf  = _wof_today - run_terms.knock_in_barrier
                    _ac_buf  = _wof_today - _next_ac_barrier

                    def _vs_strike(perf):
                        d = perf - 1.0
                        return (f"{'↓' if d < 0 else '↑'} {tr('live_metric_vs_strike', v=d)}",
                                "neg" if d < 0 else "pos")

                    st.markdown("**" + tr("live_group_today") + "**")
                    _t1, _t2 = st.columns(2)
                    _wof_delta, _wof_kind = _vs_strike(_wof_today)
                    _t1.markdown(_live_card(
                        tr("live_metric_wof_today"), f"{_wof_today:.1%}",
                        delta=_wof_delta, delta_kind=_wof_kind,
                        help_text=tr("live_help_wof_today")), unsafe_allow_html=True)
                    _t2.markdown(_live_card(
                        tr("live_metric_worst_asset"), _worst_asset_today,
                        logo=_logo_src(_live_disp_to_sym.get(_worst_asset_today, "")),
                        logo_with_value=True, value_text=True,
                        help_text=tr("live_help_worst_asset")), unsafe_allow_html=True)

                    st.markdown("**" + tr("live_group_barriers") + "**")
                    _b1, _b2 = st.columns(2)
                    _b1.markdown(_live_card(
                        tr("live_metric_ki_buffer"), f"{_ki_buf:+.1%}",
                        delta=tr("live_delta_barrier_ref", barrier=run_terms.knock_in_barrier),
                        delta_kind="neutral",
                        help_text=tr("live_help_ki_buffer", barrier=run_terms.knock_in_barrier)),
                        unsafe_allow_html=True)
                    _b2.markdown(_live_card(
                        tr("live_metric_ac_buffer"), f"{_ac_buf:+.1%}",
                        delta=tr("live_delta_autocall_ref", barrier=_next_ac_barrier),
                        delta_kind="neutral",
                        help_text=tr("live_help_ac_buffer", barrier=_next_ac_barrier)),
                        unsafe_allow_html=True)

                    # ── Per-asset current performance ─────────────────
                    st.markdown(tr("live_asset_perf_header"))
                    _asset_cols = st.columns(len(asset_names))
                    for _i, (_aname, _acol) in enumerate(zip(asset_names, _asset_cols)):
                        _ap = float(_perf_today[_i])
                        _ap_delta, _ap_kind = _vs_strike(_ap)
                        _acol.markdown(_live_card(
                            _aname, f"{_ap:.1%}",
                            delta=_ap_delta, delta_kind=_ap_kind,
                            logo=_logo_src(_live_disp_to_sym.get(_aname, ""))),
                            unsafe_allow_html=True)

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
    # Triggered either by a direct click (when results already exist) or by the
    # pending flag set when Generate-report had to run the sim first.
    _do_pdf = _pdf_btn or st.session_state.pop("_pending_pdf", False)
    # Build when results exist, OR when the report needs no Monte Carlo output at
    # all (Note-details / backtest / live only) — in that case the sim was
    # deliberately skipped and there is simply nothing to wait for.
    if _do_pdf and (_has_sim or not _needs_mc):
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
            # User-uploaded custom underlying logos, keyed by display name so the
            # PDF can override the favicon/CDN logo for that asset.
            _custom_logos = st.session_state.get("custom_logos", {})
            _pdf_logo_overrides = {
                name: _custom_logos[sym]
                for sym, name in run_terms.tickers.items()
                if _custom_logos.get(sym)
            }
            _pdf_issuer_logo_url = get_issuer_logo_url(getattr(run_terms, "issuer", "") or "")
            # Section selection from the single Build-report panel (sidebar),
            # expanded to the fine-grained include keys the PDF gates on.
            _pdf_sections = _collect_pdf_sections(len(asset_names), _has_live)
            # Underlying Breakdown inputs: live metrics + a trailing-1Y price
            # chart per underlying (same data as the dashboard note-info card).
            _ul_tt = tuple(run_terms.tickers.items())
            _pdf_ul_metrics = _load_underlying_metrics_cached(_ul_tt)
            _pdf_ul_figs: dict = {}
            try:
                _ul_px = _load_prices(_ul_tt, years=1.0)
                for _n in asset_names:
                    if _n in _ul_px.columns:
                        _pdf_ul_figs[_n] = build_underlying_price_chart(_ul_px[_n], _n, tr)
            except Exception as _e:
                print(f"[app] underlying price charts for PDF failed: {_e}")
            # In Spanish mode, translate the issuer + underlying descriptions into a
            # copy of the terms so the report matches the (auto-translated) app.
            _pdf_lang  = "es" if lang_choice == "Español" else "en"
            _pdf_terms = run_terms
            if _pdf_lang == "es":
                _td = run_terms.to_dict()
                if _td.get("issuer_description"):
                    _td["issuer_description"] = _translate_cached(_td["issuer_description"], "es")
                _uls = dict(_td.get("underlyings") or {})
                for _nm, _ov in list(_uls.items()):
                    if isinstance(_ov, dict) and _ov.get("description"):
                        _uls[_nm] = {**_ov, "description": _translate_cached(_ov["description"], "es")}
                _td["underlyings"] = _uls
                try:
                    _pdf_terms = NoteTerms.from_dict(_td)
                except Exception:
                    _pdf_terms = run_terms
            _pdf_bytes = generate_pdf_report(
                terms            = _pdf_terms,
                results          = R or {},
                asset_names      = asset_names,
                figures          = st.session_state.get("_pdf_mc_figures", {}),
                lang             = _pdf_lang,
                bt_summary       = st.session_state.get("_pdf_bt_summary"),
                bt_figures       = st.session_state.get("_pdf_bt_figures"),
                live_data        = st.session_state.get("_pdf_live_data"),
                live_figure      = st.session_state.get("_pdf_live_figure"),
                logo_urls        = _pdf_logo_urls,
                issuer_logo_url  = _pdf_issuer_logo_url,
                issuer_logo_override = st.session_state.get("issuer_logo_bytes"),
                branding         = st.session_state.get("branding"),
                logo_tickers     = _pdf_logo_tickers,
                include_sections = _pdf_sections,
                logo_overrides   = _pdf_logo_overrides,
                underlying_metrics    = _pdf_ul_metrics,
                underlying_price_figs = _pdf_ul_figs,
            )
        _pdf_slot.download_button(
            tr("sidebar_download_pdf"),
            data=_pdf_bytes,
            file_name=f"{run_terms.name.replace(' ', '_')}_report.pdf",
            mime="application/pdf",
            key="dl_pdf_sidebar",
        )