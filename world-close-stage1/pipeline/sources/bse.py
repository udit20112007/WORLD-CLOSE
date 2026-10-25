"""BSE (Bombay Stock Exchange) daily equity bhavcopy, UDiFF format.

BSE uses the same common column layout as NSE. TckrSymb is BSE's scrip id
(e.g. RELIANCE); the numeric scrip code is in FinInstrmId. SctySrs holds the
BSE group (A, B, T, X, Z, M, ...).
"""
from __future__ import annotations

import datetime as dt

from ..common import dedupe, get_bytes, normalize, read_csv_maybe_zipped, session, stocks_only

URL = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"

COLUMNS = {
    "symbol":     ["TckrSymb", "SC_NAME"],
    "name":       ["FinInstrmNm", "SC_NAME"],
    "isin":       ["ISIN", "ISIN_CODE"],
    "series":     ["SctySrs", "SC_GROUP"],
    "open":       ["OpnPric", "OPEN"],
    "high":       ["HghPric", "HIGH"],
    "low":        ["LwPric", "LOW"],
    "close":      ["ClsPric", "CLOSE"],
    "prev_close": ["PrvsClsgPric", "PREVCLOSE"],
    "volume":     ["TtlTradgVol", "NO_OF_SHRS"],
    "value":      ["TtlTrfVal", "NET_TURNOV"],
    "trades":     ["TtlNbOfTxsExctd", "NO_TRADES"],
}

_session = None


def fetch(day: dt.date, cfg: dict):
    global _session
    if _session is None:
        _session = session(referer="https://www.bseindia.com/")
    raw = read_csv_maybe_zipped(get_bytes(_session, URL.format(d=day)))
    return parse(raw, cfg)


def parse(raw, cfg: dict):
    df = normalize(stocks_only(raw), COLUMNS)
    excluded = {s.upper() for s in cfg.get("exclude_series") or []}
    if excluded:
        df = df[~df["series"].str.upper().isin(excluded)]
    return dedupe(df)
