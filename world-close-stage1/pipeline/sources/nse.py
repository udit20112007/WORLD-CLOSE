"""NSE (National Stock Exchange of India) daily bhavcopy.

Since July 2024 NSE publishes the cash-market bhavcopy in the common
"UDiFF" format, one zipped CSV per trading day covering every traded stock.
The older format's column names are also accepted, in case NSE changes again.
"""
from __future__ import annotations

import datetime as dt

from ..common import dedupe, get_bytes, normalize, read_csv_maybe_zipped, session, stocks_only

URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"

COLUMNS = {
    "symbol":     ["TckrSymb", "SYMBOL"],
    "name":       ["FinInstrmNm", "NAME OF COMPANY"],
    "isin":       ["ISIN"],
    "series":     ["SctySrs", "SERIES"],
    "open":       ["OpnPric", "OPEN"],
    "high":       ["HghPric", "HIGH"],
    "low":        ["LwPric", "LOW"],
    "close":      ["ClsPric", "CLOSE"],
    "prev_close": ["PrvsClsgPric", "PREVCLOSE"],
    "volume":     ["TtlTradgVol", "TOTTRDQTY"],
    "value":      ["TtlTrfVal", "TOTTRDVAL"],
    "trades":     ["TtlNbOfTxsExctd", "TOTALTRADES"],
    "_type":      ["FinInstrmTp"],
}

_session = None


def fetch(day: dt.date, cfg: dict):
    global _session
    if _session is None:
        _session = session(referer="https://www.nseindia.com/")
    raw = read_csv_maybe_zipped(get_bytes(_session, URL.format(d=day)))
    return parse(raw, cfg)


def parse(raw, cfg: dict):
    cols = {k: v for k, v in COLUMNS.items() if not k.startswith("_")}
    df = normalize(stocks_only(raw), cols)
    allowed = {s.upper() for s in cfg.get("series") or []}
    if allowed:
        df = df[df["series"].str.upper().isin(allowed)]
    return dedupe(df)
