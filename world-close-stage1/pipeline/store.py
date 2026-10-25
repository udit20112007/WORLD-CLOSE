"""Daily snapshots live in the repository, so history builds up over time:

    data/<EXCHANGE>/<YYYY>/<YYYY-MM-DD>.csv.gz   one file per trading day
    data/<EXCHANGE>/status.json                  last attempt, success, errors
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd

from .common import ROOT, STANDARD_COLUMNS

DATA_DIR = Path(os.environ.get("WC_DATA_DIR", ROOT / "data"))


def day_file(exchange: str, day: dt.date) -> Path:
    return DATA_DIR / exchange / f"{day:%Y}" / f"{day:%Y-%m-%d}.csv.gz"


def save_day(exchange: str, day: dt.date, df: pd.DataFrame) -> Path:
    path = day_file(exchange, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps the gzip bytes identical for identical data (cleaner git history)
    df[STANDARD_COLUMNS].to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
    return path


def stored_days(exchange: str) -> list[dt.date]:
    base = DATA_DIR / exchange
    if not base.exists():
        return []
    days = []
    for p in base.glob("*/*.csv.gz"):
        try:
            days.append(dt.date.fromisoformat(p.name[:10]))
        except ValueError:
            pass
    return sorted(days)


TEXT_COLUMNS = ("symbol", "name", "isin", "series", "sector", "currency")


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={c: str for c in TEXT_COLUMNS}, keep_default_na=False,
                     na_values={c: [""] for c in STANDARD_COLUMNS if c not in TEXT_COLUMNS})
    for col in STANDARD_COLUMNS:  # files saved before a column existed
        if col not in df.columns:
            df[col] = "" if col in TEXT_COLUMNS else float("nan")
    return df[STANDARD_COLUMNS]


def load_day(exchange: str, day: dt.date) -> pd.DataFrame | None:
    path = day_file(exchange, day)
    return _read(path) if path.exists() else None


def load_days(exchange: str, since: dt.date) -> pd.DataFrame:
    """All stored rows from `since` onward, with a `date` column."""
    frames = []
    for day in stored_days(exchange):
        if day < since:
            continue
        df = _read(day_file(exchange, day))
        df["date"] = pd.Timestamp(day)
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=STANDARD_COLUMNS + ["date"])
    return pd.concat(frames, ignore_index=True)


def status_file(exchange: str) -> Path:
    return DATA_DIR / exchange / "status.json"


def read_status(exchange: str) -> dict:
    path = status_file(exchange)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def write_status(exchange: str, **fields) -> None:
    status = read_status(exchange)
    status.update(fields)
    path = status_file(exchange)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

