"""Random demo snapshots so the site can be previewed without downloading.

Writes into store.DATA_DIR, so set WC_DATA_DIR to a temporary folder to keep
fake data out of the real data/ directory.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import store
from .common import STANDARD_COLUMNS

SECTORS = ["Textiles", "Power", "Pharma", "Finance", "Steel", "Chemicals", "Software", "Cement",
           "Foods", "Auto Parts", "Realty", "Logistics", "Media", "Agro", "Engineering"]


def _universe(n: int, prefix: str, rng, start: int = 0):
    out = []
    for i in range(start, start + n):
        out.append({
            "symbol": f"{prefix}{i:04d}",
            "name": f"Demo {SECTORS[i % len(SECTORS)]} {i:04d}",
            "isin": f"INDEMO{i:06d}",
            "price": float(rng.lognormal(5.0, 1.3)),
            "liq": float(rng.lognormal(0, 1.5)),
        })
    return out


def make_demo(days: int = 260) -> None:
    rng = np.random.default_rng(11)
    end = dt.date.today()
    trading = [d.date() for d in pd.bdate_range(end=end - dt.timedelta(days=(end.weekday() - 4) if end.weekday() > 4 else 0),
                                                 periods=days)]
    shared = _universe(2000, "DEMO", rng)
    plans = {
        "NSE": (shared + _universe(350, "DEMO", rng, start=2000), ["EQ"] * 2300 + ["BE"] * 50, 0.98),
        "BSE": (shared + _universe(2500, "BDEMO", rng, start=5000), ["A", "B", "T", "X", "Z"], 0.70),
    }
    for code, (stocks, series, trade_prob) in plans.items():
        prices = np.array([s["price"] for s in stocks])
        last_close = prices.copy()
        for d in trading:
            rets = rng.normal(0.0004, 0.022, len(stocks))
            close = np.round(last_close * np.exp(rets), 2)
            traded = rng.random(len(stocks)) < trade_prob
            vol = np.array([int(rng.lognormal(10, 1.4) * s["liq"]) + 1 for s in stocks])
            rows = []
            for i, s in enumerate(stocks):
                if not traded[i]:
                    continue
                hi = close[i] * (1 + abs(rng.normal(0, 0.01)))
                lo = close[i] * (1 - abs(rng.normal(0, 0.01)))
                rows.append([s["symbol"], s["name"], s["isin"], series[i % len(series)],
                             round(float(last_close[i]), 2), round(hi, 2), round(lo, 2), float(close[i]),
                             round(float(last_close[i]), 2), int(vol[i]), round(float(vol[i] * close[i]), 2),
                             int(vol[i] / 40) + 1])
                last_close[i] = close[i]
            store.save_day(code, d, pd.DataFrame(rows, columns=STANDARD_COLUMNS))
        store.write_status(code, last_attempt=f"{trading[-1]}T14:00:00Z", last_success=f"{trading[-1]}T14:00:00Z",
                           new_days=1, errors=[], last_trading_day=trading[-1].isoformat(),
                           days_stored=len(trading))
        print(f"[{code}] demo: {len(stocks)} stocks over {len(trading)} days")


US_SECTORS = ["Technology", "Health Care", "Finance", "Consumer Discretionary", "Industrials", "Energy",
              "Real Estate", "Utilities", "Telecommunications", "Basic Materials", "Consumer Staples"]
US_TYPES = ["Common"] * 14 + ["ADR", "Preferred", "Warrant", "Unit"]


def make_demo_us(days: int = 260, counts=None) -> None:
    """Demo snapshots for the US exchanges, with sectors and market caps."""
    counts = counts or {"NASDAQ": 3300, "NYSE": 2400, "NYSEAM": 280}
    rng = np.random.default_rng(23)
    end = dt.date.today()
    last_friday = end - dt.timedelta(days=(end.weekday() - 4) % 7)
    trading = [d.date() for d in pd.bdate_range(end=last_friday, periods=days)]
    offset = 0
    for code, n in counts.items():
        stocks = []
        for i in range(offset, offset + n):
            sector = US_SECTORS[i % len(US_SECTORS)]
            kind = US_TYPES[i % len(US_TYPES)]
            price = float(rng.lognormal(3.3, 1.2)) if kind != "Warrant" else float(rng.uniform(0.01, 1.5))
            shares = float(rng.lognormal(18, 1.6))
            stocks.append({"symbol": f"DM{i:04d}", "name": f"Demo {sector} {i:04d}", "sector": sector,
                           "series": kind, "price": price, "shares": shares})
        offset += n
        last = np.array([s["price"] for s in stocks])
        for d in trading:
            close = np.round(last * np.exp(rng.normal(0.0004, 0.021, n)), 4)
            rows = []
            for i, s in enumerate(stocks):
                vol = int(rng.lognormal(12, 1.6))
                rows.append([s["symbol"], s["name"], "", s["series"], None, None, None, float(close[i]),
                             float(last[i]), vol, round(float(close[i]) * vol, 0), None, s["sector"],
                             round(float(close[i]) * s["shares"], 0) if s["series"] in ("Common", "ADR") else None])
            last = close
            store.save_day(code, d, pd.DataFrame(rows, columns=STANDARD_COLUMNS))
        store.write_status(code, last_attempt=f"{trading[-1]}T23:00:00Z", last_success=f"{trading[-1]}T23:00:00Z",
                           new_days=1, errors=[], notes=[], last_trading_day=trading[-1].isoformat(),
                           days_stored=len(trading))
        print(f"[{code}] demo: {n} stocks over {len(trading)} days")
