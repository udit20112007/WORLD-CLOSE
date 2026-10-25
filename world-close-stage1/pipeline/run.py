"""Command line entry point.

    python -m pipeline.run update --exchanges NSE BSE          # new trading days since last run
    python -m pipeline.run update --exchanges NSE BSE --backfill-days 370
    python -m pipeline.run build                               # write site/data from stored days
    python -m pipeline.run demo                                # fake data for previews (needs WC_DATA_DIR)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from zoneinfo import ZoneInfo

from .common import NotPublished, load_config
from .sources import SOURCES
from . import store

MIN_ROWS = 50            # a real exchange file has far more rows; fewer means something broke
MAX_CONSECUTIVE_ERRORS = 5
FIRST_RUN_LOOKBACK = 7   # days to look back when nothing is stored yet


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def candidate_days(have: set[dt.date], today: dt.date, backfill_days: int) -> list[dt.date]:
    if backfill_days:
        start = today - dt.timedelta(days=backfill_days)
    elif have:
        start = max(have) + dt.timedelta(days=1)
    else:
        start = today - dt.timedelta(days=FIRST_RUN_LOOKBACK)
    days, d = [], start
    while d <= today:
        if d.weekday() < 5 and d not in have:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def update_exchange(code: str, cfg: dict, backfill_days: int) -> bool:
    source = SOURCES[cfg["source"]]
    today = dt.datetime.now(ZoneInfo(cfg["timezone"])).date()
    days = candidate_days(set(store.stored_days(code)), today, backfill_days)
    print(f"[{code}] checking {len(days)} day(s): {days[0] if days else '-'} to {days[-1] if days else '-'}")

    saved, errors, streak = [], [], 0
    for day in days:
        try:
            df = source.fetch(day, cfg)
            if len(df) < MIN_ROWS:
                raise ValueError(f"only {len(df)} rows, expected thousands")
        except NotPublished:
            streak = 0
            continue
        except Exception as exc:
            errors.append(f"{day}: {exc}")
            print(f"[{code}] {day}: ERROR {exc}", file=sys.stderr)
            streak += 1
            if streak >= MAX_CONSECUTIVE_ERRORS:
                errors.append(f"Stopped after {streak} failures in a row.")
                break
            continue
        streak = 0
        store.save_day(code, day, df)
        saved.append(day)
        print(f"[{code}] {day}: saved {len(df)} stocks")
        time.sleep(1.0 if backfill_days else 0.3)

    have = store.stored_days(code)
    fields = {"last_attempt": now_utc(), "new_days": len(saved), "errors": errors[-6:]}
    if saved:
        fields["last_success"] = now_utc()
    if have:
        fields["last_trading_day"] = have[-1].isoformat()
        fields["days_stored"] = len(have)
    store.write_status(code, **fields)
    return bool(saved) or not errors


def cmd_update(args) -> int:
    cfg = load_config()
    results = {}
    for code in args.exchanges:
        if code not in cfg:
            print(f"Unknown exchange {code}; known: {', '.join(cfg)}", file=sys.stderr)
            return 2
        results[code] = update_exchange(code, cfg[code], args.backfill_days)
    print("Result:", ", ".join(f"{k} {'ok' if v else 'FAILED'}" for k, v in results.items()))
    return 0 if any(results.values()) else 1


def cmd_build(args) -> int:
    from .build_site import build
    build()
    return 0


def cmd_demo(args) -> int:
    from .demo import make_demo
    make_demo(args.days)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="pipeline.run")
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update", help="download new trading days")
    u.add_argument("--exchanges", nargs="+", required=True)
    u.add_argument("--backfill-days", type=int, default=0,
                   help="also fetch missing days this far back (use 370 on the first run)")
    u.set_defaults(func=cmd_update)
    b = sub.add_parser("build", help="write site/data from stored days")
    b.set_defaults(func=cmd_build)
    d = sub.add_parser("demo", help="write random demo snapshots (set WC_DATA_DIR to keep them out of data/)")
    d.add_argument("--days", type=int, default=260)
    d.set_defaults(func=cmd_demo)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
