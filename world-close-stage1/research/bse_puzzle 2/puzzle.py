"""Step 2 (puzzle study): why does BSE close above NSE for thinly traded stocks?

Runs four tests plus a check on the August 2026 level shift, and writes results_puzzle.json.
Uses the same clean sample and liquidity groups as the first paper.

  Test 1  Stale prices: does the gap move opposite to the day's NSE return?
  Test 2  Thin BSE days: is the bias concentrated on days with almost no BSE trading?
  Test 3  Who adjusts: after a gap, does NSE move toward BSE, or BSE back toward NSE?
  Test 4  Selection: are the days a thin stock trades on BSE unusual days on NSE?
  Check   Level shift: when did the daily median gap jump, and what changed at that date?
"""
import json, os
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

GROUPS = ["Q1 (least)", "Q2", "Q3", "Q4", "Q5 (most)"]
r1 = lambda x: None if x is None or pd.isna(x) else round(float(x), 1)
r3 = lambda x: None if x is None or pd.isna(x) else round(float(x), 3)


def ols(formula, data, cluster="isin"):
    """OLS with standard errors clustered by company."""
    g = pd.factorize(data[cluster])[0]
    return smf.ols(formula, data=data).fit(cov_type="cluster", cov_kwds={"groups": g})


def coef(fit, name):
    return {"b": r3(fit.params[name]), "se": r3(fit.bse[name]), "t": r1(fit.tvalues[name]), "n": int(fit.nobs)}


def add_returns(df, close, prev, out):
    """Daily return in %, from the previous close if the files have it, else from the previous row."""
    if prev in df.columns:
        r = df[close] / df[prev] - 1
    else:
        df = df.sort_values(["isin", "date"])
        r = df.groupby("isin")[close].pct_change()
        gap_days = df.groupby("isin")["date"].diff().dt.days
        r[gap_days > 5] = np.nan                                  # only consecutive trading days
    r[r.abs() > 0.25] = np.nan                                    # unadjusted splits and bonuses
    df[out] = r * 100
    return df


p = pd.read_pickle("work/pairs_full.pkl")
R = {"columns_available": sorted(p.columns)}
has = lambda col: col in p.columns

# ---- same clean sample as the first paper ---------------------------------------------------
c = p[(p.series_n == "EQ") & (p.mid >= 20) & (p.volume_n > 0) & (p.volume_b > 0)].copy()
c = c.sort_values(["isin", "date"]).reset_index(drop=True)
c = add_returns(c, "close_n", "prev_close_n", "ret_n")
c = add_returns(c, "close_b", "prev_close_b", "ret_b")

# ---- liquidity groups: reuse the first paper's if available, so the groups are identical -----
FIRST = [f for f in ("work/paper_frames.pkl", "../nse_bse_gaps/work/paper_frames.pkl") if os.path.exists(f)]
if FIRST:
    st = pd.read_pickle(FIRST[0])["st"][["liq_q"]].copy()
    R["liquidity_groups_from"] = f"first paper ({FIRST[0]})"
else:
    s = c.groupby("isin").agg(days=("date", "size"), value_n=("value_n", "median"))
    s = s[s.days >= 60]
    s["liq_q"] = pd.qcut(np.log10(s.value_n), 5, labels=GROUPS)
    st = s[["liq_q"]]
    R["liquidity_groups_from"] = "recomputed (companies with at least 60 matched days)"
st["liq_q"] = st["liq_q"].astype(str)
c = c.merge(st, left_on="isin", right_index=True, how="inner")
R["sample"] = {"stock_days": int(len(c)), "companies": int(c["isin"].nunique()),
               "from": str(c.date.min().date()), "to": str(c.date.max().date())}

