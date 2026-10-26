"""Step 3: robustness checks and the remaining numbers quoted in the paper."""
import json, numpy as np, pandas as pd
import statsmodels.formula.api as smf
F = pd.read_pickle("work/paper_frames.pkl"); c, st, mr = F["c"], F["st"], F["mr"]
R = json.load(open("results.json")); out = {}
mid = c.date.sort_values().iloc[len(c)//2]
for label, half in [("first half", c[c.date < mid]), ("second half", c[c.date >= mid])]:
    s = half.groupby("isin").agg(med_gap=("abs_gap","median"), value_n=("value_n","median"), days=("date","size"))
    s = s[s.days >= 30]; s["lg"] = np.log10(s.med_gap.clip(lower=.5)); s["lv"] = np.log10(s.value_n)
    f = smf.ols("lg ~ lv", data=s).fit(cov_type="HC1")
    h = half.dropna(subset=["next_gap"]); h = h[(h.next_date - h.date).dt.days <= 5]
    a = smf.ols("next_gap ~ gap_bps", data=h).fit()
    out[label] = {"from": str(half.date.min().date()), "to": str(half.date.max().date()),
                  "median_gap": round(float(half.abs_gap.median()),1), "liq_slope": round(float(f.params["lv"]),3),
                  "liq_r2": round(float(f.rsquared),3), "ar1": round(float(a.params["gap_bps"]),3)}
s = c.groupby("isin").agg(mean_gap=("abs_gap","mean"), value_n=("value_n","median"), days=("date","size"))
s = s[s.days >= 60]; f = smf.ols("np.log10(mean_gap) ~ np.log10(value_n)", data=s).fit(cov_type="HC1")
out["mean_gap_liq_slope"] = round(float(f.params.iloc[1]),3); out["mean_gap_r2"] = round(float(f.rsquared),3)
w = mr.copy(); w["g"] = w.gap_bps.clip(-200,200); w["n"] = w.next_gap.clip(-200,200)
out["ar1_winsorised"] = round(float(smf.ols("n ~ g", data=w).fit().params["g"]),3)
R["robust"] = out; json.dump(R, open("results.json","w"), indent=1); print(json.dumps(out, indent=1))

# --- further numbers quoted in the paper ------------------------------------------------
c2 = c.merge(st[["liq_q"]], left_on="isin", right_index=True)
t = c2.groupby("liq_q", observed=True).agg(signed_mean=("gap_bps", "mean"), signed_median=("gap_bps", "median"),
                                           bse_higher=("gap_bps", lambda s: (s > 0).mean() * 100))
R["signed_by_liq"] = {str(k): {"mean": round(float(v.signed_mean), 1), "median": round(float(v.signed_median), 1),
                               "bse_higher_pct": round(float(v.bse_higher), 1)} for k, v in t.iterrows()}
q1 = c2[c2.liq_q == "Q1 (least)"].groupby("isin").gap_bps.median()
R["q1_positive_share"] = round(float((q1 > 0).mean() * 100)); R["q1_median_of_medians"] = round(float(q1.median()), 1)
R["bse_share_median_pct"] = round(float(st.bse_share.median() * 100), 1)
R["value_total_share_bse_pct"] = round(float(c.value_b.sum() / (c.value_b.sum() + c.value_n.sum()) * 100), 1)
R["price_median"] = round(float(st.price.median())); R["vol_median_pct"] = round(float(st.vol_pct.median()), 2)
m = smf.ols("log_gap ~ log_value", data=st).fit(cov_type="HC1")
R["xs_liq_only_slope"] = round(float(m.params["log_value"]), 3)
json.dump(R, open("results.json", "w"), indent=1)
print("results.json complete")
