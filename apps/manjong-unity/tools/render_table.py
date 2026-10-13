"""Render the mahjong table textures for manjong-unity (pure PIL, nothing downloaded).

Usage: python render_table.py <out-dir> [--preview <png>] [--tiles <tiles-dir>]

Output in <out-dir> (the client keeps them in Assets/Resources/Table/):
  felt.png        256x256 seamless green baize tile (repeats; Image.Type.Tiled in uGUI)
  felt_shade.png  770x369 vignette (dark corners) plus a soft light pool in the middle, stretched over the felt
  frame.png       1696x894 wooden table frame: mitred walnut rails with grain, bevel, brass inlay, inner shadow
                  on the felt and a soft drop shadow outside (the frame's hole is transparent)
  console.png     480x194 electric-table console: dark bezel with brass trim and three recessed screens

Every run also checks the worst-case seat layout (17 concealed tiles, 5 kongs, 8 flowers and a full river for each seat) for
overlapping tiles, tiles outside the felt and tiles on the console, and prints the problems. With --preview a 1920x1080 mock-up
of that worst case (plus a 1821x1138 one, <png> with _1610 appended) is written, using the tile images in --tiles; it is only
for checking the look and never goes into the client.

All geometry below is in canvas units (1 texel = 1 unit at the 1920x1080 reference) and must match the constants in
Assets/Scripts/Screens/TableScreen.cs (Table*, Console*, the seat layout helpers).
"""
import math
import os
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- geometry (mirrors TableScreen.cs)
FRAME_W, FRAME_H = 1600, 798           # outer size of the wooden frame
FRAME_MARGIN = 48                      # transparent margin around the frame that holds its drop shadow
WOOD = 30                              # width of the wood rail
FELT_W, FELT_H = FRAME_W - 2 * WOOD, FRAME_H - 2 * WOOD   # 1540 x 738 visible felt
CONSOLE_W, CONSOLE_H = 440, 154        # console body
CONSOLE_MARGIN = 20                    # shadow margin around the console
# Recessed screens inside the console (x, y, w, h in console units, top-left origin).
SCREEN_COMPASS = (14, 12, 96, 96)
SCREEN_INFO = (124, 12, 302, 96)
SCREEN_TURN = (14, 114, 412, 28)

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(HERE, "..", "client", "Assets", "Resources", "Fonts", "huninn.ttf")

# ---------------------------------------------------------------- palette
FELT_BASE = (32, 90, 62)
FELT_LIGHT = (44, 110, 76)
WALNUT_DARK = (64, 36, 22)
WALNUT_MID = (112, 68, 40)
WALNUT_LIGHT = (164, 108, 66)
BRASS = (201, 162, 74)
BRASS_DARK = (122, 92, 36)
BRASS_LIGHT = (246, 220, 140)


def pixels(img):
    """Flat pixel sequence (Pillow 12+ deprecates getdata in favour of get_flattened_data)."""
    f = getattr(img, "get_flattened_data", None)
    return f() if f else img.getdata()


def clamp8(v):
    return 0 if v < 0 else 255 if v > 255 else int(v)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c0, c1, t):
    return tuple(clamp8(lerp(c0[i], c1[i], t)) for i in range(3))