# ---- Test 1: stale prices ---------------------------------------------------------------------
# If BSE's close is stale for a thin stock, then on a day NSE rises the BSE close lags behind
# (gap < 0), and on a day NSE falls it stays above (gap > 0). So the slope of the gap on the NSE
# return should be clearly negative for thin stocks. The intercept is the bias left over on a day
# when NSE did not move at all, which staleness cannot explain.
t1 = {}
for q in GROUPS:
    g = c[(c.liq_q == q)].dropna(subset=["ret_n"])
    f = ols("gap_bps ~ ret_n", g)
    up, down, flat = g[g.ret_n > 0.5], g[g.ret_n < -0.5], g[g.ret_n.abs() <= 0.25]
    mean_gap, mean_ret = g.gap_bps.mean(), g.ret_n.mean()
    t1[q] = {"slope_bps_per_pct": coef(f, "ret_n"), "intercept_bps": coef(f, "Intercept"),
             "mean_gap_bps": r1(mean_gap), "mean_nse_return_pct": r3(mean_ret),
             "mean_gap_up_days": r1(up.gap_bps.mean()), "mean_gap_down_days": r1(down.gap_bps.mean()),
             "mean_gap_flat_days": r1(flat.gap_bps.mean()),
             "bse_higher_up_days_pct": r1((up.gap_bps > 0).mean() * 100),
             "bse_higher_down_days_pct": r1((down.gap_bps > 0).mean() * 100),
             "bse_higher_flat_days_pct": r1((flat.gap_bps > 0).mean() * 100),
             # how much of the average bias staleness can account for: slope x average return
             # only meaningful when there is a clear average bias to explain (at least 2 bps)
             "bias_explained_by_staleness_pct": r1(100 * f.params["ret_n"] * mean_ret / mean_gap) if abs(mean_gap) >= 2 else None}
R["test1_stale"] = t1

# Market-wide version: classify days by the median stock's NSE return.
mkt = c.groupby("date").ret_n.median().rename("mkt_ret")
c = c.merge(mkt, left_on="date", right_index=True)
q1 = c[c.liq_q == "Q1 (least)"]
R["test1_market_days_q1"] = {"mean_gap_market_up_bps": r1(q1[q1.mkt_ret > 0].gap_bps.mean()),
                             "mean_gap_market_down_bps": r1(q1[q1.mkt_ret < 0].gap_bps.mean()),
                             "share_of_days_market_down_pct": r1((mkt < 0).mean() * 100)}

# ---- Test 2: thin BSE days -------------------------------------------------------------------
flags = {}
if has("high_b") and has("low_b"):
    c["one_price_b"] = c.high_b == c.low_b                         # every BSE trade at one price
    flags["one_price_b"] = "BSE high equals BSE low (all trades at one price)"
if has("open_b"):
    c["close_eq_open_b"] = c.close_b == c.open_b
    flags["close_eq_open_b"] = "BSE close equals BSE open"
if has("trades_b"):
    c["few_trades_b"] = c.trades_b <= 3
    flags["few_trades_b"] = "3 or fewer trades on BSE"
c["low_volume_b"] = c.volume_b <= c.groupby("isin").volume_b.transform(lambda s: s.quantile(0.2))
flags["low_volume_b"] = "BSE volume in the stock's own lowest fifth of days"

t2 = {}
for fl, label in flags.items():
    t2[fl] = {"label": label}
    for q in ["Q1 (least)", "Q3", "Q5 (most)"]:
        g = c[c.liq_q == q].copy()
        g["flag"] = g[fl].astype(int)
        if g.flag.nunique() < 2:
            continue
        f = ols("gap_bps ~ flag", g)
        t2[fl][q] = {"share_of_days_flagged_pct": r1(g.flag.mean() * 100),
                     "mean_gap_flagged_bps": r1(g[g.flag == 1].gap_bps.mean()),
                     "mean_gap_other_bps": r1(g[g.flag == 0].gap_bps.mean()),
                     "bse_higher_flagged_pct": r1((g[g.flag == 1].gap_bps > 0).mean() * 100),
                     "bse_higher_other_pct": r1((g[g.flag == 0].gap_bps > 0).mean() * 100),
                     "difference": coef(f, "flag")}
R["test2_thin_days"] = t2

