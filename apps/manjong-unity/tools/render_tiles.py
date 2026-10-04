"""Render traditional-style mahjong tile faces for manjong-unity.

Output: <out>/<code>.png at 150x200 (rendered at 2x and downsampled), plus back.png.
Codes: 1m-9m, 1p-9p, 1s-9s, E S W N, RD GD WD, F1-F8.
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
FONT = os.path.join(os.path.dirname(__file__), "NotoSerifTC-Black.otf")
FONT_BOLD = os.path.join(os.path.dirname(__file__), "NotoSerifTC-Bold.otf")

S = 2  # supersampling
W, H = 150 * S, 200 * S
R = 17 * S  # corner radius
EDGE = 14 * S  # visible thickness of the tile body at the bottom

IVORY_TOP = (255, 253, 245)
IVORY_BOTTOM = (239, 231, 210)
BODY = (46, 125, 91)  # green back / body
BODY_DARK = (31, 92, 66)
OUTLINE = (200, 188, 158)

RED = (192, 41, 43)
GREEN = (24, 120, 72)
BLUE = (28, 70, 150)
NAVY = (24, 34, 74)
BLACK = (30, 30, 34)

# Content box on the face (where symbols go)
FACE_BOTTOM = H - EDGE
CX0, CY0, CX1, CY1 = 16 * S, 16 * S, W - 16 * S, FACE_BOTTOM - 14 * S


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def base_tile():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # body (visible as a thick bottom edge)
    d = ImageDraw.Draw(img)
    rounded(d, (0, 2 * S, W - 1, H - 1), R, BODY_DARK)
    rounded(d, (0, 0, W - 1, H - 3 * S), R, BODY)
    # face with a vertical gradient
    face = Image.new("RGBA", (W, FACE_BOTTOM), (0, 0, 0, 0))
    grad = Image.new("RGBA", (W, FACE_BOTTOM))
    gd = ImageDraw.Draw(grad)
    for y in range(FACE_BOTTOM):
        t = y / max(1, FACE_BOTTOM - 1)
        c = tuple(int(IVORY_TOP[i] * (1 - t) + IVORY_BOTTOM[i] * t) for i in range(3)) + (255,)
        gd.line([(0, y), (W, y)], fill=c)
    mask = Image.new("L", (W, FACE_BOTTOM), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, FACE_BOTTOM - 1), radius=R, fill=255)
    face.paste(grad, (0, 0), mask)
    img.alpha_composite(face)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, W - 1, FACE_BOTTOM - 1), radius=R, outline=OUTLINE, width=2 * S)
    # soft highlight along the top
    d.rounded_rectangle((3 * S, 3 * S, W - 4 * S, FACE_BOTTOM - 4 * S), radius=R - 3 * S, outline=(255, 255, 255, 140), width=S)
    return img


def text_center(draw, cx, cy, s, size, fill, bold=False):
    f = font(size, bold)
    bbox = draw.textbbox((0, 0), s, font=f)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - w / 2 - bbox[0], cy - h / 2 - bbox[1]), s, font=f, fill=fill)


def fit_text(draw, cx, cy, s, max_w, max_h, fill, bold=False):
    size = int(max_h)
    while size > 10:
        f = font(size, bold)
        bbox = draw.textbbox((0, 0), s, font=f)
        if bbox[2] - bbox[0] <= max_w and bbox[3] - bbox[1] <= max_h:
            break
        size -= 2
    text_center(draw, cx, cy, s, size, fill, bold)


# ---------------------------------------------------------------- characters (萬)
NUMS = "一二三四五六七八九"


def draw_man(img, n):
    d = ImageDraw.Draw(img)
    cx = (CX0 + CX1) / 2
    box_h = CY1 - CY0
    fit_text(d, cx, CY0 + box_h * 0.27, NUMS[n - 1], (CX1 - CX0) * 0.86, box_h * 0.42, NAVY)
    fit_text(d, cx, CY0 + box_h * 0.73, "萬", (CX1 - CX0) * 0.86, box_h * 0.46, RED)


# ---------------------------------------------------------------- dots (筒)
def coin(d, cx, cy, r, color):
    """Traditional dot: coloured disc, white ring, coloured core, tiny highlight."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    d.ellipse((cx - r * 0.72, cy - r * 0.72, cx + r * 0.72, cy + r * 0.72), fill=(255, 252, 240))
    d.ellipse((cx - r * 0.56, cy - r * 0.56, cx + r * 0.56, cy + r * 0.56), fill=color)
    d.ellipse((cx - r * 0.22, cy - r * 0.22, cx + r * 0.22, cy + r * 0.22), fill=(255, 252, 240))
    # petal ticks between rings
    for k in range(8):
        a = k * math.pi / 4
        x1, y1 = cx + math.cos(a) * r * 0.60, cy + math.sin(a) * r * 0.60
        x2, y2 = cx + math.cos(a) * r * 0.70, cy + math.sin(a) * r * 0.70
        d.line([(x1, y1), (x2, y2)], fill=(255, 252, 240), width=max(1, int(r * 0.08)))


