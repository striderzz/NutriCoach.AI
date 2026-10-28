"""Draws the NutriCoach.AI icon (leaf on a green tile) into static/icon.png and static/icon.ico."""
import math
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
OUT = Path(__file__).resolve().parent / "static"


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile = Image.new("RGBA", (S, S))
    top, bottom = (46, 204, 113), (12, 74, 40)
    for y in range(S):                                   # vertical gradient
        t = y / (S - 1)
        tile.paste(tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)), (0, y, S, y + 1))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=220, fill=255)
    img.paste(tile, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # leaf: two sine-bulged edges between tips A and B on the diagonal, then midrib and veins
    ax, ay, bx, by, w = 250, 774, 774, 250, 200
    pts = []
    for side in (1, -1):
        for k in range(61):
            t = k / 60 if side == 1 else 1 - k / 60
            bulge = side * w * math.sin(math.pi * t) ** 0.8 / math.sqrt(2)
            pts.append((ax + (bx - ax) * t + bulge, ay + (by - ay) * t + bulge))
    d.polygon(pts, fill=(255, 255, 255, 255))
    rib = (26, 138, 69, 255)
    d.line((ax + 60, ay - 60, bx - 40, by + 40), fill=rib, width=20)
    for t in (0.3, 0.48, 0.66):
        x, y = ax + (bx - ax) * t, ay + (by - ay) * t
        for side in (1, -1):
            d.line((x, y, x + 95 + side * 75, y - 95 + side * 75), fill=rib, width=13)
    return img


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    icon = draw()
    icon.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png")
    icon.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", OUT / "icon.png", OUT / "icon.ico")
