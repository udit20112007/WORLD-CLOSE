"""Step 5 (puzzle study): build the paper (BSE_closes_higher.pdf) from results_puzzle.json and figures 5-7.

Every number and every interpretation in the text is taken from results_puzzle.json, so the paper
always matches the data. The wording of each finding depends on what the results show (for example,
whether a slope is significant), so read the PDF carefully, check that each sentence is right, and
edit the text below in your own words where you want to.

Before building, fill in FIRST_PAPER_DOI (and THIS_PAPER_DOI once Zenodo gives you one).
"""
import datetime, json, os
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FIRST_PAPER_DOI = "10.5281/zenodo.23666692"      # <- the DOI of "Same Company, Two Prices"
THIS_PAPER_DOI = ""                              # <- fill in after Zenodo gives this paper a DOI
REPO = "https://github.com/udit20112007/WORLD-CLOSE"
TITLE = "Why Does BSE Close Higher? Stale Prices, Thin Trading and the Law of One Price in India"
SHORT = "Why Does BSE Close Higher?"
AUTHOR = "Udit Goyal"
DATE = datetime.date.today().strftime("%B %Y")

R = json.load(open("results_puzzle.json"))
G = ["Q1 (least)", "Q2", "Q3", "Q4", "Q5 (most)"]
GL = {"Q1 (least)": "Least-traded fifth", "Q2": "2nd fifth", "Q3": "3rd fifth", "Q4": "4th fifth", "Q5 (most)": "Most-traded fifth"}

# ---- fonts: DejaVu Serif if available (as in the first paper), otherwise Times ------------------
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu/", "/Library/Fonts/", os.path.expanduser("~/Library/Fonts/"),
             "C:/Windows/Fonts/", os.path.join(os.path.dirname(__import__("matplotlib").__file__), "mpl-data/fonts/ttf/")]
SER = {"Serif": "DejaVuSerif.ttf", "Serif-B": "DejaVuSerif-Bold.ttf", "Serif-I": "DejaVuSerif-Italic.ttf",
       "Serif-BI": "DejaVuSerif-BoldItalic.ttf"}
fd = next((d for d in FONT_DIRS if all(os.path.exists(d + f) for f in SER.values())), None)
if fd:
    for k, f in SER.items():
        pdfmetrics.registerFont(TTFont(k, fd + f))
    registerFontFamily("Serif", normal="Serif", bold="Serif-B", italic="Serif-I", boldItalic="Serif-BI")
    N, B, I, BI = "Serif", "Serif-B", "Serif-I", "Serif-BI"
else:
    N, B, I, BI = "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"

INK = colors.HexColor("#1f2a44")
body = ParagraphStyle("body", fontName=N, fontSize=9.6, leading=14.2, alignment=TA_JUSTIFY, spaceAfter=7)
title = ParagraphStyle("title", fontName=B, fontSize=16, leading=21, alignment=TA_CENTER, textColor=INK, spaceAfter=6)
sub = ParagraphStyle("sub", fontName=N, fontSize=10, leading=14, alignment=TA_CENTER, spaceAfter=3)
h1 = ParagraphStyle("h1", fontName=B, fontSize=11.5, leading=15, textColor=INK, spaceBefore=12, spaceAfter=5, keepWithNext=1)
h2 = ParagraphStyle("h2", fontName=BI, fontSize=10, leading=14, textColor=INK, spaceBefore=8, spaceAfter=4, keepWithNext=1)
abstract = ParagraphStyle("abs", parent=body, fontSize=9, leading=13, leftIndent=1.2 * cm, rightIndent=1.2 * cm)
caption = ParagraphStyle("cap", fontName=N, fontSize=8, leading=11, alignment=TA_JUSTIFY, spaceBefore=3, spaceAfter=10,
                         textColor=colors.HexColor("#333333"))
cell = ParagraphStyle("cell", fontName=N, fontSize=8, leading=10.5)
cellb = ParagraphStyle("cellb", fontName=B, fontSize=8, leading=10.5)
ref = ParagraphStyle("ref", fontName=N, fontSize=8.6, leading=12, leftIndent=0.6 * cm, firstLineIndent=-0.6 * cm, spaceAfter=4)
P = lambda t, s=body: Paragraph(t, s)


def f(x, d=1, sign=False, unit=""):
    """Format a number, or n/a if missing."""
    if x is None:
        return "n/a"
    s = f"{x:+,.{d}f}" if sign else f"{x:,.{d}f}"
    return s.replace("-", "−") + unit