def grid(cols, rows, x0=CX0, y0=CY0, x1=CX1, y1=CY1):
    xs = [x0 + (x1 - x0) * (i + 0.5) / cols for i in range(cols)]
    ys = [y0 + (y1 - y0) * (j + 0.5) / rows for j in range(rows)]
    return xs, ys


def draw_pin(img, n):
    d = ImageDraw.Draw(img)
    cw, ch = CX1 - CX0, CY1 - CY0
    cx, cy = (CX0 + CX1) / 2, (CY0 + CY1) / 2
    if n == 1:
        r = min(cw, ch) * 0.44
        coin(d, cx, cy, r, GREEN)
        d.ellipse((cx - r * 0.40, cy - r * 0.40, cx + r * 0.40, cy + r * 0.40), fill=RED)
        d.ellipse((cx - r * 0.18, cy - r * 0.18, cx + r * 0.18, cy + r * 0.18), fill=(255, 252, 240))
        for k in range(16):
            a = k * math.pi / 8
            px, py = cx + math.cos(a) * r * 0.86, cy + math.sin(a) * r * 0.86
            d.ellipse((px - r * 0.05, py - r * 0.05, px + r * 0.05, py + r * 0.05), fill=BLUE)
        return
    layouts = {
        2: ([(0.5, 0.26), (0.5, 0.74)], [BLUE, GREEN], 0.21),
        3: ([(0.22, 0.18), (0.5, 0.5), (0.78, 0.82)], [BLUE, RED, GREEN], 0.17),
        4: ([(0.27, 0.27), (0.73, 0.27), (0.27, 0.73), (0.73, 0.73)], [BLUE, GREEN, GREEN, BLUE], 0.19),
        5: ([(0.25, 0.2), (0.75, 0.2), (0.5, 0.5), (0.25, 0.8), (0.75, 0.8)], [BLUE, GREEN, RED, GREEN, BLUE], 0.165),
        6: ([(0.28, 0.16), (0.72, 0.16), (0.28, 0.52), (0.72, 0.52), (0.28, 0.84), (0.72, 0.84)],
            [GREEN, GREEN, RED, RED, RED, RED], 0.15),
        7: ([(0.2, 0.12), (0.5, 0.22), (0.8, 0.32), (0.28, 0.6), (0.72, 0.6), (0.28, 0.87), (0.72, 0.87)],
            [GREEN, GREEN, GREEN, RED, RED, RED, RED], 0.125),
        8: ([(0.28, 0.12), (0.72, 0.12), (0.28, 0.375), (0.72, 0.375), (0.28, 0.625), (0.72, 0.625), (0.28, 0.88), (0.72, 0.88)],
            [BLUE] * 8, 0.12),
        9: ([(x, y) for y in (0.17, 0.5, 0.83) for x in (0.2, 0.5, 0.8)],
            [BLUE] * 3 + [RED] * 3 + [GREEN] * 3, 0.135),
    }
    pts, colors, rf = layouts[n]
    r = min(cw, ch) * rf if n != 2 else ch * 0.19
    for (fx, fy), c in zip(pts, colors):
        coin(d, CX0 + cw * fx, CY0 + ch * fy, r, c)


