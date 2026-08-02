"""
Build a complex, multi-page sample document — every page a different layout with a
different mix of accessibility failures. Exercises the pager, the cross-page audio
timeline, per-page reading-order trails, and findings aggregation across pages.

  Page 1  Q3 Regional Review   3 tall columns · headerless table · red/green status · uncaptioned chart
  Page 2  Market Segments      section header · 2 columns · traffic-light legend (colour-only) · chart
  Page 3  Financial Summary    two headerless tables · two side-by-side uncaptioned charts · footnotes
  Page 4  Regional Detail      3 columns · a callout box placed out of flow · uncaptioned chart

Aggregated findings you should see:
  figure_no_description (pages 1-4) · table_no_header (pages 1, 3) ·
  reading_order_columns (pages 1, 4) · colour_only_status (pages 1, 2)
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib import colors
from PIL import Image, ImageDraw
import os, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "Second-Reader-sample-multipage.pdf")
W, H = letter
RED, GREEN, AMBER = (0xC0, 0x39, 0x2B), (0x27, 0xAE, 0x60), (0xF3, 0x9C, 0x12)


def chart_png(path, bars):
    im = Image.new("RGB", (520, 300), "white")
    d = ImageDraw.Draw(im)
    for i, (h, col) in enumerate(bars):
        x = 40 + i * 80
        d.rectangle([x, 260 - h, x + 52, 260], fill=col)
    d.line([30, 260, 500, 260], fill="black", width=2)
    d.line([30, 20, 30, 260], fill="black", width=2)
    im.save(path)
    return path


def columns(c, texts, xs, top, width=30, lh=14, size=10):
    c.setFont("Helvetica", size)
    for cx, para in zip(xs, texts):
        y = top
        for line in textwrap.wrap(para, width=width):
            c.drawString(cx, y, line)
            y -= lh


def headerless_table(c, x0, ty, rows, colw, status_col=True):
    c.setFont("Helvetica", 11)
    rh = 0.32 * inch
    for i, row in enumerate(rows):
        ry = ty - i * rh
        c.setStrokeColor(colors.black)
        c.rect(x0, ry - rh + 6, sum(colw), rh, stroke=1, fill=0)
        c.setFillColor(colors.black)
        cx = x0 + 6
        for j, cell in enumerate(row):
            if status_col and j == len(row) - 1:
                col = GREEN if cell in ("on track", "on plan") else RED
                c.setFillColorRGB(col[0] / 255, col[1] / 255, col[2] / 255)
            c.drawString(cx, ry - 8, str(cell))
            c.setFillColor(colors.black)
            cx += colw[j]


def footer(c, text):
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.grey)
    c.drawString(0.75 * inch, 0.5 * inch, text)
    c.setFillColor(colors.black)


def page1(c):
    c.setFont("Helvetica-Bold", 22)
    c.drawString(0.75 * inch, H - 0.85 * inch, "Q3 Regional Review")
    cols = [
        ("Northern region held steady through the quarter despite the supply delays "
         "that hit every distribution hub in the first six weeks, and the team still "
         "closed within two points of the original commit for the period. Fulfilment "
         "recovered once the second carrier came online and the backlog cleared."),
        ("Southern accounts grew on the back of two large renewals, though margin "
         "slipped as discounting crept into the final stage of each deal and set an "
         "expectation the field will have to unwind before the next cycle begins. Two "
         "deals were pulled forward, which flatters this result."),
        ("Eastern pipeline looks thin for the coming quarter and needs attention now "
         "rather than in the review that nobody schedules until the numbers have "
         "already slipped and the recovery has become a great deal more expensive. "
         "Coverage is concentrated in three names."),
    ]
    columns(c, cols, [0.75 * inch, 3.15 * inch, 5.55 * inch], H - 1.35 * inch)
    headerless_table(c, 0.75 * inch, H - 5.0 * inch, [
        ("Northern", "1,240", "on track"), ("Southern", "980", "at risk"),
        ("Eastern", "610", "on track"), ("Western", "1,455", "at risk")],
        [1.6 * inch, 1.1 * inch, 1.6 * inch])
    c.drawImage(chart_png(os.path.join(HERE, "_c1.png"),
                [(90, RED), (150, GREEN), (210, RED), (120, GREEN), (255, GREEN)]),
                4.1 * inch, H - 5.15 * inch, width=3.0 * inch, height=1.9 * inch)
    footer(c, "Confidential draft - do not distribute - page 1 of 4")
    c.showPage()


def page2(c):
    c.setFont("Helvetica-Bold", 18)
    c.drawString(0.75 * inch, H - 0.9 * inch, "Market Segments")
    cols = [
        ("Enterprise demand stayed resilient even as mid-market softened, and the two "
         "segments now pull in opposite directions on price. The result is a blended "
         "number that hides more than it shows and needs to be read one tier at a time."),
        ("Public sector remains lumpy and entirely deal-driven; a single procurement "
         "cycle moved the whole segment this quarter, which is not a trend and should "
         "not be planned against as though it were a dependable run rate."),
    ]
    columns(c, cols, [0.75 * inch, 4.4 * inch], H - 1.5 * inch, width=42)
    # traffic-light legend — meaning carried by colour alone
    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.75 * inch, H - 4.2 * inch, "Segment health")
    labels = [("Behind", RED), ("Watch", AMBER), ("On plan", GREEN)]
    x = 0.75 * inch
    c.setFont("Helvetica", 11)
    for label, col in labels:
        c.setFillColorRGB(col[0] / 255, col[1] / 255, col[2] / 255)
        c.rect(x, H - 4.65 * inch, 16, 16, stroke=0, fill=1)
        c.setFillColor(colors.black)
        c.drawString(x + 22, H - 4.62 * inch, label)
        x += 1.7 * inch
    c.drawImage(chart_png(os.path.join(HERE, "_c2.png"),
                [(120, GREEN), (200, AMBER), (90, RED), (160, GREEN)]),
                0.75 * inch, H - 7.2 * inch, width=4.0 * inch, height=2.3 * inch)
    footer(c, "Confidential draft - do not distribute - page 2 of 4")
    c.showPage()


def page3(c):
    c.setFont("Helvetica-Bold", 18)
    c.drawString(0.75 * inch, H - 0.9 * inch, "Financial Summary")
    c.setFont("Helvetica", 10)
    c.drawString(0.75 * inch, H - 1.3 * inch,
                 "Revenue and margin by region, with the prior-quarter comparison below.")
    headerless_table(c, 0.75 * inch, H - 1.9 * inch, [
        ("Region", "Revenue", "Margin", "vs Q2"), ("North", "1,240", "31%", "+4"),
        ("South", "980", "22%", "-3"), ("East", "610", "18%", "-6"),
        ("West", "1,455", "27%", "+1")],
        [1.4 * inch, 1.3 * inch, 1.1 * inch, 1.0 * inch], status_col=False)
    headerless_table(c, 0.75 * inch, H - 4.6 * inch, [
        ("Cash", "4.2M", "stable"), ("Runway", "19 mo", "on track"),
        ("Burn", "220K/mo", "at risk")],
        [1.6 * inch, 1.3 * inch, 1.3 * inch])
    c.drawImage(chart_png(os.path.join(HERE, "_c3a.png"),
                [(80, GREEN), (140, GREEN), (200, GREEN)]),
                0.75 * inch, H - 8.0 * inch, width=3.0 * inch, height=1.8 * inch)
    c.drawImage(chart_png(os.path.join(HERE, "_c3b.png"),
                [(180, RED), (120, RED), (60, RED)]),
                4.2 * inch, H - 8.0 * inch, width=3.0 * inch, height=1.8 * inch)
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.grey)
    c.drawString(0.75 * inch, 0.75 * inch,
                 "1. Figures unaudited. 2. Margin excludes one-time items. 3. R&D spend < 5% of revenue.")
    footer(c, "Confidential draft - do not distribute - page 3 of 4")
    c.showPage()


def page4(c):
    c.setFont("Helvetica-Bold", 18)
    c.drawString(0.75 * inch, H - 0.9 * inch, "Regional Detail")
    cols = [
        ("Northern detail confirms the headline: distribution recovered and the region "
         "carried the quarter, but the dependence on two carriers is a risk nobody has "
         "priced and the contingency plan is still a paragraph rather than a process."),
        ("Southern detail is the discounting story in miniature, deal by deal, and the "
         "pattern is consistent enough that it now looks like policy rather than a set "
         "of one-off exceptions the team keeps describing it as."),
        ("Eastern detail is thin by design because the pipeline is thin in fact; there "
         "is no amount of formatting that turns three opportunities into a forecast, "
         "and pretending otherwise is how the last two quarters went wrong."),
    ]
    columns(c, cols, [0.75 * inch, 3.15 * inch, 5.55 * inch], H - 1.5 * inch)
    # callout box placed visually to the side, mid-flow
    c.setFillColorRGB(0.95, 0.95, 0.88)
    c.rect(1.5 * inch, H - 6.4 * inch, 3.5 * inch, 1.1 * inch, stroke=1, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1.65 * inch, H - 5.4 * inch, "Action required")
    c.setFont("Helvetica", 10)
    c.drawString(1.65 * inch, H - 5.7 * inch, "Name a second carrier for the North by")
    c.drawString(1.65 * inch, H - 5.95 * inch, "the end of the month or accept the risk.")
    c.drawImage(chart_png(os.path.join(HERE, "_c4.png"),
                [(70, GREEN), (110, GREEN), (150, AMBER), (90, RED)]),
                4.2 * inch, H - 8.2 * inch, width=3.0 * inch, height=1.9 * inch)
    footer(c, "Confidential draft - do not distribute - page 4 of 4")
    c.showPage()


def build():
    c = pdfcanvas.Canvas(OUT, pagesize=letter)
    page1(c); page2(c); page3(c); page4(c)
    c.save()
    for f in os.listdir(HERE):
        if f.startswith("_c") and f.endswith(".png"):
            os.remove(os.path.join(HERE, f))
    print("wrote", OUT)


if __name__ == "__main__":
    build()