def value_noise(w, h, cell_x, cell_y, rng):
    """Smooth random field (L mode) with feature size cell_x x cell_y."""
    lw, lh = max(2, w // cell_x + 3), max(2, h // cell_y + 3)
    small = Image.new("L", (lw, lh))
    small.putdata([rng.randrange(256) for _ in range(lw * lh)])
    big = small.resize((lw * cell_x, lh * cell_y), Image.BICUBIC)
    return big.crop((0, 0, w, h))


def tiled_noise(size, cells, rng):
    """Seamless smooth noise: a small random grid repeated 3x3, smoothed, centre tile cropped."""
    small = Image.new("L", (cells, cells))
    small.putdata([rng.randrange(256) for _ in range(cells * cells)])
    big = Image.new("L", (cells * 3, cells * 3))
    for ty in range(3):
        for tx in range(3):
            big.paste(small, (tx * cells, ty * cells))
    k = size // cells
    big = big.resize((cells * 3 * k, cells * 3 * k), Image.BICUBIC)
    return big.crop((size, size, size * 2, size * 2))


def rounded_mask(w, h, radius, ss=3):
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=radius * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def shift(img, dx, dy):
    """Move the content of an L image by (dx, dy), filling with 0."""
    out = Image.new("L", img.size, 0)
    out.paste(img, (dx, dy))
    return out


def subtract(a, b):
    return ImageChops.subtract(a, b)


def dither(img, rng, amount=1.5):
    """Tiny noise on the colour channels so 8-bit gradients do not band."""
    w, h = img.size
    n = Image.new("L", (w, h))
    n.putdata([rng.randrange(256) for _ in range(w * h)])
    n = n.point(lambda v: int((v - 128) * amount / 128.0 + 128))
    r, g, b, a = img.convert("RGBA").split()
    chans = []
    for ch in (r, g, b):
        chans.append(ImageChops.add(ch, n, scale=1.0, offset=-128))
    return Image.merge("RGBA", (*chans, a))


# ---------------------------------------------------------------- felt
def make_felt(size=256, seed=11):
    rng = random.Random(seed)
    mottle = pixels(tiled_noise(size, 8, rng))
    mottle2 = pixels(tiled_noise(size, 32, rng))
    out = []
    for y in range(size):
        for x in range(size):
            i = y * size + x
            # woven baize: a faint 4-texel cross-hatch + fibre noise + soft cloudy mottling
            weave = math.sin(x * math.pi / 2.0) * math.sin(y * math.pi / 2.0)
            fibre = rng.gauss(0.0, 1.0)
            t = 0.5 + (mottle[i] - 128) / 255.0 * 0.55 + (mottle2[i] - 128) / 255.0 * 0.20
            col = lerp_color(FELT_BASE, FELT_LIGHT, max(0.0, min(1.0, t)))
            k = 1.0 + weave * 0.020 + fibre * 0.030
            out.append((clamp8(col[0] * k), clamp8(col[1] * k), clamp8(col[2] * k), 255))
    img = Image.new("RGBA", (size, size))
    img.putdata(out)
    return img


def make_felt_shade(w=FELT_W // 2, h=FELT_H // 2, seed=3):
    """Dark corners + a soft warm light pool in the middle (RGBA, premultiplied-free)."""
    rng = random.Random(seed)
    out = []
    for y in range(h):
        ny = (y + 0.5) / h * 2 - 1
        for x in range(w):
            nx = (x + 0.5) / w * 2 - 1
            r = math.sqrt((nx * 0.92) ** 2 + (ny * 1.0) ** 2)
            dark = max(0.0, (r - 0.42) / 0.78)
            dark = min(1.0, dark) ** 1.7 * 0.62
            # edges of the felt also get a little darker (the baize sinks toward the rails)
            edge = max(abs(nx), abs(ny))
            dark = min(0.85, dark + max(0.0, (edge - 0.93) / 0.07) * 0.12)
            glow = max(0.0, 1.0 - r / 0.75) ** 2 * 0.06
            if dark >= glow:
                out.append((6, 24, 14, clamp8(dark * 255 + rng.random())))
            else:
                out.append((190, 235, 170, clamp8(glow * 255 + rng.random())))
    img = Image.new("RGBA", (w, h))
    img.putdata(out)
    return img


# ---------------------------------------------------------------- wood
def make_wood(w, h, seed):
    """Walnut with the grain running along x: fine wavy grain lines, long per-row tone streaks, broad tone drift."""
    rng = random.Random(seed)
    warp = pixels(value_noise(w, h, 320, 22, rng))
    streak = pixels(value_noise(w, h, 460, 1, rng))
    streak2 = pixels(value_noise(w, h, 170, 3, rng))
    tone = pixels(value_noise(w, h, 520, 40, rng))
    out = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            gy = y + (warp[i] - 128) * 0.09
            line = 0.5 + 0.5 * math.sin(gy * 2 * math.pi / 6.5 + tone[i] / 22.0)
            line = line ** 2.4
            t = 0.30 * line + 0.34 * (streak[i] / 255.0) + 0.20 * (streak2[i] / 255.0) + 0.16 * (tone[i] / 255.0)
            t = max(0.0, min(1.0, (t - 0.18) * 1.55))
            c = lerp_color(WALNUT_DARK, WALNUT_MID, t * 2.0) if t < 0.5 else lerp_color(WALNUT_MID, WALNUT_LIGHT, (t - 0.5) * 2.0)
            out.append((c[0], c[1], c[2], 255))
    img = Image.new("RGBA", (w, h))
    img.putdata(out)
    return img


def poly_mask(size, pts, ss=3):
    m = Image.new("L", (size[0] * ss, size[1] * ss), 0)
    ImageDraw.Draw(m).polygon([(x * ss, y * ss) for x, y in pts], fill=255)
    return m.resize(size, Image.LANCZOS)


def make_frame():
    W, H = FRAME_W + 2 * FRAME_MARGIN, FRAME_H + 2 * FRAME_MARGIN
    ox = oy = FRAME_MARGIN
    t = WOOD
    rng = random.Random(5)

    # --- shapes
    outer = Image.new("L", (W, H), 0)
    outer.paste(rounded_mask(FRAME_W, FRAME_H, 34), (ox, oy))
    hole = Image.new("L", (W, H), 0)
    hole.paste(rounded_mask(FELT_W, FELT_H, 12), (ox + t, oy + t))
    wood_mask = subtract(outer, hole)

    # --- mitred rails, each with the grain running along its length
    horiz = make_wood(W, t + 6, 21)                         # top / bottom rails
    horiz2 = make_wood(W, t + 6, 22)
    vert = make_wood(H, t + 6, 23).transpose(Image.ROTATE_90)   # left / right rails, (t+6) x H
    vert2 = make_wood(H, t + 6, 24).transpose(Image.ROTATE_90)
    wood = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x0, y0, x1, y1 = ox, oy, ox + FRAME_W, oy + FRAME_H
    top = poly_mask((W, H), [(x0, y0), (x1, y0), (x1 - t, y0 + t), (x0 + t, y0 + t)])
    bottom = poly_mask((W, H), [(x0, y1), (x1, y1), (x1 - t, y1 - t), (x0 + t, y1 - t)])
    left = poly_mask((W, H), [(x0, y0), (x0 + t, y0 + t), (x0 + t, y1 - t), (x0, y1)])
    right = poly_mask((W, H), [(x1, y0), (x1 - t, y0 + t), (x1 - t, y1 - t), (x1, y1)])
    for mask, tex, pos in (
        (top, horiz, (0, y0 - 3)),
        (bottom, horiz2.transpose(Image.FLIP_TOP_BOTTOM), (0, y1 - t - 3)),
        (left, vert, (x0 - 3, 0)),
        (right, vert2.transpose(Image.FLIP_LEFT_RIGHT), (x1 - t - 3, 0)),
    ):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        layer.paste(tex, pos)
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
        wood = Image.alpha_composite(wood, layer)

    wood.putalpha(ImageChops.multiply(wood.getchannel("A"), wood_mask))   # rounded outer corners, rounded hole

    # mitre seams: thin dark diagonal lines
    seam = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(seam)
    for (ax, ay), (bx, by) in (
        ((x0 + 10, y0 + 10), (x0 + t, y0 + t)),
        ((x1 - 10, y0 + 10), (x1 - t, y0 + t)),
        ((x0 + 10, y1 - 10), (x0 + t, y1 - t)),
        ((x1 - 10, y1 - 10), (x1 - t, y1 - t)),
    ):
        sd.line((ax, ay, bx, by), fill=(28, 14, 6, 120), width=2)
    wood = Image.alpha_composite(wood, seam)

    # --- lighting: light from the top-left. Lit edges = pixels whose up-left neighbour is empty.
    def edge_layer(k, color, strength, lit):
        if lit:
            e = subtract(wood_mask, shift(wood_mask, k, k))
        else:
            e = subtract(wood_mask, shift(wood_mask, -k, -k))
        e = e.filter(ImageFilter.GaussianBlur(0.8))
        layer = Image.new("RGBA", (W, H), color + (0,))
        layer.putalpha(e.point(lambda v: int(v * strength)))
        return layer

    wood = Image.alpha_composite(wood, edge_layer(3, (255, 226, 178), 0.55, True))
    wood = Image.alpha_composite(wood, edge_layer(3, (20, 8, 2), 0.55, False))
    # broad soft bevel: the rail rounds off toward both edges
    soft_in = subtract(wood_mask, shift(wood_mask, 6, 6)).filter(ImageFilter.GaussianBlur(3))
    soft_out = subtract(wood_mask, shift(wood_mask, -6, -6)).filter(ImageFilter.GaussianBlur(3))
    lit = Image.new("RGBA", (W, H), (255, 215, 160, 0))
    lit.putalpha(soft_in.point(lambda v: int(v * 0.10)))
    dark = Image.new("RGBA", (W, H), (10, 4, 0, 0))
    dark.putalpha(soft_out.point(lambda v: int(v * 0.18)))
    wood = Image.alpha_composite(wood, lit)
    wood = Image.alpha_composite(wood, dark)

    # --- brass inlay line along the middle of the rail
    inlay_mask = Image.new("L", (W * 3, H * 3), 0)
    idr = ImageDraw.Draw(inlay_mask)
    inset = 11
    idr.rounded_rectangle(((ox + inset) * 3, (oy + inset) * 3, (ox + FRAME_W - inset) * 3, (oy + FRAME_H - inset) * 3),
                          radius=25 * 3, outline=255, width=2 * 3)
    inlay_mask = inlay_mask.resize((W, H), Image.LANCZOS)
    inlay = Image.new("RGBA", (W, H), BRASS + (0,))
    inlay.putalpha(ImageChops.multiply(inlay_mask, wood_mask).point(lambda v: int(v * 0.85)))
    inlay_hi = Image.new("RGBA", (W, H), BRASS_LIGHT + (0,))
    inlay_hi.putalpha(ImageChops.multiply(shift(inlay_mask, -1, -1), wood_mask).point(lambda v: int(v * 0.35)))
    wood = Image.alpha_composite(wood, inlay_hi)
    wood = Image.alpha_composite(wood, inlay)

    # --- brass corner caps
    cap = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cap)
    for cx, cy in ((x0 + 18, y0 + 18), (x1 - 18, y0 + 18), (x0 + 18, y1 - 18), (x1 - 18, y1 - 18)):
        cd.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=BRASS_DARK + (255,))
        cd.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=BRASS + (255,))
        cd.ellipse((cx - 3, cy - 3, cx + 1, cy + 1), fill=BRASS_LIGHT + (200,))
    wood = Image.alpha_composite(wood, cap)

    # --- composite: drop shadow, wood, inner shadow cast on the felt
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    drop = shift(outer, 0, 11).filter(ImageFilter.GaussianBlur(11))
    shadow = Image.new("RGBA", (W, H), (48, 30, 16, 0))
    shadow.putalpha(drop.point(lambda v: int(v * 0.42)))
    img = Image.alpha_composite(img, shadow)
    img = Image.alpha_composite(img, wood)
    cast = shift(wood_mask, 3, 6).filter(ImageFilter.GaussianBlur(9))
    cast = ImageChops.multiply(cast, hole)           # only on the felt side
    inner = Image.new("RGBA", (W, H), (2, 14, 8, 0))
    inner.putalpha(cast.point(lambda v: int(v * 0.62)))
    img = Image.alpha_composite(img, inner)
    return dither(img, rng, 1.2)


