# World Close

The closing price of every listed stock, exchange by exchange, updated
automatically after each trading day and hosted free on GitHub Pages.

**Covered so far:** every stock on **NSE and BSE** (stage 1), **NYSE, Nasdaq
and NYSE American** (stage 2), and **Shanghai, Shenzhen, Hong Kong, Taiwan,
KOSPI, KOSDAQ and B3 Brazil** (stage 3), and **Tokyo, Australia, Singapore,
Malaysia, Thailand, Indonesia, London, Euronext, Xetra, SIX, Nasdaq Nordic,
Madrid, Warsaw, Istanbul, Saudi Arabia, Dubai, Tel Aviv, Johannesburg,
Toronto, the Canadian Securities Exchange and Mexico** (stage 4): 33
exchanges in all. More exchanges plug in as separate
sources (see the roadmap below).

What the site shows for each exchange:

- **Market breadth:** how many stocks rose, fell, stayed flat, or didn't trade.
- **Biggest gains and falls** among the most actively traded fifth of stocks (so
  a tiny stock jumping 20% on a few trades doesn't top the list), and the
  **most traded** stocks by value.
- **Every stock** with search (name, symbol or ISIN), series filter, sorting by
  close, daily change, volume, value traded or 52-week position, 50 per page.
- **Click any stock** for a 1-month to 1-year chart, its stats, and a link to the
  same company on the other exchange (matched by ISIN).
- A **Data status** page showing when each exchange last updated and any errors.

## Setup (about 10 minutes)

1. Create a new **public** repository on GitHub. Public repositories get free
   Actions minutes and free Pages hosting.
2. Upload everything in this folder, keeping the structure. Make sure the
   hidden `.github` folder is included (on a Mac, press Cmd+Shift+. in Finder
   to show hidden files).
3. **Settings → Pages:** set **Source** to **GitHub Actions**.
4. **Settings → Actions → General → Workflow permissions:** choose
   **Read and write permissions** and save. The workflow needs this to save
   each day's prices into the repository.
5. **Actions tab → Update World Close → Run workflow.** In the *backfill
   days* box enter **370** to download the past year, so charts and 52-week
   ranges work from day one. For a first run of all 33 exchanges, split it
   into groups in the *exchanges* box (for example `NSE BSE NYSE NASDAQ`),
   one run at a time, since a full backfill can take several hours.
6. Your site is at `https://<your-username>.github.io/<repo-name>/`.

From then on it runs by itself about ten times a day, after each region's
markets close.

## How it works

One GitHub workflow (`.github/workflows/update.yml`) runs about ten times a
day, timed after each region's markets close. Every run checks every exchange;
each one only downloads when it has a finished session it hasn't saved yet, so
the extra runs are cheap. The workflow just calls `scripts/ci_run.sh`, which
holds all the logic, so changes never need workflow edits.

```
scripts/ci_run.sh
 ├─ checks out the "data" branch (the price data; see Storage below)
 ├─ for each exchange: python -m pipeline.run update --exchanges <CODE>
 │    then saves the data branch straight away
 ├─ python -m pipeline.run prune --keep-days 400
 └─ python -m pipeline.run build   → site/, published to GitHub Pages
```

### Storage

Price data lives on a separate branch called **`data`**, not on `main`. Git
normally keeps every version of every file forever, which would make the
repository grow by roughly half a gigabyte a year. Instead, the data branch is
always **a single commit** holding the current files (each save replaces it),
and daily files older than 400 days are deleted, which is still enough for
one-year charts and 52-week ranges. So storage stays roughly constant. The
`main` branch only holds code.

The first run of `ci_run.sh` creates the data branch from `main`'s
`world-close-stage1/data` folder (reusing the stored files, so nothing is
uploaded twice) and removes that folder from `main`. Older versions of the data
remain in `main`'s history from before the move, but nothing is added there any
more.

To look at the data on GitHub, switch the branch selector from `main` to
`data`. To work with it locally: `git fetch origin data` and
`git worktree add ../wc-data origin/data`, then set
`WC_DATA_DIR=../wc-data/data` when running the pipeline.

### Sources

| Exchange | File | Notes |
|---|---|---|
| NSE | Daily cash-market bhavcopy (UDiFF format), `nsearchives.nseindia.com` | Series EQ, BE, BZ and SME series SM, ST, SZ. Bonds, G-secs and other instruments are excluded. |
| BSE | Daily equity bhavcopy (UDiFF format), `bseindia.com` | All equity groups (A, B, T, X, Z, M, ...). Debt groups are excluded. |
| NYSE, Nasdaq, NYSE American | Nasdaq's public stock screener, `api.nasdaq.com` | Every listed stock with last price, change, volume, sector and market cap. Types: Common, ADR, Preferred, Warrant, Unit, Right. |

| Shanghai, Shenzhen, Hong Kong | Sina Finance market lists via the AKShare library, with East Money as a fallback | Latest session only; Yahoo backfill for history. Mainland boards: Main Board, STAR Market, ChiNext. Mainland names are in Chinese; Hong Kong names are in English. East Money often refuses connections from outside China, which is why Sina is tried first. |
| Taiwan | Official TWSE OpenAPI (`STOCK_DAY_ALL`) | Latest session, with its trading date; Yahoo backfill for history. Stocks and ETFs. |
| KOSPI, KOSDAQ | Yahoo Finance's stock screener | Latest session, with English names and market caps; Yahoo backfill for history. No sign-up needed. (A KRX OpenAPI source is also included; see below.) |
| B3 (Brazil) | B3's official COTAHIST files | Any date; the backfill uses the annual file (one download per year). Standard-lot shares on the cash market. |

### Stage 4: the rest of the world through Yahoo's screener

The 21 stage 4 exchanges all use Yahoo Finance's stock screener (the
`yahoo_screen` source), updated by the "Update rest of world" workflow four
times a day plus Sundays for Saudi Arabia (which trades Sunday to Thursday;
each exchange's weekend is set in `config/exchanges.json`).

- **Symbols are Yahoo's** (e.g. `7203.T` Toyota, `SHEL.L` Shell). Euronext and
  Nasdaq Nordic span several cities, filterable on their pages.
- **Each stock keeps its own currency**: London has stocks in pence, pounds,
  dollars and euros; Oslo trades in kroner within Euronext. London prices show
  in pence (p), Johannesburg in cents (c) and Tel Aviv in agorot (ag.), as those
  exchanges quote them; values and market caps show in pounds, rand and shekels.
- **Mexico shows Mexican companies only.** Its exchange also has an
  international market (the SIC) where shares of foreign companies like Apple or
  Prada trade in pesos. These would appear twice and crowd out Mexican stocks, so
  the site leaves them out (`pipeline/foreign.py`, switched on with
  `"drop_foreign_listings": true` in `config/exchanges.json`). The stored data
  keeps them, so this is easy to undo.
- **Dead listings are left out.** Yahoo's screener still lists many delisted or
  long-suspended securities (thousands on Euronext alone), so any stock with no
  trade in the last 30 days is dropped. The status page says how many.
- **Coverage is whatever Yahoo carries.** Most stocks on major exchanges are
  there; some very small companies may be missing. Abu Dhabi (ADX) isn't
  available in Yahoo's screener, so the UAE is Dubai only.
- **The first run** with backfill 370 downloads a year of history for every
  stage 4 stock, which can take several hours. The workflow's *exchanges* box
  lets you split it into smaller runs (for example Asia first, then Europe).
  The workflow saves each exchange as soon as it's done
  (`scripts/update_and_save.sh`), and stops starting new ones after 5 hours so
  the site still gets published; any it didn't reach are listed as a warning.
- **A market that's open during the first run** still gets its history: the
  stock list is taken from the screener and history is filled up to the
  previous trading day. Today's unfinished session is never saved.

### English company names

Shanghai, Shenzhen and Taiwan publish company names only in Chinese. Each
week the pipeline fetches every company's official English name from Yahoo
Finance's screener (for Taiwan, also the exchange's own English short names,
since Yahoo's screener carries few Taiwanese companies) and saves it in `data/<EXCHANGE>/english_names.json`. The
site shows the English name with the original beside it, and searching works
in either language. A stock with no English name on Yahoo keeps its original
name. To turn this on for another exchange, add for example
`"english_names": {"yahoo_exchange": "SHH"}` to its entry in
`config/exchanges.json`.

### Optional: Korea from the official KRX OpenAPI

Korea uses Yahoo's screener by default. If you'd rather use the Korea
Exchange's own data, the `krx` source is included and needs a free API key.
Note that sign-up may require a Korean mobile number for identity
verification. To switch, set `"source": "krx"` for KOSPI and KOSDAQ in
`config/exchanges.json`, then:

1. Go to https://openapi.krx.co.kr, sign up, and request an API key
   (My page → API key application). Approval usually takes about a day and
   arrives by email.
2. Still on that site, apply to use the two APIs **유가증권 일별매매정보**
   (KOSPI daily trading, `stk_bydd_trd`) and **코스닥 일별매매정보** (KOSDAQ daily
   trading, `ksq_bydd_trd`).
3. In your GitHub repository: **Settings → Secrets and variables → Actions →
   New repository secret**. Name it `KRX_OPENAPI_KEY` and paste the key.
4. Run the "Update Asia and Brazil" workflow again with backfill days 370.

GitHub secrets are never shown in logs, and the pipeline also removes the key
from any error message before saving it to the public status page.

### How the US source differs

The Nasdaq screener only shows the **latest** session, not past days, so:

- The US workflow runs once each weekday evening in New York (19:15 EDT,
  with a second try at 21:30) and labels the data with that day's date.
  If it runs while the market is open, it saves nothing rather than storing
  intraday prices as a close.
- **Market holidays** are detected by comparison: if nearly every price and
  volume is identical to the previous saved day, the market was closed and
  nothing is saved.
- **Chart history** comes from a one-off backfill: run the US workflow by hand
  with *backfill days* set to 370, and it downloads the past year of daily
  closes from Yahoo Finance for common stocks, ADRs and preferreds. This is
  best effort: Yahoo may refuse some requests from GitHub's servers. The status
  page reports how many stocks returned history. Running it again only fills
  in what's missing and never overwrites saved days.
- Yahoo data is unofficial and meant for personal use.

Change which series or groups are included in `config/exchanges.json`.

The parsers match columns by name and also accept NSE's and BSE's older
column names, so a column being reordered or renamed back won't break them.
If a file arrives in a format they can't read, the run records a clear
"Unrecognised file format" error on the status page instead of publishing
bad data.

### Things to know

- **Only traded stocks appear in a day's file.** On BSE, many small companies
  don't trade every day. The site keeps showing their last close (labelled
  "last traded on ...") for up to 30 days, then drops them until they trade
  again.
