"""Generate a background image for the DMG installer.
Dark background with a subtle arrow + app name — matches the app's look.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "dmg-bg.png"

W, H = 600, 400
BG_TOP = (18, 21, 28)
BG_BOT = (32, 37, 49)
ARROW = (124, 156, 255)
MUTED = (120, 128, 144)


def main():
    img = Image.new("RGB", (W, H), BG_TOP)
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        for x in range(W):
            px[x, y] = (r, g, b)

    d = ImageDraw.Draw(img)

    # A subtle arrow in the middle between the two icon positions (140 and 460 @ y=200-ish)
    # Icons sit at about y=190, so draw arrow just above that area at the visual center
    mid_y = H // 2
    shaft_x0 = 240
    shaft_x1 = 360
    shaft_h = 3
    d.rectangle([(shaft_x0, mid_y - shaft_h // 2), (shaft_x1, mid_y + shaft_h // 2)], fill=ARROW)
    # Arrow head
    hs = 12
    hx = shaft_x1
    d.polygon(
        [(hx, mid_y - hs), (hx + hs * 1.5, mid_y), (hx, mid_y + hs)],
        fill=ARROW,
    )

    # Title text at bottom — use default bundled font since system fonts are unreliable in Pillow
    title = "Through the Wall"
    subtitle = "Drag the app to your Applications folder"
    try:
        font_t = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 22)
        font_s = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 12)
    except Exception:
        font_t = ImageFont.load_default()
        font_s = ImageFont.load_default()

    tw = d.textlength(title, font=font_t)
    sw = d.textlength(subtitle, font=font_s)
    d.text(((W - tw) / 2, H - 70), title, fill=(230, 233, 238), font=font_t)
    d.text(((W - sw) / 2, H - 40), subtitle, fill=MUTED, font=font_s)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)

    # Also save @2x for retina — dmgbuild supports tiff with two resolutions
    img2x = Image.new("RGB", (W * 2, H * 2), BG_TOP)
    # Simple approach: scale up with nearest-ish; honestly for retina DMG backgrounds we'd draw at 2x
    # but for a background this is fine as a placeholder
    img2x = img.resize((W * 2, H * 2), Image.LANCZOS)
    img2x.save(ROOT / "assets" / "dmg-bg@2x.png")

    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