# ---- Test 3: which exchange adjusts? -----------------------------------------------------------
# gap is (BSE - NSE) / mid. If BSE's close is noise, the next day BSE moves back toward NSE
# (negative slope for BSE's next return) and NSE does not react. If BSE's close carries real
# information, NSE moves toward BSE (positive slope for NSE's next return).
c = c.sort_values(["isin", "date"])
nx = c.groupby("isin")[["close_n", "close_b", "date"]].shift(-1)
c["next_ret_n_bps"] = (nx.close_n / c.close_n - 1) * 1e4
c["next_ret_b_bps"] = (nx.close_b / c.close_b - 1) * 1e4
ok = ((nx.date - c.date).dt.days <= 5) & (c.next_ret_n_bps.abs() < 2500) & (c.next_ret_b_bps.abs() < 2500)
a = c[ok].copy()
t3 = {}
for q in ["all"] + GROUPS:
    g = a if q == "all" else a[a.liq_q == q]
    fn, fb = ols("next_ret_n_bps ~ gap_bps", g), ols("next_ret_b_bps ~ gap_bps", g)
    bn, bb = float(fn.params["gap_bps"]), float(fb.params["gap_bps"])
    total = bn - bb                                                     # how much the gap closes in total
    t3[q] = {"nse_next_return": coef(fn, "gap_bps"), "bse_next_return": coef(fb, "gap_bps"),
             "gap_closed_next_day_pct": r1(total * 100),
             "share_of_correction_by_bse_pct": r1(100 * (-bb) / total) if total > 0 else None}
R["test3_who_adjusts"] = t3

# ---- Test 4: selection ---------------------------------------------------------------------------
# A thin stock only enters the sample on days it trades on BSE. Are those days different on NSE?
n = pd.read_pickle("work/nse_days.pkl")
n = n[(n.series == "EQ") & (n.close >= 20) & (n.volume > 0)].copy()
n = add_returns(n, "close", "prev_close", "ret")
n = n.merge(st, left_on="isin", right_index=True, how="inner")
n["rel_value"] = n.value / n.groupby("isin").value.transform("median")
if "high" in n.columns and "low" in n.columns:
    rng = (n.high - n.low).replace(0, np.nan)
    n["close_location"] = (n.close - n.low) / rng                       # 0 = closed at low, 1 = at high
t4 = {}
for q in GROUPS:
    g = n[n.liq_q == q].dropna(subset=["ret"]).copy()
    g["on_bse_i"] = g.on_bse.astype(int)
    if g.on_bse_i.nunique() < 2:
        t4[q] = {"share_of_nse_days_also_on_bse_pct": r1(g.on_bse_i.mean() * 100), "note": "no variation"}
        continue
    for v in ["ret", "on_bse_i"]:                                       # within-company comparison
        g[v + "_dm"] = g[v] - g.groupby("isin")[v].transform("mean")
    f = ols("ret_dm ~ on_bse_i_dm - 1", g)
    t4[q] = {"share_of_nse_days_also_on_bse_pct": r1(g.on_bse_i.mean() * 100),
             "nse_return_on_bse_days_pct": r3(g[g.on_bse].ret.mean()),
             "nse_return_other_days_pct": r3(g[~g.on_bse].ret.mean()),
             "within_company_difference_pct": coef(f, "on_bse_i_dm"),
             "nse_value_vs_usual_on_bse_days": r3(g[g.on_bse].rel_value.median()),
             "nse_value_vs_usual_other_days": r3(g[~g.on_bse].rel_value.median())}
    if "close_location" in g.columns:
        t4[q]["nse_close_location_on_bse_days"] = r3(g[g.on_bse].close_location.mean())
        t4[q]["nse_close_location_other_days"] = r3(g[~g.on_bse].close_location.mean())
R["test4_selection"] = t4

# ---- Check: the level shift in the daily median gap --------------------------------------------
c["abs_gap"] = c.gap_bps.abs()
day = c.groupby("date").agg(median_gap=("abs_gap", "median"), stocks=("isin", "nunique"),
                            median_price=("mid", "median"))
