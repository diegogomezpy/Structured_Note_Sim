"""
app/underlyings.py
------------------
The selectable underlying universe, ticker-logo URLs, and label helpers.

Pure data + helpers — NO Streamlit/Plotly imports — so the ticker list and
logos live in one source of truth without dragging in the UI framework.
"""
from __future__ import annotations

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


def _label_to_name(lbl: str) -> str:
    """Resolve a multiselect label to its human display name (never the ticker).

    Universe labels are formatted ``"TICKER — Company"`` so the company name is
    the part AFTER the em-dash; custom labels are ``"Company — SYM (custom)"`` so
    it is the part BEFORE it. Using ``split(" — ")[0]`` unconditionally (the old
    bug) returned the ticker for every universe pick, e.g. "MSFT" instead of
    "Microsoft".
    """
    if lbl.endswith(" (custom)"):
        return lbl.split(" — ", 1)[0]
    return lbl.split(" — ", 1)[1] if " — " in lbl else lbl