# ---------------------------------------------------------------- bamboo (條)
def stick(d, cx, cy, w, h, color):
    """A bamboo stick: rounded body, three nodes, lighter centre line."""
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    d.rounded_rectangle((x0, y0, x1, y1), radius=w / 2, fill=color)
    light = tuple(min(255, int(v + (255 - v) * 0.45)) for v in color)
    d.line([(cx, y0 + w * 0.5), (cx, y1 - w * 0.5)], fill=light, width=max(1, int(w * 0.18)))
    for t in (0.0, 0.5, 1.0):
        y = y0 + w * 0.35 + (h - w * 0.7) * t
        d.line([(x0 + w * 0.05, y), (x1 - w * 0.05, y)], fill=(255, 252, 240), width=max(1, int(w * 0.16)))
        d.ellipse((x0 - w * 0.08, y - w * 0.18, x0 + w * 0.22, y + w * 0.18), fill=color)
        d.ellipse((x1 - w * 0.22, y - w * 0.18, x1 + w * 0.08, y + w * 0.18), fill=color)


def draw_bird(img):
    """1條: a stylised peacock."""
    d = ImageDraw.Draw(img)
    cw, ch = CX1 - CX0, CY1 - CY0
    cx, cy = (CX0 + CX1) / 2, (CY0 + CY1) / 2
    # tail fan
    for k in range(7):
        a = math.radians(200 + k * 20)
        tx, ty = cx + math.cos(a) * cw * 0.42, cy + ch * 0.22 + math.sin(a) * ch * 0.42
        d.line([(cx, cy + ch * 0.22), (tx, ty)], fill=GREEN, width=int(5 * S))
        d.ellipse((tx - 9 * S, ty - 9 * S, tx + 9 * S, ty + 9 * S), fill=BLUE)
        d.ellipse((tx - 4 * S, ty - 4 * S, tx + 4 * S, ty + 4 * S), fill=(230, 180, 40))
    # body
    d.ellipse((cx - cw * 0.17, cy + ch * 0.02, cx + cw * 0.17, cy + ch * 0.38), fill=GREEN)
    d.ellipse((cx - cw * 0.10, cy + ch * 0.08, cx + cw * 0.10, cy + ch * 0.30), fill=(60, 160, 100))
    # neck and head
    d.line([(cx, cy + ch * 0.08), (cx + cw * 0.08, cy - ch * 0.12)], fill=BLUE, width=int(9 * S))
    hx, hy = cx + cw * 0.09, cy - ch * 0.16
    d.ellipse((hx - 11 * S, hy - 11 * S, hx + 11 * S, hy + 11 * S), fill=BLUE)
    d.polygon([(hx + 9 * S, hy - 2 * S), (hx + 24 * S, hy + 3 * S), (hx + 9 * S, hy + 6 * S)], fill=(230, 160, 30))
    d.ellipse((hx + 2 * S, hy - 5 * S, hx + 6 * S, hy - 1 * S), fill=(255, 252, 240))
    # crest
    for k in range(3):
        a = math.radians(-120 + k * 25)
        d.line([(hx, hy - 8 * S), (hx + math.cos(a) * 20 * S, hy - 8 * S + math.sin(a) * 20 * S)], fill=RED, width=int(3 * S))
        d.ellipse((hx + math.cos(a) * 20 * S - 4 * S, hy - 8 * S + math.sin(a) * 20 * S - 4 * S,
                   hx + math.cos(a) * 20 * S + 4 * S, hy - 8 * S + math.sin(a) * 20 * S + 4 * S), fill=RED)
    # legs
    for dx in (-0.06, 0.06):
        d.line([(cx + cw * dx, cy + ch * 0.36), (cx + cw * dx, cy + ch * 0.46)], fill=RED, width=int(4 * S))