vb, vn = c.groupby("date").value_b.sum(), c.groupby("date").value_n.sum()
day["bse_value_share_pct"] = vb / (vb + vn) * 100
if "one_price_b" in c.columns:
    day["one_price_b_pct"] = c.groupby("date").one_price_b.mean() * 100
day = day.sort_index()
y = day.median_gap.values
best = None
for k in range(int(len(y) * 0.1), int(len(y) * 0.9)):                 # single break in the mean
    sse = ((y[:k] - y[:k].mean()) ** 2).sum() + ((y[k:] - y[k:].mean()) ** 2).sum()
    if best is None or sse < best[1]:
        best = (k, sse)
k = best[0]
sse0 = ((y - y.mean()) ** 2).sum()
F = (sse0 - best[1]) / (best[1] / (len(y) - 2))
brk = day.index[k]
before, after = day.iloc[:k], day.iloc[k:]
R["level_shift"] = {"break_date": str(brk.date()), "F_stat": r1(F),
                    "note": "F is the sup-F from scanning every break date; it needs larger critical values than an ordinary F test (roughly 9 at 5%).",
                    "before": {col: r1(before[col].mean()) for col in day.columns},
                    "after": {col: r1(after[col].mean()) for col in day.columns}}
pre, post = c[c.date < brk], c[c.date >= brk]
R["level_shift"]["stocks_only_before"] = int(len(set(pre["isin"]) - set(post["isin"])))
R["level_shift"]["stocks_only_after"] = int(len(set(post["isin"]) - set(pre["isin"])))
R["level_shift"]["median_gap_by_group"] = {q: {"before": r1(pre[pre.liq_q == q].abs_gap.median()),
                                               "after": r1(post[post.liq_q == q].abs_gap.median())} for q in GROUPS}

# Was the change abrupt in the data (a sign of a collection change)? Compare the 10 days either side.
R["level_shift"]["stocks_10_days_before"] = r1(day.stocks.iloc[max(0, k - 10):k].mean())
R["level_shift"]["stocks_10_days_after"] = r1(day.stocks.iloc[k:k + 10].mean())
# The same companies on both sides, so a change in the mix of companies cannot drive it.
both = set(pre["isin"]) & set(post["isin"])
R["level_shift"]["same_companies_median_gap"] = {"before": r1(pre[pre["isin"].isin(both)].abs_gap.median()),
                                                 "after": r1(post[post["isin"].isin(both)].abs_gap.median())}
# Did the market become more volatile? (The first paper found gaps widen on big market days.)
day["abs_mkt"] = c.groupby("date").mkt_ret.first().abs()
day["post"] = (day.index >= brk).astype(int)
R["level_shift"]["abs_market_move_pct"] = {"before": r3(day.abs_mkt[day.post == 0].mean()),
                                           "after": r3(day.abs_mkt[day.post == 1].mean())}
dd = day.dropna(subset=["abs_mkt"])
f0 = smf.ols("median_gap ~ post", data=dd).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
f1 = smf.ols("median_gap ~ post + abs_mkt", data=dd).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
R["level_shift"]["shift_without_control"] = coef(f0, "post")
R["level_shift"]["shift_controlling_for_market_move"] = coef(f1, "post")
R["level_shift"]["market_move_coef"] = coef(f1, "abs_mkt")

