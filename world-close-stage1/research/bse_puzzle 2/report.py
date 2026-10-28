"""Step 4 (puzzle study): turn results_puzzle.json into a plain-language results report
(puzzle_results.md). This is a working summary for you to read and interpret before you write
the paper, not the paper itself."""
import json
R = json.load(open("results_puzzle.json"))
G = ["Q1 (least)", "Q2", "Q3", "Q4", "Q5 (most)"]
sig = lambda c: abs(c["t"]) >= 2.0
L = []
w = L.append

w("# BSE puzzle: results summary\n")
s = R["sample"]
w(f"Sample: {s['companies']:,} companies, {s['stock_days']:,} stock-days, {s['from']} to {s['to']}. "
  f"Liquidity groups: {R['liquidity_groups_from']}.\n")
w(f"Columns available: {', '.join(R['columns_available'])}\n")

# Test 1
w("## Test 1: stale prices\n")
w("Prediction if BSE's close is stale: a clearly negative slope for thin stocks, and a bias that "
  "shows up on down days but not on flat days.\n")
w("| Group | Slope (bps per 1% NSE move) | t | Bias on flat days (bps) | Mean gap up / down days (bps) | BSE higher on flat days | Share of bias explained by staleness |")
w("|---|---|---|---|---|---|---|")
for q in G:
    t = R["test1_stale"][q]
    share = t["bias_explained_by_staleness_pct"]
    share = "n/a (no clear bias)" if share is None else f"{share}%"
    w(f"| {q} | {t['slope_bps_per_pct']['b']} | {t['slope_bps_per_pct']['t']} | {t['mean_gap_flat_days']} | "
      f"{t['mean_gap_up_days']} / {t['mean_gap_down_days']} | {t['bse_higher_flat_days_pct']}% | {share} |")
t = R["test1_stale"]["Q1 (least)"]
w("")
if t["slope_bps_per_pct"]["b"] < 0 and sig(t["slope_bps_per_pct"]):
    w(f"**Reading:** for the least-traded fifth the slope is negative and significant (t = {t['slope_bps_per_pct']['t']}), "
      "so BSE closes do lag NSE moves for thin stocks.")
else:
    w("**Reading:** no clear negative slope for the least-traded fifth, so stale BSE closes are not the main story.")
if t["mean_gap_flat_days"] is not None and t["mean_gap_flat_days"] > 2:
    w(f" But the bias is still {t['mean_gap_flat_days']} bps on days when NSE barely moved, which staleness "
      "cannot explain. Something else adds to it.\n")
else:
    w(" The bias mostly disappears on flat days, which points to staleness.\n")
m = R["test1_market_days_q1"]
w(f"Least-traded fifth by market direction: mean gap {m['mean_gap_market_up_bps']} bps on up-market days, "
  f"{m['mean_gap_market_down_bps']} bps on down-market days; the market fell on {m['share_of_days_market_down_pct']}% of days.\n")

# Test 2
w("## Test 2: thin BSE days\n")
for fl, d in R["test2_thin_days"].items():
    w(f"**{d['label']}**\n")
    w("| Group | Days flagged | Mean gap flagged / other (bps) | BSE higher flagged / other | Difference (t) |")
    w("|---|---|---|---|---|")
    if not any(q in d for q in ["Q1 (least)", "Q3", "Q5 (most)"]):
        w("| (this flag never varies in your data, so it cannot be tested) | | | | |")
    for q in ["Q1 (least)", "Q3", "Q5 (most)"]:
        if q in d:
            x = d[q]
            w(f"| {q} | {x['share_of_days_flagged_pct']}% | {x['mean_gap_flagged_bps']} / {x['mean_gap_other_bps']} | "
              f"{x['bse_higher_flagged_pct']}% / {x['bse_higher_other_pct']}% | {x['difference']['b']} ({x['difference']['t']}) |")
    w("")
w("**Reading:** if the bias is much larger on flagged days, it comes from how BSE's close is formed when "
  "there is almost no trading (the closing-price rule or a few buyer-initiated trades).\n")

# Test 3
w("## Test 3: who closes the gap the next day?\n")
w("| Group | NSE moves toward BSE (% of gap) | t | BSE moves back toward NSE (% of gap) | t | Gap closed next day | Share of correction by BSE |")
w("|---|---|---|---|---|---|---|")
for q in ["all"] + G:
    x = R["test3_who_adjusts"][q]
    w(f"| {q} | {round(x['nse_next_return']['b'] * 100, 1)} | {x['nse_next_return']['t']} | "
      f"{round(-x['bse_next_return']['b'] * 100, 1)} | {x['bse_next_return']['t']} | {x['gap_closed_next_day_pct']}% | "
      f"{x['share_of_correction_by_bse_pct']}% |")
x = R["test3_who_adjusts"]["Q1 (least)"]
w("")
if x["share_of_correction_by_bse_pct"] is not None and x["share_of_correction_by_bse_pct"] > 70:
    w("**Reading:** for thin stocks BSE does most of the correcting, so BSE's close is the noisy one and NSE's "
      "close is the better price. This supports treating the bias as noise in BSE's close.\n")
