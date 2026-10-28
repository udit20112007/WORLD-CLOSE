# What to do with the paper, step by step

Everything has already been run on your real data (20 Oct 2025 to 26 Oct 2026, the same period as
your first paper). Your first paper's numbers were reproduced exactly as a check. You do **not** need
to run any code. This folder already contains:

| File | What it is |
|---|---|
| `BSE_closes_higher.pdf` | The paper (9 pages) |
| `puzzle_results.md` | Every number with a short explanation; read this alongside the paper |
| `results_puzzle.json` | The raw results the paper reads its numbers from |
| `figures/` | Figures used in the paper |
| `*.py` | The code that produced everything |
| `README.md` | Description of the folder for GitHub |

---

## Step 1: Read and check the paper (2-3 days)

1. Open `BSE_closes_higher.pdf` and `puzzle_results.md` side by side.
2. For every paragraph, ask yourself:
   - Do I understand what this number means?
   - Could I explain it out loud to a professor, without notes?
   - Would I say it this way? If not, note what you'd change and send it to Claude to update.
3. Make sure you understand the three main findings:
   - **The BSE puzzle:** thin stocks' BSE closes are partly stale, the bias is biggest on days with almost no BSE
     trading, and BSE trades for thin stocks happen mostly on days the stock falls.
   - **Which close is right:** for thin stocks, BSE's close is the noisy one (BSE does 84% of the correction).
   - **The closing auction (your strongest result):** from 3 Aug 2026, the gap for the most-traded stocks
     roughly doubled, from 3.7 to 8.0 bps, while other stocks didn't change.

## Step 2: Check four prices against the exchanges' websites (30 minutes). Do this before publishing.

The closing-auction result rests on the closing prices in your downloaded files. Check a few against
the official sources so you know the jump is real and not a download problem.

Look up the official closing prices on **nseindia.com** and **bseindia.com** (each stock's page has
historical data, or use the bhavcopy archives) and compare with your files:

| Stock | Date | NSE close (your file) | BSE close (your file) |
|---|---|---|---|
| RELIANCE | 31 Jul 2026 | 1307.80 | 1307.30 |
| RELIANCE | 03 Aug 2026 | 1319.00 | 1309.00 |
| TCS | 31 Jul 2026 | 2365.60 | 2365.60 |
| TCS | 03 Aug 2026 | 2473.70 | 2450.00 |
| INFY | 03 Aug 2026 | 1180.00 | 1170.00 |
| HDFCBANK | 03 Aug 2026 | 753.00 | 751.05 |

- **If they match:** the result is real. Go on to step 3.
- **If they don't match:** stop, and tell Claude what you found. The closing-auction section would need to change.

## Step 3: Add your first paper's DOI (5 minutes)

The PDF currently shows `doi:10.5281/zenodo.XXXXXXX` where your first paper's DOI should be. Either:

- **Easiest:** send Claude your first paper's DOI and ask for the PDF to be rebuilt, or
- **Yourself:** open `build_paper2.py`, put the DOI in the line `FIRST_PAPER_DOI = "..."` near the top,
  and run `python build_paper2.py` in this folder. That needs Python with reportlab installed
  (`pip install reportlab pillow`).

## Step 4: Upload the folder to GitHub (10 minutes, in your browser)

1. Go to `github.com/udit20112007/WORLD-CLOSE`.
2. Click into the folders `world-close-stage1` → `research`.
3. Click **Add file** → **Upload files**.
4. Drag the whole **`bse_puzzle`** folder (unzipped) from your computer onto the page. GitHub keeps the
   folder structure, so the files end up in `world-close-stage1/research/bse_puzzle/`.
5. At the bottom, under "Commit changes", write:
   `Add follow-up study: why BSE closes higher, and the closing auction experiment`
6. Click **Commit changes**.
7. Check that the PDF opens at
   `github.com/udit20112007/WORLD-CLOSE/tree/main/world-close-stage1/research/bse_puzzle`.
8. **Optional:** edit the main `README.md` (pencil icon) and add a line under your first paper:
   `- [Why Does BSE Close Higher?](world-close-stage1/research/bse_puzzle/BSE_closes_higher.pdf), follow-up paper (2026)`

