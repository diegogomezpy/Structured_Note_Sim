"""
data/loader.py
--------------
Single source of truth for price data loading.

Three backends, one interface:

    load_prices()                          # pull live from yfinance (default)
    load_prices(source="csv", csv_files={"my.csv": "SPX"})  # local CSVs
    load_prices(source="df", df=my_df)    # pre-loaded DataFrame

No CSVs are bundled with the repo: source="csv" always requires an explicit
csv_files mapping.

Nothing else in the codebase should know about file paths or yfinance.
"""

from __future__ import annotations

import pathlib
import warnings
import pandas as pd

_DATA_DIR = pathlib.Path(__file__).parent

# Default ticker → display name mapping
DEFAULT_TICKERS: dict[str, str] = {
    "^GSPC":     "SPX",
    "^STOXX50E": "SX5E",
    "^SSMI":     "SMI",
}


def load_prices(
    source:     str                     = "yfinance",
    tickers:    dict[str, str] | None   = None,
    years:      float | None            = 5.0,
    end_date:   str | None              = None,
    ssl_verify: bool                    = True,
    csv_files:  dict[str, str] | None   = None,
    df:         pd.DataFrame | None     = None,
    field:      str                     = "close",
) -> pd.DataFrame:
    """
    Load and align daily closing prices.

    Parameters
    ----------
    source : str
        "yfinance"  — pull live data from Yahoo Finance (default).
        "csv"       — load from local CSV files (csv_files is required).
        "df"        — use a pre-loaded DataFrame directly.

    field : str
        "close"     — raw (unadjusted) official closing prices. This is what
                      structured note term sheets observe for barrier /
                      coupon / autocall / knock-in fixings. Default.
        "adj_close" — dividend-adjusted (total return) closing prices. Use for
                      drift / vol / correlation calibration only; never for
                      barrier observation. (Both series are split-adjusted.)

    tickers : dict[str, str] or None
        yfinance ticker → display name mapping.
        Only used when source="yfinance".
        Defaults to DEFAULT_TICKERS (SPX / SX5E / SMI).

    years : float or None
        How many years of history to pull.
        Pass None to fetch the maximum available history for each ticker.
        Only used when source="yfinance". Default 5.

    end_date : str or None
        End date as "YYYY-MM-DD". Defaults to today.
        Only used when source="yfinance".

    ssl_verify : bool
        Set False if behind a corporate proxy with self-signed SSL cert.
        Only used when source="yfinance". Default True.

    csv_files : dict[str, str] or None
        Mapping from file path → display name.
        Required when source="csv" — no CSVs are bundled with the repo.

    df : pd.DataFrame or None
        Pre-loaded price DataFrame with asset names as columns.
        Only used when source="df".

    Returns
    -------
    pd.DataFrame
        Aligned daily closing prices, one column per asset, sorted by date.
        Rows with any missing price are dropped (non-overlapping holidays).

    Raises
    ------
    ValueError        if source is unrecognised or fewer than 60 observations remain.
    ImportError       if source="yfinance" and yfinance is not installed.
    FileNotFoundError if source="csv" and a file does not exist.
    """
    if field not in ("close", "adj_close"):
        raise ValueError(f"field must be 'close' or 'adj_close'; got '{field}'")
    if source == "yfinance":
        return _from_yfinance(tickers or DEFAULT_TICKERS, years, end_date, ssl_verify, field)
    elif source == "csv":
        if csv_files is None:
            raise ValueError(
                "source='csv' requires csv_files={path: display_name, ...} — "
                "no CSVs are bundled with the repo."
            )
        return _from_csv(csv_files, field)
    elif source == "df":
        if df is None:
            raise ValueError("source='df' requires a DataFrame passed via df=")
        return _from_dataframe(df)
    else:
        raise ValueError(f"Unknown source '{source}'. Use 'yfinance', 'csv', or 'df'.")


# ---------------------------------------------------------------------------
# Private backends
# ---------------------------------------------------------------------------

