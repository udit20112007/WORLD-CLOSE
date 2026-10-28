# BSE puzzle: results summary

Sample: 2,212 companies, 491,644 stock-days, 2025-10-20 to 2026-10-26. Liquidity groups: first paper (../nse_bse_gaps/work/paper_frames.pkl).

Columns available: close_b, close_n, date, gap_bps, high_b, high_n, isin, low_b, low_n, mid, name_b, name_n, open_b, open_n, prev_close_b, prev_close_n, series_b, series_n, symbol_b, symbol_n, trades_b, trades_n, value_b, value_n, volume_b, volume_n

## Test 1: stale prices

Prediction if BSE's close is stale: a clearly negative slope for thin stocks, and a bias that shows up on down days but not on flat days.

| Group | Slope (bps per 1% NSE move) | t | Bias on flat days (bps) | Mean gap up / down days (bps) | BSE higher on flat days | Share of bias explained by staleness |
|---|---|---|---|---|---|---|
| Q1 (least) | -6.638 | -18.7 | 12.0 | -8.9 / 38.4 | 53.0% | 1.2% |
| Q2 | -1.672 | -15.1 | 1.0 | -4.3 / 7.3 | 49.0% | n/a (no clear bias) |
| Q3 | -0.346 | -8.8 | -0.2 | -0.7 / 2.2 | 48.3% | n/a (no clear bias) |
| Q4 | -0.143 | -4.8 | -0.6 | -0.4 / 1.0 | 45.3% | n/a (no clear bias) |
| Q5 (most) | -0.442 | -11.9 | -1.4 | -2.1 / 0.6 | 41.9% | n/a (no clear bias) |

**Reading:** for the least-traded fifth the slope is negative and significant (t = -18.7), so BSE closes do lag NSE moves for thin stocks.
 But the bias is still 12.0 bps on days when NSE barely moved, which staleness cannot explain. Something else adds to it.

Least-traded fifth by market direction: mean gap 13.4 bps on up-market days, 18.5 bps on down-market days; the market fell on 58.4% of days.

## Test 2: thin BSE days

**BSE high equals BSE low (all trades at one price)**

| Group | Days flagged | Mean gap flagged / other (bps) | BSE higher flagged / other | Difference (t) |
|---|---|---|---|---|
| Q1 (least) | 5.6% | 39.6 / 14.9 | 56.4% / 54.1% | 24.658 (4.0) |
| Q3 | 0.2% | -3.7 / 0.7 | 19.9% / 50.2% | -4.359 (-1.1) |
| Q5 (most) | 0.0% | 0.9 / -0.8 | 56.2% / 44.0% | 1.727 (0.9) |

**BSE close equals BSE open**

| Group | Days flagged | Mean gap flagged / other (bps) | BSE higher flagged / other | Difference (t) |
|---|---|---|---|---|
| Q1 (least) | 7.1% | 34.9 / 14.9 | 56.6% / 54.1% | 20.002 (4.0) |
| Q3 | 0.7% | -1.8 / 0.7 | 37.0% / 50.2% | -2.477 (-1.6) |
| Q5 (most) | 0.4% | -1.5 / -0.8 | 45.7% / 44.0% | -0.709 (-0.7) |

**3 or fewer trades on BSE**

| Group | Days flagged | Mean gap flagged / other (bps) | BSE higher flagged / other | Difference (t) |
|---|---|---|---|---|
| Q1 (least) | 9.4% | 37.4 / 14.1 | 56.0% / 54.1% | 23.339 (4.8) |
| Q3 | 0.0% | 23.7 / 0.7 | 43.8% / 50.1% | 23.011 (1.7) |
| Q5 (most) | 0.0% | 1.4 / -0.8 | 51.6% / 44.0% | 2.232 (1.4) |

**BSE volume in the stock's own lowest fifth of days**

| Group | Days flagged | Mean gap flagged / other (bps) | BSE higher flagged / other | Difference (t) |
|---|---|---|---|---|
| Q1 (least) | 20.4% | 26.9 / 13.6 | 56.8% / 53.6% | 13.302 (6.6) |
| Q3 | 20.0% | 0.3 / 0.8 | 49.7% / 50.2% | -0.486 (-2.2) |
| Q5 (most) | 20.0% | -1.0 / -0.8 | 43.4% / 44.1% | -0.247 (-1.8) |

**Reading:** if the bias is much larger on flagged days, it comes from how BSE's close is formed when there is almost no trading (the closing-price rule or a few buyer-initiated trades).

## Test 3: who closes the gap the next day?

