"""
Generate a single page that packs every accessibility failure at once. It is both
the test fixture AND the demo screenshot. The three TALL columns are the point:
a screen reader announces column 1 top-to-bottom, then leaps back up to column 2,
then column 3 — so the reading-order trail zigzags violently across the page.

Failures included:
  1. Three tall newspaper columns  -> reading order leaps between columns
  2. A data table with NO header row -> numbers read with nothing attached
  3. A chart image with NO caption / alt text -> "Image. No description available."
  4. A red/green status column -> identical grey for ~1 in 12 men
  5. A footer sitting in the flow
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib import colors
from PIL import Image, ImageDraw
import os, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.path.join(HERE, "test.pdf")
CHART_PATH = os.path.join(HERE, "_chart.png")

RED = (0xC0, 0x39, 0x2B)
GREEN = (0x27, 0xAE, 0x60)

COLS = [
    ("Northern region held steady through the quarter despite the supply delays "
     "that hit every distribution hub in the first six weeks, and the team still "
     "closed within two points of the original commit for the period. Fulfilment "
     "recovered once the second carrier came online, and backlog cleared by the "
     "final week without the overtime the plan had budgeted for."),
    ("Southern accounts grew on the back of two large renewals, though margin "
     "slipped as discounting crept into the final stage of each deal and set an "
     "expectation the field will have to unwind before the next cycle begins. Two "
     "further deals were pulled forward from the coming quarter, which flatters "
     "this result and leaves a visible gap that the forecast has not yet caught."),
    ("Eastern pipeline looks thin for the coming quarter and needs attention now "
     "rather than in the review that nobody schedules until the numbers have "
     "already slipped and the recovery has become a great deal more expensive. "
     "Coverage is concentrated in three names, and if any one of them slips the "
     "whole region misses, so the risk here is narrower and sharper than it looks."),
]


def make_chart_png():
    W, H = 520, 300
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    for i, (h, col) in enumerate([(90, RED), (150, GREEN), (210, RED),
                                  (120, GREEN), (255, GREEN)]):
        x = 40 + i * 90
        d.rectangle([x, H - 40 - h, x + 60, H - 40], fill=col)
    d.line([30, H - 40, W - 20, H - 40], fill="black", width=2)
    d.line([30, 20, 30, H - 40], fill="black", width=2)
    img.save(CHART_PATH)


def build_pdf():
    make_chart_png()
    c = pdfcanvas.Canvas(PDF_PATH, pagesize=letter)
    w, h = letter  # 612 x 792 pt

    # Title
    c.setFont("Helvetica-Bold", 22)
    c.drawString(0.75 * inch, h - 0.85 * inch, "Q3 Regional Review")

    # Three TALL columns
    c.setFont("Helvetica", 10)
    col_x = [0.75 * inch, 3.15 * inch, 5.55 * inch]
    top = h - 1.35 * inch
    for cx, para in zip(col_x, COLS):
        y = top
        for line in textwrap.wrap(para, width=30):
            c.drawString(cx, y, line)
            y -= 14

    # Data table with NO header row + red/green status column
    ty = h - 5.0 * inch
    rows = [
        ("Northern", "1,240", "on track", GREEN),
        ("Southern", "980", "at risk", RED),
        ("Eastern", "610", "on track", GREEN),
        ("Western", "1,455", "at risk", RED),
    ]
    c.setFont("Helvetica", 11)
    row_h = 0.32 * inch
    x0 = 0.75 * inch
    colw = [1.6 * inch, 1.1 * inch, 1.6 * inch]
    for i, (region, num, status, col) in enumerate(rows):
        ry = ty - i * row_h
        c.setStrokeColor(colors.black)
        c.rect(x0, ry - row_h + 6, sum(colw), row_h, stroke=1, fill=0)
        c.setFillColor(colors.black)
        c.drawString(x0 + 6, ry - 8, region)
        c.drawString(x0 + colw[0] + 6, ry - 8, num)
        c.setFillColorRGB(col[0] / 255, col[1] / 255, col[2] / 255)
        c.drawString(x0 + colw[0] + colw[1] + 6, ry - 8, status)
        c.setFillColor(colors.black)

    # Chart image with NO caption
    c.drawImage(CHART_PATH, 4.1 * inch, h - 5.15 * inch, width=3.0 * inch,
                height=1.9 * inch, preserveAspectRatio=True, mask=None)

    # Footer in the flow
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.grey)
    c.drawString(0.75 * inch, 0.5 * inch,
                 "Confidential draft - do not distribute - page 1 of 1")

    c.showPage()
    c.save()
    if os.path.exists(CHART_PATH):
        os.remove(CHART_PATH)
    print("wrote", PDF_PATH)


if __name__ == "__main__":
    build_pdf()
