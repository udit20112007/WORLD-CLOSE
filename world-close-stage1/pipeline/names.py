"""Official English company names for exchanges whose own data is in another
language (Shanghai, Shenzhen, Taiwan), taken from Yahoo Finance's screener.

Names are saved in data/<EXCHANGE>/english_names.json and refreshed weekly, or
sooner if many listed stocks are missing (new listings). The site shows the
English name with the original name underneath, and both are searchable.

config:  "english_names": {"yahoo_exchange": "SHH", "etfs": false}
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
    quotes = screen_all(spec["yahoo_exchange"])
    if spec.get("etfs"):
        quotes += screen_all(spec["yahoo_exchange"], "ETF")
    names = load(code)
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
