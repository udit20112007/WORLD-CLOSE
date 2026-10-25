"""Registry of exchange data sources.

Each source module exposes:
    fetch(day: datetime.date, cfg: dict) -> pandas.DataFrame   (standard schema)
and raises common.NotPublished when there is no file for that day.

Sources with LATEST_ONLY = True can only return the most recent session; the
pipeline calls them once per run. They may also offer
    backfill(latest_rows, start, end) -> ({day: DataFrame}, symbols_ok, errors)
to fill in past days from another source.
"""
from . import bse, nasdaq, nse

SOURCES = {
    "nse": nse,
    "bse": bse,
    "nasdaq_screener": nasdaq,
}