# ---------------------------------------------------------------- console
def screen_layer(size, rect, radius, tint, gloss):
    """A recessed glass screen: dark gradient, inner shadow on top/left, bright rim on bottom/right."""
    W, H = size
    x, y, w, h = rect
    m = Image.new("L", (W, H), 0)
    m.paste(rounded_mask(w, h, radius), (x, y))
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("RGBA", (w, h))
    gp = []
    for yy in range(h):
        k = yy / max(1, h - 1)
        c = lerp_color(tint[0], tint[1], k)
        gp.extend([c + (255,)] * w)
    grad.putdata(gp)
    base.paste(grad, (x, y))
    base.putalpha(m)
    # inner shadow (top-left) and rim light (bottom-right)
    inner_dark = subtract(m, shift(m, 3, 3)).filter(ImageFilter.GaussianBlur(1.6))
    d = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d.putalpha(inner_dark.point(lambda v: int(v * 0.85)))
    base = Image.alpha_composite(base, d)
    rim = subtract(m, shift(m, -2, -2)).filter(ImageFilter.GaussianBlur(0.9))
    r = Image.new("RGBA", (W, H), (150, 170, 160, 0))
    r.putalpha(rim.point(lambda v: int(v * 0.35)))
    # the rim sits just outside the screen: draw it on a slightly grown mask
    outer_rim = subtract(shift(m, 1, 1).filter(ImageFilter.MaxFilter(3)), m).filter(ImageFilter.GaussianBlur(0.7))
    r2 = Image.new("RGBA", (W, H), (190, 205, 198, 0))
    r2.putalpha(outer_rim.point(lambda v: int(v * 0.30)))
    if gloss:
        g = Image.new("RGBA", (W, H), (255, 255, 255, 0))
        gm = Image.new("L", (W, H), 0)
        gd = ImageDraw.Draw(gm)
        gd.polygon([(x, y), (x + int(w * 0.62), y), (x + int(w * 0.30), y + h), (x, y + h)], fill=255)
        gm = ImageChops.multiply(gm, m).filter(ImageFilter.GaussianBlur(2))
        g.putalpha(gm.point(lambda v: int(v * 0.045)))
        base = Image.alpha_composite(base, g)
    return base, r2


