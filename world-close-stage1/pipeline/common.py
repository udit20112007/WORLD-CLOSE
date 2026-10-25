"""Shared pieces every exchange source uses.

Every source returns a pandas DataFrame in the STANDARD schema below, one row
per stock for one trading day. Everything after that (storage, site build) is
exchange-agnostic, so adding an exchange only means writing one parser.
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config" / "exchanges.json"

STANDARD_COLUMNS = [
    "symbol",      # exchange ticker, e.g. RELIANCE
    "name",        # company name
    "isin",        # international id, links the same company across exchanges
    "series",      # exchange-specific series or group (EQ, BE, A, B, ...)
    "open", "high", "low", "close",
    "prev_close",  # exchange's own previous close (correct even for illiquid stocks)
    "volume",      # shares traded
    "value",       # traded value in the exchange currency
    "trades",      # number of trades (if the exchange reports it)
    "sector",      # industry sector (if the source reports it)
    "market_cap",  # market capitalisation in the exchange currency (if reported)
]
NUMERIC = ["open", "high", "low", "close", "prev_close", "volume", "value", "trades", "market_cap"]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class NotPublished(Exception):
    """No file for that date: a holiday, a weekend, or not published yet."""


def load_config() -> dict:
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def session(referer: str | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    if referer:
        s.headers["Referer"] = referer
    return s


def get_bytes(sess: requests.Session, url: str, retries: int = 3, timeout: int = 30) -> bytes:
    """GET a URL. 404 means "no file for this day" and raises NotPublished."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = sess.get(url, timeout=timeout)
            if r.status_code == 404:
                raise NotPublished(url)
            r.raise_for_status()
            # Some sites return an HTML error page with status 200
            if r.content[:15].lower().startswith((b"<!doctype", b"<html")):
                raise NotPublished(f"{url} returned a web page instead of a data file")
            return r.content
        except NotPublished:
            raise
        except Exception as exc:  # timeouts, 403s, connection resets
            last_exc = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Download failed after {retries} tries: {url} ({last_exc})")


def read_csv_maybe_zipped(blob: bytes) -> pd.DataFrame:
    if blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            blob = z.read(name)
    return pd.read_csv(io.BytesIO(blob), dtype=str, keep_default_na=False)


def normalize(raw: pd.DataFrame, colmap: dict[str, list[str]]) -> pd.DataFrame:
    """Rename columns to the standard schema.

    colmap maps each standard column to the possible source column names, so
    the parser keeps working if an exchange renames or reorders columns.
    """
    lookup = {c.strip().lower(): c for c in raw.columns}
    out = pd.DataFrame(index=raw.index)
    for std, candidates in colmap.items():
        for cand in candidates:
            if cand.lower() in lookup:
                out[std] = raw[lookup[cand.lower()]].astype(str).str.strip()
                break
    required = {"symbol", "close"}
    if not required <= set(out.columns):
        raise ValueError(
            f"Unrecognised file format: could not find {sorted(required - set(out.columns))}. "
            f"Columns were: {list(raw.columns)[:20]}"
        )
    for col in STANDARD_COLUMNS:
        if col not in out.columns:
            out[col] = "" if col not in NUMERIC else None
    for col in NUMERIC:
        if not pd.api.types.is_numeric_dtype(out[col]):  # "$1,234.50", "1.2%" -> 1234.5, 1.2
            out[col] = out[col].astype(str).str.replace(r"[$,%\s]", "", regex=True)
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out[out["symbol"].ne("") & out["close"].gt(0)]
    if out["name"].eq("").all():
        out["name"] = out["symbol"]
    return out[STANDARD_COLUMNS].reset_index(drop=True)


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """One row per symbol, keeping the most traded line if a stock appears twice."""
    return (df.sort_values("volume", ascending=False, na_position="last")
              .drop_duplicates("symbol", keep="first")
              .sort_values("symbol")
              .reset_index(drop=True))


def stocks_only(raw: pd.DataFrame) -> pd.DataFrame:
    """In UDiFF files, keep rows whose instrument type is STK (equity shares)."""
    lookup = {c.strip().lower(): c for c in raw.columns}
    col = lookup.get("fininstrmtp")
    if col is None:
        return raw
    return raw[raw[col].astype(str).str.strip().str.upper().eq("STK")]
