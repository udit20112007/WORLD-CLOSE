import pathlib, numpy as np, pandas as pd, matplotlib
pathlib.Path('figures').mkdir(exist_ok=True)
matplotlib.use("Agg")
import matplotlib.pyplot as plt
F = pd.read_pickle("work/paper_frames.pkl"); c, st, day, mr = F["c"], F["st"], F["day"], F["mr"]
plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 10, "axes.labelsize": 9, "figure.dpi": 200})
INK, ACC, MUTED = "#1f2a44", "#b5472b", "#8a93a3"

# Figure 1: distribution of the signed gap
fig, ax = plt.subplots(figsize=(6.2, 2.7))
g = c.gap_bps.clip(-150, 150)
ax.hist(g, bins=np.arange(-150, 151, 2.5), color=INK, alpha=.85)
ax.set_yscale("log"); ax.set_xlabel("BSE close minus NSE close (basis points of the average price)")
ax.set_ylabel("Stock-days (log scale)"); ax.axvline(0, color=ACC, lw=.8)
ax.text(.99, .92, "Values beyond ±150 bps are\nshown in the end bins", transform=ax.transAxes, ha="right", va="top", fontsize=7.5, color=MUTED)
fig.tight_layout(); fig.savefig("figures/fig1_distribution.png"); plt.close(fig)

# Figure 2: liquidity and the typical gap, one point per company
fig, ax = plt.subplots(figsize=(6.2, 3.1))
ax.scatter(st.value_n / 1e7, st.med_gap, s=3, color=MUTED, alpha=.35, lw=0)
bins = pd.qcut(st.log_value, 20)
b = st.groupby(bins, observed=True).agg(x=("value_n", "median"), y=("med_gap", "median"))
ax.plot(b.x / 1e7, b.y, "o-", color=ACC, ms=3.5, lw=1.2, label="Median within each twentieth of companies")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("Median daily value traded on NSE (Rs crore, log scale)"); ax.set_ylabel("Median |gap| (bps, log scale)")
ax.legend(frameon=False, fontsize=7.5, loc="upper right")
fig.tight_layout(); fig.savefig("figures/fig2_liquidity.png"); plt.close(fig)

# Figure 3: does a gap carry over to the next day? binned, by liquidity group
fig, ax = plt.subplots(figsize=(6.2, 3.1))
edges = np.arange(-150, 151, 15)
for q, colour, lab in [("Q1 (least)", ACC, "Least-traded fifth"), ("Q3", MUTED, "Middle fifth"), ("Q5 (most)", INK, "Most-traded fifth")]:
    d = mr[(mr.liq_q == q) & mr.gap_bps.between(-150, 150)]
    bb = d.groupby(pd.cut(d.gap_bps, edges), observed=True).agg(x=("gap_bps", "mean"), y=("next_gap", "mean"), n=("next_gap", "size"))
    bb = bb[bb.n >= 50]
    ax.plot(bb.x, bb.y, "o-", ms=3, lw=1.1, color=colour, label=lab)
ax.plot([-60, 60], [-60, 60], ls=":", color=MUTED, lw=.9)
ax.text(30, 44, "if gaps fully persisted", fontsize=7, color=MUTED, rotation=24, ha="center")
ax.axhline(0, color=MUTED, lw=.5)
ax.set_xlim(-155, 155); ax.set_ylim(-60, 60)
ax.set_xlabel("Gap today (bps)"); ax.set_ylabel("Average gap next day (bps)")
ax.legend(frameon=False, fontsize=7.5, loc="lower right")
fig.tight_layout(); fig.savefig("figures/fig3_reversion.png"); plt.close(fig)

# Figure 4: daily median gap and the size of the market's move
fig, ax = plt.subplots(figsize=(6.2, 2.8))
ax.plot(day.index, day.median_gap, color=INK, lw=1, label="Median |gap| across stocks (bps, left)")
ax.set_ylabel("Median |gap| (bps)")
ax2 = ax.twinx(); ax2.bar(day.index, day.abs_mkt, color=ACC, alpha=.35, width=1.0, label="Size of the day's market move (% , right)")
ax2.set_ylabel("|Median stock return| (%)"); ax2.spines["top"].set_visible(False)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=7.5, loc="upper left")
fig.autofmt_xdate(); fig.tight_layout(); fig.savefig("figures/fig4_daily.png"); plt.close(fig)
print("figures written")
