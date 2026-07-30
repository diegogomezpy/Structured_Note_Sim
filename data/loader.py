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
import re
import time
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor
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
    # The parentheses are load-bearing: `A if C else B` binds LOOSER than `not in`,
    # so without them this parsed as `(col not in ...) if isinstance(...) else raw.columns`
    # and the flat-columns branch evaluated an Index as a truth value —
    # "ValueError: The truth value of a Index is ambiguous" instead of the clear
    # message below. Latent only because yfinance 1.4 returns a MultiIndex even for
    # a single-ticker list; the `else` branch further down exists for the flat case,
    # so the author expected it to be reachable.
    have = (raw.columns.get_level_values(0) if isinstance(raw.columns, pd.MultiIndex)
            else raw.columns)
    if col not in have:
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

    # Non-positive prices survive dropna() — 0.0 is not NaN — and the very first
    # thing the calibrator does is log(p[1:]/p[:-1]). One zero anywhere in the
    # column turns two returns into ±inf, which makes the rolling variance NaN,
    # which makes theta NaN, which makes EVERY parameter and every simulated path
    # NaN. Nothing raises; the app just reports blanks. Yahoo does occasionally
    # serve a 0.0 for an illiquid or newly-delisted symbol, and the CSV / DataFrame
    # sources are user-supplied, so fail here with the ticker and date instead.
    bad = prices.le(0).any()
    if bool(bad.any()):
        names = [str(c) for c in bad[bad].index]
        first = {n: str(prices.index[prices[n].le(0)][0].date()) for n in names}
        raise ValueError(
            f"Non-positive prices (source='{source_label}') in: "
            + ", ".join(f"{n} (first on {first[n]})" for n in names)
            + ". Prices must be > 0 — log-returns are undefined otherwise, and the "
              "calibration would silently produce NaN parameters. Check the ticker "
              "symbol, or the data file if you supplied one."
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

    def _one(item: tuple[str, str]) -> tuple[str, pd.Series]:
        sym, name = item
        try:
            divs = yf.Ticker(sym).dividends
            if divs is None or len(divs) == 0:
                return name, pd.Series(dtype=float)
            divs = divs.copy()
            if getattr(divs.index, "tz", None) is not None:
                divs.index = divs.index.tz_localize(None)
            return name, divs.astype(float)
        except Exception as e:
            print(f"[loader] WARNING: could not load dividends for {sym}: {e} — assuming none.")
            return name, pd.Series(dtype=float)

    items = list(tickers.items())
    if not items:
        return {}
    # One Yahoo round-trip per ticker — fetch concurrently.
    with ThreadPoolExecutor(max_workers=min(8, len(items))) as ex:
        return dict(ex.map(_one, items))


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


_IV_MIN = 0.01    # 1%   — reject Yahoo's junk near-zero ATM quotes
_IV_MAX = 5.0     # 500% — reject obvious garbage on the high side


def _atm_iv(calls: pd.DataFrame, puts: pd.DataFrame, spot: float, n_near: int = 3):
    """ATM implied vol near spot (~100% moneyness): the median of the plausible
    call/put implied-vol quotes among the ``n_near`` strikes closest to spot.
    Returns None if no usable quote is found.

    Yahoo regularly returns junk implied vols for the exact ATM strike — values
    like 1e-5 or 5e-4 that are not real vols (they'd display as 0.0%). Taking the
    nearest strike alone then surfaced that garbage. We instead scan a few near-
    ATM strikes and keep only quotes inside a sane band (_IV_MIN.._IV_MAX); if
    they are ALL junk, returning None lets _iv_3m fall back to a realized vol that
    is at least honest, rather than printing 0.0%."""
    import numpy as np
    ivs = []
    for chain in (calls, puts):
        try:
            if chain is None or len(chain) == 0 or not spot:
                continue
            order = (chain["strike"] - spot).abs().to_numpy().argsort()[:n_near]
            for iv in chain["impliedVolatility"].to_numpy()[order]:
                iv = float(iv)
                if np.isfinite(iv) and _IV_MIN <= iv <= _IV_MAX:
                    ivs.append(iv)
        except Exception:
            continue
    return float(np.median(ivs)) if ivs else None


def _realized_vol(closes, window: int = 63):
    """Annualised ~3-month realized vol: stdev of daily log-returns over the last
    ``window`` (~63 trading-day) observations, scaled by √252. None if too few
    points. Used as a fallback when an underlying has no listed options on Yahoo
    (e.g. single European stocks), so it never gets a real implied figure."""
    import numpy as np
    c = np.asarray(closes, dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    if c.size < 21:
        return None
    r = np.diff(np.log(c[-(window + 1):]))
    if r.size < 15:
        return None
    sd = float(np.std(r, ddof=1))
    return sd * float(np.sqrt(252.0)) if np.isfinite(sd) and sd > 0 else None


def _iv_3m(ticker, sym: str, quote_type: str | None, spot, closes=None):
    """3-month vol, returned as ``(value, source)`` where source is "implied",
    "realized", or None. Equities: ATM implied vol at the expiry nearest +90 days
    (strike nearest spot, call/put averaged). Indices: the matching vol-index
    level (also an implied figure). When neither is available — e.g. a single
    European stock with no Yahoo option chain — falls back to a ~3M realized vol
    computed from ``closes`` so the figure is still populated and honestly
    labelled. ``(None, None)`` only when there is no price history either.

    A realized-vol sanity gate guards against Yahoo's intermittently broken ATM
    quotes: implied vol carries a risk premium and so normally sits AT or ABOVE
    realized, never a small fraction of it. When the option-chain figure comes
    back far below realized (e.g. Morgan Stanley at 2.3% against ~30% realized —
    above the 1% junk floor but still nonsense) we treat it as bad data and use
    the realized figure instead, honestly labelled."""
    rv = _realized_vol(closes) if closes is not None else None
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
                # Implausibly far below realized → bad quote; prefer realized.
                if rv is not None and iv < 0.5 * rv:
                    return rv, "realized"
                return iv, "implied"
        except Exception:
            pass
    vsym = _VOL_INDEX.get(sym) or _VOL_INDEX.get("^" + sym.lstrip("^"))
    if vsym:
        try:
            import yfinance as yf
            h = yf.Ticker(vsym).history(period="5d")["Close"].dropna()
            if len(h):
                return float(h.iloc[-1]) / 100.0, "implied"
        except Exception:
            pass
    if rv is not None:
        return rv, "realized"
    return None, None


_SA_CAP_RE = re.compile(r'Market Cap</a><!--\]--></td><td[^>]*>\s*([\d.,]+)\s*([TBMK])\b', re.S)
_SA_MULT = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
_SA_CACHE: dict[str, tuple[float, float | None]] = {}   # sym → (ts, market_cap)
_SA_TTL = 3600.0


def _stockanalysis_market_cap(sym: str) -> float | None:
    """Independent market-cap source, used only when Yahoo doesn't supply one.

    Yahoo's `.info["marketCap"]` is dropped for some tickers on cloud IPs (Yahoo
    throttles the fundamentals payload — prices still come through, so a single
    ticker shows "—"). stockanalysis.com renders the figure server-side, so a plain
    GET works without an API key or JS. US-listed symbols only — exchange-suffixed
    tickers ('MBG.DE') and share-class dashes are skipped (Yahoo covers those, and
    the stockanalysis URL scheme differs). Returns None on any failure; cached 1h."""
    if not sym or "." in sym or "-" in sym:
        return None
    base = sym.upper().strip()
    now = time.time()
    hit = _SA_CACHE.get(base)
    if hit is not None and now - hit[0] < _SA_TTL:
        return hit[1]
    cap = None
    for path in (f"stocks/{base}", f"etf/{base}"):
        try:
            req = urllib.request.Request(
                f"https://stockanalysis.com/{path}/",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "ignore")
            m = _SA_CAP_RE.search(html)
            if m:
                cap = float(m.group(1).replace(",", "")) * _SA_MULT[m.group(2)]
                break
        except Exception:
            continue
    _SA_CACHE[base] = (now, cap)
    return cap


_ANALYST_CACHE: dict[str, tuple[float, dict | None]] = {}   # sym → (ts, split)
_ANALYST_TTL = 3600.0


def _analyst_split(ticker, sym: str, quote_type: str | None) -> dict | None:
    """Analyst buy/hold/sell counts from Yahoo's recommendation grid (current period).

    Yahoo exposes a rolling grid of analyst ratings — strongBuy / buy / hold / sell /
    strongSell — with one row per month (`0m` = now). We collapse it to the three
    buckets the cards render (strongBuy+buy → buy, sell+strongSell → sell). Indices,
    currencies and funds have no coverage, so we skip the call to avoid a wasted 404.
    Returns None on any failure; cached 1h (keyed on symbol)."""
    qt = (quote_type or "").upper()
    if any(k in qt for k in ("INDEX", "CURRENCY", "ETF", "MUTUALFUND", "CRYPTO")):
        return None
    now = time.time()
    hit = _ANALYST_CACHE.get(sym)
    if hit is not None and now - hit[0] < _ANALYST_TTL:
        return hit[1]
    split = None
    try:
        rec = ticker.recommendations
        if rec is not None and len(rec):
            row = rec.iloc[0]                       # current period ('0m')
            g = lambda c: int(row.get(c, 0) or 0)   # noqa: E731 — tiny local
            buy  = g("strongBuy") + g("buy")
            hold = g("hold")
            sell = g("sell") + g("strongSell")
            if buy + hold + sell > 0:
                split = {"buy": buy, "hold": hold, "sell": sell}
    except Exception as e:
        print(f"[loader] analyst split failed for {sym}: {e}")
    _ANALYST_CACHE[sym] = (now, split)
    return split


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

    def _one(item: tuple[str, str]) -> tuple[str, dict]:
        """One underlying's metrics block. Each is an independent Yahoo round-trip
        (.info + history + options), so these run concurrently below."""
        sym, name = item
        rec = {k: None for k in (
            "long_name", "type", "sector", "industry", "market_cap", "currency",
            "last_price", "day_change", "rsi_14", "iv_3m", "iv_source",
            "business_summary", "analyst")}
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
            # Keep the close history around — it also feeds the realized-vol
            # fallback for underlyings with no listed options (see _iv_3m).
            _hist = None
            ser = (closes or {}).get(name)
            if ser is not None and len(ser):
                _ps = ser.dropna()
                rec["last_price"] = float(_ps.iloc[-1])
                rec["rsi_14"]     = _wilder_rsi(_ps.values)
                if len(_ps) >= 2:
                    rec["day_change"] = float(_ps.iloc[-1] / _ps.iloc[-2] - 1.0)
                _hist = _ps.values
            else:
                rec["last_price"] = (info.get("currentPrice")
                                     or info.get("regularMarketPrice"))
                try:
                    h = t.history(period="6mo")["Close"].dropna()
                    if len(h):
                        rec["last_price"] = rec["last_price"] or float(h.iloc[-1])
                        rec["rsi_14"]     = _wilder_rsi(h.values)
                        if len(h) >= 2:
                            rec["day_change"] = float(h.iloc[-1] / h.iloc[-2] - 1.0)
                        _hist = h.values
                except Exception:
                    pass

            # Market cap: `.info["marketCap"]` is flaky — Yahoo omits it from the
            # .info payload for some tickers (partial/rate-limited responses), so a
            # single source leaves cards showing "—". Fall back to the lighter
            # fast_info endpoint, then to shares × last price.
            if rec["market_cap"] is None:
                try:
                    fi = t.fast_info
                    mc = getattr(fi, "market_cap", None)
                    if mc is None and hasattr(fi, "get"):
                        mc = fi.get("market_cap") or fi.get("marketCap")
                    rec["market_cap"] = mc
                except Exception:
                    pass
            if rec["market_cap"] is None and rec["last_price"]:
                shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
                if shares is None:
                    try:
                        shares = getattr(t.fast_info, "shares", None)
                    except Exception:
                        shares = None
                if shares:
                    try:
                        rec["market_cap"] = float(shares) * float(rec["last_price"])
                    except (TypeError, ValueError):
                        pass
            # Last resort: an independent, non-Yahoo source. Yahoo can drop the whole
            # fundamentals payload (marketCap AND sharesOutstanding) for a ticker on
            # cloud IPs, defeating the tiers above — stockanalysis.com still has it.
            if rec["market_cap"] is None:
                rec["market_cap"] = _stockanalysis_market_cap(sym)

            rec["iv_3m"], rec["iv_source"] = _iv_3m(
                t, sym, rec["type"], rec["last_price"], _hist)
            # Analyst consensus (buy/hold/sell) — autofilled from Yahoo's rating grid.
            rec["analyst"] = _analyst_split(t, sym, rec["type"])
        except Exception as e:
            print(f"[loader] WARNING: could not load metrics for {sym}: {e}")
        return name, rec

    items = list(tickers.items())
    if not items:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(items))) as ex:
        return dict(ex.map(_one, items))


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


