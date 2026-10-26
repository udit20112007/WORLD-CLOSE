"""Spotting foreign companies' shares on an exchange's international market.

Mexico's exchange includes the SIC (Sistema Internacional de Cotizaciones), where
shares of foreign companies (Apple, Prada, BYD, ...) trade in pesos. They'd appear
twice on the site and crowd out Mexican companies, so the site leaves them out:
they're already shown on their home exchanges.

A listing counts as foreign when its name has no Mexican legal form or trust, and
any of these hold: its ticker is also listed in the US; it ends in "N" (the SIC's
suffix); the same company name appears on another exchange the site covers; or its
name ends in a foreign legal form (Inc., plc, N.V., ...).
"""
from __future__ import annotations

import re

import pandas as pd

HOME_FORMS = re.compile(
    r"S\.?\s?A\.?\s?B\.?\b|de\s+C\.?\s?V\b|S\.?\s?A\.?\s?P\.?|S\.\s?C\.|Fideicomiso|Fibra|\bTRAC\b|"
    r"Instituci[oó]n de Banca|Nacional Financiera|\bCKD\b", re.I)
FOREIGN_FORMS = re.compile(
    r"\b(Inc|Corp|Corporation|Company|Co|Ltd|Limited|plc|PLC|N\.V|NV|AG|SE|S\.p\.A|SpA|ASA|A/S|AB|Oyj|"
    r"GmbH|SA/NV|Holdings|Group|Trust|LP|L\.P)\.?$", re.I)


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def foreign_listings(rows: pd.DataFrame, other_names: set[str], us_symbols: set[str], suffix: str = ".MX") -> pd.Series:
    """Boolean mask: True for rows that are foreign companies' shares."""
    names = rows["name"].fillna("").astype(str)
    base = rows["symbol"].fillna("").astype(str).str.replace(re.escape(suffix) + "$", "", regex=True)
    home = names.str.contains(HOME_FORMS)
    us = base.isin(us_symbols) | base.str.replace(r"(1|\*)$", "", regex=True).isin(us_symbols)
    sic_suffix = base.str.endswith("N")
    elsewhere = names.map(normalise).isin(other_names) & names.ne("")
    foreign_form = names.str.strip().str.contains(FOREIGN_FORMS)
    return ~home & (us | sic_suffix | elsewhere | foreign_form)
