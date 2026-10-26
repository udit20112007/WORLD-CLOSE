"""Step 2: the analysis behind every number in the paper. Writes results.json."""
import json, numpy as np, pandas as pd
import statsmodels.formula.api as smf

p = pd.read_pickle("work/pairs.pkl")
R = {}
R["period"] = [str(p.date.min().date()), str(p.date.max().date())]
R["days"] = int(p.date.nunique())
steps = [("All companies matched by ISIN on both exchanges", p)]
s1 = p[p.series_n == "EQ"];                          steps.append(("NSE regular equity series (EQ) only", s1))
s2 = s1[s1.mid >= 20];                               steps.append(("Share price of at least Rs 20", s2))
s3 = s2[(s2.volume_n > 0) & (s2.volume_b > 0)];      steps.append(("Traded on both exchanges that day", s3))
R["filters"] = [{"step": n, "companies": int(d["isin"].nunique()), "stock_days": int(len(d))} for n, d in steps]
c = s3.copy()
c["abs_gap"] = c.gap_bps.abs()

# --- descriptive
a = c.abs_gap
R["desc"] = {k: round(float(v), 1) for k, v in {"mean": a.mean(), "median": a.median(), "p75": a.quantile(.75),
             "p90": a.quantile(.9), "p95": a.quantile(.95), "p99": a.quantile(.99)}.items()}
R["share_over"] = {str(t): round(float((a > t).mean()) * 100, 1) for t in (10, 25, 50, 100, 200)}
R["share_zero"] = round(float((a == 0).mean()) * 100, 1)
R["signed_median"] = round(float(c.gap_bps.median()), 2)
R["share_bse_higher"] = round(float((c.gap_bps > 0).mean()) * 100, 1)

# --- stock-level characteristics
c = c.sort_values(["isin", "date"])
c["ret_n"] = c.groupby("isin").close_n.pct_change()
c.loc[c.ret_n.abs() > 0.25, "ret_n"] = np.nan          # unadjusted splits/bonuses would look like huge moves
c["bse_share"] = c.value_b / (c.value_n + c.value_b)
st = c.groupby("isin").agg(name=("name_n", "first"), days=("date", "size"), med_gap=("abs_gap", "median"),
                           value_n=("value_n", "median"), bse_share=("bse_share", "median"),
                           price=("mid", "median"), vol=("ret_n", "std"))
st = st[st.days >= 60].dropna()
st["log_value"] = np.log10(st.value_n)
st["log_gap"] = np.log10(st.med_gap.clip(lower=0.5))
st["inv_price"] = 100 / st.price                     # relative tick: one paisa as bps of price, x100
st["vol_pct"] = st.vol * 100
st["bse_share_pct"] = st.bse_share * 100
R["stocks_in_regression"] = int(len(st))
m = smf.ols("log_gap ~ log_value + bse_share_pct + inv_price + vol_pct", data=st).fit(cov_type="HC1")
R["xs"] = {"n": int(m.nobs), "r2": round(float(m.rsquared), 3),
           "coef": {k: {"b": round(float(m.params[k]), 4), "se": round(float(m.bse[k]), 4), "t": round(float(m.tvalues[k]), 1)}
                    for k in m.params.index}}
m1 = smf.ols("log_gap ~ log_value", data=st).fit(cov_type="HC1")
R["xs_liq_only_r2"] = round(float(m1.rsquared), 3)
st["liq_q"] = pd.qcut(st.log_value, 5, labels=["Q1 (least)", "Q2", "Q3", "Q4", "Q5 (most)"])
R["by_liq"] = {str(k): {"median_gap": round(float(g.med_gap.median()), 1),
                        "median_value_cr": round(float(g.value_n.median() / 1e7), 2), "n": int(len(g))}
               for k, g in st.groupby("liq_q", observed=True)}

# --- mean reversion
c["next_gap"] = c.groupby("isin").gap_bps.shift(-1)
c["next_date"] = c.groupby("isin").date.shift(-1)
mr = c.dropna(subset=["next_gap"])
mr = mr[(mr.next_date - mr.date).dt.days <= 5]       # consecutive trading days only
fit = smf.ols("next_gap ~ gap_bps", data=mr).fit(cov_type="cluster", cov_kwds={"groups": mr["isin"]})
beta = float(fit.params["gap_bps"])
R["ar1"] = {"beta": round(beta, 3), "se": round(float(fit.bse["gap_bps"]), 3), "n": int(fit.nobs),
            "half_life_days": round(float(np.log(0.5) / np.log(abs(beta))), 2) if 0 < abs(beta) < 1 else None}
mr = mr.merge(st[["liq_q"]], left_on="isin", right_index=True, how="inner")
R["ar1_by_liq"] = {}
for q, g in mr.groupby("liq_q", observed=True):
    f = smf.ols("next_gap ~ gap_bps", data=g).fit()
    R["ar1_by_liq"][str(q)] = round(float(f.params["gap_bps"]), 3)
big = mr[mr.abs_gap > 50]
R["after_big"] = {"n": int(len(big)), "smaller_next_day": round(float((big.next_gap.abs() < big.abs_gap).mean()) * 100, 0),
                  "sign_flip": round(float((np.sign(big.next_gap) != np.sign(big.gap_bps)).mean()) * 100, 0),
                  "median_shrink": round(float((1 - big.next_gap.abs() / big.abs_gap).median()) * 100, 0)}

# --- market conditions: daily gap level vs market move and breadth
day = c.groupby("date").agg(mean_gap=("abs_gap", "mean"), median_gap=("abs_gap", "median"),
                            mkt=("ret_n", "median"), down=("ret_n", lambda s: (s < 0).mean()))
day["abs_mkt"] = day.mkt.abs() * 100
day = day.dropna()
f = smf.ols("median_gap ~ abs_mkt", data=day).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
R["daily"] = {"n": int(f.nobs), "b": round(float(f.params["abs_mkt"]), 2), "t": round(float(f.tvalues["abs_mkt"]), 1),
              "r2": round(float(f.rsquared), 3), "median_daily_gap": round(float(day.median_gap.median()), 1),
              "corr": round(float(day.median_gap.corr(day.abs_mkt)), 2)}
calm, stress = day[day.abs_mkt <= day.abs_mkt.quantile(.5)], day[day.abs_mkt >= day.abs_mkt.quantile(.9)]
R["calm_vs_stress"] = {"calm": round(float(calm.median_gap.median()), 1), "stress": round(float(stress.median_gap.median()), 1)}

# --- tradability
for t in (25, 50, 100):
    R[f"share_liquid_over_{t}"] = round(float((c[c["isin"].isin(st[st.liq_q == "Q5 (most)"].index)].abs_gap > t).mean()) * 100, 1)

pd.to_pickle({"c": c, "st": st, "day": day, "mr": mr}, "work/paper_frames.pkl")
json.dump(R, open("results.json", "w"), indent=1)
print(json.dumps(R, indent=1))