def tilted_stick(img, cx, cy, w, h, angle, color):
    """Draw a stick on its own layer, rotate it (degrees, counter-clockwise) and composite it at (cx, cy)."""
    size = int(max(w, h) * 1.6)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    stick(ImageDraw.Draw(layer), size / 2, size / 2, w, h, color)
    layer = layer.rotate(angle, resample=Image.BICUBIC)
    img.alpha_composite(layer, (int(cx - size / 2), int(cy - size / 2)))


def draw_eight_bamboo(img):
    """8條: the classic 'M' on top and an upside-down 'M' below (outer sticks upright, inner two leaning)."""
    cw, ch = CX1 - CX0, CY1 - CY0
    w = min(cw * 0.13, 20 * S)
    h = ch * 0.40
    for half, (cy_frac, sign) in enumerate(((0.26, 1), (0.74, -1))):
        cy = CY0 + ch * cy_frac
        tilted_stick(img, CX0 + cw * 0.12, cy, w, h, 0, GREEN)
        tilted_stick(img, CX0 + cw * 0.88, cy, w, h, 0, GREEN)
        # top half: inner sticks meet at the bottom (a 'V' inside the M); bottom half mirrors it
        tilted_stick(img, CX0 + cw * 0.37, cy, w, h * 1.04, 22 * sign, GREEN)
        tilted_stick(img, CX0 + cw * 0.63, cy, w, h * 1.04, -22 * sign, GREEN)


def draw_sou(img, n):
    if n == 1:
        draw_bird(img)
        return
    if n == 8:
        draw_eight_bamboo(img)
        return
    d = ImageDraw.Draw(img)
    cw, ch = CX1 - CX0, CY1 - CY0
    G, Rr = GREEN, RED
    layouts = {
        2: ([(0.5, 0.26), (0.5, 0.74)], [G, G], 1, 2),
        3: ([(0.5, 0.26), (0.28, 0.74), (0.72, 0.74)], [G, G, G], 2, 2),
        4: ([(0.3, 0.26), (0.7, 0.26), (0.3, 0.74), (0.7, 0.74)], [G] * 4, 2, 2),
        5: ([(0.22, 0.26), (0.78, 0.26), (0.5, 0.5), (0.22, 0.74), (0.78, 0.74)], [G, G, Rr, G, G], 3, 2),
        6: ([(x, y) for y in (0.26, 0.74) for x in (0.2, 0.5, 0.8)], [G] * 6, 3, 2),
        7: ([(0.5, 0.17)] + [(x, y) for y in (0.5, 0.83) for x in (0.2, 0.5, 0.8)], [Rr] + [G] * 6, 3, 3),
        8: ([(x, y) for y in (0.26, 0.74) for x in (0.14, 0.38, 0.62, 0.86)], [G] * 8, 4, 2),
        9: ([(x, y) for y in (0.17, 0.5, 0.83) for x in (0.2, 0.5, 0.8)], [G, Rr, G] * 3, 3, 3),
    }
    pts, colors, cols, rows = layouts[n]
    w = cw / cols * (0.42 if cols < 4 else 0.55)
    w = min(w, 22 * S)
    h = ch / rows * 0.82
    for (fx, fy), c in zip(pts, colors):
        stick(d, CX0 + cw * fx, CY0 + ch * fy, w, h, c)


# ---------------------------------------------------------------- honors & flowers
HONOR = {"E": ("東", NAVY), "S": ("南", NAVY), "W": ("西", NAVY), "N": ("北", NAVY), "RD": ("中", RED), "GD": ("發", GREEN)}
FLOWER = {
    "F1": ("春", RED, "1"), "F2": ("夏", RED, "2"), "F3": ("秋", RED, "3"), "F4": ("冬", RED, "4"),
    "F5": ("梅", BLUE, "1"), "F6": ("蘭", BLUE, "2"), "F7": ("竹", BLUE, "3"), "F8": ("菊", BLUE, "4"),
}