def make_console():
    W, H = CONSOLE_W + 2 * CONSOLE_MARGIN, CONSOLE_H + 2 * CONSOLE_MARGIN
    ox = oy = CONSOLE_MARGIN
    rng = random.Random(9)
    body_m = Image.new("L", (W, H), 0)
    body_m.paste(rounded_mask(CONSOLE_W, CONSOLE_H, 24), (ox, oy))

    # shadow
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = shift(body_m, 0, 7).filter(ImageFilter.GaussianBlur(7))
    s = Image.new("RGBA", (W, H), (6, 18, 10, 0))
    s.putalpha(sh.point(lambda v: int(v * 0.62)))
    img = Image.alpha_composite(img, s)

    # bezel: vertical gradient of dark graphite with a very light brushed noise
    bezel = Image.new("RGBA", (W, H))
    bp = []
    noise = pixels(value_noise(W, H, 60, 2, rng))
    for y in range(H):
        k = max(0.0, min(1.0, (y - oy) / CONSOLE_H))
        c = lerp_color((72, 78, 74), (30, 34, 32), k)
        for x in range(W):
            n = (noise[y * W + x] - 128) / 255.0 * 14
            bp.append((clamp8(c[0] + n), clamp8(c[1] + n), clamp8(c[2] + n), 255))
    bezel.putdata(bp)
    bezel.putalpha(body_m)
    img = Image.alpha_composite(img, bezel)

    # bevel + brass trim
    hi = subtract(body_m, shift(body_m, 2, 2)).filter(ImageFilter.GaussianBlur(0.8))
    h = Image.new("RGBA", (W, H), (235, 240, 236, 0))
    h.putalpha(hi.point(lambda v: int(v * 0.55)))
    img = Image.alpha_composite(img, h)
    lo = subtract(body_m, shift(body_m, -2, -2)).filter(ImageFilter.GaussianBlur(0.8))
    l = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    l.putalpha(lo.point(lambda v: int(v * 0.6)))
    img = Image.alpha_composite(img, l)
    trim = Image.new("L", (W * 3, H * 3), 0)
    ImageDraw.Draw(trim).rounded_rectangle(((ox + 4) * 3, (oy + 4) * 3, (ox + CONSOLE_W - 4) * 3, (oy + CONSOLE_H - 4) * 3),
                                           radius=20 * 3, outline=255, width=3)
    trim = trim.resize((W, H), Image.LANCZOS)
    tl = Image.new("RGBA", (W, H), BRASS + (0,))
    tl.putalpha(trim.point(lambda v: int(v * 0.9)))
    img = Image.alpha_composite(img, tl)

    # three recessed screens
    for rect, radius, tint, gloss in (
        (SCREEN_COMPASS, 14, ((14, 24, 20), (22, 36, 30)), False),
        (SCREEN_INFO, 14, ((12, 22, 18), (20, 34, 28)), True),
        (SCREEN_TURN, 10, ((14, 26, 21), (20, 32, 27)), False),
    ):
        r = (rect[0] + ox, rect[1] + oy, rect[2], rect[3])
        scr, rim = screen_layer((W, H), r, radius, tint, gloss)
        img = Image.alpha_composite(img, rim)
        img = Image.alpha_composite(img, scr)

    # compass: engraved cross guide lines on the left screen
    cx = ox + SCREEN_COMPASS[0] + SCREEN_COMPASS[2] // 2
    cy = oy + SCREEN_COMPASS[1] + SCREEN_COMPASS[3] // 2
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(g)
    gd.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), outline=(120, 150, 134, 70), width=1)
    gd.line((cx - 44, cy, cx + 44, cy), fill=(120, 150, 134, 55), width=1)
    gd.line((cx, cy - 44, cx, cy + 44), fill=(120, 150, 134, 55), width=1)
    img = Image.alpha_composite(img, g)

    # four screws
    sc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sc)
    for sx, sy in ((ox + 8, oy + 8), (ox + CONSOLE_W - 8, oy + 8), (ox + 8, oy + CONSOLE_H - 8), (ox + CONSOLE_W - 8, oy + CONSOLE_H - 8)):
        sd.ellipse((sx - 3, sy - 3, sx + 3, sy + 3), fill=(24, 26, 25, 255), outline=(150, 156, 152, 200))
        sd.line((sx - 2, sy + 1, sx + 2, sy - 1), fill=(150, 156, 152, 220), width=1)
    img = Image.alpha_composite(img, sc)
    return dither(img, rng, 1.0)


