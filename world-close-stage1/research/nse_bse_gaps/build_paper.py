"""Step 5: assemble the paper (NSE_BSE_closing_price_gaps.pdf) from results.json and the figures."""
import json
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

R = json.load(open("results.json"))
F = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Serif", F + "DejaVuSerif.ttf"))
pdfmetrics.registerFont(TTFont("Serif-B", F + "DejaVuSerif-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Serif-I", F + "DejaVuSerif-Italic.ttf"))
pdfmetrics.registerFont(TTFont("Serif-BI", F + "DejaVuSerif-BoldItalic.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("Serif", normal="Serif", bold="Serif-B", italic="Serif-I", boldItalic="Serif-BI")

INK = colors.HexColor("#1f2a44")
body = ParagraphStyle("body", fontName="Serif", fontSize=9.6, leading=14.2, alignment=TA_JUSTIFY, spaceAfter=7)
title = ParagraphStyle("title", fontName="Serif-B", fontSize=16.5, leading=21, alignment=TA_CENTER, textColor=INK, spaceAfter=6)
sub = ParagraphStyle("sub", fontName="Serif", fontSize=10, leading=14, alignment=TA_CENTER, spaceAfter=3)
h1 = ParagraphStyle("h1", fontName="Serif-B", fontSize=11.5, leading=15, textColor=INK, spaceBefore=12, spaceAfter=5)
h2 = ParagraphStyle("h2", fontName="Serif-BI", fontSize=10, leading=14, textColor=INK, spaceBefore=8, spaceAfter=4)
abstract = ParagraphStyle("abs", parent=body, fontSize=9, leading=13, leftIndent=1.2 * cm, rightIndent=1.2 * cm)
caption = ParagraphStyle("cap", fontName="Serif", fontSize=8, leading=11, alignment=TA_JUSTIFY, spaceBefore=3, spaceAfter=10,
                         textColor=colors.HexColor("#333333"))
cell = ParagraphStyle("cell", fontName="Serif", fontSize=8, leading=10.5)
cellb = ParagraphStyle("cellb", fontName="Serif-B", fontSize=8, leading=10.5)
ref = ParagraphStyle("ref", fontName="Serif", fontSize=8.6, leading=12, leftIndent=0.6 * cm, firstLineIndent=-0.6 * cm, spaceAfter=4)

P = lambda t, s=body: Paragraph(t, s)
f1 = lambda x: f"{x:,.1f}"
f0 = lambda x: f"{x:,.0f}"
fi = lambda x: f"{x:,}"


def table(rows, widths, header=1, align_right_from=1):
    data = [[Paragraph(str(c), cellb if r < header else cell) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, hAlign="CENTER")
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.9, INK), ("LINEBELOW", (0, header - 1), (-1, header - 1), 0.5, INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.9, INK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    return t


def figure(path, cap, width=15.5 * cm):
    from PIL import Image as PI
    w, h = PI.open(path).size
    return KeepTogether([Image(path, width=width, height=width * h / w), P(cap, caption)])


xs, d, ar = R["xs"]["coef"], R["desc"], R["ar1"]
liq, sig, rb = R["by_liq"], R["signed_by_liq"], R["robust"]
mult = lambda b: 10 ** b
pct_change = lambda b: (10 ** b - 1) * 100
n_full, n_clean = R["filters"][0], R["filters"][-1]

story = []
story += [Spacer(1, 0.4 * cm),
          P("Same Company, Two Prices: How Closely Do India’s Two Stock Exchanges Agree on the Close?", title),
          P("Udit Goyal", sub),
          P("October 2026", sub),
          P('Data and code: <link href="https://github.com/udit20112007/WORLD-CLOSE" color="#284b8c">github.com/udit20112007/WORLD-CLOSE</link>', sub),
          Spacer(1, 0.5 * cm)]

story += [P("<b>Abstract</b>", ParagraphStyle("ah", parent=h2, alignment=TA_CENTER)), P(
    f"Thousands of Indian companies are listed on both the National Stock Exchange (NSE) and BSE, so each of them "
    f"ends every trading day with two official closing prices. Using a year of daily closing data that I collected "
    f"myself ({R['period'][0]} to {R['period'][1]}, {R['days']} trading days), I match "
    f"{fi(n_clean['companies'])} companies across the two exchanges and study {fi(n_clean['stock_days'])} pairs of "
    f"closing prices. The two closes are usually close but rarely identical: the median gap is {f1(d['median'])} basis "
    f"points, and {f1(R['share_over']['50'])}% of stock-days differ by more than half a percent. Liquidity explains "
    f"most of the variation across companies. A tenfold increase in a stock’s trading value is associated with a "
    f"median gap about {f0(-pct_change(xs['log_value']['b']))}% smaller, and trading value alone accounts for "
    f"{f0(R['xs_liq_only_r2'] * 100)}% of the cross-sectional variation in typical gaps. The gaps do not last: "
    f"only about {f0(ar['beta'] * 100)}% of a gap carries over to the next day on average, and for the most "
    f"actively traded stocks almost none does. Gaps widen modestly on days when the market moves a lot. I also "
    f"document a puzzle: for thinly traded stocks, BSE tends to close slightly above NSE. Overall, the evidence "
    f"fits a market where the law of one price holds well for liquid stocks, and where the gaps that remain look "
    f"like short-lived noise rather than lasting mispricing.", abstract), Spacer(1, 0.3 * cm)]

# 1 -------------------------------------------------------------------------------------------
story += [P("1. Introduction", h1), P(
    "The law of one price is one of the simplest ideas in finance: the same asset should not sell for two different "
    "prices at the same time. If it did, a trader could buy where it is cheap, sell where it is dear, and pocket "
    "the difference. In practice, the idea is tested whenever the same security trades in more than one place, and "
    "a long line of research shows that the law can bend. Twin shares such as Royal Dutch and Shell traded for "
    "years at prices inconsistent with their fixed claim on the same profits (Froot and Dabora, 1999), and "
    "parent companies have at times been valued below the stakes they held in their own subsidiaries (Lamont and "
    "Thaler, 2003). The usual explanation is that arbitrage is costly and risky, so small or awkward deviations "
    "can survive (Shleifer and Vishny, 1997)."), P(
    "India offers an unusually clean setting for asking the question on a large scale. Most large and mid-sized "
    "Indian companies are listed on both NSE and BSE. The shares are the same security, identified by the same "
    "ISIN, settled through interoperable clearing, and owned by the same kind of investors. Unlike twin shares or "
    "cross-listings in different countries, there is no exchange-rate risk, no difference in time zone, and no "
    "conversion between share classes. If the two closing prices differ, the difference has to come from how and "
    "where the stock happened to trade that afternoon."), P(
    "This paper asks three simple questions. How large are the gaps between NSE and BSE closing prices? Which "
    "stocks have larger gaps? And do gaps close, or do they persist from one day to the next? To answer them I "
    "built an automated data pipeline that downloads each exchange’s official end-of-day file every trading day, "
    "and I use one year of that data."), P(
    f"The main findings are easy to state. First, gaps are small but common: the median absolute gap is "
    f"{f1(d['median'])} basis points (0.{int(round(d['median'])):02d}%), and the two closes are exactly equal on only "
    f"{f1(R['share_zero'])}% of stock-days. Second, liquidity is the dominant explanation. Across companies, the "
    f"typical gap falls steadily as trading activity rises, from about {f0(liq['Q1 (least)']['median_gap'])} basis "
    f"points for the least-traded fifth of companies to about {f1(liq['Q5 (most)']['median_gap'])} for the most-traded "
    f"fifth. Third, gaps are short-lived. On average only {f0(ar['beta'] * 100)}% of today’s gap shows up again "
    f"tomorrow, and after a gap larger than half a percent the next day’s gap is smaller "
    f"{f0(R['after_big']['smaller_next_day'])}% of the time. Fourth, there is a small but systematic tendency for "
    f"BSE to close above NSE in thinly traded stocks, which I cannot fully explain with this data."), P(
    "Section 2 describes the institutional setting. Section 3 explains the data and how the sample is built. "
    "Section 4 presents the results, Section 5 checks their robustness, and Section 6 asks whether the gaps are "
    "large enough to trade on. Section 7 discusses limitations, and Section 8 concludes.")]

# 2 -------------------------------------------------------------------------------------------
story += [P("2. Institutional background", h1), P(
    f"NSE and BSE are India’s two main stock exchanges, both based in Mumbai. For companies listed on both, NSE "
    f"handles the great majority of trading. In my sample, BSE accounts for {f1(R['value_total_share_bse_pct'])}% of "
    f"the combined value traded in dual-listed stocks, and the median company does only "
    f"{f1(R['bse_share_median_pct'])}% of its trading on BSE. This matters for interpretation: BSE’s closing price "
    f"is usually based on far fewer trades than NSE’s."), P(
    "Neither exchange uses the very last trade of the day as its official closing price. As I understand the "
    "exchanges’ published methodologies, both compute the official close as a weighted average of trades in the "
    "final half hour of continuous trading. The close is therefore an average over a window, and two exchanges "
    "can arrive at different averages simply because different trades happened on each during that window. A "
    "stock that trades only a handful of times on BSE in that half hour will have a BSE close that reflects just "
    "those few trades, including whether they happened to execute at the bid or the ask. This mechanical source "
    "of difference is important when interpreting the results: a gap between the two closes is not, by itself, "
    "evidence of a price at which anyone could have traded."), P(
    "Moving shares between the exchanges is straightforward. Since 2019, the clearing corporations of the "
    "exchanges have been interoperable, so a position bought on one exchange can be sold on the other. This "
    "makes the setting close to a textbook case: the same security, the same settlement, two prices.")]

# 3 -------------------------------------------------------------------------------------------
filt = [["Step", "Companies", "Stock-days"]]
names = ["All companies matched by ISIN on both exchanges", "NSE regular equity series (EQ) only", "Share price of at least Rs 20"]
for nm, f in zip(names, R["filters"][:3]):
    filt.append([nm, fi(f["companies"]), fi(f["stock_days"])])
story += [P("3. Data and sample", h1), P(
    "The data come from the official daily “bhavcopy” files that both exchanges publish after each session. Each "
    "file lists every stock that traded that day, with its open, high, low and official closing price, the "
    "previous close, the number of shares traded and the value traded. I wrote a pipeline that downloads both "
    "files every trading day, standardises their columns, and stores them; a year of history was filled in from "
    "each exchange’s archive. The same pipeline powers a public website that shows every stock’s close on 33 "
    "exchanges worldwide, but this paper uses only the two Indian exchanges."), P(
    "Companies are matched across the two exchanges by ISIN, the international identifier that is the same for "
    "a given security wherever it trades. Because each exchange’s file only includes stocks that actually "
    "traded, a matched pair means the stock traded on both exchanges that day. I then apply two filters, shown "
    "in Table 1. I keep only NSE’s regular equity series (EQ). This removes stocks in restricted segments, such as "
    "those that may only be traded for delivery (BE) or that belong to companies that have not met listing "
    "requirements (BZ). I also drop stocks priced below Rs 20, where the minimum price step of one paisa is large "
    "relative to the price and a one-tick difference becomes a big percentage gap."),
    KeepTogether([P("<b>Table 1.</b> Sample construction", caption), table(filt, [9.6 * cm, 2.6 * cm, 2.8 * cm])]),
    Spacer(1, 6), P(
    "The filters matter more than their size suggests. In an early version of the analysis without them, the gap "
    "on one day was strongly correlated with the gap on the next (a correlation of 0.86), which seemed to imply that "
    "gaps were extremely persistent. Looking at the companies behind that result showed that it was driven almost "
    "entirely by a few restricted penny stocks with huge, stable gaps, some of them priced well below one rupee. Once "
    "these were removed, the correlation fell to 0.15. I report this because it is a good example of how a few "
    "unusual securities can dominate a statistic computed over half a million observations.")]

# 4 -------------------------------------------------------------------------------------------
story += [P("4. Results", h1), P(
    "For each stock and day, I define the gap as the BSE close minus the NSE close, divided by the average of the "
    "two, and express it in basis points (one basis point is one hundredth of a percent). A positive gap means BSE "
    "closed higher. Most of the analysis uses the absolute gap, which measures disagreement regardless of direction.")]

story += [P("4.1 How large are the gaps?", h2)]
t2 = [["Statistic", "Value"],
      ["Median absolute gap", f"{f1(d['median'])} bps"], ["Mean absolute gap", f"{f1(d['mean'])} bps"],
      ["75th / 90th percentile", f"{f1(d['p75'])} / {f1(d['p90'])} bps"],
      ["95th / 99th percentile", f"{f1(d['p95'])} / {f1(d['p99'])} bps"],
      ["Share of stock-days with identical closes", f"{f1(R['share_zero'])}%"],
      ["Share with gap above 10 / 25 bps", f"{f1(R['share_over']['10'])}% / {f1(R['share_over']['25'])}%"],
      ["Share with gap above 50 / 100 / 200 bps",
       f"{f1(R['share_over']['50'])}% / {f1(R['share_over']['100'])}% / {f1(R['share_over']['200'])}%"],
      ["Share of stock-days where BSE closed higher", f"{f1(R['share_bse_higher'])}%"]]
story += [P(
    f"Table 2 summarises the distribution. The typical gap is small, {f1(d['median'])} basis points, but the "
    f"distribution has a long tail: the mean is {f1(d['mean'])} basis points, almost three times the median, and one "
    f"stock-day in twenty has a gap above {f0(d['p95'])} basis points. The two closes are identical on only "
    f"{f1(R['share_zero'])}% of stock-days, which is what one would expect if each close is an average of "
    f"different trades. Across the whole sample there is no tendency for either exchange to close higher: BSE is "
    f"above NSE on {f1(R['share_bse_higher'])}% of stock-days and the median signed gap is essentially zero. "
    f"Figure 1 shows the shape of the distribution, which is symmetric, sharply peaked at zero and heavy-tailed."),
    KeepTogether([P("<b>Table 2.</b> The size of NSE–BSE closing-price gaps (clean sample)", caption),
                  table(t2, [9.6 * cm, 5.4 * cm])]), Spacer(1, 8),
    figure("figures/fig1_distribution.png",
           "<b>Figure 1.</b> Distribution of the signed gap between BSE and NSE closing prices, in basis points of "
           "the average of the two prices. The vertical axis is logarithmic, so the tails are visible. Values beyond "
           "±150 basis points are collected in the end bins.")]

story += [P("4.2 Which stocks have larger gaps?", h2)]
qt = [["Liquidity group", "Companies", "Median daily value traded on NSE", "Median absolute gap"]]
for k in ["Q1 (least)", "Q2", "Q3", "Q4", "Q5 (most)"]:
    v = liq[k]
    lab = {"Q1 (least)": "Least-traded fifth", "Q5 (most)": "Most-traded fifth"}.get(k, f"{k[1]}th fifth" if k[1] != "2" else "2nd fifth")
    lab = {"Q3": "3rd fifth", "Q4": "4th fifth"}.get(k, lab)
    qt.append([lab, fi(v["n"]), f"Rs {v['median_value_cr']:,.2f} crore", f"{f1(v['median_gap'])} bps"])
coef_rows = [["Variable", "Coefficient", "Std. error", "t-statistic"]]
labels = {"log_value": "log<sub>10</sub> median daily value traded on NSE", "bse_share_pct": "BSE share of trading (%)",
          "vol_pct": "Daily return volatility (%)", "inv_price": "Relative tick size (100 / price)", "Intercept": "Constant"}
for k in ["log_value", "bse_share_pct", "vol_pct", "inv_price", "Intercept"]:
    c = xs[k]
    coef_rows.append([labels[k], f"{c['b']:.4f}", f"{c['se']:.4f}", f"{c['t']:.1f}"])
coef_rows.append(["Companies / R<super>2</super>", f"{fi(R['xs']['n'])}", "", f"{R['xs']['r2']:.3f}"])
story += [P(
    "To see which stocks have larger gaps, I summarise each company by its median absolute gap over the year and "
    "relate it to its characteristics. Table 3 groups companies into fifths by how much they trade, and the "
    "pattern is striking. The typical gap falls at every step, from "
    f"{f1(liq['Q1 (least)']['median_gap'])} basis points in the least-traded fifth to "
    f"{f1(liq['Q5 (most)']['median_gap'])} in the most-traded fifth, a difference of about "
    f"{f0(liq['Q1 (least)']['median_gap'] / liq['Q5 (most)']['median_gap'])} times. Figure 2 shows the same "
    "relationship company by company. On logarithmic scales it is close to a straight line, which means the gap "
    "shrinks by a roughly constant percentage for each doubling of trading activity."),
    KeepTogether([P("<b>Table 3.</b> Typical gaps by liquidity group (companies with at least 60 matched days)", caption),
                  table(qt, [3.6 * cm, 2.2 * cm, 5.0 * cm, 4.2 * cm])]), Spacer(1, 8),
    figure("figures/fig2_liquidity.png",
           "<b>Figure 2.</b> Each grey point is one company: its median daily value traded on NSE against its median "
           "absolute gap over the year. The line joins the medians within twenty equal-sized groups of companies. "
           "Both axes are logarithmic.")]
story += [P(
    f"Table 4 reports a regression of each company’s (log) median gap on four characteristics: how much it trades, "
    f"how much of that trading happens on BSE, how volatile it is, and how large one price step is relative to its "
    f"price. Standard errors are robust to heteroskedasticity. The model explains {f0(R['xs']['r2'] * 100)}% of the "
    f"variation in typical gaps, and trading value on its own explains {f0(R['xs_liq_only_r2'] * 100)}%. The "
    f"coefficient on log trading value is {xs['log_value']['b']:.2f}: a company that trades ten times as much has, "
    f"other things equal, a typical gap about {f0(-pct_change(xs['log_value']['b']))}% smaller. Volatility pushes "
    f"the other way: each extra percentage point of daily volatility is associated with a gap about "
    f"{f0(pct_change(xs['vol_pct']['b'] ))}% larger, which makes sense, since prices move more within the closing "
    f"window of a volatile stock. A larger BSE share of trading goes with smaller gaps (about "
    f"{f0(-pct_change(xs['bse_share_pct']['b'] * 10))}% smaller for ten extra percentage points), consistent with the "
    f"idea that BSE’s close is noisier when it rests on fewer trades. The relative tick size has a small negative "
    f"coefficient. Its sign is the opposite of what I expected, and since prices below Rs 20 have already been "
    f"removed, I do not read much into it."),
    KeepTogether([P("<b>Table 4.</b> What explains a company’s typical gap? Dependent variable: log<sub>10</sub> of the "
                    "company’s median absolute gap (bps). OLS with heteroskedasticity-robust standard errors.", caption),
                  table(coef_rows, [7.4 * cm, 2.5 * cm, 2.5 * cm, 2.6 * cm])]), Spacer(1, 6)]

story += [P("4.3 Do gaps close?", h2)]
arl = R["ar1_by_liq"]
story += [P(
    f"If gaps were genuine mispricing that took time to correct, today’s gap would predict tomorrow’s. I test this "
    f"by regressing each stock’s gap on the next trading day on its gap today. The slope is {ar['beta']:.3f} "
    f"(standard error {ar['se']:.3f}, clustered by company, {fi(ar['n'])} observations). In other words, only about "
    f"{f0(ar['beta'] * 100)}% of a gap carries over to the next day on average, which corresponds to a half-life of "
    f"well under a day. Persistence is highest for the least-traded stocks, with a slope of "
    f"{arl['Q1 (least)']:.3f}, and falls to {arl['Q5 (most)']:.3f} for the most-traded fifth, where tomorrow’s gap is "
    f"essentially unrelated to today’s."), P(
    f"Large gaps behave the same way. On the {fi(R['after_big']['n'])} stock-days with a gap above 50 basis points, "
    f"the next day’s gap was smaller {f0(R['after_big']['smaller_next_day'])}% of the time, it shrank by a median of "
    f"{f0(R['after_big']['median_shrink'])}%, and it changed direction {f0(R['after_big']['sign_flip'])}% of the time. "
    f"That last number is telling: a gap that flips sign about half the time looks much more like random noise "
    f"around zero than like a mispricing waiting to be corrected. Figure 3 shows this directly. For all three "
    f"liquidity groups, the average gap tomorrow is nearly flat whatever today’s gap was."),
    figure("figures/fig3_reversion.png",
           "<b>Figure 3.</b> Average gap on the next trading day against today’s gap, for three liquidity groups. "
           "The dotted line shows what complete persistence would look like. All three groups are close to flat; "
           "the least-traded group sits slightly above zero throughout, reflecting the level effect discussed in "
           "Section 4.4.")]

story += [P("4.4 A puzzle: BSE closes higher for thinly traded stocks", h2)]
sg = [["Liquidity group", "Mean signed gap", "Median signed gap", "BSE closed higher"]]
for k, lab in [("Q1 (least)", "Least-traded fifth"), ("Q2", "2nd fifth"), ("Q3", "3rd fifth"), ("Q4", "4th fifth"),
               ("Q5 (most)", "Most-traded fifth")]:
    v = sig[k]
    sg.append([lab, f"{v['mean']:+.1f} bps", f"{v['median']:+.1f} bps", f"{v['bse_higher_pct']:.1f}%"])
story += [P(
    f"Figure 3 reveals something the absolute gap hides. For the least-traded stocks, the average gap is positive "
    f"whatever happened the day before, which means BSE tends to close slightly above NSE. Table 5 shows this is "
    f"systematic. In the least-traded fifth, the mean signed gap is {sig['Q1 (least)']['mean']:+.1f} basis points and BSE "
    f"closes higher on {f1(sig['Q1 (least)']['bse_higher_pct'])}% of stock-days; {R['q1_positive_share']}% of these "
    f"companies have a positive median gap over the year. The effect fades steadily with liquidity and reverses "
    f"slightly for the most-traded stocks, where BSE closes higher on only "
    f"{f1(sig['Q5 (most)']['bse_higher_pct'])}% of days."),
    KeepTogether([P("<b>Table 5.</b> The direction of the gap (BSE minus NSE) by liquidity group", caption),
                  table(sg, [4.0 * cm, 3.6 * cm, 3.6 * cm, 3.8 * cm])]), Spacer(1, 6), P(
    "I do not have a definitive explanation, and the data cannot separate the possibilities. Three candidates seem "
    "worth investigating. The first is the composition of trading: if the few trades in illiquid stocks on BSE "
    "late in the day are more often buyer-initiated, they would execute nearer the ask and lift BSE’s average. The "
    "second is the closing-price rule itself: when very few trades occur on BSE in the final half hour, the way the "
    "exchange computes or substitutes the close could differ from NSE’s in a way that has a direction. The third is "
    "selection: a stock only enters the sample on days it traded on BSE, and the days when it trades there may "
    "not be typical days. Telling these apart would need intraday trade data, which is beyond this paper.")]

story += [P("4.5 Do gaps widen when the market is under stress?", h2), P(
    f"Limits-to-arbitrage arguments suggest that gaps should widen when markets are volatile, because prices move "
    f"faster within the closing window and arbitrage capital is stretched. To check, I compute the median absolute "
    f"gap across all stocks for each day and compare it with the size of that day’s market move, measured as the "
    f"absolute value of the median stock’s return. The two are positively related (correlation "
    f"{R['daily']['corr']:.2f}). A regression with standard errors that allow for correlation across nearby days "
    f"gives a slope of {R['daily']['b']:.1f} basis points of gap for each percentage point of market movement "
    f"(t = {R['daily']['t']:.1f}). The effect is real but modest. On the calmer half of days the typical gap was "
    f"{f1(R['calm_vs_stress']['calm'])} basis points, and on the most turbulent tenth it rose to "
    f"{f1(R['calm_vs_stress']['stress'])}. Figure 4 shows the daily series."),
    figure("figures/fig4_daily.png",
           "<b>Figure 4.</b> The line is the median absolute gap across all stocks on each day (left axis). The bars "
           "show the size of that day’s market move, measured as the absolute return of the median stock (right "
           "axis).")]

# 5 -------------------------------------------------------------------------------------------
h1r, h2r = rb["first half"], rb["second half"]
rt = [["Check", "Liquidity slope", "R<super>2</super>", "Persistence (next-day slope)"],
      ["Full year (main sample)", f"{R['xs_liq_only_slope']:.3f}", f"{R['xs_liq_only_r2']:.3f}", f"{ar['beta']:.3f}"],
      [f"First half of the year ({h1r['from']} to {h1r['to']})", f"{h1r['liq_slope']:.3f}", f"{h1r['liq_r2']:.3f}", f"{h1r['ar1']:.3f}"],
      [f"Second half of the year ({h2r['from']} to {h2r['to']})", f"{h2r['liq_slope']:.3f}", f"{h2r['liq_r2']:.3f}", f"{h2r['ar1']:.3f}"],
      ["Mean instead of median gap per company", f"{rb['mean_gap_liq_slope']:.3f}", f"{rb['mean_gap_r2']:.3f}", "—"],
      ["Gaps capped at ±200 bps", "—", "—", f"{rb['ar1_winsorised']:.3f}"]]
story += [P("5. Robustness", h1), P(
    "Table 6 repeats the two central results on different cuts of the data. Splitting the year in half gives almost "
    "identical answers in each half: the liquidity relationship has a slope of about −0.33 to −0.36 and explains "
    "around 80% of the variation, and the next-day persistence is the same in both halves. Using each company’s "
    "mean gap rather than its median gives the same picture, as does capping extreme gaps before measuring "
    "persistence, which if anything lowers it further. The results do not depend on a particular period or on a few "
    "extreme observations."),
    KeepTogether([P("<b>Table 6.</b> Robustness checks. The liquidity slope is from a regression of log<sub>10</sub> "
                    "median gap on log<sub>10</sub> trading value alone, so every row is comparable.",
                    caption),
                  table(rt, [7.6 * cm, 2.4 * cm, 1.6 * cm, 3.4 * cm])]), Spacer(1, 6)]

# 6 -------------------------------------------------------------------------------------------
story += [P("6. Is there money on the table?", h1), P(
    f"A natural question is whether these gaps could be traded profitably. The evidence suggests not, for three "
    f"reasons. First, the gaps are smallest exactly where trading is easiest. Among the most-traded fifth of "
    f"companies, a gap above 50 basis points occurs on only {f1(R['share_liquid_over_50'])}% of stock-days, and above "
    f"100 basis points on {f1(R['share_liquid_over_100'])}%. The larger gaps are concentrated in stocks where trading "
    f"a meaningful amount would itself move the price. Second, the closing price is an average over a half-hour "
    f"window, not a price anyone could trade at, so observing a gap after the fact does not mean a trader could have "
    f"captured it. Third, a round trip involves brokerage, exchange fees and taxes on both legs, and once those "
    f"are counted the typical gap of around 11 basis points looks small. Combined with the finding that gaps "
    f"largely disappear by the next day, the picture is of a market that arbitrageurs keep in line for the stocks "
    f"where it matters, with the remaining differences reflecting noise in how each exchange’s close is formed.")]

# 7 -------------------------------------------------------------------------------------------
story += [P("7. Limitations", h1), P(
    "The study has several limitations. It uses one year of data, so it cannot say whether the patterns are "
    "stable across market regimes or how they changed with past reforms. It uses only official closing prices; "
    "with intraday trades and quotes, one could measure gaps at the same instant, separate bid-ask effects from "
    "genuine disagreement, and resolve the BSE puzzle in Section 4.4. Prices are not adjusted for corporate "
    "actions, which does not affect same-day gaps between exchanges but does affect the volatility measure; I "
    "reduce this by excluding daily moves larger than 25%. The market-stress measure is a simple proxy based on "
    "the median stock’s return rather than an index. Finally, the description of each exchange’s closing-price "
    "rule is based on my reading of their published methodologies, and readers interested in the mechanism should "
    "consult the exchanges’ current rules directly.")]

# 8 -------------------------------------------------------------------------------------------
story += [P("8. Conclusion", h1), P(
    "For more than two thousand Indian companies, two exchanges publish a closing price every day. Those two prices "
    "usually agree to within a tenth of a percent, rarely agree exactly, and disagree most for the stocks that trade "
    "least. The disagreements do not last: they largely vanish by the next day and switch direction about as often "
    "as not, which is what one would expect if they mostly reflect the particular trades that happened to land in "
    "each exchange’s closing window. In that sense, the law of one price holds well where it is easiest to enforce. "
    "The small, persistent tendency for BSE to close higher in thinly traded stocks is the one pattern that does not "
    "fit neatly, and it would be a natural starting point for work with intraday data.")]

story += [P("Data and code", h1), P(
    'The data were collected with an automated pipeline that downloads both exchanges’ official daily files and '
    'stores them in a public repository, <link href="https://github.com/udit20112007/WORLD-CLOSE" color="#284b8c">github.com/udit20112007/WORLD-CLOSE</link>. '
    'The same data feed a public website, <link href="https://udit20112007.github.io/WORLD-CLOSE/" color="#284b8c">udit20112007.github.io/WORLD-CLOSE</link>, '
    'which shows daily closing prices for 33 exchanges. The code that produces every number, table and figure in '
    'this paper is in the <link href="https://github.com/udit20112007/WORLD-CLOSE/tree/main/world-close-stage1/research/nse_bse_gaps" color="#284b8c">research/nse_bse_gaps</link> folder of the repository, '
    'with instructions for rerunning it.'), P("Acknowledgements", h2), P(
    "I thank the National Stock Exchange of India and BSE for publishing their daily market data openly, which made "
    "this study possible, and the developers of the open-source Python libraries used throughout the work, "
    "including pandas, NumPy, statsmodels and Matplotlib. Any errors are my own.")]

refs = [P("References", h1)]
for r in [
    "Amihud, Y. (2002). Illiquidity and stock returns: cross-section and time-series effects. <i>Journal of Financial Markets</i>, 5(1), 31–56.",
    "Froot, K. A., and Dabora, E. M. (1999). How are stock prices affected by the location of trade? <i>Journal of Financial Economics</i>, 53(2), 189–216.",
    "Gagnon, L., and Karolyi, G. A. (2010). Multi-market trading and arbitrage. <i>Journal of Financial Economics</i>, 97(1), 53–80.",
    "Hasbrouck, J. (1995). One security, many markets: determining the contributions to price discovery. <i>Journal of Finance</i>, 50(4), 1175–1199.",
    "Lamont, O. A., and Thaler, R. H. (2003). Can the market add and subtract? Mispricing in tech stock carve-outs. <i>Journal of Political Economy</i>, 111(2), 227–268.",
    "Roll, R. (1984). A simple implicit measure of the effective bid-ask spread in an efficient market. <i>Journal of Finance</i>, 39(4), 1127–1139.",
    "Shleifer, A., and Vishny, R. W. (1997). The limits of arbitrage. <i>Journal of Finance</i>, 52(1), 35–55."]:
    refs.append(P(r, ref))
story.append(KeepTogether(refs))


def on_page(canv, doc):
    canv.saveState()
    canv.setFont("Serif", 7.5); canv.setFillColor(colors.HexColor("#666666"))
    if doc.page > 1:
        canv.drawString(2.2 * cm, A4[1] - 1.3 * cm, "Same Company, Two Prices")
    canv.drawCentredString(A4[0] / 2, 1.2 * cm, str(doc.page))
    canv.restoreState()


doc = SimpleDocTemplate("NSE_BSE_closing_price_gaps.pdf", pagesize=A4,
                        leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2.0 * cm, bottomMargin=2.0 * cm,
                        title="Same Company, Two Prices: How Closely Do India's Two Stock Exchanges Agree on the Close?",
                        author="Udit Goyal")
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print("built")
