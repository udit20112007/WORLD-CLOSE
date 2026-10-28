"""Turn stored daily snapshots into the small JSON files the website loads.

    site/data/exchanges.json              list of exchanges, counts, status
    site/data/<EX>/summary.json           every stock's latest close (loaded when you pick the exchange)
    site/data/<EX>/hist/<n>.json          1-year closes, ~150 stocks per file (loaded when you open a stock)
"""
from __future__ import annotations

import datetime as dt
import json
import math
import shutil
from collections import defaultdict

import pandas as pd

from .common import ROOT, load_config
from . import store

SITE_DATA = ROOT / "site" / "data"
BUCKET_SIZE = 150
STALE_AFTER_DAYS = 30   # a stock not traded for this long is dropped from the list
HISTORY_DAYS = 370

SUMMARY_FIELDS = ["symbol", "name", "isin", "series", "close", "prev_close", "change_pct",
                  "high_52w", "low_52w", "volume", "value", "days_ago", "bucket", "also",
                  "sector", "market_cap", "local_name", "currency"]


def _num(v, digits=2):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    v = float(v)
    if digits == 2 and abs(v) < 1:       # prices under 1 (penny stocks) keep 4 decimals
        return round(v, 4)
    return round(v, digits)


def _latest_rows(code: str):
    days = store.stored_days(code)
    if not days:
        return None, None, None
    latest = days[-1]
    df = store.load_days(code, latest - dt.timedelta(days=HISTORY_DAYS))
    recent = df[df["date"] >= pd.Timestamp(latest - dt.timedelta(days=STALE_AFTER_DAYS))]
    last = recent.sort_values("date").groupby("symbol", as_index=False).tail(1).copy()

    year = df[df["date"] >= pd.Timestamp(latest - dt.timedelta(days=365))].copy()
    year["hi"] = year["high"].fillna(year["close"])
    year["lo"] = year["low"].fillna(year["close"])
    hl = year.groupby("symbol").agg(high_52w=("hi", "max"), low_52w=("lo", "min"))
    last = last.join(hl, on="symbol")

    prev = last["prev_close"].where(last["prev_close"] > 0)
    last["change_pct"] = (last["close"] / prev - 1) * 100
    last["days_ago"] = (pd.Timestamp(latest) - last["date"]).dt.days
    last["sector"] = last["sector"].fillna("").astype(str)
    last["currency"] = last["currency"].fillna("").astype(str)
    last["isin"] = last["isin"].fillna("").astype(str)
    last["series"] = last["series"].fillna("").astype(str)
    last = last.sort_values("symbol").reset_index(drop=True)
    last["bucket"] = last.index // BUCKET_SIZE
    return latest, last, df