- **Prices are not adjusted** for splits, bonus issues or other corporate
  actions. Charts and 52-week ranges can show a sudden jump on those dates.
- **Repository size** grows by roughly 40–60 MB a year for India. That's fine
  for GitHub for several years.
- **GitHub pauses schedules after 60 days without repository activity.** The
  daily data commits count as activity, so this shouldn't happen, but if it
  does, re-enable the workflow from the Actions tab.
- The data is the exchanges' own published files. Check NSE's and BSE's terms
  before using the site commercially. Nothing here is investment advice.

## Troubleshooting

Open the site's **Data status** page, or the workflow run's log in the
Actions tab.

- **"HTTP 403" or "returned a web page instead of a data file" for NSE:** NSE's
  website sometimes blocks requests from cloud servers. The run stops after
  five failures in a row and tries again at the next scheduled time. If it
  keeps happening, BSE still covers almost every NSE company (matched by
  ISIN). Send the error text and the parser can be adapted.
- **"Unrecognised file format":** the exchange changed its file. The error
  lists the columns it found, which is what's needed to update the parser.
- **No new data on a weekday:** usually a market holiday. Holidays return no
  file and are skipped silently.

## Running it on your computer

```bash
pip install -r requirements.txt
python -m unittest discover tests               # 60 tests using sample exchange files
python -m pipeline.run update --exchanges NSE BSE
python -m pipeline.run build
cd site && python -m http.server 8000           # open http://localhost:8000
```

To try the site without downloading anything:

```bash
WC_DATA_DIR=/tmp/wc-demo python -m pipeline.run demo   # random demo stocks
WC_DATA_DIR=/tmp/wc-demo python -m pipeline.run build
```

`python scripts/build_preview.py` bundles the page and current summaries into
one standalone `preview.html` (charts in it use invented paths).

## Adding an exchange

1. Write `pipeline/sources/<name>.py` with a `fetch(day, cfg)` function that
   returns a DataFrame with the columns in `pipeline.common.STANDARD_COLUMNS`
   and raises `NotPublished` when there's no file for that day. The helpers
   `session`, `get_bytes`, `read_csv_maybe_zipped`, `normalize` and `dedupe`
   do most of the work.
2. Register it in `pipeline/sources/__init__.py`.
3. Add the exchange to `config/exchanges.json` with its currency and timezone.
4. Add a sample file and a test in `tests/`.
5. Copy `.github/workflows/india.yml`, change the exchanges and set the
   schedule to shortly after that market's daily file is published.

The site picks up new exchanges automatically.

## Roadmap

- **Stage 4:** the remaining exchanges through Yahoo Finance, with the
  largest stocks updated daily and the rest on a rotation.
