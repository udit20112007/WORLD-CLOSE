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

import pandas as pd

from .common import NeedsSetup, NotPublished, load_config
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


REPEAT_THRESHOLD = 0.9   # share of identical closes+volumes that means "same session as before"
SETTLE_MINUTES = 30      # wait this long after the close before trusting latest-only data


def previous_weekday(day: dt.date) -> dt.date:
    day -= dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def session_day(cfg: dict, now: dt.datetime) -> dt.date | None:
    """The trading day a latest-only source is showing right now, or None while the market is open."""
    day = now.date()
    if day.weekday() >= 5:                       # weekend: Friday's session
        return day - dt.timedelta(days=day.weekday() - 4)
    if cfg.get("open_time"):                     # before the open: still the previous session's close
        oh, om = map(int, cfg["open_time"].split(":"))
        if now.time() < dt.time(oh, om):
            return previous_weekday(day)
    hh, mm = map(int, cfg.get("close_time", "16:00").split(":"))
    settled = (dt.datetime.combine(day, dt.time(hh, mm)) + dt.timedelta(minutes=SETTLE_MINUTES)).time()
    if now.time() < settled:
        return None                              # session still running: prices aren't closes yet
    return day


def is_repeat(new: "pd.DataFrame", old: "pd.DataFrame") -> bool:
    """True if `new` is the same session as `old` (a market holiday repeats the last close)."""
    m = new[["symbol", "close", "volume"]].merge(old[["symbol", "close", "volume"]], on="symbol")
    if len(m) < 0.5 * len(new):
        return False
    same = (m["close_x"].round(4) == m["close_y"].round(4)) & (m["volume_x"] == m["volume_y"])
    return same.mean() >= REPEAT_THRESHOLD


def local_now(tz: str) -> dt.datetime:
    """Current time in an exchange's timezone (a separate function so tests can set the clock)."""
    return dt.datetime.now(ZoneInfo(tz))


def has_history(have: list[dt.date], backfill_days: int) -> bool:
    """True if we already hold most of the trading days a backfill would fetch."""
    start = have[-1] - dt.timedelta(days=backfill_days)
    expected = backfill_days * 5 / 7 * 0.8      # weekdays, allowing for holidays
    return sum(1 for d in have if d >= start) >= expected


def fill_prev_close(code: str, day: dt.date, df: "pd.DataFrame") -> "pd.DataFrame":
    """For sources that don't report a previous close, use our last stored close before `day`."""
    if df["prev_close"].notna().any():
        return df
    earlier = [d for d in store.stored_days(code) if d < day]
    if not earlier:
        return df
    prev = store.load_day(code, earlier[-1]).set_index("symbol")["close"]
    df = df.copy()
    df["prev_close"] = df["symbol"].map(prev)
    return df


def update_latest_only(code: str, cfg: dict, source, backfill_days: int) -> bool:
    now = local_now(cfg["timezone"])
    day = session_day(cfg, now)
    have = store.stored_days(code)
    saved, errors, notes = [], [], []

    if day is None:
        notes.append("Today’s session isn’t finished yet (or hasn’t started); nothing saved.")
    elif day in have:
        notes.append(f"{day} already saved.")
    else:
        try:
            df = source.fetch(day, cfg)
            if len(df) < MIN_ROWS:
                raise ValueError(f"only {len(df)} rows, expected thousands")
            if df.attrs.get("provider"):
                notes.append(f"Prices from {df.attrs['provider']}.")
            reported = df.attrs.get("session_date")   # sources that say which day the prices are for
            if reported and reported != day:
                notes.append(f"The source reports prices for {reported}.")
                day = reported
            prev = store.load_day(code, have[-1]) if have else None
            if day in have:
                notes.append(f"{day} already saved.")
            elif prev is not None and is_repeat(df, prev):
                notes.append(f"Prices are identical to {have[-1]}: market holiday, nothing saved.")
            else:
                store.save_day(code, day, df)
                saved.append(day)
                print(f"[{code}] {day}: saved {len(df)} stocks")
        except NotPublished as exc:
            notes.append(str(exc))
        except NeedsSetup as exc:
            errors.append(f"Needs setup: {exc}")
        except Exception as exc:
            errors.append(f"{day}: {exc}")
            print(f"[{code}] {day}: ERROR {exc}", file=sys.stderr)

    if backfill_days and hasattr(source, "backfill"):
        have = store.stored_days(code)
        if have and has_history(have, backfill_days):
            notes.append(f"Backfill skipped: {len(have)} days already stored.")
        elif have:
            latest = store.load_day(code, have[-1])
            start = have[-1] - dt.timedelta(days=backfill_days)
            print(f"[{code}] backfilling {start} to {have[-1]} from Yahoo for {len(latest)} stocks…")
            days, ok, bf_errors = source.backfill(latest, start, have[-1] - dt.timedelta(days=1), cfg)
            errors.extend(bf_errors[-3:])
            for d, rows in sorted(days.items()):
                existing = store.load_day(code, d)
                if existing is not None:   # keep what we have, add stocks it was missing
                    rows = pd.concat([existing, rows[~rows["symbol"].isin(existing["symbol"])]], ignore_index=True)
                store.save_day(code, d, rows)
            notes.append(f"Backfill: {ok} of {len(latest)} stocks returned history, {len(days)} days written.")
            print(f"[{code}] {notes[-1]}")
        else:
            errors.append("Backfill skipped: no current day saved yet to take the stock list from.")

    if hasattr(source, "repair"):
        try:
            notes.extend(source.repair(code, cfg, store))
        except Exception as exc:
            notes.append(f"Couldn't fill in missing volumes this time ({str(exc)[:120]}).")

    for n in notes:
        print(f"[{code}] {n}")
    have = store.stored_days(code)
    fields = {"last_attempt": now_utc(), "new_days": len(saved), "errors": errors[-6:], "notes": notes[-4:]}
    if saved:
        fields["last_success"] = now_utc()
    if have:
        fields["last_trading_day"] = have[-1].isoformat()
        fields["days_stored"] = len(have)
    store.write_status(code, **fields)
    return not errors or bool(saved)


