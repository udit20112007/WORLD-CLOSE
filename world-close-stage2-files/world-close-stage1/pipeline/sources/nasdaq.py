"""US stocks (NYSE, Nasdaq, NYSE American) from Nasdaq's public stock screener.

One request per exchange returns every listed stock with its last price, daily
change, volume, sector and market cap. The screener only knows the *latest*
session, so this source is marked LATEST_ONLY: the pipeline calls it once per
run, after the US close, and labels the data with that day's New York date.

History for charts can be filled in once with `backfill()`, which downloads
past daily closes from Yahoo Finance (best effort, safe to re-run).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import defaultdict

import pandas as pd

from ..common import STANDARD_COLUMNS, dedupe, get_bytes, normalize, session

LATEST_ONLY = True
URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true&exchange={exchange}"

COLUMNS = {
    "symbol":     ["symbol"],
    "name":       ["name"],
    "close":      ["lastsale"],
    "volume":     ["volume"],
    "sector":     ["sector"],
    "market_cap": ["marketCap"],
}

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = session(referer="https://www.nasdaq.com/")
        _session.headers.update({"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com"})
    return _session


def fetch(day: dt.date, cfg: dict) -> pd.DataFrame:
    blob = get_bytes(_get_session(), URL.format(exchange=cfg["screener_exchange"]), timeout=60)
    return parse(json.loads(blob), cfg)


def classify(symbol: str, name: str) -> str:
    """Rough security type from the symbol and name, used as the series filter."""
    n = name.lower()
    if "warrant" in n:
        return "Warrant"
    if " right" in n or n.endswith("rights"):
        return "Right"
    if " unit" in n:
        return "Unit"
    if "^" in symbol or "preferred" in n or "depositary shares, each representing" in n:
        return "Preferred"
    if "american depositary" in n or " ads" in n:
        return "ADR"
    return "Common"


def parse(payload: dict, cfg: dict) -> pd.DataFrame:
    data = payload.get("data") or {}
    rows = data.get("rows") or (data.get("table") or {}).get("rows")
    if not rows:
        status = payload.get("status") or {}
        raise ValueError(f"Unrecognised screener response: no rows (status {status})")
    raw = pd.DataFrame(rows).astype(str)

    def num(col):
        if col not in raw:
            return pd.Series(float("nan"), index=raw.index)
        return pd.to_numeric(raw[col].str.replace(r"[$,%\s]", "", regex=True), errors="coerce")

    # The screener gives last price and net change; previous close is the difference
    raw["_prev_close"] = (num("lastsale") - num("netchange")).round(4).astype(str)
    df = normalize(raw, {**COLUMNS, "prev_close": ["_prev_close"]})
    df["value"] = (df["close"] * df["volume"]).round(0)
    df["market_cap"] = df["market_cap"].where(df["market_cap"] > 0)
    df["symbol"] = df["symbol"].str.replace(" ", "", regex=False)
    df["series"] = [classify(s, n) for s, n in zip(df["symbol"], df["name"])]
    return dedupe(df)


# --------------------------------------------------------------------------
# One-off history backfill from Yahoo Finance
# --------------------------------------------------------------------------

def to_yahoo(symbol: str) -> str:
    """Nasdaq-style symbols to Yahoo's: BRK/B -> BRK-B, ABR^D -> ABR-PD."""
    return symbol.replace("^", "-P").replace("/", "-")


def backfill(latest: pd.DataFrame, start: dt.date, end: dt.date, chunk_size: int = 100,
             pause: float = 2.0) -> tuple[dict[dt.date, pd.DataFrame], int, list[str]]:
    """Download daily closes for the symbols in `latest` between start and end.

    Returns ({day: rows}, number of symbols that returned data, errors).
    Only common stocks, ADRs and preferreds are requested; warrants, units and
    rights are mostly missing on Yahoo and would just waste requests.
    """
    import yfinance as yf

    meta = latest.set_index("symbol")
    wanted = [s for s in meta.index if meta.at[s, "series"] in ("Common", "ADR", "Preferred")]
    ymap = {to_yahoo(s): s for s in wanted}
    ysyms = list(ymap)
    per_day: dict[dt.date, list] = defaultdict(list)
    ok, errors = 0, []

    for i in range(0, len(ysyms), chunk_size):
        chunk = ysyms[i:i + chunk_size]
        try:
            frame = yf.download(chunk, start=start.isoformat(), end=(end + dt.timedelta(days=1)).isoformat(),
                                interval="1d", auto_adjust=False, group_by="ticker", threads=True,
                                progress=False)
        except Exception as exc:
            errors.append(f"Yahoo chunk {i // chunk_size + 1}: {exc}")
            time.sleep(pause * 5)
            continue
        if frame is None or frame.empty:
            errors.append(f"Yahoo chunk {i // chunk_size + 1}: no data returned")
            time.sleep(pause * 5)
            continue
        for ysym in chunk:
            try:
                sub = frame[ysym] if isinstance(frame.columns, pd.MultiIndex) else frame
            except KeyError:
                continue
            sub = sub.dropna(subset=["Close"])
            sub = sub[sub["Close"] > 0]
            if sub.empty:
                continue
            ok += 1
            sym = ymap[ysym]
            prev = sub["Close"].shift(1)
            for ts, row in sub.iterrows():
                vol = row.get("Volume")
                per_day[ts.date()].append({
                    "symbol": sym, "name": meta.at[sym, "name"], "isin": "", "series": meta.at[sym, "series"],
                    "open": row.get("Open"), "high": row.get("High"), "low": row.get("Low"),
                    "close": row["Close"], "prev_close": prev.get(ts), "volume": vol,
                    "value": row["Close"] * vol if pd.notna(vol) else None, "trades": None,
                    "sector": meta.at[sym, "sector"], "market_cap": None,
                })
        print(f"  Yahoo: {min(i + chunk_size, len(ysyms))}/{len(ysyms)} symbols requested, {ok} with data",
              file=sys.stderr)
        time.sleep(pause)

    days = {d: pd.DataFrame(rows, columns=STANDARD_COLUMNS) for d, rows in per_day.items() if d.weekday() < 5}
    return days, ok, errors