def _from_yfinance(
    tickers:    dict[str, str],
    years:      float,
    end_date:   str | None,
    ssl_verify: bool,
    field:      str = "close",
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError(
            "yfinance is not installed. Run: pip install yfinance\n"
            "Or use load_prices(source='csv') to load from the bundled CSVs."
        )

    end   = pd.Timestamp(end_date) if end_date else pd.Timestamp.today()
    start = None if years is None else end - pd.DateOffset(years=years)

    ticker_symbols = list(tickers.keys())
    if start is not None:
        print(f"[loader] Pulling {ticker_symbols} from yfinance "
              f"({start.date()} → {end.date()}) …")
    else:
        print(f"[loader] Pulling {ticker_symbols} from yfinance "
              f"(max history → {end.date()}) …")

    session = None
    if not ssl_verify:
        import requests, urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session = requests.Session()
        session.verify = False
        print("[loader] SSL verification disabled.")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # auto_adjust=False keeps BOTH the official close ('Close') and the
        # dividend-adjusted close ('Adj Close'); `field` selects which one.
        if start is not None:
            # Bounded window: explicit start → end
            kwargs = dict(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=False,
                progress=False,
            )
        else:
            # Max history: use period="max" — omitting start only returns 30 days
            kwargs = dict(
                period="max",
                auto_adjust=False,
                progress=False,
            )
        if session:
            kwargs["session"] = session
        raw = yf.download(ticker_symbols, **kwargs)

    if len(raw) == 0:
        raise ValueError(
            f"yfinance returned no data for {ticker_symbols}. "
            "This is usually a transient rate-limit or network error — "
            "wait a moment and try again. If the problem persists, check "
            "that all ticker symbols are valid on Yahoo Finance."
        )

    col = "Close" if field == "close" else "Adj Close"
    if col not in raw.columns.get_level_values(0) if isinstance(raw.columns, pd.MultiIndex) else raw.columns:
        raise ValueError(
            f"yfinance response is missing the '{col}' column. "
            f"Columns present: {list(raw.columns)}. "
            "Set field='close' or field='adj_close'."
        )

    # yfinance returns a MultiIndex for multiple tickers, flat for one
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw[col][ticker_symbols]
    else:
        prices = raw[[col]].rename(columns={col: ticker_symbols[0]})

    prices = prices.rename(columns=tickers)
    return _align(prices, "yfinance")


def _from_csv(csv_files: dict[str, str], field: str = "close") -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    col = "Close" if field == "close" else "Adj Close"

    for path, name in csv_files.items():
        p = pathlib.Path(path)
        if not p.exists():
            raise FileNotFoundError(
                f"Price CSV not found: {p}.\n"
                f"Provide an absolute path or use source='yfinance'."
            )
        df = pd.read_csv(p, index_col="Date", parse_dates=True)
        df = df[pd.to_datetime(df.index, errors="coerce").notna()]
        df.index = pd.to_datetime(df.index)

        if col not in df.columns:
            raise ValueError(
                f"'{path}' has no '{col}' column. "
                f"Columns found: {list(df.columns)}. "
                f"Use a raw Yahoo Finance CSV export."
            )
        series[name] = pd.to_numeric(df[col], errors="coerce")
        print(f"[loader] Loaded {name} from '{p.name}' "
              f"({len(series[name])} rows, "
              f"{df.index[0].date()} → {df.index[-1].date()})")

    prices = pd.DataFrame(series)
    return _align(prices, "csv")


def _from_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    prices = df.copy()
    if not isinstance(prices.index, pd.DatetimeIndex):
        prices.index = pd.to_datetime(prices.index)
    print(f"[loader] Using pre-loaded DataFrame "
          f"({len(prices)} rows, assets: {list(prices.columns)})")
    return _align(prices, "df")


def _align(prices: pd.DataFrame, source_label: str) -> pd.DataFrame:
    """Drop NaN rows, sort, and validate minimum length."""
    prices = prices.sort_index()
    n_before = len(prices)
    prices   = prices.dropna()
    n_after  = len(prices)

    if n_before - n_after > 0:
        print(f"[loader] Dropped {n_before - n_after} rows with missing prices "
              f"(non-overlapping holidays).")

    if n_after == 0:
        raise ValueError(
            f"No data returned (source='{source_label}'). "
            f"Check your ticker symbols, date range, or network connection."
        )

    print(f"[loader] Aligned: {n_after} common trading days "
          f"({prices.index[0].date()} → {prices.index[-1].date()})")

    if n_after < 60:
        raise ValueError(
            f"Only {n_after} overlapping observations after alignment "
            f"(source='{source_label}'). "
            f"Increase years= or check that your files cover an overlapping date range."
        )
    return prices


# ---------------------------------------------------------------------------
# Dividends — history loading and forward projection for the MC simulator
# ---------------------------------------------------------------------------

def load_dividends(
    tickers:    dict[str, str],
    ssl_verify: bool = True,
) -> dict[str, pd.Series]:
    """
    Load cash dividend history (ex-date → cash amount) for each ticker.

    Returns {display_name: pd.Series} with a tz-naive DatetimeIndex. Price
    indices (^GSPC etc.) and non-distributing assets return an empty Series —
    they get no dividend jumps in the simulation (a price index already
    reflects constituent dividends in its drift).
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance is not installed. Run: pip install yfinance")

    out: dict[str, pd.Series] = {}
    for sym, name in tickers.items():
        try:
            divs = yf.Ticker(sym).dividends
            if divs is None or len(divs) == 0:
                out[name] = pd.Series(dtype=float)
                continue
            divs = divs.copy()
            if getattr(divs.index, "tz", None) is not None:
                divs.index = divs.index.tz_localize(None)
            out[name] = divs.astype(float)
        except Exception as e:
            print(f"[loader] WARNING: could not load dividends for {sym}: {e} — assuming none.")
            out[name] = pd.Series(dtype=float)
    return out


# ---------------------------------------------------------------------------
# Per-underlying summary metrics (powers the report's Underlying Breakdown)
# ---------------------------------------------------------------------------

# Index → volatility-index symbol, used for a 3-month-ish implied vol when the
# underlying is an INDEX (an index level has no option chain on Yahoo, so we read
# the matching vol index's level, which is already an annualised IV in %).
# ^VIX3M is the true 3-month SPX IV; the others are 30-day proxies — close enough
# for a headline figure, and only ever used for index underlyings (every current
# note config is single stocks, which get a real 3M IV from their option chain).
_VOL_INDEX: dict[str, str] = {
    "^GSPC": "^VIX3M", "^SPX": "^VIX3M",
    "^NDX":  "^VXN",   "^IXIC": "^VXN",
    "^DJI":  "^VXD",   "^RUT":  "^RVX",
}


def _wilder_rsi(closes, period: int = 14):
    """Wilder's 14-day RSI from a close-price array. None if too few points."""
    import numpy as np
    c = np.asarray(closes, dtype=float)
    c = c[~np.isnan(c)]
    if c.size < period + 1:
        return None
    d  = np.diff(c)
    up = pd.Series(np.where(d > 0,  d, 0.0))
    dn = pd.Series(np.where(d < 0, -d, 0.0))
    au = up.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
    ad = dn.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
    if ad == 0:
        return 100.0
    return float(100.0 - 100.0 / (1.0 + au / ad))


def _atm_iv(calls: pd.DataFrame, puts: pd.DataFrame, spot: float):
    """Average of the ATM call and put implied vols (nearest strike to spot)."""
    import numpy as np
    ivs = []
    for chain in (calls, puts):
        try:
            if chain is None or len(chain) == 0 or not spot:
                continue
            row = chain.iloc[(chain["strike"] - spot).abs().argmin()]
            iv  = float(row["impliedVolatility"])
            if np.isfinite(iv) and iv > 0:
                ivs.append(iv)
        except Exception:
            continue
    return float(np.mean(ivs)) if ivs else None


def _iv_3m(ticker, sym: str, quote_type: str | None, spot):
    """3-month implied vol. Equities: ATM IV at the expiry nearest +90 days.
    Indices: the matching vol-index level. None when neither is available."""
    try:
        exps = ticker.options
    except Exception:
        exps = ()
    if exps:
        target = pd.Timestamp.today() + pd.Timedelta(days=90)
        best   = min(exps, key=lambda e: abs((pd.Timestamp(e) - target).days))
        try:
            oc = ticker.option_chain(best)
            iv = _atm_iv(oc.calls, oc.puts, spot)
            if iv is not None:
                return iv
        except Exception:
            pass
    vsym = _VOL_INDEX.get(sym) or _VOL_INDEX.get("^" + sym.lstrip("^"))
    if vsym:
        try:
            import yfinance as yf
            h = yf.Ticker(vsym).history(period="5d")["Close"].dropna()
            if len(h):
                return float(h.iloc[-1]) / 100.0
        except Exception:
            pass
    return None


def load_underlying_metrics(
    tickers: dict[str, str],
    closes:  dict[str, pd.Series] | None = None,
    ssl_verify: bool = True,
) -> dict[str, dict]:
    """
    Pull a per-underlying summary for the report's Underlying Breakdown.

    For each display name returns a dict with keys (any unavailable field = None):
        long_name, type, sector, industry, market_cap, currency,
        last_price, rsi_14, iv_3m, business_summary

    One ``yf.Ticker(sym).info`` call per ticker, plus an options lookup for the
    3-month implied vol, plus a Wilder RSI computed from ``closes`` when supplied
    (the app already holds the price history — pass it to avoid a second pull).
    A single ticker raising never aborts the others; that name just gets Nones.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance is not installed. Run: pip install yfinance")

    out: dict[str, dict] = {}
    for sym, name in tickers.items():
        rec = {k: None for k in (
            "long_name", "type", "sector", "industry", "market_cap", "currency",
            "last_price", "rsi_14", "iv_3m", "business_summary")}
        try:
            t = yf.Ticker(sym)
            try:
                info = t.info or {}
            except Exception as e:
                info = {}
                print(f"[loader] WARNING: info() failed for {sym}: {e}")

            rec["long_name"]        = info.get("longName") or info.get("shortName") or name
            rec["type"]             = info.get("typeDisp") or info.get("quoteType")
            rec["sector"]           = info.get("sector")
            rec["industry"]         = info.get("industry")
            rec["market_cap"]       = info.get("marketCap")
            rec["currency"]         = info.get("currency")
            rec["business_summary"] = info.get("longBusinessSummary") or None

            # Last price: prefer the (reused) loaded close series, else Yahoo.
            ser = (closes or {}).get(name)
            if ser is not None and len(ser):
                rec["last_price"] = float(ser.dropna().iloc[-1])
                rec["rsi_14"]     = _wilder_rsi(ser.dropna().values)
            else:
                rec["last_price"] = (info.get("currentPrice")
                                     or info.get("regularMarketPrice"))
                try:
                    h = t.history(period="6mo")["Close"]
                    if len(h):
                        rec["last_price"] = rec["last_price"] or float(h.iloc[-1])
                        rec["rsi_14"]     = _wilder_rsi(h.values)
                except Exception:
                    pass

            rec["iv_3m"] = _iv_3m(t, sym, rec["type"], rec["last_price"])
        except Exception as e:
            print(f"[loader] WARNING: could not load metrics for {sym}: {e}")
        out[name] = rec
    return out


def translate_text(text: str | None, target_lang: str,
                   source_lang: str = "auto") -> str | None:
    """Best-effort machine translation — used to localise the English Yahoo
    business summaries when prefilling a description in a non-English UI.

    Returns the original text unchanged when target is English/empty, when the
    text is blank, or on ANY failure. Never raises. Tries Google first (best
    quality, no length limit) and falls back to MyMemory if Google is blocked or
    rate-limited (common on corporate networks) — MyMemory has a ~500-char
    per-request limit, so each paragraph is chunked by sentence. Paragraph breaks
    are preserved throughout."""
    if not text or not text.strip() or target_lang in (None, "", "en"):
        return text
    paras = text.split("\n\n")

    def _by_para(translate_one) -> str:
        return "\n\n".join(translate_one(p) if p.strip() else p for p in paras)

    # An engine "succeeds" only if it actually CHANGED the text. Google's scraper
    # can return the input unchanged when its IP hits bot-detection (no exception
    # raised) — treat that as a failure so we fall through to the next engine
    # instead of silently handing back English. (en->es always changes the text.)
    def _ok(res) -> bool:
        return bool(res and res.strip()) and res.strip() != text.strip()

    # 1) Google Translate — preferred (best quality).
    try:
        from deep_translator import GoogleTranslator
        gt  = GoogleTranslator(source=source_lang, target=target_lang)
        res = _by_para(lambda p: gt.translate(p))
        if _ok(res):
            return res
        print("[loader] Google returned untranslated text; trying MyMemory.")
    except Exception as e:
        print(f"[loader] Google translate failed ({type(e).__name__}: {e}); trying MyMemory.")

    # 2) MyMemory — a real API (not a scraper), so it works where Google's
    #    bot-detection blocks the host. ~500-char/request limit -> chunk by sentence.
    try:
        import re
        from deep_translator import MyMemoryTranslator
        mm = MyMemoryTranslator(source="en-GB",
                                target="es-ES" if target_lang == "es" else target_lang)

        def _mm(p: str) -> str:
            chunks, cur = [], ""
            for sent in re.split(r"(?<=[.!?])\s+", p):
                if cur and len(cur) + len(sent) + 1 > 480:
                    chunks.append(cur)
                    cur = ""
                cur = (cur + " " + sent).strip()
            if cur:
                chunks.append(cur)
            return " ".join(mm.translate(c) for c in chunks if c.strip())

        res = _by_para(_mm)
        if _ok(res):
            return res
        print("[loader] MyMemory returned untranslated text; keeping original.")
    except Exception as e:
        print(f"[loader] MyMemory translate failed ({type(e).__name__}: {e}); keeping original.")

    return text


def resolve_issuer_summary(name: str, ssl_verify: bool = True) -> str | None:
    """Best-effort: resolve an issuer NAME (e.g. 'BBVA', 'Bank Julius Baer') to a
    listed ticker via Yahoo search, then return that company's business summary —
    used to prefill the issuer description. Tries the name and a 'Bank/Banco'-
    stripped variant and takes the first EQUITY match. None if nothing resolves.

    Note: Yahoo exposes no issuer CREDIT rating (S&P/Moody's/Fitch are proprietary;
    only an analyst buy/hold/sell `averageAnalystRating` is available), so credit
    ratings remain a manual field — there is no free programmatic source."""
    if not name or not name.strip():
        return None
    try:
        import yfinance as yf
    except ImportError:
        return None
    queries = [name.strip()]
    stripped = name.replace("Bank ", "").replace("Banco ", "").strip()
    if stripped and stripped != name.strip():
        queries.append(stripped)
    for q in queries:
        try:
            quotes = yf.Search(q, max_results=5).quotes or []
            eq   = [x for x in quotes if x.get("quoteType") == "EQUITY"]
            cand = (eq[0]["symbol"] if eq else
                    (quotes[0].get("symbol") if quotes else None))
            if not cand:
                continue
            summ = (yf.Ticker(cand).info or {}).get("longBusinessSummary")
            if summ:
                return summ
        except Exception:
            continue
    return None


def build_dividend_schedule(
    div_history: list[pd.Series],
    spot_prices: list[float],
    grid_dates:  pd.DatetimeIndex,
) -> np.ndarray:
    """
    Project forward dividends onto a simulated trading-day grid.

    Forecast rule: the trailing-12-month dividends (relative to grid_dates[0])
    repeat on their anniversary ex-dates for as long as the grid runs. Each
    cash amount is converted to a proportional drop d = cash / spot (spot =
    current price), so the simulator can apply S ← S × (1 − d) at the step
    whose end date is the first grid date on/after the forecast ex-date.

    Parameters
    ----------
    div_history : one pd.Series per asset (ex-date → cash), tz-naive index.
                  Empty series → no jumps for that asset.
    spot_prices : current raw closing price per asset (same order).
    grid_dates  : the simulation date grid, length N+1 (anchor + N steps).

    Returns
    -------
    np.ndarray shape (n_assets, N): proportional drop applied at the END of
    step t (i.e. affecting the price at grid_dates[t+1]). Mostly zeros.
    """
    import numpy as np

    n_assets = len(div_history)
    N        = len(grid_dates) - 1
    sched    = np.zeros((n_assets, N))
    anchor   = grid_dates[0]
    horizon  = grid_dates[-1]
    n_years  = int(np.ceil((horizon - anchor).days / 365.25)) + 1

    for i, (divs, spot) in enumerate(zip(div_history, spot_prices)):
        if divs is None or len(divs) == 0 or not spot or spot <= 0:
            continue
        trailing = divs[(divs.index > anchor - pd.DateOffset(years=1)) & (divs.index <= anchor)]
        for ex_date, cash in trailing.items():
            prop = float(cash) / float(spot)
            if not (0.0 < prop < 0.5):     # sanity guard against bad data
                continue
            for y in range(1, n_years + 1):
                fcast = ex_date + pd.DateOffset(years=y)
                if fcast <= anchor or fcast > horizon:
                    continue
                idx = int(grid_dates.searchsorted(fcast))   # first grid date >= fcast
                if 1 <= idx <= N:
                    sched[i, idx - 1] += prop
    return sched