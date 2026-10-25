"""Shanghai, Shenzhen and Hong Kong stocks (latest session), via AKShare.

Two providers, tried in order until one answers:
  sina       Sina Finance's market lists (usually reachable from outside China)
  eastmoney  East Money's quote lists (has market caps, but often refuses
             connections from outside China, including GitHub's servers)

Both only show the latest session, so this source is LATEST_ONLY; history
comes from a one-off Yahoo backfill. config "board": sh_a, sz_a or hk.
"""
from __future__ import annotations

import datetime as dt
import sys

import pandas as pd

from ..common import dedupe, normalize

LATEST_ONLY = True
PROVIDERS = ("sina", "eastmoney")

EM_COLUMNS = {
    "symbol": ["代码"], "name": ["名称"], "open": ["今开"], "high": ["最高"], "low": ["最低"],
    "close": ["最新价"], "prev_close": ["昨收"], "volume": ["成交量"], "value": ["成交额"],
    "market_cap": ["总市值"],
}
EM_FUNCTIONS = {"sh_a": "stock_sh_a_spot_em", "sz_a": "stock_sz_a_spot_em", "hk": "stock_hk_spot_em"}

SINA_A_COLUMNS = {
    "symbol": ["代码"], "name": ["名称"], "open": ["今开"], "high": ["最高"], "low": ["最低"],
    "close": ["最新价"], "prev_close": ["昨收"], "volume": ["成交量"], "value": ["成交额"],
}
SINA_HK_COLUMNS = {
    "symbol": ["代码"], "name": ["英文名称", "中文名称"], "open": ["今开"], "high": ["最高"], "low": ["最低"],
    "close": ["最新价"], "prev_close": ["昨收"], "volume": ["成交量"], "value": ["成交额"],
}

_sina_a_cache: pd.DataFrame | None = None   # Sina's A-share list covers both Shanghai and Shenzhen


def fetch(day: dt.date, cfg: dict) -> pd.DataFrame:
    errors = []
    for provider in cfg.get("providers", PROVIDERS):
        try:
            df = (from_sina if provider == "sina" else from_eastmoney)(cfg)
            df.attrs["provider"] = provider
            return df
        except Exception as exc:
            errors.append(f"{provider}: {str(exc)[:160]}")
            print(f"  {provider} failed: {exc}", file=sys.stderr)
    raise RuntimeError("all providers failed; " + " | ".join(errors))


def from_eastmoney(cfg: dict) -> pd.DataFrame:
    import akshare as ak
    raw = getattr(ak, EM_FUNCTIONS[cfg["board"]])()
    return parse(raw, cfg, EM_COLUMNS)


def from_sina(cfg: dict) -> pd.DataFrame:
    global _sina_a_cache
    import akshare as ak
    if cfg["board"] == "hk":
        raw = ak.stock_hk_spot()
        df = parse(raw, cfg, SINA_HK_COLUMNS)
        if "日期时间" in raw:
            dates = pd.to_datetime(raw["日期时间"], errors="coerce").dt.date.dropna()
            if len(dates):
                df.attrs["session_date"] = dates.mode().iloc[0]
        return df
    if _sina_a_cache is None:
        _sina_a_cache = ak.stock_zh_a_spot()
    raw = _sina_a_cache.astype(str)
    prefix = "sh" if cfg["board"] == "sh_a" else "sz"
    raw = raw[raw["代码"].str.lower().str.startswith(prefix)].copy()
    raw["代码"] = raw["代码"].str[2:]
    return parse(raw, cfg, SINA_A_COLUMNS)


def board_of(symbol: str, board: str) -> str:
    """Market segment from the stock code."""
    if board == "sh_a":
        return "STAR Market" if symbol.startswith(("688", "689")) else "Main Board"
    if board == "sz_a":
        return "ChiNext" if symbol.startswith(("300", "301")) else "Main Board"
    return "GEM" if symbol.startswith("08") else "Main Board"


def volume_in_shares(df: pd.DataFrame) -> pd.DataFrame:
    """Some feeds quote volume in lots of 100 shares. value / (volume x price) is
    about 1 when volume is in shares and about 100 when it's in lots."""
    ok = df[(df["volume"] > 0) & (df["value"] > 0) & (df["close"] > 0)]
    if len(ok):
        ratio = (ok["value"] / (ok["volume"] * ok["close"])).median()
        if 50 < ratio < 200:
            df = df.copy()
            df["volume"] = df["volume"] * 100
    return df


def parse(raw: pd.DataFrame, cfg: dict, columns: dict = EM_COLUMNS) -> pd.DataFrame:
    df = normalize(raw.astype(str), columns)
    if df.empty:
        raise ValueError("no stocks with a price in the response")
    df = volume_in_shares(df)
    df["market_cap"] = df["market_cap"].where(df["market_cap"] > 0)
    df["series"] = [board_of(s, cfg["board"]) for s in df["symbol"]]
    return dedupe(df)


def to_yahoo_for(board: str):
    if board == "sh_a":
        return lambda s: f"{s}.SS"
    if board == "sz_a":
        return lambda s: f"{s}.SZ"
    return lambda s: f"{int(s):04d}.HK"          # 00700 -> 0700.HK


def backfill(latest: pd.DataFrame, start: dt.date, end: dt.date, cfg: dict | None = None):
    from ..yahoo import backfill as yahoo_backfill
    board = (cfg or {}).get("board", "sh_a")
    return yahoo_backfill(latest, start, end, to_yahoo_for(board))
