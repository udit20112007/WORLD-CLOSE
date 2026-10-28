# Why does BSE close higher? Follow-up to "Same Company, Two Prices"

**Paper:** [BSE_closes_higher.pdf](BSE_closes_higher.pdf), by Udit Goyal (October 2026). Results: [puzzle_results.md](puzzle_results.md).

The first paper found that for thinly traded stocks, BSE's official close tends to sit slightly
above NSE's. This folder tests why, using the same daily data and the same clean sample.

| Test | Question | What would support it |
|---|---|---|
| 1. Stale prices | Does the gap move opposite to the day's NSE return? | A clearly negative slope for thin stocks; the bias disappears on flat days |
| 2. Thin BSE days | Is the bias concentrated on days with almost no BSE trading? | A much larger bias on one-price / few-trade / low-volume days |
| 3. Who adjusts | After a gap, does BSE move back to NSE, or NSE move to BSE? | Which exchange does most of the next-day correction |
| 4. Selection | Are the days a thin stock trades on BSE unusual days on NSE? | Higher NSE returns, activity or closes near the high on BSE days |
| Check | When did the daily median gap jump, and what changed then? | A data change, a change in the mix of companies, or market volatility |
| Natural experiment | Did the Closing Auction Session (from 3 Aug 2026, stocks with derivatives only) change the gap? | A change for treated stocks only (difference-in-differences) |

## Where this folder goes

Put it next to the first paper's folder:

```
world-close-stage1/research/
    nse_bse_gaps/      <- first paper
    bse_puzzle/        <- this folder
```

If the first paper's `work/paper_frames.pkl` exists, the liquidity groups are reused so both papers
use identical groups. Otherwise they are recomputed the same way.

## Running it

```bash
pip install pandas numpy statsmodels matplotlib reportlab pillow

# the data branch, as for the first paper
git fetch origin data
git worktree add ../../../wc-data origin/data      # skip if you already did this
export WC_DATA_DIR=../../../wc-data/data

python load_pairs_full.py   # 1. match NSE and BSE, keeping open/high/low/prev close/trades -> work/
python puzzle.py            # 2. the four tests and the level-shift check         -> results_puzzle.json
python puzzle_figures.py    # 3. figures 5-7                                      -> figures/
python report.py            # 4. plain-language summary of every number            -> puzzle_results.md
python build_paper2.py      # 5. the paper (fill in FIRST_PAPER_DOI first)         -> BSE_closes_higher.pdf
```

Every number in the paper is read from `results_puzzle.json`, so the text, tables and figures
always match the data they were computed from. See `STEPS.md` for checking, publishing and using it.

`load_pairs_full.py` prints the columns it found in your files. Tests that need a column your
files do not have (for example, number of trades) are skipped automatically.

The code was checked on simulated data with known effects, and run on the real data for
20 Oct 2025 to 26 Oct 2026 (the first paper's period; the first paper's numbers reproduce exactly).
If `fo_stocks.csv` (a `symbol` column of NSE stocks with derivatives) is added to this folder, the
closing-auction test uses it instead of the most-traded fifth as the treated group.

The data branch keeps only the most recent 400 days, so rerunning later uses a different period. The
`results_puzzle.json` in this folder is the one the paper was built from.
