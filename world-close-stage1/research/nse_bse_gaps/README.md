# Same Company, Two Prices: NSE vs BSE closing-price gaps

**Paper:** [NSE_BSE_closing_price_gaps.pdf](NSE_BSE_closing_price_gaps.pdf), by Udit Goyal (October 2026)

How closely do India's two stock exchanges agree on the closing price of the same company?
Using one year of official daily closing prices (20 Oct 2025 to 26 Oct 2026) for 2,524
companies traded on both NSE and BSE, the paper finds that the two closes usually differ by a
small amount (median 0.11%), that liquidity explains most of the variation across companies,
that gaps largely disappear by the next day, and that thinly traded stocks tend to close
slightly higher on BSE.

## Reproducing every number, table and figure

The daily price files live on the repository's `data` branch (see the main README). From this
folder:

```bash
pip install pandas numpy statsmodels matplotlib reportlab pillow

# get the data branch next to the repository
git fetch origin data
git worktree add ../../../wc-data origin/data
export WC_DATA_DIR=../../../wc-data/data

python load_pairs.py    # 1. match companies across NSE and BSE by ISIN  -> work/pairs.pkl
python analysis.py      # 2. main results                                -> results.json
python robust.py        # 3. robustness checks and remaining numbers     -> results.json
python figures.py       # 4. the four figures                            -> figures/
python build_paper.py   # 5. the paper                                   -> NSE_BSE_closing_price_gaps.pdf
```

Every number in the paper is read from `results.json` by `build_paper.py`, so the text, tables
and figures always match the data they were computed from.

**Note:** the data branch keeps the most recent 400 days, so rerunning later uses a later year
of data and the numbers will differ somewhat from the published version. The version of
`results.json` in this folder is the one the paper was built from.