def build() -> None:
    cfg = load_config()
    if SITE_DATA.exists():
        shutil.rmtree(SITE_DATA)
    SITE_DATA.mkdir(parents=True)

    built = {}
    for code, c in cfg.items():
        if c.get("enabled"):
            built[code] = _latest_rows(code)

    # On exchanges where Yahoo's screener also lists certificates, warrants, notes, bonds and
    # foreign shares (Euronext, London, Xetra), show only listings that have a market cap.
    # Chart-history days carry no market cap, so use any day in the stored window.
    for code, c in cfg.items():
        if c.get("require_market_cap") and code in built and built[code][1] is not None:
            latest, last, history = built[code]
            capped = set(history.loc[pd.to_numeric(history["market_cap"], errors="coerce") > 0, "symbol"])
            if capped:
                kept = last[last["symbol"].isin(capped)].reset_index(drop=True)
                kept["bucket"] = kept.index // BUCKET_SIZE
                built[code] = (latest, kept, history)
                print(f"[{code}] showing {len(kept)} listings with a market cap, left out {len(last) - len(kept)}")

    # Home-market rules for exchanges that also carry many foreign shares (London, Xetra):
    #   drop_symbol_pattern  e.g. London's international order book codes (0ABC.L)
    #   home_currencies      keep listings quoted in these currencies (London: GBp, GBP)
    #   home_name_pattern    keep names with a home legal form (Xetra: AG, SE, KGaA, GmbH)
    for code, c in cfg.items():
        rules = [k for k in ("drop_symbol_pattern", "home_currencies", "home_name_pattern") if c.get(k)]
        if not rules or code not in built or built[code][1] is None:
            continue
        latest, last, history = built[code]
        keep = pd.Series(True, index=last.index)
        if c.get("drop_symbol_pattern"):
            keep &= ~last["symbol"].astype(str).str.contains(c["drop_symbol_pattern"], regex=True)
        if c.get("home_currencies"):
            cur = last["currency"].fillna("").astype(str).replace("", c["currency"])
            keep &= cur.isin(c["home_currencies"])
        if c.get("home_name_pattern"):
            keep &= last["name"].fillna("").astype(str).str.contains(c["home_name_pattern"], case=False, regex=True)
        kept = last[keep].reset_index(drop=True)
        kept["bucket"] = kept.index // BUCKET_SIZE
        built[code] = (latest, kept, history)
        print(f"[{code}] home-market rules ({', '.join(rules)}): kept {len(kept)}, left out {len(last) - len(kept)}")

    # Leave out foreign companies' shares on exchanges with an international market (Mexico's SIC)
    for code, c in cfg.items():
        if c.get("drop_foreign_listings") and code in built and built[code][1] is not None:
            from .foreign import foreign_listings, normalise
            latest, last, history = built[code]
            other_names = {normalise(n) for k, (_, l, _) in built.items() if k != code and l is not None
                           for n in l["name"] if n}
            us = {str(s).replace("/", "-") for k in ("NYSE", "NASDAQ", "NYSEAM") if k in built and built[k][1] is not None
                  for s in built[k][1]["symbol"]}
            mask = foreign_listings(last, other_names, us)
            kept = last[~mask].reset_index(drop=True)
            kept["bucket"] = kept.index // BUCKET_SIZE
            built[code] = (latest, kept, history)
            print(f"[{code}] left out {int(mask.sum())} foreign listings, kept {len(kept)}")

    # Which exchanges each ISIN trades on, to show "also listed on"
    isin_map: dict[str, set[str]] = defaultdict(set)
    for code, (latest, last, _) in built.items():
        if last is not None:
            for isin in last["isin"]:
                if isin:
                    isin_map[isin].add(code)

    index = {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "exchanges": []}

    for code, (latest, last, history) in built.items():
        c = cfg[code]
        status = store.read_status(code)
        entry = {"code": code, **{k: c[k] for k in ("name", "short", "country", "city", "region", "currency")},
                 "series_label": c.get("series_label", "Series"), "note": c.get("note"),
                 "status": status, "available": last is not None}
        if last is None:
            index["exchanges"].append(entry)
            continue

        out_dir = SITE_DATA / code
        (out_dir / "hist").mkdir(parents=True)

        from .names import load as load_names
        english = load_names(code) if c.get("english_names") else {}
        rows = []
        for r in last.itertuples(index=False):
            local = None
            name = r.name
            if english.get(r.symbol) and english[r.symbol] != r.name:
                name, local = english[r.symbol], r.name
            also = sorted(isin_map.get(r.isin, set()) - {code}) if r.isin else []
            rows.append([r.symbol, name, r.isin, r.series, _num(r.close), _num(r.prev_close),
                         _num(r.change_pct, 3), _num(r.high_52w), _num(r.low_52w),
                         None if pd.isna(r.volume) else int(r.volume), _num(r.value, 0),
                         int(r.days_ago), int(r.bucket), also,
                         r.sector or None, _num(r.market_cap, 0), local,
                         (r.currency if r.currency and r.currency != c["currency"] else None)])
        today_rows = last[last["days_ago"] == 0]
        breadth = {
            "up": int((today_rows["change_pct"] > 0).sum()),
            "down": int((today_rows["change_pct"] < 0).sum()),
            "flat": int((today_rows["change_pct"] == 0).sum()),
        }
        summary = {"code": code, "as_of": latest.isoformat(), "currency": c["currency"],
                   "fields": SUMMARY_FIELDS, "rows": rows, "breadth": breadth}
        (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
                                              encoding="utf-8")

        # History buckets
        t0 = history["date"].min()
        hist = history[history["symbol"].isin(last["symbol"])][["symbol", "date", "close"]]
        hist = hist.dropna().sort_values("date")
        bucket_of = dict(zip(last["symbol"], last["bucket"]))
        buckets: dict[int, dict] = defaultdict(dict)
        for sym, g in hist.groupby("symbol"):
            buckets[bucket_of[sym]][sym] = {
                "d": [int((d - t0).days) for d in g["date"]],
                "c": [_num(v) for v in g["close"]],
            }
        for b, series in buckets.items():
            (out_dir / "hist" / f"{b}.json").write_text(
                json.dumps({"t0": t0.strftime("%Y-%m-%d"), "series": series}, separators=(",", ":")),
                encoding="utf-8")

        entry.update({"as_of": latest.isoformat(), "count": len(rows), "traded_today": len(today_rows),
                      "breadth": breadth})
        index["exchanges"].append(entry)
        print(f"[{code}] {len(rows)} stocks as of {latest}, {len(buckets)} history files")

    (SITE_DATA / "exchanges.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
