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
    years:      float                   = 5.0,
    end_date:   str | None              = None,
    ssl_verify: bool                    = True,
    csv_files:  dict[str, str] | None   = None,
    df:         pd.DataFrame | None     = None,
) -> pd.DataFrame:
    """
    Load and align daily adjusted closing prices.

    Parameters
    ----------
    source : str
        "yfinance"  — pull live data from Yahoo Finance (default).
        "csv"       — load from CSV files (bundled or custom).
        "df"        — use a pre-loaded DataFrame directly.

    tickers : dict[str, str] or None
        yfinance ticker → display name mapping.
        Only used when source="yfinance".
        Defaults to DEFAULT_TICKERS (SPX / SX5E / SMI).

    years : float
        How many years of history to pull.
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
    if source == "yfinance":
        return _from_yfinance(tickers or DEFAULT_TICKERS, years, end_date, ssl_verify)
    elif source == "csv":
        return _from_csv(csv_files or DEFAULT_CSV_FILES)
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
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError(
            "yfinance is not installed. Run: pip install yfinance\n"
            "Or use load_prices(source='csv') to load from the bundled CSVs."
        )

    end   = pd.Timestamp(end_date) if end_date else pd.Timestamp.today()
    start = end - pd.DateOffset(years=years)

    ticker_symbols = list(tickers.keys())
    print(f"[loader] Pulling {ticker_symbols} from yfinance "
          f"({start.date()} → {end.date()}) …")

    session = None
    if not ssl_verify:
        import requests, urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session = requests.Session()
        session.verify = False
        print("[loader] SSL verification disabled.")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        kwargs = dict(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )
        if session:
            kwargs["session"] = session
        raw = yf.download(ticker_symbols, **kwargs)

    # yfinance returns a MultiIndex for multiple tickers, flat for one
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"][ticker_symbols]
    else:
        prices = raw[["Close"]].rename(columns={"Close": ticker_symbols[0]})

    prices = prices.rename(columns=tickers)
    return _align(prices, "yfinance")


def _from_csv(csv_files: dict[str, str]) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}

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

        if "Adj Close" not in df.columns:
            raise ValueError(
                f"'{path}' has no 'Adj Close' column. "
                f"Columns found: {list(df.columns)}. "
                f"Use a raw Yahoo Finance CSV export."
            )
        series[name] = pd.to_numeric(df["Adj Close"], errors="coerce")
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

    print(f"[loader] Aligned: {n_after} common trading days "
          f"({prices.index[0].date()} → {prices.index[-1].date()})")

    if n_after == 0:
        raise ValueError(
            f"No data returned (source='{source_label}'). "
            f"Check your ticker symbols, date range, or network connection."
        )

    if n_after < 60:
        raise ValueError(
            f"Only {n_after} overlapping observations after alignment "
            f"(source='{source_label}'). "
            f"Increase years= or check that your files cover an overlapping date range."
        )
    return prices