def fetch_business_summary(sym: str, ssl_verify: bool = True) -> str | None:
    """Fetch ONLY a ticker's business summary — the lightweight path for the
    description prefill buttons.

    ``load_underlying_metrics`` pulls the full profile *plus* an option-chain
    implied-vol lookup and an RSI computation; the prefill needs none of that, so
    going through it made the button wait on work it then discarded. This hits
    ``yf.Ticker(sym).info`` once and reads a single field. Returns None on any
    failure (caller falls back / shows a toast)."""
    if not sym:
        return None
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        info = yf.Ticker(sym).info or {}
        return info.get("longBusinessSummary") or None
    except Exception as e:
        print(f"[loader] fetch_business_summary failed for {sym}: {e}")
        return None


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
    import re

    raw = name.strip()
    # If the input looks like a ticker symbol (short, no spaces — e.g. "SAN" for
    # Banco Santander, "GLE.PA", "8306.T"), try it directly as a symbol first: that
    # resolves the issuer straight away without the fuzzy name search below.
    if raw and " " not in raw and len(raw) <= 7 and raw.upper() == raw:
        try:
            info = yf.Ticker(raw).info or {}
            if info.get("quoteType") in (None, "EQUITY") and info.get("longBusinessSummary"):
                return info["longBusinessSummary"]
        except Exception:
            pass
    # Build query candidates from most specific to least. Note issuers are very
    # often financing subsidiaries ("Morgan Stanley B.V.", "Morgan Stanley
    # Finance LLC", "BNP Paribas Issuance B.V.", "Goldman Sachs Finance Corp")
    # that Yahoo can't resolve to the listed parent — the search returns either
    # nothing or the structured notes themselves (MUTUALFUND rows), never the
    # parent equity. So progressively strip corporate-form / descriptor suffixes
    # and finally fall back to the leading 1-2 brand words.
    cands: list[str] = []
    def _add(q: str) -> None:
        q = re.sub(r"\s+", " ", q).strip(" ,.&-")
        if q and q.lower() not in {c.lower() for c in cands}:
            cands.append(q)

    _add(raw)
    _add(re.sub(r"\b(Bank|Banco)\b", "", raw))
    # Iteratively strip trailing corporate-form / descriptor tokens.
    _suffix = re.compile(
        r"[\s,]*\b("
        r"B\.?V\.?|N\.?V\.?|S\.?A\.?S\.?|S\.?A\.?|S\.?p\.?A\.?|"
        r"LLC|L\.?P\.?|Ltd\.?|Limited|PLC|AG|GmbH|Inc\.?|Corp\.?|"
        r"Co\.?|Company|Issuance|Finance|Financial|Funding|Capital|"
        r"International|Group|Holdings?|Securities|Services"
        r")\.?$", re.IGNORECASE)
    core = raw
    for _ in range(6):
        nxt = _suffix.sub("", core).strip(" ,.&-")
        if nxt == core or not nxt:
            break
        core = nxt
        _add(core)
    # Brand fallback: leading two words, then the leading word.
    toks = [t for t in re.split(r"[\s&,]+", raw) if t]
    if len(toks) >= 2:
        _add(" ".join(toks[:2]))
    if toks:
        _add(toks[0])

    for q in cands:
        try:
            quotes = yf.Search(q, max_results=8).quotes or []
            # Accept EQUITY only — MUTUALFUND/MONEY_MARKET rows are the notes and
            # funds themselves and carry no parent business summary. Probe the
            # first few equities in case the top listing lacks a summary.
            eq = [x for x in quotes if x.get("quoteType") == "EQUITY"]
            for x in eq[:3]:
                sym = x.get("symbol")
                if not sym:
                    continue
                summ = (yf.Ticker(sym).info or {}).get("longBusinessSummary")
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