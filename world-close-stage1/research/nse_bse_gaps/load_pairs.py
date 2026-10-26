"""Step 1: match every company traded on both NSE and BSE (by ISIN) for each day.

Reads the daily files from the data branch. Set WC_DATA_DIR to the data folder, e.g.
    git fetch origin data && git worktree add ../wc-data origin/data
    WC_DATA_DIR=../wc-data/data python load_pairs.py
"""
import glob, os, pathlib, pandas as pd, numpy as np
DATA = os.environ.get("WC_DATA_DIR", "data")
pathlib.Path("work").mkdir(exist_ok=True)
def load(ex):
    frames = []
    for p in sorted(glob.glob(f"{DATA}/{ex}/*/*.csv.gz")):
        d = pd.read_csv(p, usecols=["symbol","name","isin","series","close","volume","value"], dtype={"isin": str, "symbol": str})
        d["date"] = pd.Timestamp(p[-17:-7]); frames.append(d)
    return pd.concat(frames, ignore_index=True)
nse, bse = load("NSE"), load("BSE")
nse = nse[nse["isin"].notna() & (nse["isin"] != "")]; bse = bse[bse["isin"].notna() & (bse["isin"] != "")]
pairs = nse.merge(bse, on=["isin", "date"], suffixes=("_n", "_b"))
pairs["mid"] = (pairs.close_n + pairs.close_b) / 2
pairs["gap_bps"] = (pairs.close_b - pairs.close_n) / pairs.mid * 1e4     # BSE minus NSE, basis points
pairs.to_pickle("work/pairs.pkl")
print(f"{len(pairs):,} matched stock-days written to work/pairs.pkl")