# ---------------------------------------------------------------- seat layout (mirrors TableScreen.cs, preview only)
# Every seat is laid out in its own frame: u runs along the seat's table edge (the seat's left to right), v runs from that
# edge toward the table centre. The right / left seats are the same frame turned by +90 / -90 degrees, so their tiles stand
# rotated like on a real table; the opposite seat keeps its tiles upright (v points down the screen, no rotation).
HW, HH = FELT_W // 2, FELT_H // 2                    # felt half extents: 770, 369
BACK, BACK_PITCH = (30, 40), 31                      # concealed tiles
MELD_T = (34, 45)                                    # melds and flowers
RIVER_T, RIVER_PITCH = (42, 56), (44, 58)            # discards
LEN = {0: FELT_W, 2: FELT_W, 1: FELT_H, 3: FELT_H}   # length of each seat's table edge
RIVER_COLS = {0: 16, 2: 16, 1: 12, 3: 12}            # tiles per row (a row of the side seats runs along the screen's vertical)
RIVER_ROWS = {0: 3, 2: 3, 1: 4, 3: 4}                # rows reserved (the capacity the layout is checked for)
HAND_SLOTS, HAND_WIN_GAP = 17, 10
HAND_W = HAND_SLOTS * BACK_PITCH + HAND_WIN_GAP + BACK[0]
MELD_GAP = {0: 10, 2: 10, 1: 6, 3: 6}
MELDS_U0, MELDS_W = {0: 160, 2: 160, 1: 6, 3: 6}, {0: 760, 2: 760, 1: 726, 3: 726}
FLOWERS_U0 = {0: 940, 2: 940, 1: 6, 3: 6}
V_HAND = 6
V_MELDS = {0: 6, 2: 52, 1: 52, 3: 52}
V_FLOWERS = {0: 6, 2: 52, 1: 103, 3: 103}            # the top / bottom seats keep flowers on the melds row
V_RIVER = {0: 57, 2: 103, 1: 154, 3: 154}
CONSOLE = (-220, -77, 220, 77)


