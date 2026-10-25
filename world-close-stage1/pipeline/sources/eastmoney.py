"""Shanghai, Shenzhen and Hong Kong stocks from East Money (via AKShare).

East Money's quote lists cover every listed stock on each market with last
price, change, open/high/low, previous close, volume and value (and market cap
for mainland China). They only show the latest session, so this source is
LATEST_ONLY. History comes from a one-off Yahoo backfill.

config "board" picks the list:  sh_a (Shanghai A), sz_a (Shenzhen A), hk.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from ..common import dedupe, normalize

LATEST_ONLY = True

COLUMNS = {
    "symbol":     ["代码"],
    "name":       ["名称"],
    "open":       ["今开"],
    "high":       ["最高"],
    "low":        ["最低"],
    "close":      ["最新价"],
    "prev_close": ["昨收"],
    "volume":     ["成交量"],
    "value":      ["成交额"],
    "market_cap": ["总市值"],
}

FUNCTIONS = {"sh_a": "stock_sh_a_spot_em", "sz_a": "stock_sz_a_spot_em", "hk": "stock_hk_spot_em"}


def fetch(day: dt.date, cfg: dict) -> pd.DataFrame:
    import akshare as ak
    try:
        raw = getattr(ak, FUNCTIONS[cfg["board"]])()
    except Exception as exc:
        raise RuntimeError(f"East Money download failed: {exc}") from exc
    return parse(raw, cfg)


def board_of(symbol: str, board: str) -> str:
    """Market segment from the stock code."""
    if board == "sh_a":
        return "STAR Market" if symbol.startswith(("688", "689")) else "Main Board"
    if board == "sz_a":
        return "ChiNext" if symbol.startswith(("300", "301")) else "Main Board"
    return "GEM" if symbol.startswith("08") else "Main Board"


def parse(raw: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = normalize(raw.astype(str), COLUMNS)
    if cfg["board"] in ("sh_a", "sz_a"):
        df["volume"] = df["volume"] * 100     # mainland volumes are quoted in lots of 100 shares
    df["market_cap"] = df["market_cap"].where(df["market_cap"] > 0)
    df["series"] = [board_of(s, cfg["board"]) for s in df["symbol"]]
    return dedupe(df)


def to_yahoo_for(board: str):
    if board == "sh_a":
        return lambda s: f"{s}.SS"
    if board == "sz_a":
        return lambda s: f"{s}.SZ"
    return lambda s: f"{int(s):04d}.HK"          # East Money 00700 -> Yahoo 0700.HK


def backfill(latest: pd.DataFrame, start: dt.date, end: dt.date, cfg: dict | None = None):
    from ..yahoo import backfill as yahoo_backfill
    board = (cfg or {}).get("board", "sh_a")
    return yahoo_backfill(latest, start, end, to_yahoo_for(board))
