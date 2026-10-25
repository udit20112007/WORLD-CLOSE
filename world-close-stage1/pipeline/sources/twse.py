"""Taiwan Stock Exchange from the official TWSE OpenAPI.

STOCK_DAY_ALL lists every listed stock and ETF for the latest session, with
open/high/low/close, change, volume, value, number of trades, and the trading
date in the Taiwanese (ROC) calendar, which tells us exactly which day the
prices are for. History comes from a one-off Yahoo backfill.
"""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from ..common import dedupe, get_bytes, normalize, session

LATEST_ONLY = True
URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"

COLUMNS = {
    "symbol": ["Code"],
    "name":   ["Name"],
    "open":   ["OpeningPrice"],
    "high":   ["HighestPrice"],
    "low":    ["LowestPrice"],
    "close":  ["ClosingPrice"],
    "volume": ["TradeVolume"],
    "value":  ["TradeValue"],
    "trades": ["Transaction"],
}

_session = None


def fetch(day: dt.date, cfg: dict) -> pd.DataFrame:
    global _session
    if _session is None:
        _session = session(referer="https://openapi.twse.com.tw/")
        _session.headers["Accept"] = "application/json"
    return parse(json.loads(get_bytes(_session, URL, timeout=60)), cfg)


def roc_date(value: str) -> dt.date | None:
    """'1151023' (ROC year 115) -> 2026-10-23."""
    v = str(value).strip()
    if len(v) == 7 and v.isdigit():
        return dt.date(int(v[:3]) + 1911, int(v[3:5]), int(v[5:]))
    if len(v) == 8 and v.isdigit():
        return dt.date(int(v[:4]), int(v[4:6]), int(v[6:]))
    return None


def parse(rows, cfg: dict) -> pd.DataFrame:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Unrecognised TWSE response: expected a list of stocks")
    raw = pd.DataFrame(rows).astype(str)
    raw["_change"] = pd.to_numeric(raw.get("Change", pd.Series("", index=raw.index))
                                   .str.replace(r"[,+\s]", "", regex=True), errors="coerce")
    close = pd.to_numeric(raw["ClosingPrice"].str.replace(",", ""), errors="coerce") if "ClosingPrice" in raw else None
    if close is not None:
        raw["_prev"] = (close - raw["_change"]).round(4).astype(str)
    df = normalize(raw, {**COLUMNS, "prev_close": ["_prev"]})
    df["series"] = ["ETF" if s.startswith("00") else "Stock" for s in df["symbol"]]
    df = dedupe(df)
    dates = {roc_date(v) for v in raw.get("Date", [])} - {None}
    if len(dates) == 1:
        df.attrs["session_date"] = dates.pop()
    return df


def backfill(latest: pd.DataFrame, start: dt.date, end: dt.date, cfg: dict | None = None):
    from ..yahoo import backfill as yahoo_backfill
    return yahoo_backfill(latest, start, end, lambda s: f"{s}.TW")
