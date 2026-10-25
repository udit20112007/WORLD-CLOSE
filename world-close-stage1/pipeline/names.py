"""Official English company names for exchanges whose own data is in another
language (Shanghai, Shenzhen, Taiwan), taken from Yahoo Finance's screener.

For Taiwan, the exchange's own listed-company data adds English short names
for the many companies Yahoo's screener doesn't carry.

Names are saved in data/<EXCHANGE>/english_names.json and refreshed weekly, or
sooner if many listed stocks are missing (new listings). The site shows the
English name with the original name underneath, and both are searchable.

config:  "english_names": {"yahoo_exchange": "SHH", "etfs": false, "twse_company_info": false}
"""
from __future__ import annotations

import datetime as dt
import json

from . import store

REFRESH_DAYS = 7
MISSING_LIMIT = 0.05


def path(code: str):
    return store.DATA_DIR / code / "english_names.json"


def load(code: str) -> dict[str, str]:
    p = path(code)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("names", {})


def needs_refresh(code: str, symbols: list[str], today: dt.date) -> bool:
    p = path(code)
    if not p.exists():
        return True
    saved = json.loads(p.read_text(encoding="utf-8"))
    updated = dt.date.fromisoformat(saved.get("updated", "2000-01-01"))
    names = saved.get("names", {})
    missing = sum(1 for s in symbols if s not in names) / max(1, len(symbols))
    return (today - updated).days >= REFRESH_DAYS or missing > MISSING_LIMIT


def refresh(code: str, cfg: dict, symbols: list[str], today: dt.date) -> str | None:
    """Update the saved names if due. Returns a note for the status page, or None."""
    spec = cfg.get("english_names")
    if not spec or not needs_refresh(code, symbols, today):
        return None
    from .sources.yahoo_screen import screen_all, strip_suffix
    names = load(code)
    if spec.get("twse_company_info"):
        # Official English short names from the Taiwan Stock Exchange (e.g. "TSMC");
        # fuller Yahoo names below replace them where Yahoo has one
        names.update(twse_english_names())
    quotes = screen_all(spec["yahoo_exchange"])
    if spec.get("etfs"):
        quotes += screen_all(spec["yahoo_exchange"], "ETF")
    for q in quotes:
        name = q.get("longName") or q.get("shortName")
        if name and q.get("symbol"):
            names[strip_suffix(str(q["symbol"]))] = " ".join(str(name).split())
    p = path(code)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"updated": today.isoformat(), "source": "Yahoo Finance", "names": names},
                            ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    found = sum(1 for s in symbols if s in names)
    return f"English names: {found} of {len(symbols)} stocks."


TWSE_COMPANIES = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"


def twse_english_names() -> dict[str, str]:
    """{stock code: English short name} for every TWSE-listed company."""
    from .common import get_bytes, session
    sess = session(referer="https://openapi.twse.com.tw/")
    sess.headers["Accept"] = "application/json"
    rows = json.loads(get_bytes(sess, TWSE_COMPANIES, timeout=60))
    out = {}
    for r in rows:
        code = str(r.get("公司代號", "")).strip()
        name = " ".join(str(r.get("英文簡稱", "")).split())
        if code and name:
            out[code] = name
    return out