def seat_point(rel, u, v):
    return {0: (-HW + u, -HH + v), 1: (HW - v, -HH + u), 2: (-HW + u, HH - v), 3: (-HW + v, HH - u)}[rel]


def seat_rect(rel, u, v, w, h):
    """Bounding box (x0, y0, x1, y1) in table coordinates of the local rectangle u..u+w, v..v+h of a seat."""
    pts = [seat_point(rel, u, v), seat_point(rel, u + w, v + h)]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def seat_items(rel, melds=5, meld_len=4, flowers=8, river=48):
    """Worst case content of one seat: [(kind, local u, local v, w, h, code)] in local frame coordinates."""
    items = []
    if rel != 0:
        u_h = (LEN[rel] - HAND_W) // 2
        for i in range(HAND_SLOTS):
            items.append(("hand", u_h + i * BACK_PITCH, V_HAND, BACK[0], BACK[1], "back"))
        items.append(("hand", u_h + HAND_SLOTS * BACK_PITCH + HAND_WIN_GAP, V_HAND, BACK[0], BACK[1], "back"))
    u = MELDS_U0[rel]
    for m in range(melds):
        for k in range(meld_len):
            items.append(("meld", u + k * (MELD_T[0] + 1), V_MELDS[rel], MELD_T[0], MELD_T[1], ["1m", "2m", "3m", "5p", "5p", "5p", "5p", "E"][(m + k) % 8]))
        u += meld_len * (MELD_T[0] + 1) - 1 + MELD_GAP[rel]
    for f in range(flowers):
        items.append(("flower", FLOWERS_U0[rel] + f * MELD_T[0], V_FLOWERS[rel], MELD_T[0], MELD_T[1], "F%d" % (f + 1)))
    cols = RIVER_COLS[rel]
    u0 = (LEN[rel] - (cols * RIVER_PITCH[0] - 2)) // 2
    for i in range(river):
        items.append(("river", u0 + (i % cols) * RIVER_PITCH[0], V_RIVER[rel] + (i // cols) * RIVER_PITCH[1], RIVER_T[0], RIVER_T[1],
                      ["1m", "9p", "E", "5s", "RD", "3m", "7p", "2s", "N", "6m", "8p", "GD", "4s", "W", "1p", "9s"][i % 16]))
    return items


def check_layout(river=48):
    """Worst case of all four seats: no two tiles overlap, nothing leaves the felt or touches the console. Returns the problems."""
    boxes = []
    for rel in range(4):
        for kind, u, v, w, h, code in seat_items(rel, river=river):
            boxes.append((rel, kind, seat_rect(rel, u, v, w, h)))
    problems = []
    for i, (r1, k1, a) in enumerate(boxes):
        if a[0] < -HW or a[2] > HW or a[1] < -HH or a[3] > HH:
            problems.append("outside felt: seat %d %s %s" % (r1, k1, a))
        if a[0] < CONSOLE[2] and a[2] > CONSOLE[0] and a[1] < CONSOLE[3] and a[3] > CONSOLE[1]:
            problems.append("on the console: seat %d %s %s" % (r1, k1, a))
        for r2, k2, b in boxes[i + 1:]:
            if a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]:
                problems.append("overlap: seat %d %s / seat %d %s" % (r1, k1, r2, k2))
    return problems


