"""B3 (Brasil Bolsa Balcão) from its official COTAHIST historical quotes files.

The daily file COTAHIST_D<DDMMYYYY>.ZIP holds every trade summary for one day;
the annual file COTAHIST_A<YYYY>.ZIP holds the whole year so far, which makes
the history backfill a couple of downloads instead of hundreds. Both are
fixed-width text in B3's published layout. We keep standard-lot shares on the
cash market (TPMERC 010, CODBDI 02) and drop options, forwards and odd lots.

COTAHIST has no previous close, so the pipeline fills it from the prior day.
"""
from __future__ import annotations

import datetime as dt
import io
import zipfile

import pandas as pd

from ..common import STANDARD_COLUMNS, dedupe, get_bytes, session

BASE = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/"

# 0-based slices from B3's "Séries Históricas" layout
F = {
    "tipreg": (0, 2), "date": (2, 10), "codbdi": (10, 12), "symbol": (12, 24), "tpmerc": (24, 27),
    "name": (27, 39), "especi": (39, 49), "open": (56, 69), "high": (69, 82), "low": (82, 95),
    "close": (108, 121), "trades": (147, 152), "volume": (152, 170), "value": (170, 188), "isin": (230, 242),
}
PRICE_FIELDS = ("open", "high", "low", "close", "value")   # two implied decimals

_session = None


def _get(url: str) -> bytes:
    global _session
    if _session is None:
        _session = session(referer="https://www.b3.com.br/")
    return get_bytes(_session, url, retries=4, timeout=300)


def parse_lines(lines, start: dt.date | None = None, end: dt.date | None = None) -> pd.DataFrame:
    rows = []
    for raw in lines:
        line = raw.decode("latin-1") if isinstance(raw, bytes) else raw
        if len(line) < 242 or line[0:2] != "01" or line[24:27] != "010" or line[10:12] != "02":
            continue
        day = dt.date(int(line[2:6]), int(line[6:8]), int(line[8:10]))
        if (start and day < start) or (end and day > end):
            continue
        r = {k: line[a:b].strip() for k, (a, b) in F.items()}
        for k in PRICE_FIELDS:
            r[k] = int(r[k]) / 100
        r["volume"], r["trades"] = int(r["volume"]), int(r["trades"])
        r["series"] = r["especi"].split()[0] if r["especi"] else ""
        r["day"] = day
        rows.append(r)
    return pd.DataFrame(rows)


def _standard(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in STANDARD_COLUMNS:
        if col not in out:
            out[col] = "" if col in ("sector",) else None
    out["prev_close"] = pd.to_numeric(out["prev_close"], errors="coerce")
    return dedupe(out[STANDARD_COLUMNS])


def _read_zip(blob: bytes, start=None, end=None) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = z.namelist()[0]
        with z.open(name) as fh:
            return parse_lines(io.TextIOWrapper(fh, encoding="latin-1"), start, end)


def fetch(day: dt.date, cfg: dict) -> pd.DataFrame:
    df = _read_zip(_get(BASE + f"COTAHIST_D{day:%d%m%Y}.ZIP"))
    if df.empty:
        raise ValueError("file had no standard-lot cash-market shares")
    return _standard(df[df["day"] == day])


def fetch_range(start: dt.date, end: dt.date, cfg: dict) -> dict[dt.date, pd.DataFrame]:
    """Every day from start to end, from the annual files (with previous closes filled in)."""
    frames = [_read_zip(_get(BASE + f"COTAHIST_A{year}.ZIP"), start - dt.timedelta(days=10), end)
              for year in range(start.year, end.year + 1)]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    df = df.sort_values(["symbol", "day"])
    df["prev_close"] = df.groupby("symbol")["close"].shift(1)
    return {d: _standard(g) for d, g in df.groupby("day") if start <= d <= end}