# ---- Natural experiment: the Closing Auction Session (CAS), live from 3 August 2026 ---------------
# From that date the official close of stocks with derivatives is set by a separate closing auction
# on each exchange; other stocks keep the 30-minute VWAP close. If a file fo_stocks.csv with a
# 'symbol' column (NSE symbols of the stocks in the derivatives segment) is in this folder, it defines
# the treated group; otherwise the most-traded fifth is used as a proxy (most derivatives stocks are in it).
CAS = pd.Timestamp("2026-08-03")
dates = sorted(c.date.unique())
if CAS in dates and len(dates) - dates.index(CAS) >= 10:
    if os.path.exists("fo_stocks.csv"):
        fo = set(pd.read_csv("fo_stocks.csv")["symbol"].astype(str).str.strip())
        c["treated"] = c.symbol_n.astype(str).isin(fo)
        how = "stocks listed in fo_stocks.csv (derivatives segment)"
    else:
        c["treated"] = c.liq_q == "Q5 (most)"
        how = "most-traded fifth of companies (proxy for stocks with derivatives)"
    i = dates.index(CAS)
    win = c[c.date.isin(dates[max(0, i - 40):])].copy()               # 40 trading days before, all after
    win["post"] = (win.date >= CAS).astype(int)
    dm = win.groupby(["date", "treated"]).abs_gap.median().unstack()
    dm.columns = ["control", "treated"]
    dm["diff"] = dm.treated - dm.control
    dm["post"] = (dm.index >= CAS).astype(int)
    dm["abs_mkt"] = win.groupby("date").mkt_ret.first().abs()
    fd = smf.ols("diff ~ post", data=dm).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    fdm = smf.ols("diff ~ post + abs_mkt", data=dm.dropna()).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    t, k_ = win[win.treated], win[~win.treated]
    R["closing_auction"] = {
        "date": str(CAS.date()), "treated_group": how,
        "treated_companies": int(t["isin"].nunique()), "control_companies": int(k_["isin"].nunique()),
        "days_before": int(min(40, i)), "days_after": int(len(dates) - i),
        "median_gap_treated": {"before": r1(t[t.post == 0].abs_gap.median()), "after": r1(t[t.post == 1].abs_gap.median())},
        "median_gap_control": {"before": r1(k_[k_.post == 0].abs_gap.median()), "after": r1(k_[k_.post == 1].abs_gap.median())},
        "treated_first_day": r1(dm.loc[CAS, "treated"]),
        "treated_last_10_days": r1(dm.treated.iloc[-10:].mean()),
        "did_daily_median": coef(fd, "post"), "did_controlling_market_move": coef(fdm, "post"),
        "signed_gap_treated": {"before": r1(t[t.post == 0].gap_bps.mean()), "after": r1(t[t.post == 1].gap_bps.mean())},
        "bse_higher_treated_pct": {"before": r1((t[t.post == 0].gap_bps > 0).mean() * 100),
                                   "after": r1((t[t.post == 1].gap_bps > 0).mean() * 100)},
        "identical_close_treated_pct": {"before": r1((t[t.post == 0].abs_gap == 0).mean() * 100),
                                        "after": r1((t[t.post == 1].abs_gap == 0).mean() * 100)},
        # auctions clear at the price of a limit order, and limit orders cluster on whole rupees
        "whole_rupee_close_treated_pct": {
            ex: {"before": r1((np.round(t[t.post == 0][col] * 100) % 100 == 0).mean() * 100),
                 "after": r1((np.round(t[t.post == 1][col] * 100) % 100 == 0).mean() * 100)}
            for ex, col in [("nse", "close_n"), ("bse", "close_b")]},
        "whole_rupee_close_control_pct": {
            ex: {"before": r1((np.round(k_[k_.post == 0][col] * 100) % 100 == 0).mean() * 100),
                 "after": r1((np.round(k_[k_.post == 1][col] * 100) % 100 == 0).mean() * 100)}
            for ex, col in [("nse", "close_n"), ("bse", "close_b")]},
        "by_group": {q: {"before": r1(win[(win.liq_q == q) & (win.post == 0)].abs_gap.median()),
                         "after": r1(win[(win.liq_q == q) & (win.post == 1)].abs_gap.median())} for q in GROUPS}}
    cas_daily = dm
else:
    cas_daily = None

pd.to_pickle({"c": c, "day": day, "brk": brk, "cas_daily": cas_daily}, "work/puzzle_frames.pkl")
json.dump(R, open("results_puzzle.json", "w"), indent=1)
print(json.dumps(R, indent=1))
