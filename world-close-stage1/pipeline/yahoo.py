"""Best-effort history backfill from Yahoo Finance, shared by sources whose
own feed only covers the latest session (US, China, Hong Kong, Taiwan).
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from collections import defaultdict
from typing import Callable, Iterable

import pandas as pd

from .common import STANDARD_COLUMNS


def backfill(latest: pd.DataFrame, start: dt.date, end: dt.date, to_yahoo: Callable[[str], str],
             series: Iterable[str] | None = None, chunk_size: int = 100, pause: float = 2.0,
             volume_factor: float = 1.0) -> tuple[dict[dt.date, pd.DataFrame], int, list[str]]:
    """Download daily closes for the stocks in `latest` between start and end.

    latest     today's rows (symbol, name, series, sector are copied onto history rows)
    to_yahoo   maps an exchange symbol to Yahoo's, e.g. 600519 -> 600519.SS
    series     only request stocks whose series is in this set (None = all)
    Returns ({day: rows}, number of stocks that returned data, errors).
    """
    import yfinance as yf

    meta = latest.set_index("symbol")
    wanted = [s for s in meta.index if series is None or meta.at[s, "series"] in set(series)]
    ymap = {to_yahoo(s): s for s in wanted}
    ysyms = list(ymap)
    per_day: dict[dt.date, list] = defaultdict(list)
    ok, errors = 0, []

    for i in range(0, len(ysyms), chunk_size):
        chunk = ysyms[i:i + chunk_size]
        n = i // chunk_size + 1
        try:
            frame = yf.download(chunk, start=start.isoformat(), end=(end + dt.timedelta(days=1)).isoformat(),
                                interval="1d", auto_adjust=False, group_by="ticker", threads=True,
                                progress=False, timeout=30)
        except Exception as exc:
            errors.append(f"Yahoo chunk {n}: {exc}")
            time.sleep(pause * 5)
            continue
        if frame is None or frame.empty:
            errors.append(f"Yahoo chunk {n}: no data returned")
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
                vol = vol * volume_factor if pd.notna(vol) else None
                per_day[ts.date()].append({
                    "symbol": sym, "name": meta.at[sym, "name"], "isin": meta.at[sym, "isin"] or "",
                    "series": meta.at[sym, "series"], "open": row.get("Open"), "high": row.get("High"),
                    "low": row.get("Low"), "close": row["Close"], "prev_close": prev.get(ts), "volume": vol,
                    "value": row["Close"] * vol if vol is not None else None, "trades": None,
                    "sector": meta.at[sym, "sector"], "market_cap": None,
                    "currency": meta.at[sym, "currency"] if "currency" in meta else "",
                })
        print(f"  Yahoo: {min(i + chunk_size, len(ysyms))}/{len(ysyms)} requested, {ok} with data", file=sys.stderr)
        time.sleep(pause)

    days = {d: pd.DataFrame(rows, columns=STANDARD_COLUMNS) for d, rows in per_day.items() if d.weekday() < 5}
    return days, ok, errors
