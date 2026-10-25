"""Registry of exchange data sources.

Each source module exposes:
    fetch(day: datetime.date, cfg: dict) -> pandas.DataFrame   (standard schema)
and raises common.NotPublished when there is no file for that day.

Sources with LATEST_ONLY = True can only return the most recent session; the
pipeline calls them once per run. They may also offer
    backfill(latest_rows, start, end) -> ({day: DataFrame}, symbols_ok, errors)
to fill in past days from another source. Date-based sources may offer
    fetch_range(start, end, cfg) -> {day: DataFrame}
to download a whole range at once for the backfill.
"""
from . import b3, bse, eastmoney, krx, nasdaq, nse, twse

SOURCES = {
    "nse": nse,
    "bse": bse,
    "nasdaq_screener": nasdaq,
    "eastmoney": eastmoney,
    "twse": twse,
    "krx": krx,
    "b3": b3,
}
