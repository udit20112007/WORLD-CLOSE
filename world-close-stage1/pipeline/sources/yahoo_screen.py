"""Any exchange, from Yahoo Finance's stock screener (latest session).

The screener lists every stock Yahoo carries on an exchange, 250 at a time,
with English names, last price, previous close, open/high/low, volume, market
cap and the time of the last trade (which tells us the session date). Used for
KOSPI and KOSDAQ, and for English company names on other exchanges.

config:  yahoo_exchange  Yahoo's exchange code, e.g. KSC (KOSPI), KOE (KOSDAQ)
         yahoo_suffix    suffix of Yahoo symbols there, e.g. .KS or .KQ
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from zoneinfo import ZoneInfo

import pandas as pd

from ..common import dedupe, normalize

LATEST_ONLY = True
PAGE = 250
MAX_PAGES = 60          # 15,000 stocks: far more than any exchange we use


def screen_all(yahoo_exchange: str, quote_type: str = "EQUITY", pause: float = 1.0) -> list[dict]:
    """Every quote Yahoo's screener returns for one exchange, page by page."""
    import yfinance as yf
    query_cls = yf.EquityQuery if quote_type == "EQUITY" else yf.ETFQuery
    query = query_cls("eq", ["exchange", yahoo_exchange])
    quotes, offset, total = [], 0, None
    for _ in range(MAX_PAGES):
        result = yf.screen(query, offset=offset, size=PAGE, sortField="ticker", sortAsc=True)
        page = result.get("quotes") or []
        quotes += page
        total = result.get("total", total)
        offset += len(page)
        print(f"  Yahoo screener {yahoo_exchange} {quote_type}: {offset}/{total}", file=sys.stderr)
        if not page or (total is not None and offset >= total):
            break
        time.sleep(pause)
    return quotes


def strip_suffix(symbol: str) -> str:
    return symbol.rsplit(".", 1)[0] if "." in symbol else symbol


def parse(quotes: list[dict], cfg: dict) -> pd.DataFrame:
    if not quotes:
        raise ValueError(f"Yahoo screener returned no stocks for {cfg.get('yahoo_exchange')}")
    raw = pd.DataFrame(quotes)
    raw["_symbol"] = raw["symbol"].astype(str).map(strip_suffix)
    raw["_name"] = raw.get("longName", pd.Series(index=raw.index, dtype=object)).fillna(
        raw.get("shortName", pd.Series(index=raw.index, dtype=object))).fillna(raw["symbol"])
    df = normalize(raw.astype(str), {
        "symbol": ["_symbol"], "name": ["_name"],
        "open": ["regularMarketOpen"], "high": ["regularMarketDayHigh"], "low": ["regularMarketDayLow"],
        "close": ["regularMarketPrice"], "prev_close": ["regularMarketPreviousClose"],
        "volume": ["regularMarketVolume"], "market_cap": ["marketCap"],
    })
    df["value"] = (df["close"] * df["volume"]).round(0)
    df["market_cap"] = df["market_cap"].where(df["market_cap"] > 0)
    df["series"] = "Stock"
    df = dedupe(df)
    if "regularMarketTime" in raw:
        tz = ZoneInfo(cfg.get("timezone", "UTC"))
        times = pd.to_numeric(raw["regularMarketTime"], errors="coerce").dropna()
        if len(times):
            days = pd.Series([dt.datetime.fromtimestamp(t, tz).date() for t in times])
            df.attrs["session_date"] = days.mode().iloc[0]
    return df


def fetch(day: dt.date, cfg: dict) -> pd.DataFrame:
    try:
        quotes = screen_all(cfg["yahoo_exchange"])
    except Exception as exc:
        raise RuntimeError(f"Yahoo screener failed: {exc}") from exc
    return parse(quotes, cfg)


def backfill(latest: pd.DataFrame, start: dt.date, end: dt.date, cfg: dict | None = None):
    from ..yahoo import backfill as yahoo_backfill
    suffix = (cfg or {}).get("yahoo_suffix", "")
    return yahoo_backfill(latest, start, end, lambda s: f"{s}{suffix}")