elif x["share_of_correction_by_bse_pct"] is not None and x["share_of_correction_by_bse_pct"] < 30:
    w("**Reading:** NSE does most of the correcting, so BSE's close seems to carry information NSE has not yet "
      "priced. That would be a surprising and interesting finding; check it carefully.\n")
else:
    w("**Reading:** both exchanges share the correction, so both closes contain some noise.\n")

# Test 4
w("## Test 4: selection\n")
w("| Group | NSE days also traded on BSE | NSE return on BSE days / other days (%) | Within-company difference (t) | NSE value vs usual, BSE days / other | NSE close location, BSE days / other |")
w("|---|---|---|---|---|---|")
for q in G:
    x = R["test4_selection"][q]
    if "within_company_difference_pct" not in x:
        w(f"| {q} | {x['share_of_nse_days_also_on_bse_pct']}% | no variation | | | |"); continue
    loc = f"{x.get('nse_close_location_on_bse_days')} / {x.get('nse_close_location_other_days')}"
    w(f"| {q} | {x['share_of_nse_days_also_on_bse_pct']}% | {x['nse_return_on_bse_days_pct']} / {x['nse_return_other_days_pct']} | "
      f"{x['within_company_difference_pct']['b']} ({x['within_company_difference_pct']['t']}) | "
      f"{x['nse_value_vs_usual_on_bse_days']} / {x['nse_value_vs_usual_other_days']} | {loc} |")
w("\n**Reading:** if thin stocks trade on BSE mainly on days with higher NSE returns, more NSE activity or NSE "
  "closes near the day's high, BSE trading is happening on days of buying pressure, and part of the bias is "
  "selection rather than mispricing. Close location runs from 0 (closed at the low) to 1 (closed at the high).\n")

# Level shift
ls = R["level_shift"]
w("## Check: the level shift in the daily median gap\n")
w(f"Estimated break date: **{ls['break_date']}** (sup-F = {ls['F_stat']}; {ls['note']})\n")
w("| Measure | Before | After |")
w("|---|---|---|")
for k in ls["before"]:
    w(f"| {k} | {ls['before'][k]} | {ls['after'][k]} |")
w(f"\nCompanies only before the break: {ls['stocks_only_before']}; only after: {ls['stocks_only_after']}.\n")
w("| Group | Median abs gap before | after |")
w("|---|---|---|")
for q, v in ls["median_gap_by_group"].items():
    w(f"| {q} | {v['before']} | {v['after']} |")
w("\n**What to check:** if the number of stocks, the share of one-price BSE days or the BSE value share jumps at "
  "the break, look first at your pipeline's commit history around that date (a file format or source change). "
  "If nothing in your data changed, search NSE, BSE and SEBI circulars from the weeks before the break "
  "(tick sizes, closing-price method, closing auction). If the jump appears in every liquidity group, a "
  "market-wide rule change is more likely than a change in the mix of stocks.\n")

for k in ["stocks_10_days_before", "stocks_10_days_after", "same_companies_median_gap", "abs_market_move_pct",
          "shift_without_control", "shift_controlling_for_market_move"]:
    if k in ls:
        w(f"- {k}: {ls[k]}")
w("")

if "closing_auction" in R:
    ca = R["closing_auction"]
    w("## Natural experiment: the closing auction (from " + ca["date"] + ")\n")
    w(f"Treated group: {ca['treated_group']} ({ca['treated_companies']} companies; {ca['control_companies']} in the control group). "
      f"{ca['days_before']} trading days before, {ca['days_after']} after.\n")
    w("| | Before | After |")
    w("|---|---|---|")
    w(f"| Median abs gap, treated (bps) | {ca['median_gap_treated']['before']} | {ca['median_gap_treated']['after']} |")
    w(f"| Median abs gap, control (bps) | {ca['median_gap_control']['before']} | {ca['median_gap_control']['after']} |")
    w(f"| Mean signed gap, treated (bps) | {ca['signed_gap_treated']['before']} | {ca['signed_gap_treated']['after']} |")
    w(f"| BSE higher, treated | {ca['bse_higher_treated_pct']['before']}% | {ca['bse_higher_treated_pct']['after']}% |")
    w(f"| Identical closes, treated | {ca['identical_close_treated_pct']['before']}% | {ca['identical_close_treated_pct']['after']}% |")
    w(f"\nDifference-in-differences on daily medians: {ca['did_daily_median']} ; controlling for the market move: "
      f"{ca['did_controlling_market_move']}. First day: {ca['treated_first_day']} bps; last 10 days: {ca['treated_last_10_days']} bps.\n")
    w("**Check before trusting this:** pick 3-4 large stocks, look up their official closing prices on NSE's and BSE's "
      "websites for a few days just before and after the start date, and confirm they match your files. That rules "
      "out a change in the downloaded files themselves.\n")

open("puzzle_results.md", "w").write("\n".join(L))
print("puzzle_results.md written")
