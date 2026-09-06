"""Regenerates public/images/og-default.png in the site palette (ivory / black / yellow). Run with api/.venv (has Pillow)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SITE = Path(__file__).resolve().parents[1]
W, H = 1200, 630
CREAM, INK, YELLOW, MUTED = "#F5F3EC", "#141413", "#FFD84D", "#5F5E5A"


def font(size: int, serif: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        ["/System/Library/Fonts/Supplemental/Georgia.ttf", "/System/Library/Fonts/Supplemental/Times New Roman.ttf"]
        if serif
        else ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"]
    )
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


img = Image.new("RGB", (W, H), CREAM)
d = ImageDraw.Draw(img)
d.rectangle([0, 0, W, 14], fill=YELLOW)

logo = Image.open(SITE / "public/images/logo-dark.png").convert("RGBA")
logo = logo.resize((int(logo.width * 64 / logo.height), 64))
img.paste(logo, (80, 70), logo)

d.text((80, 180), "Free Local SEO Tools for", font=font(74, True), fill=INK)
d.text((80, 262), "Google Search & AI Answers", font=font(74, True), fill=INK)

pill = font(24)
label = "Ask for a tool \u2192 built free within 3 days"
pw = d.textlength(label, font=pill) + 48
d.rounded_rectangle([80, 380, 80 + pw, 436], radius=28, fill=YELLOW)
d.text((104, 394), label, font=pill, fill=INK)

x, y, small = 80, 490, font(22)
for t in ["Free forever", "No card required. Never.", "No account needed"]:
    w = d.textlength(t, font=small) + 44
    d.rounded_rectangle([x, y, x + w, y + 46], radius=23, outline=INK, width=2)
    d.text((x + 22, y + 11), t, font=small, fill=INK)
    x += w + 14
d.text((80, 572), "locan.ai", font=font(24), fill=MUTED)

out = SITE / "public/images/og-default.png"
img.save(out, optimize=True)
print("wrote", out, img.size)
