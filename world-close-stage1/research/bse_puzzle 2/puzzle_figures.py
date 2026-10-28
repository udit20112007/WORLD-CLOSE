"""Step 3 (puzzle study): figures, in the same style as the first paper."""
import json, pathlib
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

pathlib.Path("figures").mkdir(exist_ok=True)
F = pd.read_pickle("work/puzzle_frames.pkl"); c, day, brk = F["c"], F["day"], F["brk"]
R = json.load(open("results_puzzle.json"))
plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.labelsize": 9, "figure.dpi": 200})
INK, ACC, MUTED = "#1f2a44", "#b5472b", "#8a93a3"
SHOW = [("Q1 (least)", ACC, "Least-traded fifth"), ("Q3", MUTED, "Middle fifth"), ("Q5 (most)", INK, "Most-traded fifth")]

# Figure 5: average signed gap against the day's NSE return (the stale-price test)
fig, ax = plt.subplots(figsize=(6.2, 3.1))
edges = np.arange(-5, 5.01, 0.5)
for q, col, lab in SHOW:
    d = c[(c.liq_q == q) & c.ret_n.between(-5, 5)]
    b = d.groupby(pd.cut(d.ret_n, edges), observed=True).agg(x=("ret_n", "mean"), y=("gap_bps", "mean"), n=("gap_bps", "size"))
    b = b[b.n >= 50]
    ax.plot(b.x, b.y, "o-", ms=3, lw=1.1, color=col, label=lab)
ax.axhline(0, color=MUTED, lw=.5); ax.axvline(0, color=MUTED, lw=.5)
ax.set_xlabel("Stock's NSE return that day (%)"); ax.set_ylabel("Average gap, BSE minus NSE (bps)")
ax.legend(frameon=False, fontsize=7.5)
fig.tight_layout(); fig.savefig("figures/fig5_stale.png"); plt.close(fig)

# Figure 6: who closes the gap the next day?
t3 = R["test3_who_adjusts"]
groups = ["Q1 (least)", "Q2", "Q3", "Q4", "Q5 (most)"]
labels = ["Least", "2nd", "3rd", "4th", "Most"]
bn = [t3[g]["nse_next_return"]["b"] * 100 for g in groups]
bb = [-t3[g]["bse_next_return"]["b"] * 100 for g in groups]
x = np.arange(len(groups)); w = .38
fig, ax = plt.subplots(figsize=(6.2, 2.9))
ax.bar(x - w / 2, bb, w, color=ACC, label="BSE moves back toward NSE")
ax.bar(x + w / 2, bn, w, color=INK, label="NSE moves toward BSE")
ax.set_xticks(x, labels); ax.set_xlabel("Liquidity group (fifths of companies by trading value)")
ax.set_ylabel("% of today's gap closed\nby next day's move")
ax.axhline(0, color=MUTED, lw=.5)
ax.legend(frameon=False, fontsize=7.5, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.0))
fig.tight_layout(); fig.savefig("figures/fig6_who_adjusts.png"); plt.close(fig)

# Figure 7: daily median gap with the estimated break date
fig, ax = plt.subplots(figsize=(6.2, 2.7))
ax.plot(day.index, day.median_gap, color=INK, lw=1)
ax.axvline(brk, color=ACC, lw=1, ls="--")
pre, post = day[day.index < brk].median_gap.mean(), day[day.index >= brk].median_gap.mean()
ax.hlines(pre, day.index.min(), brk, color=ACC, lw=1.2); ax.hlines(post, brk, day.index.max(), color=ACC, lw=1.2)
ax.text(brk, ax.get_ylim()[1], f"  estimated break: {brk.date()}", color=ACC, fontsize=7.5, va="top")
ax.set_ylabel("Median |gap| across stocks (bps)")
fig.autofmt_xdate(); fig.tight_layout(); fig.savefig("figures/fig7_level_shift.png"); plt.close(fig)
# Figure 8: the closing auction (only if the sample covers its start)
dm = F.get("cas_daily")
if dm is not None:
    ca = R["closing_auction"]
    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    ax.plot(dm.index, dm.treated, color=ACC, lw=1.1, marker="o", ms=2,
            label="Treated: " + ("stocks with derivatives" if "fo_stocks" in ca["treated_group"] else "most-traded fifth"))
    ax.plot(dm.index, dm.control, color=INK, lw=1.1, marker="o", ms=2, label="All other companies")
    ax.axvline(pd.Timestamp(ca["date"]), color=MUTED, ls="--", lw=1)
    ax.text(pd.Timestamp(ca["date"]), ax.get_ylim()[1], "  closing auction starts", color=MUTED, fontsize=7.5, va="top")
    ax.set_ylabel("Median |gap| (bps)"); ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=7.5, loc="center left")
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig("figures/fig8_closing_auction.png"); plt.close(fig)
print("figures written")
