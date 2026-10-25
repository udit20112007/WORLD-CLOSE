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
    # The screener reports volume 0 for some markets (e.g. Korea): treat it as unknown, not zero
    df["volume"] = df["volume"].where(df["volume"] > 0)
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
    df = parse(quotes, cfg)
    if missing_volume(df):
        session = df.attrs.get("session_date", day)
        filled = fill_from_history(df, session, cfg)
        if filled is not None:
            filled.attrs.update(df.attrs)
            df = filled
    return df


def missing_volume(df: pd.DataFrame) -> bool:
    """True if most stocks have no volume (more than half missing or zero)."""
    vol = pd.to_numeric(df["volume"], errors="coerce")
    return len(df) > 0 and (vol > 0).mean() < 0.5


def fill_from_history(df: pd.DataFrame, day: dt.date, cfg: dict) -> pd.DataFrame | None:
    """Fill volume (and missing open/high/low) for `day` from Yahoo's daily history.
    Returns the filled rows, or None if Yahoo's history doesn't have that day yet."""
    from ..yahoo import backfill as yahoo_backfill
    suffix = cfg.get("yahoo_suffix", "")
    days, ok, errors = yahoo_backfill(df, day - dt.timedelta(days=7), day, lambda s: f"{s}{suffix}", pause=1.0)
    hist = days.get(day)
    if hist is None or hist.empty:
        print(f"  Yahoo history has no {day} yet; volume left blank", file=sys.stderr)
        return None
    h = hist.set_index("symbol")
    out = df.copy()
    for col in ("volume", "open", "high", "low"):
        src = out["symbol"].map(h[col])
        out[col] = pd.to_numeric(out[col], errors="coerce").where(lambda v: v > 0, src)
    out["volume"] = out["volume"].where(out["volume"] > 0)
    out["value"] = (out["close"] * out["volume"]).round(0)
    got = int((out["volume"] > 0).sum())
    print(f"  Volume filled from Yahoo history for {got} of {len(out)} stocks", file=sys.stderr)
    return out


def repair(code: str, cfg: dict, store, days_back: int = 3) -> list[str]:
    """Fill volume on recently saved days that were stored without it."""
    notes = []
    for day in store.stored_days(code)[-days_back:]:
        df = store.load_day(code, day)
        if df is None or not missing_volume(df):
            continue
        filled = fill_from_history(df, day, cfg)
        if filled is not None and not missing_volume(filled):
            store.save_day(code, day, filled)
            notes.append(f"Volume filled in for {day}.")
    return notes


def backfill(latest: pd.DataFrame, start: dt.date, end: dt.date, cfg: dict | None = None):
    from ..yahoo import backfill as yahoo_backfill
    suffix = (cfg or {}).get("yahoo_suffix", "")
    return yahoo_backfill(latest, start, end, lambda s: f"{s}{suffix}")
