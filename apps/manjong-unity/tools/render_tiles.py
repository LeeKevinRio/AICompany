"""Render Taiwan-style white mahjong tile faces for manjong-unity.

Usage: python render_tiles.py <out-dir> [<sheet-dir>]

Output: <out>/<code>.png at 150x200 (rendered at 3x and downsampled), plus back.png.
Codes: 1m-9m, 1p-9p, 1s-9s, E S W N, RD GD WD, F1-F8.
If <sheet-dir> is given, contact sheets (full size and 44 px high) are written there
for visual review; nothing but the tile PNGs is ever written into <out>.

Everything except the glyphs is drawn procedurally (circles, bead-chain bamboo, bird,
flower/plant illustrations). Glyphs use Noto Serif TC (SIL OFL 1.1, not committed).
The style (white body, muted green / crimson / near-black palette, bead-chain bamboo,
flower tiles with corner numbers and plant pictures) follows common Taiwan machine
mahjong sets; no image is copied or traced, all shapes are generated here.
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
SHEET_DIR = sys.argv[2] if len(sys.argv) > 2 else None
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [HERE] + ([os.environ["TILE_FONT_DIR"]] if os.environ.get("TILE_FONT_DIR") else [])


def find_font(name):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"{name} not found in {FONT_DIRS} (see tools/README.md)")


FONT = find_font("NotoSerifTC-Black.otf")
FONT_BOLD = find_font("NotoSerifTC-Bold.otf")

S = 3  # supersampling
W, H = 150 * S, 200 * S
R = 16 * S  # corner radius
EDGE = 14 * S  # visible thickness of the tile body at the bottom

# white porcelain face, light jade thickness
FACE_TOP = (255, 255, 252)
FACE_BOTTOM_C = (240, 240, 233)
BODY = (200, 217, 204)
BODY_DARK = (150, 174, 158)
OUTLINE = (206, 206, 198)
PAPER = (255, 255, 250)  # "white" used inside symbols

RED = (196, 30, 64)  # crimson
GREEN = (36, 92, 62)  # dark green
GREEN_L = (74, 128, 92)
INK = (26, 28, 36)  # near-black
BLUE = INK  # kept name for pin layout readability
BROWN = (84, 74, 52)

# Content box on the face (where symbols go)
FACE_BOTTOM = H - EDGE
CX0, CY0, CX1, CY1 = 15 * S, 15 * S, W - 15 * S, FACE_BOTTOM - 13 * S


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def base_tile():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rounded(d, (0, 2 * S, W - 1, H - 1), R, BODY_DARK)
    rounded(d, (0, 0, W - 1, H - 3 * S), R, BODY)
    face = Image.new("RGBA", (W, FACE_BOTTOM), (0, 0, 0, 0))
    grad = Image.new("RGBA", (W, FACE_BOTTOM))
    gd = ImageDraw.Draw(grad)
    for y in range(FACE_BOTTOM):
        t = y / max(1, FACE_BOTTOM - 1)
        c = tuple(int(FACE_TOP[i] * (1 - t) + FACE_BOTTOM_C[i] * t) for i in range(3)) + (255,)
        gd.line([(0, y), (W, y)], fill=c)
    mask = Image.new("L", (W, FACE_BOTTOM), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, FACE_BOTTOM - 1), radius=R, fill=255)
    face.paste(grad, (0, 0), mask)
    img.alpha_composite(face)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, W - 1, FACE_BOTTOM - 1), radius=R, outline=OUTLINE, width=2 * S)
    d.rounded_rectangle((3 * S, 3 * S, W - 4 * S, FACE_BOTTOM - 4 * S), radius=R - 3 * S, outline=(255, 255, 255, 170), width=S)
    return img


def text_center(draw, cx, cy, s, size, fill, bold=False):
    f = font(size, bold)
    bbox = draw.textbbox((0, 0), s, font=f)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - w / 2 - bbox[0], cy - h / 2 - bbox[1]), s, font=f, fill=fill)


def fit_text(draw, cx, cy, s, max_w, max_h, fill, bold=False):
    size = int(max_h * 1.3)
    while size > 10:
        f = font(size, bold)
        bbox = draw.textbbox((0, 0), s, font=f)
        if bbox[2] - bbox[0] <= max_w and bbox[3] - bbox[1] <= max_h:
            break
        size -= 2
    text_center(draw, cx, cy, s, size, fill, bold)


# ---------------------------------------------------------------- drawing helpers
def lerp(a, b, t):
    return a + (b - a) * t


def mix(c, o, t):
    return tuple(int(c[i] * (1 - t) + o[i] * t) for i in range(3))


def bezier(p0, p1, p2, p3, n=36):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return pts


def stroke(d, pts, w0, w1, color):
    """Polyline with linearly tapering width, drawn as overlapping discs (points are densified)."""
    dense = [pts[0]]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        steps = max(1, int(math.hypot(bx - ax, by - ay) / max(1.0, min(w0, w1) * 0.3)))
        for k in range(1, steps + 1):
            dense.append((lerp(ax, bx, k / steps), lerp(ay, by, k / steps)))
    n = len(dense) - 1
    for i, (x, y) in enumerate(dense):
        r = lerp(w0, w1, i / max(1, n)) / 2
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def leaf(d, p0, p1, width, color, bend=0.0, vein=None):
    """Lens-shaped leaf from p0 (base) to p1 (tip); bend curves the axis sideways (fraction of length)."""
    vx, vy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(vx, vy) or 1.0
    nx, ny = -vy / length, vx / length
    left, right, axis = [], [], []
    steps = 22
    for i in range(steps + 1):
        t = i / steps
        off = bend * length * math.sin(math.pi * t)
        cx = p0[0] + vx * t + nx * off
        cy = p0[1] + vy * t + ny * off
        half = width / 2 * math.sin(math.pi * t) ** 0.8
        left.append((cx + nx * half, cy + ny * half))
        right.append((cx - nx * half, cy - ny * half))
        axis.append((cx, cy))
    d.polygon(left + right[::-1], fill=color)
    if vein:
        d.line(axis[2:-2], fill=vein, width=max(1, int(S * 0.9)))


def petal(d, cx, cy, angle, r0, r1, width, color):
    """Petal pointing at `angle` (radians) starting r0 from the centre and reaching r1."""
    p0 = (cx + math.cos(angle) * r0, cy + math.sin(angle) * r0)
    p1 = (cx + math.cos(angle) * r1, cy + math.sin(angle) * r1)
    leaf(d, p0, p1, width, color)


def dot(d, x, y, r, color):
    d.ellipse((x - r, y - r, x + r, y + r), fill=color)


# ---------------------------------------------------------------- characters (萬)
NUMS = "一二三四伍六七八九"


def draw_man(img, n):
    d = ImageDraw.Draw(img)
    cx = (CX0 + CX1) / 2
    box_h = CY1 - CY0
    fit_text(d, cx, CY0 + box_h * 0.255, NUMS[n - 1], (CX1 - CX0) * 0.80, box_h * 0.36, INK)
    fit_text(d, cx, CY0 + box_h * 0.725, "萬", (CX1 - CX0) * 0.90, box_h * 0.46, RED)


# ---------------------------------------------------------------- dots (筒)
def coin(d, cx, cy, r, color):
    """Dot: coloured disc, thin inner ring and a four-lobed cross cut, hollow centre."""
    dot(d, cx, cy, r, color)
    dot(d, cx, cy, r * 0.80, PAPER)
    dot(d, cx, cy, r * 0.70, color)
    arm = max(1.0, r * 0.17)
    for k in range(4):
        a = k * math.pi / 2
        d.line([(cx + math.cos(a) * r * 0.30, cy + math.sin(a) * r * 0.30),
                (cx + math.cos(a) * r * 0.74, cy + math.sin(a) * r * 0.74)], fill=PAPER, width=int(arm * 2))
    dot(d, cx, cy, r * 0.30, PAPER)
    dot(d, cx, cy, r * 0.17, color)


def big_coin(d, cx, cy, r):
    """1筒: large disc, scalloped ring, red four-lobed core."""
    dot(d, cx, cy, r, GREEN)
    dot(d, cx, cy, r * 0.90, PAPER)
    dot(d, cx, cy, r * 0.84, GREEN)
    for k in range(20):
        a = k * 2 * math.pi / 20
        dot(d, cx + math.cos(a) * r * 0.68, cy + math.sin(a) * r * 0.68, r * 0.095, PAPER)
    dot(d, cx, cy, r * 0.55, PAPER)
    dot(d, cx, cy, r * 0.50, GREEN)
    dot(d, cx, cy, r * 0.44, PAPER)
    coin(d, cx, cy, r * 0.42, RED)


def draw_pin(img, n):
    d = ImageDraw.Draw(img)
    cw, ch = CX1 - CX0, CY1 - CY0
    cx, cy = (CX0 + CX1) / 2, (CY0 + CY1) / 2
    if n == 1:
        big_coin(d, cx, cy, min(cw, ch) * 0.47)
        return
    G, K, Rr = GREEN, INK, RED
    layouts = {
        2: ([(0.5, 0.25), (0.5, 0.75)], [G, K], 0.24),
        3: ([(0.24, 0.2), (0.5, 0.5), (0.76, 0.8)], [K, Rr, G], 0.2),
        4: ([(0.27, 0.27), (0.73, 0.27), (0.27, 0.73), (0.73, 0.73)], [G, K, K, G], 0.2),
        5: ([(0.27, 0.2), (0.73, 0.2), (0.5, 0.5), (0.27, 0.8), (0.73, 0.8)], [G, K, Rr, K, G], 0.19),
        6: ([(0.27, 0.17), (0.73, 0.17), (0.27, 0.57), (0.73, 0.57), (0.27, 0.84), (0.73, 0.84)],
            [G, G, Rr, Rr, Rr, Rr], 0.19),
        7: ([(0.18, 0.12), (0.45, 0.24), (0.72, 0.36), (0.27, 0.62), (0.73, 0.62), (0.27, 0.87), (0.73, 0.87)],
            [G, G, G, Rr, Rr, Rr, Rr], 0.155),
        8: ([(x, y) for y in (0.125, 0.375, 0.625, 0.875) for x in (0.27, 0.73)], [K] * 8, 0.17),
        9: ([(x, y) for y in (0.16, 0.5, 0.84) for x in (0.2, 0.5, 0.8)],
            [K] * 3 + [Rr] * 3 + [G] * 3, 0.14),
    }
    pts, colors, rf = layouts[n]
    r = min(cw, ch) * rf
    for (fx, fy), c in zip(pts, colors):
        coin(d, CX0 + cw * fx, CY0 + ch * fy, r, c)


# ---------------------------------------------------------------- bamboo (條)
def bead_stick(d, cx, top, bottom, w, color):
    """Bamboo drawn as a chain of overlapping beads (like machine-printed sets), each with a paper-coloured rim."""
    h = bottom - top
    n = max(2, int(round((h - w) / (w * 0.72))) + 1)
    step = (h - w) / (n - 1)
    for i in range(n):
        y = top + w / 2 + step * i
        d.ellipse((cx - w / 2, y - w / 2, cx + w / 2, y + w / 2), fill=color, outline=PAPER, width=max(1, int(w * 0.07)))
        dot(d, cx, y, w * 0.16, PAPER)


def bead_stick_tilted(img, cx, cy, w, h, angle, color):
    size = int(max(w, h) * 1.7)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bead_stick(ImageDraw.Draw(layer), size / 2, size / 2 - h / 2, size / 2 + h / 2, w, color)
    layer = layer.rotate(angle, resample=Image.BICUBIC)
    img.alpha_composite(layer, (int(cx - size / 2), int(cy - size / 2)))


def draw_bird(img):
    """1條: small crimson bird at the lower left, dark green tail fan rising to the upper right."""
    d = ImageDraw.Draw(img)
    cw, ch = CX1 - CX0, CY1 - CY0

    def P(u, v):
        return (CX0 + cw * u, CY0 + ch * v)

    # tail fan (behind the body), pivot at the rump
    pivot = P(0.42, 0.66)
    for k in range(11):
        a = math.radians(-136 + k * 11)
        ln = ch * (0.5 - 0.05 * abs(k - 5) / 5)
        tip = (pivot[0] + math.cos(a) * ln, pivot[1] + math.sin(a) * ln)
        leaf(d, pivot, tip, cw * 0.15, GREEN if k % 2 == 0 else GREEN_L, bend=0.03)
    for k in range(1, 10, 2):
        a = math.radians(-136 + k * 11)
        tip = (pivot[0] + math.cos(a) * ch * 0.4, pivot[1] + math.sin(a) * ch * 0.4)
        dot(d, tip[0], tip[1], cw * 0.03, RED)
    # body (tilted ellipse)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    bx, by = P(0.38, 0.74)
    ld.ellipse((bx - cw * 0.27, by - ch * 0.12, bx + cw * 0.27, by + ch * 0.12), fill=RED)
    for k in range(3):
        ld.arc((bx - cw * 0.08 + k * cw * 0.04, by - ch * 0.07, bx + cw * 0.2 + k * cw * 0.04, by + ch * 0.07),
               start=15, end=165, fill=PAPER, width=int(1.8 * S))
    layer = layer.rotate(18, resample=Image.BICUBIC, center=(bx, by))
    img.alpha_composite(layer)
    d = ImageDraw.Draw(img)
    # neck + head
    hx, hy = P(0.2, 0.56)
    stroke(d, [(bx - cw * 0.12, by - ch * 0.04), (hx + cw * 0.02, hy + ch * 0.08), (hx, hy)], cw * 0.17, cw * 0.14, RED)
    dot(d, hx, hy, cw * 0.095, RED)
    d.polygon([(hx - cw * 0.06, hy - ch * 0.02), (hx - cw * 0.19, hy + ch * 0.025), (hx - cw * 0.06, hy + ch * 0.04)], fill=RED)
    dot(d, hx - cw * 0.012, hy - ch * 0.014, cw * 0.026, PAPER)
    dot(d, hx - cw * 0.016, hy - ch * 0.012, cw * 0.012, INK)
    for k in range(3):  # crest
        a = math.radians(-100 + k * 28)
        stroke(d, [(hx, hy - ch * 0.04), (hx + math.cos(a) * cw * 0.13, hy - ch * 0.04 + math.sin(a) * cw * 0.13)], cw * 0.045, cw * 0.012, RED)
    # legs and toes
    for lx in (0.3, 0.44):
        x, y = P(lx, 0.83)
        stroke(d, [(x, y), (x, y + ch * 0.1)], cw * 0.06, cw * 0.055, RED)
        for dx in (-0.07, 0.0, 0.07):
            stroke(d, [(x, y + ch * 0.1), (x + cw * dx, y + ch * 0.14)], cw * 0.05, cw * 0.035, RED)


def draw_eight_bamboo(img):
    """8條: the classic 'M' on top and an upside-down 'M' below (outer sticks upright, inner two leaning)."""
    cw, ch = CX1 - CX0, CY1 - CY0
    w = cw * 0.17
    h = ch * 0.42
    for cy_frac, sign in ((0.26, 1), (0.74, -1)):
        cy = CY0 + ch * cy_frac
        bead_stick_tilted(img, CX0 + cw * 0.12, cy, w, h, 0, GREEN)
        bead_stick_tilted(img, CX0 + cw * 0.88, cy, w, h, 0, GREEN)
        bead_stick_tilted(img, CX0 + cw * 0.37, cy, w, h * 1.04, 23 * sign, GREEN)
        bead_stick_tilted(img, CX0 + cw * 0.63, cy, w, h * 1.04, -23 * sign, GREEN)


def draw_sou(img, n):
    if n == 1:
        draw_bird(img)
        return
    if n == 8:
        draw_eight_bamboo(img)
        return
    d = ImageDraw.Draw(img)
    cw, ch = CX1 - CX0, CY1 - CY0
    G, K, Rr = GREEN, INK, RED
    # each entry: (x fraction, centre y fraction, height fraction, colour)
    layouts = {
        2: ([(0.5, 0.25, 0.44), (0.5, 0.75, 0.44)], [G, K], 3),
        3: ([(0.5, 0.25, 0.44), (0.27, 0.75, 0.44), (0.73, 0.75, 0.44)], [G, G, G], 3),
        4: ([(0.27, 0.25, 0.44), (0.73, 0.25, 0.44), (0.27, 0.75, 0.44), (0.73, 0.75, 0.44)], [G, K, K, G], 3),
        5: ([(0.16, 0.25, 0.44), (0.84, 0.25, 0.44), (0.5, 0.5, 0.44), (0.16, 0.75, 0.44), (0.84, 0.75, 0.44)],
            [G, G, Rr, G, G], 3),
        6: ([(x, y, 0.44) for y in (0.25, 0.75) for x in (0.17, 0.5, 0.83)], [G] * 6, 3),
    }
    if n == 7:
        # red short stick on top centre, then three tall columns below (as in the machine sets)
        w = min(cw * 0.19, 24 * S)
        bead_stick(d, CX0 + cw * 0.5, CY0, CY0 + ch * 0.27, w, Rr)
        for fx in (0.17, 0.5, 0.83):
            bead_stick(d, CX0 + cw * fx, CY0 + ch * 0.35, CY1, w, G if fx != 0.5 else K)
        return
    if n == 9:
        w = min(cw * 0.19, 24 * S)
        for fx, c in ((0.17, G), (0.5, Rr), (0.83, G)):
            bead_stick(d, CX0 + cw * fx, CY0, CY1, w, c)
        return
    sticks, colors, _ = layouts[n]
    cols = len({round(s[0], 2) for s in sticks})
    w = min(cw / max(cols, 2) * 0.58, 24 * S)
    for (fx, fy, fh), c in zip(sticks, colors):
        h = ch * fh
        bead_stick(d, CX0 + cw * fx, CY0 + ch * fy - h / 2, CY0 + ch * fy + h / 2, w, c)


# ---------------------------------------------------------------- honors
HONOR = {"E": ("東", INK), "S": ("南", INK), "W": ("西", INK), "N": ("北", INK), "RD": ("中", RED), "GD": ("發", GREEN)}


def draw_white_dragon(img):
    """White board: dark double frame with a ladder-like pattern in the band, empty window inside."""
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = CX0 + 8 * S, CY0 + 6 * S, CX1 - 8 * S, CY1 - 6 * S
    band = 21 * S
    d.rectangle((x0, y0, x1, y1), fill=INK)
    ix0, iy0, ix1, iy1 = x0 + band, y0 + band, x1 - band, y1 - band
    # slits in the band (paper coloured) leave a ladder pattern
    gap = 3 * S
    sl = 6 * S  # slit thickness
    # top and bottom bands: three horizontal slits each
    third = (ix1 - ix0) / 3
    for yb in (y0, iy1):
        for k in range(3):
            sx0 = ix0 + third * k + gap
            sx1 = ix0 + third * (k + 1) - gap
            d.rectangle((sx0, yb + band * 0.5 - sl / 2, sx1, yb + band * 0.5 + sl / 2), fill=PAPER)
    # left and right bands: vertical slits
    n = 6
    seg = (iy1 - iy0) / n
    for xb in (x0, ix1):
        for k in range(n):
            sy0 = iy0 + seg * k + gap
            sy1 = iy0 + seg * (k + 1) - gap
            d.rectangle((xb + band * 0.5 - sl / 2, sy0, xb + band * 0.5 + sl / 2, sy1), fill=PAPER)
    d.rectangle((ix0, iy0, ix1, iy1), fill=PAPER)
    d.rectangle((ix0, iy0, ix1, iy1), outline=INK, width=2 * S)


def draw_honor(img, code):
    if code == "WD":
        draw_white_dragon(img)
        return
    d = ImageDraw.Draw(img)
    cx, cy = (CX0 + CX1) / 2, (CY0 + CY1) / 2
    ch, color = HONOR[code]
    fit_text(d, cx, cy, ch, (CX1 - CX0) * 0.90, (CY1 - CY0) * 0.74, color)


# ---------------------------------------------------------------- flowers (花牌)
def plum_flower(d, cx, cy, r, color=RED):
    """Five round petals with a stamen crown."""
    for k in range(5):
        a = math.radians(-90 + k * 72)
        px, py = cx + math.cos(a) * r * 0.58, cy + math.sin(a) * r * 0.58
        d.ellipse((px - r * 0.52, py - r * 0.52, px + r * 0.52, py + r * 0.52), fill=color, outline=PAPER, width=max(1, int(r * 0.07)))
    dot(d, cx, cy, r * 0.30, PAPER)
    dot(d, cx, cy, r * 0.20, mix(color, (0, 0, 0), 0.25))
    for k in range(5):
        a = math.radians(-54 + k * 72)
        dot(d, cx + math.cos(a) * r * 0.36, cy + math.sin(a) * r * 0.36, r * 0.06, PAPER)


def draw_plum(d, P, sc):
    stroke(d, bezier(P(0.04, 0.96), P(0.3, 0.9), P(0.45, 0.62), P(0.95, 0.12)), sc * 0.075, sc * 0.03, BROWN)
    stroke(d, bezier(P(0.3, 0.84), P(0.32, 0.7), P(0.26, 0.5), P(0.2, 0.34)), sc * 0.04, sc * 0.02, BROWN)
    stroke(d, bezier(P(0.56, 0.58), P(0.62, 0.6), P(0.72, 0.58), P(0.86, 0.6)), sc * 0.035, sc * 0.018, BROWN)
    plum_flower(d, *P(0.4, 0.62), sc * 0.23)
    plum_flower(d, *P(0.76, 0.34), sc * 0.17)
    plum_flower(d, *P(0.2, 0.34), sc * 0.14)
    for (u, v) in ((0.62, 0.8), (0.9, 0.5), (0.08, 0.6), (0.5, 0.2)):  # buds
        dot(d, *P(u, v), sc * 0.05, RED)
    leaf(d, P(0.34, 0.9), P(0.12, 0.84), sc * 0.1, GREEN, bend=0.1)
    leaf(d, P(0.5, 0.4), P(0.56, 0.18), sc * 0.1, GREEN, bend=-0.1)


def draw_orchid(d, P, sc):
    base = P(0.5, 0.97)
    ends = [(0.04, 0.38, -0.12), (0.16, 0.2, -0.1), (0.34, 0.06, -0.08), (0.7, 0.1, 0.08), (0.86, 0.26, 0.12), (0.97, 0.48, 0.12)]
    for i, (u, v, bend) in enumerate(ends):
        e = P(u, v)
        mid1 = (lerp(base[0], e[0], 0.25), lerp(base[1], e[1], 0.6))
        mid2 = (lerp(base[0], e[0], 0.75) + (e[0] - base[0]) * bend * 0.3, lerp(base[1], e[1], 0.85))
        stroke(d, bezier(base, mid1, mid2, e), sc * 0.12, sc * 0.015, GREEN if i % 2 == 0 else GREEN_L)
    # flower stalk with two orchid blossoms
    stalk = bezier(P(0.5, 0.97), P(0.52, 0.7), P(0.47, 0.55), P(0.5, 0.38))
    stroke(d, stalk, sc * 0.03, sc * 0.02, GREEN)
    for (u, v, r, rot) in ((0.5, 0.4, 0.26, -90), (0.34, 0.66, 0.2, -140), (0.66, 0.62, 0.2, -40)):
        cx, cy = P(u, v)
        for k in range(5):
            a = math.radians(rot + k * 72)
            petal(d, cx, cy, a, 0, sc * r * (1.0 if k % 2 == 0 else 0.8), sc * r * 0.5, RED)
        dot(d, cx, cy, sc * r * 0.22, PAPER)
        dot(d, cx, cy, sc * r * 0.12, GREEN)


def draw_bamboo(d, P, sc):
    culms = [(0.2, 0.97, 0.14, 0.2, 0.12), (0.5, 0.99, 0.5, 0.06, 0.13), (0.8, 0.97, 0.86, 0.2, 0.12)]
    for (u0, v0, u1, v1, w) in culms:
        x0, y0 = P(u0, v0)
        x1, y1 = P(u1, v1)
        seg = 4
        for i in range(seg):
            pts = [(lerp(x0, x1, (i + t / 6) / seg), lerp(y0, y1, (i + t / 6) / seg)) for t in range(7)]
            stroke(d, pts, sc * w, sc * w, GREEN if i % 2 == 0 else GREEN_L)
        for i in range(1, seg):
            nx, ny = lerp(x0, x1, i / seg), lerp(y0, y1, i / seg)
            d.ellipse((nx - sc * w * 0.62, ny - sc * 0.018, nx + sc * w * 0.62, ny + sc * 0.018), fill=PAPER)
        # leaves at the top nodes
        for k, a in enumerate((-160, -125, -55, -20)):
            sx, sy = lerp(x0, x1, 0.78), lerp(y0, y1, 0.78)
            ex = x1 + math.cos(math.radians(a)) * sc * 0.3
            ey = y1 + math.sin(math.radians(a)) * sc * 0.26 + sc * 0.1
            leaf(d, (sx, sy), (ex, ey), sc * 0.1, GREEN if k % 2 else GREEN_L, bend=0.06)


def draw_chrysanthemum(d, P, sc):
    cx, cy = P(0.5, 0.4)
    stroke(d, bezier(P(0.5, 0.98), P(0.44, 0.84), P(0.56, 0.7), P(0.5, 0.52)), sc * 0.05, sc * 0.035, GREEN)
    leaf(d, P(0.48, 0.86), P(0.1, 0.62), sc * 0.17, GREEN, bend=-0.12, vein=GREEN_L)
    leaf(d, P(0.52, 0.8), P(0.92, 0.56), sc * 0.17, GREEN_L, bend=0.12, vein=GREEN)
    leaf(d, P(0.5, 0.94), P(0.22, 0.96), sc * 0.1, GREEN, bend=0.1)
    leaf(d, P(0.5, 0.94), P(0.8, 0.97), sc * 0.1, GREEN_L, bend=-0.1)
    R0 = sc * 0.42
    for ring, (cnt, r1, wd, col, off) in enumerate(((16, R0, 0.15, RED, 0), (12, R0 * 0.76, 0.14, mix(RED, (255, 255, 255), 0.25), 0.5), (9, R0 * 0.5, 0.12, RED, 0))):
        for k in range(cnt):
            a = (k + off) * 2 * math.pi / cnt
            petal(d, cx, cy, a, R0 * 0.1, r1, R0 * wd * 2.3, col)
            # paper rim along each petal separates the layers when scaled down
            petal(d, cx, cy, a, r1 * 0.7, r1 * 0.98, R0 * wd * 0.5, mix(col, (255, 255, 255), 0.55))
    dot(d, cx, cy, R0 * 0.2, PAPER)
    dot(d, cx, cy, R0 * 0.12, GREEN)


def draw_peony(d, P, sc):
    """春: a layered round blossom with leaves and a bud."""
    stroke(d, bezier(P(0.5, 0.98), P(0.48, 0.8), P(0.52, 0.7), P(0.5, 0.52)), sc * 0.045, sc * 0.035, GREEN)
    leaf(d, P(0.5, 0.86), P(0.06, 0.7), sc * 0.18, GREEN, bend=-0.12, vein=GREEN_L)
    leaf(d, P(0.5, 0.82), P(0.94, 0.66), sc * 0.18, GREEN_L, bend=0.12, vein=GREEN)
    leaf(d, P(0.5, 0.96), P(0.16, 0.97), sc * 0.1, GREEN, bend=0.1)
    cx, cy = P(0.5, 0.38)
    R0 = sc * 0.38
    for (cnt, rr, pw, off, col) in ((6, 1.0, 0.75, 0, RED), (6, 0.78, 0.65, 0.5, mix(RED, (255, 255, 255), 0.18)), (5, 0.52, 0.5, 0, RED)):
        for k in range(cnt):
            a = (k + off) * 2 * math.pi / cnt - math.pi / 2
            px, py = cx + math.cos(a) * R0 * rr * 0.55, cy + math.sin(a) * R0 * rr * 0.55
            r = R0 * rr * pw * 0.62
            d.ellipse((px - r, py - r, px + r, py + r), fill=col, outline=PAPER, width=max(1, int(S * 1.2)))
    dot(d, cx, cy, R0 * 0.2, PAPER)
    dot(d, cx, cy, R0 * 0.12, GREEN)
    dot(d, *P(0.86, 0.32), sc * 0.07, RED)
    stroke(d, bezier(P(0.86, 0.4), P(0.84, 0.5), P(0.78, 0.6), P(0.62, 0.74)), sc * 0.025, sc * 0.02, GREEN)


def draw_lotus(d, P, sc):
    """夏: lotus blossom over a round leaf."""
    # leaf pad (flattened ellipse) with veins
    lx0, ly0 = P(0.04, 0.72)
    lx1, ly1 = P(0.96, 0.98)
    d.ellipse((lx0, ly0, lx1, ly1), fill=GREEN)
    lcx, lcy = (lx0 + lx1) / 2, (ly0 + ly1) / 2
    for k in range(9):
        a = math.radians(180 + k * 22.5)
        d.line([(lcx, lcy), (lcx + math.cos(a) * (lx1 - lx0) * 0.46, lcy + math.sin(a) * (ly1 - ly0) * 0.46)], fill=GREEN_L, width=int(S * 1.2))
    stroke(d, bezier(P(0.5, 0.86), P(0.5, 0.74), P(0.5, 0.62), P(0.5, 0.52)), sc * 0.05, sc * 0.04, GREEN)
    cx, cy = P(0.5, 0.52)
    for ang, ln, wd in ((-150, 0.5, 0.2), (-30, 0.5, 0.2), (-122, 0.56, 0.2), (-58, 0.56, 0.2), (-90, 0.62, 0.22)):
        a = math.radians(ang)
        tip = (cx + math.cos(a) * sc * ln, cy + math.sin(a) * sc * ln * 0.95)
        leaf(d, (cx, cy), tip, sc * wd, RED if ang != -90 else mix(RED, (255, 255, 255), 0.2), vein=PAPER)
    for ang in (-170, 10):
        a = math.radians(ang)
        tip = (cx + math.cos(a) * sc * 0.4, cy + math.sin(a) * sc * 0.18)
        leaf(d, (cx, cy + sc * 0.02), tip, sc * 0.17, mix(RED, (255, 255, 255), 0.1))
    dot(d, cx, cy, sc * 0.045, PAPER)


def maple_leaf(d, cx, cy, r, angle_deg, color):
    pts = []
    base = math.radians(angle_deg)
    lobes = 5
    for i in range(lobes * 2):
        a = base + i * math.pi / lobes
        rr = r if i % 2 == 0 else r * 0.45
        if i % 2 == 0 and i in (4, 6):
            rr = r * 0.8
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    d.polygon(pts, fill=color)
    return pts


def draw_maple(d, P, sc):
    """秋: maple branch with three crimson leaves."""
    stroke(d, bezier(P(0.06, 0.98), P(0.3, 0.8), P(0.6, 0.78), P(0.92, 0.5)), sc * 0.05, sc * 0.025, BROWN)
    stroke(d, bezier(P(0.34, 0.8), P(0.3, 0.6), P(0.3, 0.5), P(0.28, 0.4)), sc * 0.035, sc * 0.02, BROWN)
    stroke(d, bezier(P(0.62, 0.74), P(0.66, 0.6), P(0.68, 0.5), P(0.72, 0.36)), sc * 0.035, sc * 0.02, BROWN)
    for (u, v, r, a, c) in ((0.28, 0.34, 0.3, -90, RED), (0.72, 0.3, 0.3, -90, mix(RED, (255, 255, 255), 0.12)), (0.5, 0.64, 0.24, -90, RED)):
        cx, cy = P(u, v)
        maple_leaf(d, cx, cy, sc * r, a + 18, c)
        # veins
        for k in range(5):
            aa = math.radians(a + 18 + k * 72)
            d.line([(cx, cy), (cx + math.cos(aa) * sc * r * 0.8, cy + math.sin(aa) * sc * r * 0.8)], fill=PAPER, width=max(1, int(S * 1.1)))
    leaf(d, P(0.1, 0.94), P(0.04, 0.72), sc * 0.1, GREEN, bend=0.1)
    leaf(d, P(0.78, 0.6), P(0.96, 0.78), sc * 0.1, GREEN, bend=0.1)


def draw_pine(d, P, sc):
    """冬: pine branch with needle fans and a crimson camellia bloom."""
    stroke(d, bezier(P(0.04, 0.96), P(0.3, 0.86), P(0.5, 0.64), P(0.96, 0.5)), sc * 0.06, sc * 0.03, BROWN)
    for (u, v, rot) in ((0.16, 0.9, -70), (0.36, 0.8, -85), (0.58, 0.68, -95), (0.82, 0.58, -105), (0.28, 0.86, 55), (0.5, 0.74, 50), (0.74, 0.64, 45)):
        cx, cy = P(u, v)
        for k in range(5):
            a = math.radians(rot - 32 + k * 16)
            ex, ey = cx + math.cos(a) * sc * 0.32, cy + math.sin(a) * sc * 0.32
            leaf(d, (cx, cy), (ex, ey), sc * 0.05, GREEN if k % 2 == 0 else GREEN_L)
    cx, cy = P(0.5, 0.3)
    R0 = sc * 0.24
    for k in range(5):
        a = math.radians(-90 + k * 72)
        px, py = cx + math.cos(a) * R0 * 0.6, cy + math.sin(a) * R0 * 0.6
        d.ellipse((px - R0 * 0.6, py - R0 * 0.6, px + R0 * 0.6, py + R0 * 0.6), fill=RED, outline=PAPER, width=max(1, int(S * 1.2)))
    dot(d, cx, cy, R0 * 0.4, PAPER)
    dot(d, cx, cy, R0 * 0.26, mix(RED, (0, 0, 0), 0.25))
    for (u, v) in ((0.88, 0.32), (0.14, 0.42)):
        dot(d, *P(u, v), sc * 0.055, RED)


FLOWER = {
    # code: (character, number, season-style?, plant renderer)
    "F1": ("春", "1", True, draw_peony),
    "F2": ("夏", "2", True, draw_lotus),
    "F3": ("秋", "3", True, draw_maple),
    "F4": ("冬", "4", True, draw_pine),
    "F5": ("梅", "1", False, draw_plum),
    "F6": ("蘭", "2", False, draw_orchid),
    "F7": ("竹", "3", False, draw_bamboo),
    "F8": ("菊", "4", False, draw_chrysanthemum),
}


def draw_flower(img, code):
    d = ImageDraw.Draw(img)
    ch, num, season, painter = FLOWER[code]
    cw, chh = CX1 - CX0, CY1 - CY0
    head_h = chh * 0.24
    # corner number and character: seasons put the number left, plants put it right
    char_size = int(head_h * 1.15)
    num_size = int(head_h * 0.95)
    margin = 4 * S
    num_x = CX0 + margin + num_size * 0.3 if season else CX1 - margin - num_size * 0.3
    char_x = CX1 - margin - char_size * 0.5 if season else CX0 + margin + char_size * 0.5
    text_center(d, num_x, CY0 + head_h * 0.55, num, num_size, INK, bold=True)
    text_center(d, char_x, CY0 + head_h * 0.52, ch, char_size, RED)
    # plant picture in the lower part
    x0, y0 = CX0 + 3 * S, CY0 + chh * 0.27
    x1, y1 = CX1 - 3 * S, CY1 + 4 * S
    sc = min(x1 - x0, y1 - y0)
    ox = x0 + (x1 - x0 - sc) / 2

    def P(u, v):
        return (ox + sc * u, y0 + (y1 - y0 - sc) + sc * v) if (y1 - y0) > sc else (ox + sc * u, y0 + sc * v)

    painter(d, P, sc)


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
    rounded(d, (0, 2 * S, W - 1, H - 1), R, (31, 92, 66))
    rounded(d, (0, 0, W - 1, H - 3 * S), R, (46, 125, 91))
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


def contact_sheet(tiles, cols, tile_h, bg):
    t0 = tiles[0]
    tw, th = (t0.width * tile_h // t0.height, tile_h)
    pad = max(2, tile_h // 20)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * (tw + pad) + pad, rows * (th + pad) + pad), bg)
    for i, t in enumerate(tiles):
        t = t.resize((tw, th), Image.LANCZOS) if tile_h != t.height else t
        sheet.alpha_composite(t, (pad + (i % cols) * (tw + pad), pad + (i // cols) * (th + pad)))
    return sheet


def main():
    os.makedirs(OUT, exist_ok=True)
    codes = [f"{n}{s}" for s in "mps" for n in range(1, 10)] + ["E", "S", "W", "N", "RD", "GD", "WD"] + [f"F{i}" for i in range(1, 9)]
    images = []
    for c in codes:
        im = render(c)
        im.save(os.path.join(OUT, f"{c}.png"), optimize=True)
        images.append(im)
    back = render_back()
    back.save(os.path.join(OUT, "back.png"), optimize=True)
    images.append(back)
    if SHEET_DIR:
        os.makedirs(SHEET_DIR, exist_ok=True)
        bg = (40, 110, 76, 255)
        contact_sheet(images, 9, 200, bg).save(os.path.join(SHEET_DIR, "sheet_full.png"))
        contact_sheet(images, 9, 92, bg).save(os.path.join(SHEET_DIR, "sheet_92.png"))
        contact_sheet(images, 9, 44, bg).save(os.path.join(SHEET_DIR, "sheet_44.png"))
    print("rendered", len(images))


if __name__ == "__main__":
    main()