def font(size):
    return ImageFont.truetype(FONT_PATH, size)


def preview(frame, felt, shade, console, tiles_dir, path, canvas=(1920, 1080), river=48):
    """Worst-case mock-up of the whole table scene (every seat 17 concealed tiles, 5 kongs, 8 flowers, a full river)."""
    CW, CH = canvas
    scene = Image.new("RGBA", (CW, CH), (0xFF, 0xF4, 0xE0, 255))
    cx, cy = CW // 2, CH // 2 - 129                       # table centre on the canvas (image y grows downward)
    fx, fy = cx - HW, cy - HH
    felt_area = Image.new("RGBA", (FELT_W + 20, FELT_H + 20))
    for ty in range(0, FELT_H + 20, felt.height):
        for tx in range(0, FELT_W + 20, felt.width):
            felt_area.paste(felt, (tx, ty))
    felt_area = Image.alpha_composite(felt_area.crop((0, 0, FELT_W + 20, FELT_H + 20)), shade.resize((FELT_W + 20, FELT_H + 20), Image.BILINEAR))
    scene.alpha_composite(felt_area, (fx - 10, fy - 10))
    scene.alpha_composite(frame, (cx - frame.width // 2, cy - frame.height // 2))
    scene.alpha_composite(console, (cx - console.width // 2, cy - console.height // 2))
    d = ImageDraw.Draw(scene)

    # console contents
    ccx, ccy = cx - 220, cy - 77
    px, py = ccx + SCREEN_COMPASS[0] + 48, ccy + SCREEN_COMPASS[1] + 48
    for (dx, dy, ch, st) in ((0, -31, "南", "off"), (31, 0, "北", "off"), (0, 31, "東", "dealer"), (-31, 0, "西", "turn")):
        fill = {"off": (44, 60, 52), "dealer": (255, 216, 77), "turn": (190, 230, 207)}[st]
        txt = (150, 176, 162) if st == "off" else (74, 50, 38)
        if st == "turn":
            d.rounded_rectangle((px + dx - 16, py + dy - 16, px + dx + 16, py + dy + 16), radius=10, outline=(255, 244, 224), width=3)
        d.rounded_rectangle((px + dx - 14, py + dy - 14, px + dx + 14, py + dy + 14), radius=8, fill=fill)
        d.text((px + dx, py + dy), "莊" if st == "dealer" else ch, font=font(20), fill=txt, anchor="mm")
    d.text((ccx + 140, ccy + 36), "東風圈·第 1 局", font=font(30), fill=(255, 244, 224), anchor="lm")
    d.text((ccx + 140, ccy + 78), "剩餘 55 張", font=font(30), fill=(255, 216, 77), anchor="lm")
    d.text((ccx + 220, ccy + 128), "輪到你：點一張牌，再點一次打出", font=font(20), fill=(255, 244, 224), anchor="mm")

    def load(code, size):
        p = os.path.join(tiles_dir or "", code + ".png")
        if not os.path.exists(p):
            return Image.new("RGBA", size, (240, 240, 240, 255))
        return Image.open(p).convert("RGBA").resize(size, Image.LANCZOS)

    for rel in range(4):
        for kind, u, v, w, h, code in seat_items(rel, river=river):
            im = load(code, (w, h))
            if rel == 1:
                im = im.rotate(90, expand=True)
            elif rel == 3:
                im = im.rotate(-90, expand=True)
            x0, y0, x1, y1 = seat_rect(rel, u, v, w, h)
            scene.alpha_composite(im, (int(cx + x0), int(cy - y1)))

    # cards in the margins, my hand, the bottom strip (hint bar left, action panel right)
    def card(x, y, w, h, label):
        d.rounded_rectangle((x, y, x + w, y + h), radius=20, fill=(255, 253, 247), outline=(200, 185, 170), width=2)
        d.text((x + w // 2, y + 20), label, font=font(22), fill=(74, 50, 38), anchor="mm")
        d.ellipse((x + w // 2 - 26, y + 36, x + w // 2 + 26, y + 88), fill=(226, 212, 245))
        d.rounded_rectangle((x + w // 2 - 28, y + 94, x + w // 2 + 28, y + 118), radius=12, fill=(181, 224, 247))
        d.rounded_rectangle((x + w // 2 - 18, y + 124, x + w // 2 + 18, y + 148), radius=12, fill=(255, 179, 167))
        d.text((x + w // 2, y + 176), "+1,200", font=font(24), fill=(35, 107, 48), anchor="mm")
    mid = cy
    card(6, mid - 98, 100, 196, "左家")
    card(CW - 106, mid - 98, 100, 196, "右家")
    card(CW - 106, 12, 100, 196, "對家")
    d.rounded_rectangle((6, 6, 106, 62), radius=22, fill=(221, 213, 204))
    d.text((56, 34), "離開", font=font(28), fill=(74, 50, 38), anchor="mm")
    d.rounded_rectangle((24, CH - 134, 274, CH - 24), radius=24, fill=(255, 253, 247), outline=(200, 185, 170), width=2)
    d.text((149, CH - 79), "我的資訊卡", font=font(24), fill=(74, 50, 38), anchor="mm")
    d.rounded_rectangle((24, CH - 268, 724, CH - 164), radius=20, fill=(255, 253, 247), outline=(255, 158, 143), width=3)
    d.text((374, CH - 216), "聽牌提示列（牌圖＋剩餘張數，最高 104）", font=font(24), fill=(74, 50, 38), anchor="mm")
    d.rounded_rectangle((CW - 624, CH - 270, CW - 24, CH - 160), radius=28, fill=(255, 253, 247), outline=(200, 185, 170), width=2)
    d.text((CW - 324, CH - 215), "操作面板 吃 碰 槓 聽 胡 過", font=font(26), fill=(74, 50, 38), anchor="mm")
    for i in range(14):
        im = load(["1m", "2m", "3m", "5p", "5p", "6p", "7p", "2s", "3s", "4s", "E", "E", "RD", "9s"][i], (75, 100))
        scene.alpha_composite(im, (296 + i * 79, CH - 20 - 100))

    # FX plates (four positions around the console) as outlines
    for rel, (dx, dy) in ((0, (0, -150)), (1, (305, 0)), (2, (0, 150)), (3, (-305, 0))):
        px_, py_ = cx + dx, cy - dy
        d.rounded_rectangle((px_ - 116, py_ - 64, px_ + 116, py_ + 64), radius=34, outline=(217, 72, 15), width=3)
    scene.convert("RGB").save(path)




def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        print(__doc__)
        sys.exit(1)
    out = args[0]
    prev = args[args.index("--preview") + 1] if "--preview" in args else None
    tiles = args[args.index("--tiles") + 1] if "--tiles" in args else None
    os.makedirs(out, exist_ok=True)
    felt = make_felt()
    shade = make_felt_shade()
    frame = make_frame()
    console = make_console()
    felt.save(os.path.join(out, "felt.png"), optimize=True)
    shade.save(os.path.join(out, "felt_shade.png"), optimize=True)
    frame.save(os.path.join(out, "frame.png"), optimize=True)
    console.save(os.path.join(out, "console.png"), optimize=True)
    problems = check_layout()
    for p in problems[:20]:
        print("LAYOUT PROBLEM:", p)
    print("layout check:", "OK (no overlaps)" if not problems else "%d problems" % len(problems))
    if prev:
        preview(frame, felt, shade, console, tiles, prev)
        preview(frame, felt, shade, console, tiles, prev.replace(".png", "_1610.png"), canvas=(1821, 1138))
    print("rendered felt, felt_shade, frame, console")


if __name__ == "__main__":
    main()