def table(rows, widths, header=1):
    data = [[Paragraph(str(c), cellb if r < header else cell) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, hAlign="CENTER")
    t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.9, INK), ("LINEBELOW", (0, header - 1), (-1, header - 1), 0.5, INK),
                           ("LINEBELOW", (0, -1), (-1, -1), 0.9, INK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    return t


def figure(path, cap, width=15.5 * cm):
    from PIL import Image as PI
    w, h = PI.open(path).size
    return KeepTogether([Image(path, width=width, height=width * h / w), P(cap, caption)])


def link(url, text=None):
    return f'<link href="{url}" color="#284b8c">{text or url}</link>'


sig = lambda c: c is not None and c.get("t") is not None and abs(c["t"]) >= 2

# =============================================================================================
# Pull out the findings that drive the wording
# =============================================================================================
S = R["sample"]
T1 = R["test1_stale"]; t1q1, t1q5 = T1["Q1 (least)"], T1["Q5 (most)"]
slope1 = t1q1["slope_bps_per_pct"]
stale = slope1["b"] < 0 and sig(slope1)
flat_bias = t1q1["mean_gap_flat_days"]
bias_remains = flat_bias is not None and flat_bias >= 2
share_stale = t1q1["bias_explained_by_staleness_pct"]
mkt = R["test1_market_days_q1"]

T2 = R["test2_thin_days"]
flag_order = [k for k in ["few_trades_b", "one_price_b", "close_eq_open_b", "low_volume_b"] if k in T2 and "Q1 (least)" in T2[k]]
main_flag = flag_order[0] if flag_order else None
if main_flag:
    d2 = T2[main_flag]["Q1 (least)"]
    thin_more = d2["difference"]["b"] > 0 and sig(d2["difference"])
    thin_less = d2["difference"]["b"] < 0 and sig(d2["difference"])
else:
    d2, thin_more, thin_less = None, False, False

T3 = R["test3_who_adjusts"]; t3q1, t3all = T3["Q1 (least)"], T3["all"]
bse_share = t3q1["share_of_correction_by_bse_pct"]
bse_noisy = bse_share is not None and bse_share >= 70
nse_follows = bse_share is not None and bse_share <= 30

T4 = R["test4_selection"]; t4q1 = T4["Q1 (least)"]
has_sel = "within_company_difference_pct" in t4q1
sel_diff = t4q1["within_company_difference_pct"] if has_sel else None
selection = has_sel and sel_diff["b"] > 0 and sig(sel_diff)
loc_on, loc_off = t4q1.get("nse_close_location_on_bse_days"), t4q1.get("nse_close_location_other_days")
loc_higher = loc_on is not None and loc_off is not None and loc_on - loc_off >= 0.03

LS = R["level_shift"]
lb, la = LS["before"], LS["after"]
stocks_change = abs(la["stocks"] - lb["stocks"]) / lb["stocks"] if lb["stocks"] else 0
data_change = stocks_change > 0.05 or (LS["stocks_only_after"] + LS["stocks_only_before"]) > 0.05 * S["companies"]
if "one_price_b_pct" in lb and lb["one_price_b_pct"]:
    data_change = data_change or abs(la["one_price_b_pct"] - lb["one_price_b_pct"]) > 0.2 * lb["one_price_b_pct"]
grp_rise = [v["after"] / v["before"] for v in LS["median_gap_by_group"].values() if v["before"] and v["after"]]
all_groups_rise = len(grp_rise) == 5 and min(grp_rise) > 1.05
shift_up = la["median_gap"] > lb["median_gap"]
if "stocks_10_days_before" in LS and LS["stocks_10_days_before"]:          # abrupt change in the data?
    data_change = abs(LS["stocks_10_days_after"] - LS["stocks_10_days_before"]) / LS["stocks_10_days_before"] > 0.03
same, vol = LS.get("same_companies_median_gap"), LS.get("abs_market_move_pct")
s0, s1 = LS.get("shift_without_control"), LS.get("shift_controlling_for_market_move")
sel_neg = has_sel and sel_diff["b"] < 0 and sig(sel_diff)
loc_lower = loc_on is not None and loc_off is not None and loc_off - loc_on >= 0.03
up_d, down_d = t1q1["mean_gap_up_days"], t1q1["mean_gap_down_days"]
asym = up_d is not None and down_d is not None and down_d + up_d > 10
q5_share = T3["Q5 (most)"]["share_of_correction_by_bse_pct"]
CA = R.get("closing_auction")
cas_effect = CA is not None and CA["did_daily_median"]["b"] > 0 and sig(CA["did_daily_median"])
proxy = CA is not None and "fo_stocks" not in CA["treated_group"]
tg = "the most-traded fifth of companies" if proxy else "stocks with derivatives"
if cas_effect:
    TITLE = "Why Does BSE Close Higher? Stale Prices, Thin Trading and a Closing-Auction Experiment"
sec = 8 if cas_effect else 7                                                 # number of the first section after the tests

# =============================================================================================
# Text
# =============================================================================================
story = [Spacer(1, 0.4 * cm), P(TITLE, title), P(AUTHOR, sub), P(DATE, sub),
         P("Data and code: " + link(REPO, "github.com/udit20112007/WORLD-CLOSE") +
           (f" · DOI: {link('https://doi.org/' + THIS_PAPER_DOI, THIS_PAPER_DOI)}" if THIS_PAPER_DOI else ""), sub),
         Spacer(1, 0.5 * cm)]

# ---- abstract --------------------------------------------------------------------------------
a = [f"In earlier work I found that thousands of Indian companies end each day with two slightly different "
     f"official closing prices, one on NSE and one on BSE, and that for the least-traded companies BSE’s close tends "
     f"to sit above NSE’s. This paper asks why. Using {S['stock_days']:,} pairs of closing prices for "
     f"{S['companies']:,} companies ({S['from']} to {S['to']}), I test four explanations."]
if stale:
    a.append(f"First, BSE’s close is often stale for thin stocks: for the least-traded fifth, each 1% rise in a "
             f"stock’s NSE price goes with a gap {f(abs(slope1['b']))} basis points lower, as if BSE had not caught up.")
else:
    a.append("First, I find little evidence that BSE’s close is simply stale.")
if stale and bias_remains:
    a.append(f"Staleness does not explain the bias itself, however: on days when NSE barely moved, BSE still closed "
             f"{f(flat_bias)} basis points higher on average.")
elif stale:
    a.append("Once the day’s price move is taken into account, little of the bias remains.")
if main_flag and thin_more:
    a.append("The bias is concentrated on days with almost no trading on BSE.")
elif main_flag and thin_less:
    a.append("Surprisingly, the bias is smaller, not larger, on days with almost no trading on BSE.")
if bse_noisy:
    a.append(f"After a gap, BSE does about {f(bse_share, 0)}% of the correction the next day, so BSE’s close is the noisy price.")
elif nse_follows:
    a.append(f"After a gap it is NSE, not BSE, that does most of the correcting, which suggests BSE’s close carries information.")
elif bse_share is not None:
    a.append("After a gap, both exchanges share the correction.")
if selection or loc_higher:
    a.append("Thin stocks also tend to trade on BSE on days with buying pressure on NSE, so part of the bias reflects which days enter the sample.")
elif sel_neg or loc_lower:
    a.append("Thin stocks also trade on BSE mostly on days when they fall on NSE, and a BSE close that does not fully follow the fall sits above NSE’s.")
if s1 is not None and sig(s1):
    a.append(f"I date a {'rise' if shift_up else 'fall'} in the typical gap to {LS['break_date']} that is not explained by "
             f"changes in the data, the mix of companies or market volatility.")
else:
    a.append(f"I date a {'rise' if shift_up else 'fall'} in the typical gap to {LS['break_date']}.")
if cas_effect:
    a.append(f"Finally, I use the introduction of a closing auction for stocks with derivatives on {CA['date']} as a "
             f"natural experiment. For {tg}, the typical gap between the two exchanges’ closes rose from "
             f"{f(CA['median_gap_treated']['before'])} to {f(CA['median_gap_treated']['after'])} basis points, while "
             f"other companies barely changed. Separate auctions on each exchange appear to make the two official "
             f"closes agree less, not more.")
story += [P("<b>Abstract</b>", ParagraphStyle("ah", parent=h2, alignment=TA_CENTER)), P(" ".join(a), abstract), Spacer(1, 0.3 * cm)]

# ---- 1 introduction --------------------------------------------------------------------------
story += [P("1. Introduction", h1), P(
    f"Most large and mid-sized Indian companies are listed on both the National Stock Exchange (NSE) and BSE, and "
    f"each exchange publishes its own official closing price every day. In an earlier paper (Goyal, 2026; "
    f"{link('https://doi.org/' + FIRST_PAPER_DOI, 'doi:' + FIRST_PAPER_DOI)}) I showed that the two closes usually "
    f"differ by about a tenth of a percent, that the gaps are largest for the least-traded companies, and that they "
    f"mostly disappear by the next day. One pattern did not fit: for thinly traded companies, BSE tends to close "
    f"slightly above NSE, and the tendency is too systematic to be chance."), P(
    "This paper tries to explain that pattern. The earlier paper suggested three candidates, and I add a fourth. "
    "The first is that BSE’s close is <i>stale</i>: if a thin stock does not trade on BSE late in the day, its BSE "
    "close may come from an earlier trade and miss the day’s later move. The second is the way the close is "
    "<i>formed</i> when trading is very thin, for example a handful of buyer-initiated trades executing near the "
    "ask. The third is <i>selection</i>: a stock only appears in the matched sample on days it trades on BSE, and "
    "those days may be unusual. The fourth asks which close is closer to the truth, by looking at which exchange "
    "moves to close the gap the next day, an idea related to the price-discovery literature (Hasbrouck, 1995)."), P(
    "Stale prices are a well-known problem in finance. When some prices are recorded earlier than others, "
    "measured returns become correlated in ways that do not reflect real economic links (Scholes and Williams, 1977; "
    "Lo and MacKinlay, 1990). Dual-listed Indian stocks are a clean place to measure this, because the same security "
    "has two closing prices on the same day, and one of them is usually based on far fewer trades.")]

# ---- 2 data ----------------------------------------------------------------------------------
cols = [c for c in ["open", "high", "low", "previous close", "number of trades"]
                 if any(k.startswith({"open": "open", "high": "high", "low": "low", "previous close": "prev_close",
                                      "number of trades": "trades"}[c]) for k in R["columns_available"])]
cols = (", ".join(cols[:-1]) + " and " + cols[-1]) if len(cols) > 1 else "".join(cols)
story += [P("2. Data and method", h1), P(
    f"I use the same data and sample as the earlier paper: the official daily “bhavcopy” files that both exchanges "
    f"publish, collected by an automated pipeline, with companies matched across exchanges by ISIN. I keep NSE’s "
    f"regular equity series, drop shares priced below Rs 20, and require trading on both exchanges that day. The "
    f"sample has {S['stock_days']:,} stock-days for {S['companies']:,} companies from {S['from']} to {S['to']}. "
    f"In addition to the closing price, this paper uses each exchange’s {cols}. As in the earlier paper’s "
    f"company-level analysis, I keep companies with at least 60 matched days, and group them into fifths by "
    f"their median daily value traded on NSE."), P(
    "The gap is the BSE close minus the NSE close, divided by the average of the two, in basis points (hundredths "
    "of a percent). A positive gap means BSE closed higher. Returns are computed from each exchange’s own previous "
    "close, and daily moves larger than 25% are excluded because they usually reflect unadjusted corporate actions. "
    "All regressions report standard errors clustered by company."), P(
    "According to the exchanges’ published methodologies, both NSE and BSE compute the official close as the "
    "volume-weighted average price of trades in the last 30 minutes of continuous trading. "
    + ("From 3 August 2026, stocks with derivatives contracts moved to a Closing Auction Session on both exchanges, "
       "in which the close is the price of a separate auction held after continuous trading ends (NSE, 2026). "
       "Section 8 uses this change as a natural experiment." if cas_effect else ""))]

# ---- 3 test 1 --------------------------------------------------------------------------------
rows = [["Liquidity group", "Slope (bps per 1% NSE move)", "t", "Mean gap, NSE up / down days (bps)", "Mean gap, flat days (bps)", "BSE higher, flat days"]]
for q in G:
    t = T1[q]
    rows.append([GL[q], f(t["slope_bps_per_pct"]["b"], 1), f(t["slope_bps_per_pct"]["t"]),
                 f"{f(t['mean_gap_up_days'])} / {f(t['mean_gap_down_days'])}", f(t["mean_gap_flat_days"]),
                 f(t["bse_higher_flat_days_pct"], unit="%")])
txt = (f"If BSE’s close is stale for a thin stock, it reflects the price from earlier in the day. On a day when "
       f"the stock rises on NSE, BSE’s close will then lag below NSE’s, and on a day it falls, BSE’s close will stay "
       f"above. So the gap should move <i>opposite</i> to the day’s NSE return. Table 1 regresses the gap on the "
       f"stock’s NSE return for each liquidity group. ")
if stale:
    txt += (f"For the least-traded fifth, the slope is {f(slope1['b'])} basis points per 1% move (t = {f(slope1['t'])}): "
            f"on a day the stock rises 2% on NSE, BSE’s close is on average about {f(abs(2 * slope1['b']), 0)} basis "
            f"points lower than NSE’s. The slope shrinks steadily with liquidity, to {f(t1q5['slope_bps_per_pct']['b'])} "
            f"for the most-traded fifth. Figure 1 shows the pattern: for thin stocks, the gap falls almost in a straight "
            f"line as the day’s return rises. This is what stale prices predict.")
else:
    txt += (f"For the least-traded fifth the slope is {f(slope1['b'])} basis points per 1% move (t = {f(slope1['t'])}), "
            f"which is not the clear negative relationship that stale prices would produce.")
story += [KeepTogether([P("3. Are BSE closes stale?", h1), P(txt)]),
          KeepTogether([P("<b>Table 1.</b> The gap against the day’s NSE return. Slope from a regression of the gap (bps) "
                          "on the stock’s NSE return (%), standard errors clustered by company. Up and down days are "
                          "moves larger than 0.5%; flat days are within ±0.25%.", caption),
                        table(rows, [3.2 * cm, 2.4 * cm, 1.4 * cm, 3.4 * cm, 2.3 * cm, 2.3 * cm])]), Spacer(1, 8),
          figure("figures/fig5_stale.png",
                 "<b>Figure 1.</b> Average gap (BSE minus NSE, bps) against the stock’s NSE return that day, in bins of "
                 "0.5 percentage points, for three liquidity groups. Bins with fewer than 50 observations are omitted.")]
txt = ("Staleness explains why the gap moves with the day’s return, but it does not by itself explain why the "
       "<i>average</i> gap is positive. A stale close only produces a positive average if prices fell on average. ")
if share_stale is not None:
    txt += (f"The least-traded fifth had an average NSE return of {f(t1q1['mean_nse_return_pct'], 3)}% a day, and "
            f"multiplying this by the slope accounts for about {f(share_stale, 0)}% of the group’s average gap of "
            f"{f(t1q1['mean_gap_bps'])} basis points. ")
if bias_remains:
    txt += (f"The more direct check is to look at days when nothing happened. On days when the stock moved by less "
            f"than 0.25% on NSE, BSE still closed {f(flat_bias)} basis points higher on average, and was higher on "
            f"{f(t1q1['bse_higher_flat_days_pct'], unit='%')} of those days. Something other than staleness is "
            f"pushing BSE’s close up.")
else:
    txt += (f"On days when the stock moved by less than 0.25% on NSE, the average gap was only {f(flat_bias)} basis "
            f"points, so once the day’s move is accounted for, little of the bias remains.")
txt += (f" Grouping days by the market as a whole gives the same picture: for the least-traded fifth the average gap "
        f"was {f(mkt['mean_gap_market_up_bps'])} basis points on days the median stock rose and "
        f"{f(mkt['mean_gap_market_down_bps'])} on days it fell.")
if asym:
    txt += (f" The response is also lopsided. On days the stock fell by more than 0.5% on NSE, BSE closed "
            f"{f(down_d)} basis points higher on average, but on days it rose by more than 0.5%, BSE closed only "
            f"{f(abs(up_d))} basis points lower. Pure staleness would give roughly mirror-image numbers, so this "
            f"asymmetry is another sign of a separate upward push in BSE’s close.")
story += [P(txt)]

# ---- 4 test 2 --------------------------------------------------------------------------------
story += [P("4. Is the bias concentrated on thin BSE days?", h1)]
if flag_order:
    rows = [["Measure of a thin BSE day", "Share of days", "Mean gap, thin / other days (bps)", "BSE higher, thin / other", "Difference (t)"]]
    for k in flag_order:
        x = T2[k]["Q1 (least)"]
        rows.append([T2[k]["label"], f(x["share_of_days_flagged_pct"], unit="%"),
                     f"{f(x['mean_gap_flagged_bps'])} / {f(x['mean_gap_other_bps'])}",
                     f"{f(x['bse_higher_flagged_pct'], unit='%')} / {f(x['bse_higher_other_pct'], unit='%')}",
                     f"{f(x['difference']['b'])} ({f(x['difference']['t'])})"])
    txt = (f"If the bias comes from how BSE’s close is formed when there is almost no trading, it should be largest "
           f"on days when BSE trading is thinnest. Table 2 compares such days with other days for the least-traded "
           f"fifth, using {len(flag_order)} different ways of identifying a thin BSE day. ")
    lab = T2[main_flag]["label"]; lab = lab[0].lower() + lab[1:]
    if thin_more:
        txt += (f"The bias is clearly larger on thin days: on days with {lab}, the mean gap is "
                f"{f(d2['mean_gap_flagged_bps'])} basis points, against {f(d2['mean_gap_other_bps'])} on other days. "
                f"This points to the closing-price formation on BSE when only a few trades occur.")
    elif thin_less:
        txt += (f"The result goes the other way. On days with {lab}, the mean gap is {f(d2['mean_gap_flagged_bps'])} basis "
                f"points, against {f(d2['mean_gap_other_bps'])} on other days. Thin days are also the days when the "
                f"close is most likely to be stale, and a stale close is as likely to sit below NSE as above it, so "
                f"these days dilute rather than drive the bias. The bias appears to come from days when BSE does trade.")
    else:
        txt += (f"On days with {lab} the mean gap is {f(d2['mean_gap_flagged_bps'])} basis points, against "
                f"{f(d2['mean_gap_other_bps'])} on other days, a difference that is not statistically clear.")
    story += [P(txt), KeepTogether([P("<b>Table 2.</b> Thin BSE days, least-traded fifth of companies. The difference is "
                                      "from a regression of the gap on an indicator for a thin day, with standard errors "
                                      "clustered by company.", caption),
                                    table(rows, [4.6 * cm, 1.7 * cm, 3.0 * cm, 2.8 * cm, 2.6 * cm])]), Spacer(1, 6)]
else:
    story += [P("The daily files did not contain enough information to identify thin BSE days, so this test could not be run.")]

# ---- 5 test 3 --------------------------------------------------------------------------------
rows = [["Liquidity group", "NSE moves toward BSE (% of gap)", "BSE moves back toward NSE (% of gap)", "Gap closed next day", "Share of correction by BSE"]]
for q in ["all"] + G:
    x = T3[q]
    rows.append(["All companies" if q == "all" else GL[q],
                 f"{f(x['nse_next_return']['b'] * 100)} ({f(x['nse_next_return']['t'])})",
                 f"{f(-x['bse_next_return']['b'] * 100)} ({f(x['bse_next_return']['t'])})",
                 f(x["gap_closed_next_day_pct"], 0, unit="%"),
                 "n/a" if x["share_of_correction_by_bse_pct"] is None else f(x["share_of_correction_by_bse_pct"], 0, unit="%")])
txt = ("When the two closes disagree, at least one of them is wrong, and the next day’s prices show which. If BSE’s "
       "close was noise, BSE’s price should move back toward NSE’s the next day while NSE’s barely reacts. If BSE’s "
       "close contained information NSE had not yet priced, NSE should move toward BSE. I regress each exchange’s "
       "next-day return on today’s gap; Table 3 reports how much of the gap each exchange’s move closes. ")
if bse_noisy:
    txt += (f"For the least-traded fifth, BSE’s move closes {f(-t3q1['bse_next_return']['b'] * 100, 0)}% of the gap "
            f"and NSE’s only {f(t3q1['nse_next_return']['b'] * 100, 0)}%, so BSE does about {f(bse_share, 0)}% of the "
            f"correction. NSE’s close is the better price; BSE’s close for thin stocks is mostly noise around it.")
elif nse_follows:
    txt += (f"For the least-traded fifth it is NSE that does most of the correcting: NSE’s move closes "
            f"{f(t3q1['nse_next_return']['b'] * 100, 0)}% of the gap. This suggests BSE’s close carries information "
            f"that NSE has not yet priced, which is surprising given how little trading happens on BSE.")
else:
    txt += (f"For the least-traded fifth, BSE’s move closes {f(-t3q1['bse_next_return']['b'] * 100, 0)}% of the gap and "
            f"NSE’s {f(t3q1['nse_next_return']['b'] * 100, 0)}%, so both closes contain some noise.")
txt += (f" Across all companies, {f(t3all['gap_closed_next_day_pct'], 0)}% of a gap is closed by the next day, "
        f"consistent with the earlier paper’s finding that gaps do not persist. Figure 2 shows the split by liquidity group.")
if q5_share is not None and 35 <= q5_share <= 65:
    txt += (f" For the most-traded fifth the correction is split almost evenly ({f(q5_share, 0)}% by BSE), as one would "
            f"expect when both closes are equally informative.")
story += [KeepTogether([P("5. Which close is right?", h1), P(txt)]),
          KeepTogether([P("<b>Table 3.</b> Next-day adjustment. Coefficients from regressions of each exchange’s next-day "
                          "return on today’s gap, expressed as the percentage of the gap closed (t-statistics in brackets, "
                          "clustered by company).", caption),
                        table(rows, [3.3 * cm, 3.4 * cm, 3.6 * cm, 2.3 * cm, 2.4 * cm])]), Spacer(1, 8),
          figure("figures/fig6_who_adjusts.png",
                 "<b>Figure 2.</b> Percentage of today’s gap closed by each exchange’s move the next day, by liquidity group.")]

# ---- 6 test 4 --------------------------------------------------------------------------------
story += [P("6. Are BSE trading days unusual?", h1)]
if has_sel:
    rows = [["Liquidity group", "NSE days also traded on BSE", "NSE return, BSE days / other (%)", "Within-company difference (t)", "NSE value vs usual, BSE days / other"]]
    for q in G:
        x = T4[q]
        if "within_company_difference_pct" not in x:
            rows.append([GL[q], f(x["share_of_nse_days_also_on_bse_pct"], unit="%"), "—", "—", "—"]); continue
        rows.append([GL[q], f(x["share_of_nse_days_also_on_bse_pct"], unit="%"),
                     f"{f(x['nse_return_on_bse_days_pct'], 3)} / {f(x['nse_return_other_days_pct'], 3)}",
                     f"{f(x['within_company_difference_pct']['b'], 3)} ({f(x['within_company_difference_pct']['t'])})",
                     f"{f(x['nse_value_vs_usual_on_bse_days'], 2)} / {f(x['nse_value_vs_usual_other_days'], 2)}"])
    txt = (f"A thin stock only enters the matched sample on days it trades on BSE. The least-traded fifth traded on "
           f"BSE on {f(t4q1['share_of_nse_days_also_on_bse_pct'], 0, unit='%')} of its NSE trading days. If BSE trades "
           f"happen mostly when there is buying interest, the matched days would be days of rising prices, and the "
           f"gap measured on those days could be biased. Table 4 compares each company’s NSE behaviour on days it "
           f"also traded on BSE with days it did not. ")
    if selection:
        txt += (f"For the least-traded fifth, NSE returns are {f(sel_diff['b'], 3)} percentage points higher on BSE "
                f"trading days (t = {f(sel_diff['t'])}), so BSE trading does cluster on days of buying pressure.")
    elif sel_neg:
        txt += (f"The result goes the other way from buying pressure. For the least-traded fifth, NSE returns are "
                f"{f(abs(sel_diff['b']), 3)} percentage points <i>lower</i> on days the stock also traded on BSE "
                f"(t = {f(sel_diff['t'])}).")
    else:
        txt += (f"For the least-traded fifth, the difference in NSE returns is {f(sel_diff['b'], 3)} percentage points "
                f"(t = {f(sel_diff['t'])}), which is not clear evidence that BSE trading days are unusual.")
    if loc_on is not None:
        txt += (f" On BSE trading days the stock’s NSE close sits at {f(loc_on, 2)} of the day’s range, against "
                f"{f(loc_off, 2)} on other days (0 is the day’s low, 1 the high)"
                + (", so these are days when buyers dominated late in the session." if loc_higher else
                   ", so the stock tends to close nearer its low on NSE on those days." if loc_lower else "."))
    vo, vx = t4q1.get("nse_value_vs_usual_on_bse_days"), t4q1.get("nse_value_vs_usual_other_days")
    if vo is not None and vx is not None and vx < 0.8 * vo:
        txt += (f" Days without any BSE trading are quiet days: NSE value traded is {f(vx, 2)} times the company’s "
                f"usual level, against {f(vo, 2)} on days it also traded on BSE.")
    if sel_neg or loc_lower:
        txt += (" Together with Section 3, this suggests a simple mechanism behind part of the bias. Thin stocks "
                "tend to trade on BSE on days when they fall; BSE’s close does not fully follow the fall; and so BSE "
                "ends those days above NSE.")
    story += [P(txt), KeepTogether([P("<b>Table 4.</b> NSE behaviour on days a company also traded on BSE. The "
                                      "within-company difference compares each company with itself, with standard errors "
                                      "clustered by company. Value traded is relative to the company’s median day.", caption),
                                    table(rows, [3.0 * cm, 2.3 * cm, 3.2 * cm, 3.4 * cm, 3.0 * cm])]), Spacer(1, 6)]
else:
    story += [P("There was not enough variation in BSE trading days to run this test.")]

# ---- 7 level shift ---------------------------------------------------------------------------
rows = [["Measure (daily average)", "Before", "After"],
        ["Median absolute gap across stocks (bps)", f(lb["median_gap"]), f(la["median_gap"])],
        ["Companies traded on both exchanges", f(lb["stocks"], 0), f(la["stocks"], 0)],
        ["Median share price (Rs)", f(lb["median_price"], 0), f(la["median_price"], 0)],
        ["BSE share of value traded (%)", f(lb["bse_value_share_pct"]), f(la["bse_value_share_pct"])]]
if "one_price_b_pct" in lb:
    rows.append(["BSE days with a single price (%)", f(lb["one_price_b_pct"]), f(la["one_price_b_pct"])])
txt = (f"The earlier paper’s daily series showed the typical gap moving to a higher level during the sample. To "
       f"date the change, I fit a model in which the daily median gap has one mean before an unknown date and another "
       f"after, and choose the date that fits best (Andrews, 1993). The best break is {LS['break_date']}, with a sup-F "
       f"statistic of {f(LS['F_stat'])} (the 5% critical value for this kind of test is roughly 9). The median gap "
       f"{'rose' if shift_up else 'fell'} from {f(lb['median_gap'])} to {f(la['median_gap'])} basis points. ")
if all_groups_rise:
    txt += "The rise appears in every liquidity group. "
if data_change:
    txt += ("The number of matched companies also changed abruptly at the break, so the shift may partly reflect "
            "a change in the data rather than in the market. I flag this for further checking rather than interpreting it. ")
else:
    txt += (f"It is not a change in the data: the number of matched companies was {f(LS.get('stocks_10_days_before'), 0)} "
            f"a day in the ten days before the break and {f(LS.get('stocks_10_days_after'), 0)} in the ten days after. ")
if same:
    txt += (f"Nor is it a change in the mix of companies: for companies present on both sides of the break, the median "
            f"gap rose from {f(same['before'])} to {f(same['after'])} basis points. ")
if vol and s0 and s1:
    txt += (f"The market did become more volatile, with the median stock’s absolute daily return rising from "
            f"{f(vol['before'], 2)}% to {f(vol['after'], 2)}%, and the earlier paper found that gaps widen on volatile "
            f"days. But controlling for the size of each day’s market move barely changes the estimated shift, from "
            f"{f(s0['b'], 2)} to {f(s1['b'], 2)} basis points (t = {f(s1['t'])}). ")
if LS["break_date"] == "2026-01-19":
    txt += ("The break date coincides with NSE’s circular introducing the Closing Auction Session (NSE, 2026), but "
            "the auction itself only began in August, so the announcement alone is unlikely to have changed how "
            "closes were formed. I cannot explain the January shift with this data.")
else:
    txt += "I cannot explain the shift with this data; checking exchange and regulatory circulars from that period is a natural next step."
story += [KeepTogether([P("7. The level shift", h1), P(txt)]),
          KeepTogether([P(f"<b>Table 5.</b> Daily averages before and after the estimated break on {LS['break_date']}.", caption),
                        table(rows, [8.5 * cm, 3.0 * cm, 3.0 * cm])]), Spacer(1, 8),
          figure("figures/fig7_level_shift.png",
                 "<b>Figure 3.</b> Median absolute gap across stocks each day, with the estimated break date (dashed) "
                 "and the average level before and after.")]

# ---- the closing auction as a natural experiment ---------------------------------------------
if cas_effect:
    rows = [["", "Before", "After"],
            [f"Median absolute gap, {tg} (bps)", f(CA["median_gap_treated"]["before"]), f(CA["median_gap_treated"]["after"])],
            ["Median absolute gap, all other companies (bps)", f(CA["median_gap_control"]["before"]), f(CA["median_gap_control"]["after"])],
            [f"Mean signed gap, {tg} (bps)", f(CA["signed_gap_treated"]["before"]), f(CA["signed_gap_treated"]["after"])],
            [f"Identical closes on both exchanges, {tg}", f(CA["identical_close_treated_pct"]["before"], unit="%"),
             f(CA["identical_close_treated_pct"]["after"], unit="%")]]
    d0, d1 = CA["did_daily_median"], CA["did_controlling_market_move"]
    txt = (f"On {CA['date']} NSE and BSE replaced the 30-minute average close with a Closing Auction Session for stocks "
           f"that have derivatives contracts, while all other stocks kept the old rule (NSE, 2026). This gives a "
           f"natural experiment: if the way the close is formed matters for the gap, the gap should change for the "
           f"stocks that moved to the auction and not for the others. "
           + (f"I do not have the official list of stocks with derivatives for this period, so I use {tg} as the "
              f"treated group. Derivatives are only available on large, heavily traded stocks, so most of them should be "
              f"in this group. The group also contains companies without derivatives, which kept the old rule; "
              f"including them can only dilute the measured effect, not create it. " if proxy else
              f"The treated group is the {CA['treated_companies']:,} stocks with derivatives contracts. ")
           + f"I compare the {CA['days_before']} trading days before the change with the {CA['days_after']} days after.")
    txt2 = (f"The effect is large and immediate (Figure 4 and Table 6). For {tg}, the median gap was "
            f"{f(CA['median_gap_treated']['before'])} basis points before the change and {f(CA['median_gap_treated']['after'])} "
            f"after; on the first day of the auction it jumped to {f(CA['treated_first_day'])}, and over the last ten "
            f"days of the sample it averaged {f(CA['treated_last_10_days'])}. For all other companies the median gap "
            f"moved only from {f(CA['median_gap_control']['before'])} to {f(CA['median_gap_control']['after'])}. A "
            f"difference-in-differences regression on the daily medians gives an increase of {f(d0['b'], 2)} basis "
            f"points relative to other companies (t = {f(d0['t'])}, standard errors robust to autocorrelation), and "
            f"{f(d1['b'], 2)} (t = {f(d1['t'])}) when controlling for the size of each day’s market move.")
    txt3 = ("A plausible explanation is mechanical. A 30-minute volume-weighted average smooths out individual trades, "
            "and when most trading happens on NSE, both exchanges’ averages track the same underlying price path. A "
            "closing auction instead sets the close from a single crossing of orders on each exchange, and each "
            "exchange runs its own auction with its own order book. Two separate auctions, one of them much smaller, "
            "can easily clear at slightly different prices. "
            + (lambda w, k: f"The data show one sign of this. An auction clears at the price of a limit order, and "
               f"limit orders cluster on round numbers. For {tg}, the share of closes at a whole rupee rose from "
               f"{f(w['nse']['before'])}% to {f(w['nse']['after'])}% on NSE and from {f(w['bse']['before'])}% to "
               f"{f(w['bse']['after'])}% on BSE, while for other companies it stayed near {f(k['nse']['after'])}% "
               f"and {f(k['bse']['after'])}%. When each exchange’s auction lands on its own round number, the two "
               f"closes differ. ")(CA["whole_rupee_close_treated_pct"], CA["whole_rupee_close_control_pct"])
            + "If this is right, the closing auction made each "
            "exchange’s close a better reflection of its own end-of-day demand, but made the two official closes of "
            "the same stock less consistent with each other. This matters for anyone who uses BSE closing prices for "
            "the most actively traded Indian stocks, including index providers, fund valuations and settlement prices.")
    story += [KeepTogether([P("8. A natural experiment: the closing auction", h1), P(txt)]), P(txt2),
              KeepTogether([P(f"<b>Table 6.</b> Gaps before and after the Closing Auction Session began on {CA['date']}.", caption),
                            table(rows, [9.0 * cm, 2.8 * cm, 2.8 * cm])]), Spacer(1, 8),
              figure("figures/fig8_closing_auction.png",
                     f"<b>Figure 4.</b> Median absolute gap each day for {tg} and for all other companies, around the "
                     f"start of the Closing Auction Session (dashed line)."), P(txt3)]

# ---- 8 discussion -----------------------------------------------------------------------------
found = []
if stale:
    found.append("BSE closes for thin stocks are often stale and lag the day’s move on NSE")
if bse_noisy:
    found.append("BSE’s close, not NSE’s, is the one that corrects the next day")
if thin_more:
    found.append("the bias is largest on days with almost no BSE trading")
if selection or loc_higher:
    found.append("thin stocks tend to trade on BSE on days of buying pressure")
if sel_neg or loc_lower:
    found.append("thin stocks trade on BSE mostly on days they fall on NSE, when a lagging BSE close sits above NSE’s")
summary = ("; ".join(found[:-1]) + ("; and " if len(found) > 1 else "") + found[-1]) if found else ""
txt = ("Putting the tests together: " + summary + ". " if found else "None of the tests gives a clear explanation on its own. ")
if bias_remains and not (thin_more or selection or loc_higher or sel_neg or loc_lower):
    txt += ("What remains unexplained is the bias on days when NSE barely moved. That is the part of the puzzle that "
            "daily data cannot resolve, and the natural next step is intraday trade data, which would show the exact "
            "trades behind each exchange’s close and whether they were buyer- or seller-initiated.")
elif bias_remains:
    txt += ("Staleness explains why the gap moves with the market, while the remaining bias on quiet days is more "
            "consistent with how and when BSE trading happens for thin stocks. Intraday data would allow a direct test.")
else:
    txt += "Together these largely account for the pattern documented in the earlier paper."
story += [P(f"{sec + 1}. What explains the puzzle?", h1), P(txt), P(
    "The practical lesson is the same as in the earlier paper. For a thinly traded dual-listed stock, BSE’s official "
    "close is a noisy measure of the stock’s value, and anyone using it, for example to value a portfolio or to "
    "compute returns, should prefer NSE’s close or check both."
    + (" The closing-auction experiment adds a second lesson: for the most-traded stocks, the two exchanges’ closes "
       "have diverged since the auction began, so the choice of exchange now matters for them too." if cas_effect else ""))]

story += [P(f"{sec + 2}. Limitations", h1), P(
    "The tests use daily closing data only, so they cannot see the trades behind each close. Identifying a thin "
    "BSE day from daily high, low, open and trade counts is approximate. The selection test compares days within a "
    "company, but days with and without BSE trading may differ in ways that are not captured by NSE returns and "
    "volume. The sample covers about one year, and the level shift means it may span two different regimes. The "
    "description of each exchange’s closing-price rule follows the exchanges’ published methodologies, and readers "
    "should consult the current rules directly."
    + (" In the closing-auction experiment, the treated group is approximated by the most-traded fifth of companies "
       "rather than the official list of stocks with derivatives, and the period after the change is short." if proxy else
       " The period after the closing auction began is short." if cas_effect else ""))]

story += [P(f"{sec + 3}. Conclusion", h1), P(
    "The earlier paper found that India’s two exchanges agree closely on the closing price of the same company, "
    "except that BSE tends to close slightly higher for thinly traded stocks. This paper tested four explanations "
    "using the same daily data. " + (summary[0].upper() + summary[1:] + ". " if found else "")
    + (f"The introduction of a closing auction in {CA['date'][:4]} also offered a natural experiment: for {tg}, "
       f"separate auctions on each exchange raised the typical gap between the two official closes from "
       f"{f(CA['median_gap_treated']['before'])} to {f(CA['median_gap_treated']['after'])} basis points. " if cas_effect else "") +
    "The remaining open questions are best answered with intraday data.")]

story += [P("Data and code", h1), P(
    f"The data and the code that produces every number, table and figure in this paper are in "
    f"{link(REPO + '/tree/main/world-close-stage1/research/bse_puzzle', 'the research/bse_puzzle folder')} of "
    f"{link(REPO, 'github.com/udit20112007/WORLD-CLOSE')}. Every number in the text is read from "
    f"<i>results_puzzle.json</i>, so the paper always matches the data it was computed from."),
    P("Acknowledgements", h2), P(
    "I thank NSE and BSE for publishing their daily market data openly, and the developers of pandas, NumPy, "
    "statsmodels and Matplotlib. I used an AI assistant (Claude) to help write code and draft parts of the text; "
    "the research question, data, checks and interpretation are my own, as are any errors.")]

refs = [P("References", h1)]
for r in [
    "Andrews, D. W. K. (1993). Tests for parameter instability and structural change with unknown change point. <i>Econometrica</i>, 61(4), 821–856.",
    f"Goyal, U. (2026). Same company, two prices: how closely do India’s two stock exchanges agree on the close? Working paper. doi:{FIRST_PAPER_DOI}.",
    "Hasbrouck, J. (1995). One security, many markets: determining the contributions to price discovery. <i>Journal of Finance</i>, 50(4), 1175–1199.",
    "Lo, A. W., and MacKinlay, A. C. (1990). An econometric analysis of nonsynchronous trading. <i>Journal of Econometrics</i>, 45(1–2), 181–211.",
    "National Stock Exchange of India (NSE) (2026). Introduction of Closing Auction Session (CAS) in the equity cash segment. Circular NSE/CMTR/72394, 19 January 2026.",
    "Roll, R. (1984). A simple implicit measure of the effective bid-ask spread in an efficient market. <i>Journal of Finance</i>, 39(4), 1127–1139.",
    "Scholes, M., and Williams, J. (1977). Estimating betas from nonsynchronous data. <i>Journal of Financial Economics</i>, 5(3), 309–327.",
    "Shleifer, A., and Vishny, R. W. (1997). The limits of arbitrage. <i>Journal of Finance</i>, 52(1), 35–55."]:
    refs.append(P(r, ref))
story.append(KeepTogether(refs))


def on_page(canv, doc):
    canv.saveState()
    canv.setFont(N, 7.5); canv.setFillColor(colors.HexColor("#666666"))
    if doc.page > 1:
        canv.drawString(2.2 * cm, A4[1] - 1.3 * cm, SHORT)
    canv.drawCentredString(A4[0] / 2, 1.2 * cm, str(doc.page))
    canv.restoreState()


doc = SimpleDocTemplate("BSE_closes_higher.pdf", pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                        topMargin=2.0 * cm, bottomMargin=2.0 * cm, title=TITLE, author=AUTHOR)
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
if "XXXXXXX" in FIRST_PAPER_DOI:
    print("WARNING: fill in FIRST_PAPER_DOI at the top of build_paper2.py before sharing the PDF")
print("built BSE_closes_higher.pdf")