## Step 5: Get a DOI on Zenodo (20 minutes)

This is a **new paper**, so make a **new record**, not a new version of your first one.

1. Go to **zenodo.org** and log in (the same account as for your first paper).
2. Click **New upload** (top right).
3. **Files:** upload `BSE_closes_higher.pdf`. Also zip the `bse_puzzle` folder and upload that zip, so the code is archived with the paper.
4. Fill in the form:
   - **Do you already have a DOI?** No. Then click **Get a DOI now!** (you can copy it before publishing).
   - **Resource type:** Publication → **Working paper**
   - **Title:** `Why Does BSE Close Higher? Stale Prices, Thin Trading and a Closing-Auction Experiment`
   - **Publication date:** today
   - **Creators:** Goyal, Udit. Affiliation: Guru Gobind Singh Indraprastha University. Add your ORCID if you have one (free at orcid.org; worth doing).
   - **Description:** copy the abstract from the PDF.
   - **Licenses:** Creative Commons Attribution 4.0 International
   - **Keywords:** `law of one price`, `NSE`, `BSE`, `closing auction`, `market microstructure`, `stale prices`, `India`
   - **Related works** (click "Add related work"):
     - Relation **Continues**, identifier = your first paper's DOI, type: Publication
     - Relation **Is supplemented by**, identifier = `https://github.com/udit20112007/WORLD-CLOSE/tree/main/world-close-stage1/research/bse_puzzle`, type: Software
5. Before publishing, copy the reserved DOI. Ask Claude to put it in the PDF's title block (or set `THIS_PAPER_DOI` in `build_paper2.py` and rebuild), then replace the PDF in the upload with the new one.
6. Click **Publish**. Publishing is permanent: you can add new versions later but not delete it, so check everything first.
7. Upload the final PDF (with its DOI) to GitHub too, replacing the old one (same steps as step 4; GitHub overwrites a file with the same name).

## Step 6: Post on SSRN (30 minutes, then 2-7 days of review)

SSRN is where finance professors look for new papers.

1. Go to **ssrn.com** → **Sign In** → **Register** (free).
2. Click **Submit a Paper** (under "My Papers").
3. Upload `BSE_closes_higher.pdf`.
4. Fill in:
   - **Title** and **Abstract:** copy from the PDF
   - **Keywords:** law of one price, closing auction, market microstructure, stale prices, India, NSE, BSE
   - **JEL codes:** `G14` (Information and Market Efficiency), `G15` (International Financial Markets), `G18` (Government Policy and Regulation)
   - **Date written:** October 2026
   - **Classifications:** choose **Financial Economics Network (FEN)**, then journals on **Capital Markets: Market Microstructure** and **Emerging Markets**
   - **Affiliation:** Guru Gobind Singh Indraprastha University (as a student)
5. Submit. You'll get an email when it's public. Post your first paper the same way if you haven't yet.

## Step 7: Use it (this week)

1. **CV**, under *Research*:
   > Goyal, U. (2026). *Why Does BSE Close Higher? Stale Prices, Thin Trading and a Closing-Auction Experiment.* Working paper. DOI: 10.5281/zenodo.XXXXXXX
   >
   > Goyal, U. (2026). *Same Company, Two Prices: How Closely Do India's Two Stock Exchanges Agree on the Close?* Working paper. DOI: 10.5281/zenodo.23666692
2. **Email professors** (IIIT Delhi, IIMs, ISB, IGIDR, IITs) who work on market microstructure. Attach both
   papers and propose one concrete next step, for example: *"I found that India's new closing auction roughly
   doubled the gap between NSE and BSE closes for the most-traded stocks. I'd like to test this properly with
   the official derivatives stock list and intraday auction data. Could I work on this with you?"*
   Claude can draft this email for you.
3. **LinkedIn:** post a short summary of the closing-auction finding with one figure (Figure 4) and the SSRN link.

## Before you share it with anyone

- Do step 2 (price check). It takes 30 minutes and protects you from the one thing that could go wrong.
- Keep the AI-assistance sentence in the acknowledgements. It's honest, and it means no question about
  how the paper was written can catch you out.
- Be ready to explain the difference-in-differences test in Section 8 in your own words. It's the
  result professors will ask about first.