def update_exchange(code: str, cfg: dict, backfill_days: int) -> bool:
    ok = _update_exchange(code, cfg, backfill_days)
    if cfg.get("english_names"):
        refresh_names(code, cfg)
    return ok


def refresh_names(code: str, cfg: dict) -> None:
    from . import names
    have = store.stored_days(code)
    if not have:
        return
    symbols = list(store.load_day(code, have[-1])["symbol"])
    try:
        note = names.refresh(code, cfg, symbols, local_now(cfg["timezone"]).date())
    except Exception as exc:
        note = f"English names: couldn't refresh this time ({str(exc)[:160]})."
    if note:
        print(f"[{code}] {note}")
        status = store.read_status(code)
        store.write_status(code, notes=(status.get("notes") or [])[-3:] + [note])


def _update_exchange(code: str, cfg: dict, backfill_days: int) -> bool:
    source = SOURCES[cfg["source"]]
    if getattr(source, "LATEST_ONLY", False):
        return update_latest_only(code, cfg, source, backfill_days)
    today = local_now(cfg["timezone"]).date()
    have = set(store.stored_days(code))
    days = candidate_days(have, today, backfill_days)
    print(f"[{code}] checking {len(days)} day(s): {days[0] if days else '-'} to {days[-1] if days else '-'}")

    saved, errors, notes, streak = [], [], [], 0

    # Sources that can download a whole range at once (e.g. B3's annual file) backfill that way
    if backfill_days and hasattr(source, "fetch_range") and days:
        try:
            ranged = source.fetch_range(days[0], days[-1], cfg)
            for day in sorted(d for d in ranged if d in set(days) and len(ranged[d]) >= MIN_ROWS):
                store.save_day(code, day, fill_prev_close(code, day, ranged[day]))
                saved.append(day)
            notes.append(f"Backfill: {len(saved)} days from the full-range download.")
            print(f"[{code}] {notes[-1]}")
            days = [d for d in days if d not in set(saved)][-5:]   # still try the latest few one by one
        except NeedsSetup as exc:
            errors.append(f"Needs setup: {exc}")
            days = []
        except Exception as exc:
            errors.append(f"Range download failed ({exc}); trying day by day.")

    for day in days:
        try:
            df = source.fetch(day, cfg)
            if len(df) < MIN_ROWS:
                raise ValueError(f"only {len(df)} rows, expected thousands")
        except NotPublished:
            streak = 0
            continue
        except NeedsSetup as exc:
            errors.append(f"Needs setup: {exc}")
            break
        except Exception as exc:
            errors.append(f"{day}: {exc}")
            print(f"[{code}] {day}: ERROR {exc}", file=sys.stderr)
            streak += 1
            if streak >= MAX_CONSECUTIVE_ERRORS:
                errors.append(f"Stopped after {streak} failures in a row.")
                break
            continue
        streak = 0
        store.save_day(code, day, fill_prev_close(code, day, df))
        saved.append(day)
        print(f"[{code}] {day}: saved {len(df)} stocks")
        time.sleep(1.0 if backfill_days else 0.3)

    have = store.stored_days(code)
    fields = {"last_attempt": now_utc(), "new_days": len(saved), "errors": errors[-6:], "notes": notes[-4:]}
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
