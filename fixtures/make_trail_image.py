"""Render the reading-order trail over the page as a standalone image — the article
lead visual — using the same line-centroid logic as the frontend. No screenshot needed."""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/hi.png"
OUT = os.path.join(HERE, "trail-lead.png")

img = Image.open(PAGE).convert("RGB")
W, H = img.size
d = ImageDraw.Draw(img, "RGBA")
seq = json.load(open(os.path.join(HERE, "out.json")))["sequence"]


def block_lines(b):
    eps, lines = 0.012, []
    for wd in b["words"]:
        ln = next((l for l in lines if abs(l["y"] - wd["bbox"][1]) < eps), None)
        if not ln:
            ln = {"y": wd["bbox"][1], "items": []}
            lines.append(ln)
        ln["items"].append(wd)
    lines.sort(key=lambda l: l["y"])
    out = []
    for l in lines:
        cx = sum(w["bbox"][0] + w["bbox"][2] / 2 for w in l["items"]) / len(l["items"])
        cy = sum(w["bbox"][1] + w["bbox"][3] / 2 for w in l["items"]) / len(l["items"])
        out.append((cx * W, cy * H))
    return out


pts, nodes = [], []
for i, b in enumerate(seq):
    ls = block_lines(b) if b["words"] else [((b["bbox"][0] + b["bbox"][2] / 2) * W,
                                             (b["bbox"][1] + b["bbox"][3] / 2) * H)]
    nodes.append((i + 1, len(pts)))
    pts.extend(ls)

# polyline
d.line(pts, fill=(255, 92, 92, 235), width=max(3, W // 300), joint="curve")

# numbered nodes at each block start
r = max(14, W // 46)
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", int(r * 1.1))
except Exception:
    font = ImageFont.load_default()
for n, at in nodes:
    x, y = pts[at]
    d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 92, 92, 255), outline="white",
              width=max(2, W // 400))
    tb = d.textbbox((0, 0), str(n), font=font)
    d.text((x - (tb[2] - tb[0]) / 2, y - (tb[3] - tb[1]) / 2 - tb[1]), str(n),
           fill="white", font=font)

img.save(OUT)
print("wrote", OUT, img.size)
