"""Any exchange, from Yahoo Finance's stock screener (latest session).

The screener lists every stock Yahoo carries on an exchange, 250 at a time,
with English names, last price, previous close, open/high/low, volume, market
cap and the time of the last trade (which tells us the session date). Used for
KOSPI and KOSDAQ, and for English company names on other exchanges.

config:  yahoo_exchange  Yahoo's exchange code, e.g. KSC (KOSPI), or a list of codes
         yahoo_suffix    suffix of Yahoo symbols there, e.g. .KS, removed from our symbols
         keep_suffix     keep Yahoo's full symbol (e.g. 7203.T), needed when one exchange
                         spans several Yahoo codes whose tickers could collide
         venues          {Yahoo exchange code: label}, shown as the series (e.g. city)
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


def screen_all(yahoo_exchange, quote_type: str = "EQUITY", pause: float = 1.0) -> list[dict]:
    """Every quote Yahoo's screener returns for one exchange code (or a list of
    codes, e.g. Euronext's seven venues), page by page."""
    import yfinance as yf
    query_cls = yf.EquityQuery if quote_type == "EQUITY" else yf.ETFQuery
    codes = [yahoo_exchange] if isinstance(yahoo_exchange, str) else list(yahoo_exchange)
    query = query_cls("eq", ["exchange", codes[0]]) if len(codes) == 1 else query_cls("is-in", ["exchange", *codes])
    quotes, offset, total = [], 0, None
    for _ in range(MAX_PAGES):
        result = _screen_with_retries(yf, query, offset)
        page = result.get("quotes") or []
        quotes += page
        total = result.get("total", total)
        offset += len(page)
        print(f"  Yahoo screener {yahoo_exchange} {quote_type}: {offset}/{total}", file=sys.stderr)
        if not page or (total is not None and offset >= total):
            break
        time.sleep(pause)
    return quotes


RETRY_WAITS = (60, 180, 300)   # seconds to wait after each refusal before trying again


def _is_rate_limited(exc: Exception) -> bool:
    """Yahoo rate-limits its login-token ("crumb") request after heavy use; yfinance then
    carries on without a token and the screener answers 401 Unauthorized, or 429."""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(k in text for k in ("401", "429", "unauthorized", "too many requests", "ratelimit"))


def _screen_with_retries(yf, query, offset: int) -> dict:
    for attempt, wait in enumerate((*RETRY_WAITS, None)):
        try:
            return yf.screen(query, offset=offset, size=PAGE, sortField="ticker", sortAsc=True)
        except Exception as exc:
            if wait is None or not _is_rate_limited(exc):
                raise
            print(f"  Yahoo refused the request ({exc}); waiting {wait}s before retry {attempt + 1}",
                  file=sys.stderr)
            time.sleep(wait)


DEAD_AFTER_DAYS = 30


def drop_dead_listings(raw: pd.DataFrame) -> pd.DataFrame:
    """Yahoo's screener still lists many delisted, merged or long-suspended securities
    (e.g. thousands on Euronext). Keep only stocks that traded in the last 30 days,
    measured from the newest trade time in the response."""
    if "regularMarketTime" not in raw:
        return raw
    t = pd.to_numeric(raw["regularMarketTime"], errors="coerce")
    if t.notna().mean() < 0.5:          # the field isn't reliable here; keep everything
        return raw
    keep = t >= t.max() - DEAD_AFTER_DAYS * 86400
    dropped = int((~keep).sum())
    if dropped:
        print(f"  Dropped {dropped} of {len(raw)} listings with no trade in {DEAD_AFTER_DAYS} days",
              file=sys.stderr)
    out = raw[keep].reset_index(drop=True)
    out.attrs["dead_dropped"] = dropped
    return out


def strip_suffix(symbol: str) -> str:
    return symbol.rsplit(".", 1)[0] if "." in symbol else symbol


def parse(quotes: list[dict], cfg: dict) -> pd.DataFrame:
    if not quotes:
        raise ValueError(f"Yahoo screener returned no stocks for {cfg.get('yahoo_exchange')}")
    raw = pd.DataFrame(quotes)
    raw = drop_dead_listings(raw)
    keep = cfg.get("keep_suffix", False)
    raw["_symbol"] = raw["symbol"].astype(str) if keep else raw["symbol"].astype(str).map(strip_suffix)
    raw["_currency"] = raw["currency"].astype(str) if "currency" in raw else ""
    venues = cfg.get("venues") or {}
    raw["_series"] = raw["exchange"].map(venues).fillna("Stock") if venues and "exchange" in raw else "Stock"
    raw["_name"] = raw.get("longName", pd.Series(index=raw.index, dtype=object)).fillna(
        raw.get("shortName", pd.Series(index=raw.index, dtype=object))).fillna(raw["symbol"])
    df = normalize(raw.astype(str), {
        "symbol": ["_symbol"], "name": ["_name"],
        "open": ["regularMarketOpen"], "high": ["regularMarketDayHigh"], "low": ["regularMarketDayLow"],
        "close": ["regularMarketPrice"], "prev_close": ["regularMarketPreviousClose"],
        "volume": ["regularMarketVolume"], "market_cap": ["marketCap"],
        "currency": ["_currency"], "series": ["_series"],
    })
    df["currency"] = df["currency"].replace({"nan": "", "None": ""})
    # The screener reports volume 0 for some markets (e.g. Korea): treat it as unknown, not zero
    df["volume"] = df["volume"].where(df["volume"] > 0)
    df["value"] = (df["close"] * df["volume"]).round(0)
    df["market_cap"] = df["market_cap"].where(df["market_cap"] > 0)
    df = dedupe(df)
    if raw.attrs.get("dead_dropped"):
        df.attrs["dead_dropped"] = raw.attrs["dead_dropped"]
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
    if missing_volume(df) and not cfg.get("_listing_only"):   # the stock list alone needs no volumes
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
    days, ok, errors = yahoo_backfill(df, day - dt.timedelta(days=7), day, to_yahoo_for(cfg), pause=1.0)
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


def to_yahoo_for(cfg: dict | None):
    cfg = cfg or {}
    if cfg.get("keep_suffix"):
        return lambda s: s
    suffix = cfg.get("yahoo_suffix", "")
    return lambda s: f"{s}{suffix}"


def backfill(latest: pd.DataFrame, start: dt.date, end: dt.date, cfg: dict | None = None):
    from ..yahoo import backfill as yahoo_backfill
    return yahoo_backfill(latest, start, end, to_yahoo_for(cfg))
