"""KOSPI and KOSDAQ from the official KRX (Korea Exchange) OpenAPI.

Needs a free API key from https://openapi.krx.co.kr (sign up, request a key,
then apply to use the two daily-trading APIs). Store it as the GitHub secret
KRX_OPENAPI_KEY. Data can be requested for any date, so history backfills
natively.

config "endpoint":  stk_bydd_trd (KOSPI) or ksq_bydd_trd (KOSDAQ).
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pandas as pd

from ..common import NeedsSetup, NotPublished, dedupe, get_bytes, normalize, session

BASE = "https://data-dbg.krx.co.kr/svc/apis/sto/{endpoint}"

COLUMNS = {
    "symbol":     ["ISU_CD", "ISU_SRT_CD"],
    "name":       ["ISU_NM", "ISU_ABBRV"],
    "series":     ["SECT_TP_NM", "MKT_NM"],
    "open":       ["TDD_OPNPRC"],
    "high":       ["TDD_HGPRC"],
    "low":        ["TDD_LWPRC"],
    "close":      ["TDD_CLSPRC"],
    "volume":     ["ACC_TRDVOL"],
    "value":      ["ACC_TRDVAL"],
    "market_cap": ["MKTCAP"],
}

_session = None


def fetch(day: dt.date, cfg: dict) -> pd.DataFrame:
    key = os.environ.get("KRX_OPENAPI_KEY", "").strip()
    if not key:
        raise NeedsSetup("add your free KRX OpenAPI key as the GitHub secret KRX_OPENAPI_KEY (see README)")
    global _session
    if _session is None:
        _session = session()
        _session.headers["AUTH_KEY"] = key
    url = BASE.format(endpoint=cfg.get("krx_endpoint") or cfg["endpoint"]) + f"?basDd={day:%Y%m%d}&AUTH_KEY={key}"
    try:
        blob = get_bytes(_session, url, timeout=60)
    except NotPublished:
        raise NotPublished("no file for that day") from None
    except Exception as exc:
        # Error messages end up on the public status page: never let the key appear in them
        msg = str(exc).replace(key, "***")
        if "401" in msg or "403" in msg:
            raise NeedsSetup("KRX rejected the API key. Check it's approved and that you applied for "
                             f"the {cfg.get('krx_endpoint') or cfg.get('endpoint')} API on openapi.krx.co.kr") from None
        raise RuntimeError(msg) from None
    return parse(json.loads(blob), cfg)


def parse(payload: dict, cfg: dict) -> pd.DataFrame:
    if "OutBlock_1" not in payload:
        msg = payload.get("respMsg") or payload.get("message") or list(payload)[:5]
        raise ValueError(f"Unrecognised KRX response: {msg}")
    rows = payload["OutBlock_1"]
    if not rows:
        raise NotPublished("no trading data for that day")
    raw = pd.DataFrame(rows).astype(str)
    if "CMPPREVDD_PRC" in raw and "TDD_CLSPRC" in raw:
        num = lambda c: pd.to_numeric(raw[c].str.replace(",", ""), errors="coerce")
        raw["_prev"] = (num("TDD_CLSPRC") - num("CMPPREVDD_PRC")).astype(str)
    df = normalize(raw, {**COLUMNS, "prev_close": ["_prev"]})
    df["market_cap"] = df["market_cap"].where(df["market_cap"] > 0)
    df["series"] = df["series"].replace({"": "Stock", "nan": "Stock"})
    return dedupe(df)
