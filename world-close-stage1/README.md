# World Close

The closing price of every listed stock, exchange by exchange, updated
automatically after each trading day and hosted free on GitHub Pages.

**Covered so far:** every stock on **NSE and BSE** (stage 1), **NYSE, Nasdaq
and NYSE American** (stage 2), and **Shanghai, Shenzhen, Hong Kong, Taiwan,
KOSPI, KOSDAQ and B3 Brazil** (stage 3). More exchanges plug in as separate
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
5. **Actions tab → Update India (NSE, BSE) → Run workflow.** In the
   *backfill days* box enter **370** to download the past year, so charts and
   52-week ranges work from day one. This first run takes about 20–40 minutes.
6. Your site is at `https://<your-username>.github.io/<repo-name>/`.

From then on it runs by itself at 19:00 IST every weekday, with a second try
at 22:00 IST in case the exchange published late.

## How it works

```
GitHub Actions (weekdays 19:00 and 22:00 IST)
 ├─ python -m pipeline.run update --exchanges NSE BSE
 │    downloads each new day's official bhavcopy file and saves it as
 │    data/NSE/2026/2026-10-23.csv.gz   (one small file per exchange per day)
 ├─ commits the new files to the repository, so history builds up
 ├─ python -m pipeline.run build
 │    turns stored days into what the site loads:
 │    site/data/exchanges.json          exchange list, counts, status
 │    site/data/NSE/summary.json        every stock's latest close (~150 KB compressed)
 │    site/data/NSE/hist/<n>.json       1-year closes, 150 stocks per file, loaded on click
 └─ publishes site/ to GitHub Pages
```

Sources:

| Exchange | File | Notes |
|---|---|---|
| NSE | Daily cash-market bhavcopy (UDiFF format), `nsearchives.nseindia.com` | Series EQ, BE, BZ and SME series SM, ST, SZ. Bonds, G-secs and other instruments are excluded. |
| BSE | Daily equity bhavcopy (UDiFF format), `bseindia.com` | All equity groups (A, B, T, X, Z, M, ...). Debt groups are excluded. |
| NYSE, Nasdaq, NYSE American | Nasdaq's public stock screener, `api.nasdaq.com` | Every listed stock with last price, change, volume, sector and market cap. Types: Common, ADR, Preferred, Warrant, Unit, Right. |

| Shanghai, Shenzhen, Hong Kong | Sina Finance market lists via the AKShare library, with East Money as a fallback | Latest session only; Yahoo backfill for history. Mainland boards: Main Board, STAR Market, ChiNext. Mainland names are in Chinese; Hong Kong names are in English. East Money often refuses connections from outside China, which is why Sina is tried first. |
| Taiwan | Official TWSE OpenAPI (`STOCK_DAY_ALL`) | Latest session, with its trading date; Yahoo backfill for history. Stocks and ETFs. |
| KOSPI, KOSDAQ | Yahoo Finance's stock screener | Latest session, with English names and market caps; Yahoo backfill for history. No sign-up needed. (A KRX OpenAPI source is also included; see below.) |
| B3 (Brazil) | B3's official COTAHIST files | Any date; the backfill uses the annual file (one download per year). Standard-lot shares on the cash market. |

### English company names

Shanghai, Shenzhen and Taiwan publish company names only in Chinese. Each
week the pipeline fetches every company's official English name from Yahoo
Finance's screener and saves it in `data/<EXCHANGE>/english_names.json`. The
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
python -m unittest discover tests               # 37 tests using sample exchange files
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
