"""
data/loader.py
--------------
Single source of truth for price data loading.

Three backends, one interface:

    load_prices()                          # pull live from yfinance (default)
    load_prices(source="csv")             # bundled CSVs in data/
    load_prices(source="csv", csv_files={"my.csv": "SPX"})  # custom CSVs
    load_prices(source="df", df=my_df)    # pre-loaded DataFrame

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

# Bundled CSV files (used when source="csv" with no csv_files override)
DEFAULT_CSV_FILES: dict[str, str] = {
    str(_DATA_DIR / "SPX.csv"):  "SPX",
    str(_DATA_DIR / "SX5E.csv"): "SX5E",
    str(_DATA_DIR / "SMI.csv"):  "SMI",
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
        "csv"       — load from CSV files (bundled or custom).
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
        Only used when source="csv".
        Defaults to the three bundled index CSVs in data/.

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
        return _from_csv(csv_files or DEFAULT_CSV_FILES, field)
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
                f"Bundled CSVs live in {_DATA_DIR}. "
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