| Group | NSE moves toward BSE (% of gap) | t | BSE moves back toward NSE (% of gap) | t | Gap closed next day | Share of correction by BSE |
|---|---|---|---|---|---|---|
| all | 14.8 | 17.0 | 72.2 | -41.8 | 87.0% | 83.0% |
| Q1 (least) | 14.1 | 14.2 | 71.8 | -34.8 | 85.9% | 83.6% |
| Q2 | 16.3 | 7.4 | 78.8 | -34.9 | 95.1% | 82.9% |
| Q3 | 19.9 | 4.5 | 77.3 | -16.8 | 97.1% | 79.6% |
| Q4 | 13.2 | 2.2 | 84.9 | -13.5 | 98.2% | 86.5% |
| Q5 (most) | 49.7 | 12.9 | 49.0 | -12.7 | 98.7% | 49.6% |

**Reading:** for thin stocks BSE does most of the correcting, so BSE's close is the noisy one and NSE's close is the better price. This supports treating the bias as noise in BSE's close.

## Test 4: selection

| Group | NSE days also traded on BSE | NSE return on BSE days / other days (%) | Within-company difference (t) | NSE value vs usual, BSE days / other | NSE close location, BSE days / other |
|---|---|---|---|---|---|
| Q1 (least) | 92.7% | -0.03 / 0.054 | -0.109 (-3.5) | 1.029 / 0.609 | 0.414 / 0.459 |
| Q2 | 99.3% | -0.016 / 0.153 | -0.17 (-2.0) | 1.001 / 0.674 | 0.425 / 0.478 |
| Q3 | 99.5% | -0.027 / 0.093 | -0.101 (-1.1) | 1.0 / 0.999 | 0.434 / 0.475 |
| Q4 | 99.8% | 0.017 / 0.104 | 0.105 (2.5) | 1.0 / 0.913 | 0.448 / 0.473 |
| Q5 (most) | 99.9% | 0.035 / 0.42 | -0.473 (-1.5) | 1.0 / 1.747 | 0.472 / 0.496 |

**Reading:** if thin stocks trade on BSE mainly on days with higher NSE returns, more NSE activity or NSE closes near the day's high, BSE trading is happening on days of buying pressure, and part of the bias is selection rather than mispricing. Close location runs from 0 (closed at the low) to 1 (closed at the high).

## Check: the level shift in the daily median gap

Estimated break date: **2026-01-19** (sup-F = 68.0; F is the sup-F from scanning every break date; it needs larger critical values than an ordinary F test (roughly 9 at 5%).)

| Measure | Before | After |
|---|---|---|
| median_gap | 9.6 | 11.4 |
| stocks | 1888.5 | 1991.7 |
| median_price | 301.5 | 286.0 |
| bse_value_share_pct | 6.7 | 7.1 |
| one_price_b_pct | 1.1 | 1.1 |

Companies only before the break: 1; only after: 202.

| Group | Median abs gap before | after |
|---|---|---|
| Q1 (least) | 37.4 | 50.0 |
| Q2 | 17.2 | 20.4 |
| Q3 | 10.4 | 11.4 |
| Q4 | 6.8 | 7.4 |
| Q5 (most) | 3.7 | 4.7 |

**What to check:** if the number of stocks, the share of one-price BSE days or the BSE value share jumps at the break, look first at your pipeline's commit history around that date (a file format or source change). If nothing in your data changed, search NSE, BSE and SEBI circulars from the weeks before the break (tick sizes, closing-price method, closing auction). If the jump appears in every liquidity group, a market-wide rule change is more likely than a change in the mix of stocks.

- stocks_10_days_before: 1933.2
- stocks_10_days_after: 1956.0
- same_companies_median_gap: {'before': 9.6, 'after': 10.9}
- abs_market_move_pct: {'before': 0.521, 'after': 0.839}
- shift_without_control: {'b': 1.855, 'se': 0.298, 't': 6.2, 'n': 250}
- shift_controlling_for_market_move: {'b': 1.656, 'se': 0.286, 't': 5.8, 'n': 250}

## Natural experiment: the closing auction (from 2026-08-03)

Treated group: most-traded fifth of companies (proxy for stocks with derivatives) (441 companies; 1739 in the control group). 40 trading days before, 58 after.

| | Before | After |
|---|---|---|
| Median abs gap, treated (bps) | 3.7 | 8.0 |
| Median abs gap, control (bps) | 13.1 | 13.8 |
| Mean signed gap, treated (bps) | -0.4 | -2.7 |
| BSE higher, treated | 43.9% | 44.0% |
| Identical closes, treated | 5.8% | 5.4% |

Difference-in-differences on daily medians: {'b': 3.714, 'se': 0.336, 't': 11.1, 'n': 98} ; controlling for the market move: {'b': 3.671, 'se': 0.291, 't': 12.6, 'n': 98}. First day: 14.3 bps; last 10 days: 8.3 bps.

**Check before trusting this:** pick 3-4 large stocks, look up their official closing prices on NSE's and BSE's websites for a few days just before and after the start date, and confirm they match your files. That rules out a change in the downloaded files themselves.
