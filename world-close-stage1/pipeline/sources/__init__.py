"""Registry of exchange data sources.

Each source module exposes:
    fetch(day: datetime.date, cfg: dict) -> pandas.DataFrame   (standard schema)
and raises common.NotPublished when there is no file for that day.
"""
from . import bse, nse

SOURCES = {
    "nse": nse,
    "bse": bse,
}