def draw_honor(img, code):
    d = ImageDraw.Draw(img)
    cx, cy = (CX0 + CX1) / 2, (CY0 + CY1) / 2
    if code == "WD":
        m = 10 * S
        d.rectangle((CX0 + m, CY0 + m * 1.6, CX1 - m, CY1 - m * 1.6), outline=BLUE, width=7 * S)
        d.rectangle((CX0 + m + 14 * S, CY0 + m * 1.6 + 14 * S, CX1 - m - 14 * S, CY1 - m * 1.6 - 14 * S), outline=BLUE, width=3 * S)
        return
    ch, color = HONOR[code]
    fit_text(d, cx, cy, ch, (CX1 - CX0) * 0.95, (CY1 - CY0) * 0.72, color)


def draw_flower(img, code):
    d = ImageDraw.Draw(img)
    ch, color, num = FLOWER[code]
    cx, cy = (CX0 + CX1) / 2, (CY0 + CY1) / 2 + 8 * S
    # simple blossom decoration behind the character
    for k in range(5):
        a = math.radians(-90 + k * 72)
        px, py = cx + math.cos(a) * 40 * S, cy + math.sin(a) * 40 * S
        d.ellipse((px - 22 * S, py - 22 * S, px + 22 * S, py + 22 * S), fill=(252, 222, 222) if color == RED else (214, 228, 250))
    fit_text(d, cx, cy, ch, (CX1 - CX0) * 0.80, (CY1 - CY0) * 0.56, color)
    text_center(d, CX0 + 16 * S, CY0 + 18 * S, num, 30 * S, GREEN if color == RED else RED, bold=True)


def render(code):
    img = base_tile()
    if code[0].isdigit():
        n, suit = int(code[0]), code[1]
        {"m": draw_man, "p": draw_pin, "s": draw_sou}[suit](img, n)
    elif code.startswith("F"):
        draw_flower(img, code)
    else:
        draw_honor(img, code)
    return finish(img)


def render_back():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rounded(d, (0, 2 * S, W - 1, H - 1), R, BODY_DARK)
    rounded(d, (0, 0, W - 1, H - 3 * S), R, BODY)
    d.rounded_rectangle((10 * S, 10 * S, W - 11 * S, H - 16 * S), radius=R - 8 * S, outline=(120, 190, 150), width=2 * S)
    return finish(img)


def finish(img):
    # drop shadow + downsample
    shadow = Image.new("RGBA", (W + 12 * S, H + 12 * S), (0, 0, 0, 0))
    alpha = img.split()[3].point(lambda a: int(a * 0.28))
    shadow.paste((40, 30, 20, 255), (6 * S, 9 * S), alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(4 * S))
    shadow.alpha_composite(img, (6 * S, 4 * S))
    return shadow.resize(((W + 12 * S) // S, (H + 12 * S) // S), Image.LANCZOS).crop((6, 4, 6 + W // S, 4 + H // S))


def main():
    os.makedirs(OUT, exist_ok=True)
    codes = [f"{n}{s}" for s in "mps" for n in range(1, 10)] + ["E", "S", "W", "N", "RD", "GD", "WD"] + [f"F{i}" for i in range(1, 9)]
    for c in codes:
        render(c).save(os.path.join(OUT, f"{c}.png"), optimize=True)
    render_back().save(os.path.join(OUT, "back.png"), optimize=True)
    # contact sheet for review
    cols = 9
    tiles = codes + ["back"]
    sheet = Image.new("RGBA", (cols * 160 + 10, ((len(tiles) + cols - 1) // cols) * 210 + 10), (196, 228, 205, 255))
    for i, c in enumerate(tiles):
        t = Image.open(os.path.join(OUT, f"{c}.png"))
        sheet.alpha_composite(t, (10 + (i % cols) * 160, 10 + (i // cols) * 210))
    sheet.save(os.path.join(OUT, "_sheet.png"))
    print("rendered", len(tiles))


if __name__ == "__main__":
    main()
