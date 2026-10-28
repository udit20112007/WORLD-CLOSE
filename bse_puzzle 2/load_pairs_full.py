"""Step 1 (puzzle study): like load_pairs.py, but keeps every price and activity column the daily
files have (open, high, low, previous close, number of trades), and also saves every NSE stock-day
with a flag for whether the stock traded on BSE that day (needed for the selection test).

    WC_DATA_DIR=../wc-data/data python load_pairs_full.py

Prints the columns it found in each exchange's files, so you can see which tests can run.
"""
import glob, os, pathlib
import pandas as pd

DATA = os.environ.get("WC_DATA_DIR", "data")
pathlib.Path("work").mkdir(exist_ok=True)

# Names a column might have in the stored files -> the name used in this study.
ALIASES = {
    "symbol": ["symbol"], "name": ["name"], "isin": ["isin"], "series": ["series"],
    "open": ["open"], "high": ["high"], "low": ["low"], "close": ["close"],
    "prev_close": ["prev_close", "prevclose", "previous_close", "prev"],
    "volume": ["volume"], "value": ["value"],
    "trades": ["trades", "no_of_trades", "num_trades", "total_trades", "n_trades", "no_trades"],
}


def load(ex):
    frames = []
    files = sorted(glob.glob(f"{DATA}/{ex}/*/*.csv.gz"))
    if not files:
        raise SystemExit(f"No files found in {DATA}/{ex}/*/*.csv.gz - check WC_DATA_DIR")
    for p in files:
        d = pd.read_csv(p, dtype={"isin": str, "symbol": str})
        d.columns = [c.strip().lower() for c in d.columns]
        keep = {}
        for std, names in ALIASES.items():
            for n in names:
                if n in d.columns:
                    keep[n] = std
                    break
        d = d[list(keep)].rename(columns=keep)
        d["date"] = pd.Timestamp(p[-17:-7])
        frames.append(d)
    out = pd.concat(frames, ignore_index=True)
    return out[out["isin"].notna() & (out["isin"] != "")]


nse, bse = load("NSE"), load("BSE")
print("NSE columns found:", sorted(c for c in nse.columns if c != "date"))
print("BSE columns found:", sorted(c for c in bse.columns if c != "date"))

pairs = nse.merge(bse, on=["isin", "date"], suffixes=("_n", "_b"))
pairs["mid"] = (pairs.close_n + pairs.close_b) / 2
pairs["gap_bps"] = (pairs.close_b - pairs.close_n) / pairs.mid * 1e4      # BSE minus NSE, basis points
pairs.to_pickle("work/pairs_full.pkl")

on_bse = bse[["isin", "date"]].drop_duplicates().assign(on_bse=True)
nse_days = nse.merge(on_bse, on=["isin", "date"], how="left")
nse_days["on_bse"] = nse_days["on_bse"].eq(True)
nse_days.to_pickle("work/nse_days.pkl")

print(f"{len(pairs):,} matched stock-days -> work/pairs_full.pkl")
print(f"{len(nse_days):,} NSE stock-days ({nse_days.on_bse.mean():.1%} also traded on BSE) -> work/nse_days.pkl")
