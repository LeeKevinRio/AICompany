"""Render the mahjong table textures for manjong-unity (pure PIL, nothing downloaded).

Usage: python render_table.py <out-dir> [--preview <png>] [--tiles <tiles-dir>]

Output in <out-dir> (the client keeps them in Assets/Resources/Table/):
  felt.png        256x256 seamless green baize tile (repeats; Image.Type.Tiled in uGUI)
  felt_shade.png  610x322 vignette (dark corners) plus a soft light pool in the middle, stretched over the felt
  frame.png       1376x800 wooden table frame: mitred walnut rails with grain, bevel, brass inlay, inner shadow
                  on the felt and a soft drop shadow outside (the frame's hole is transparent)
  console.png     480x194 electric-table console: dark bezel with brass trim and three recessed screens

With --preview a 1920x1080 mock-up of the table scene is written (felt, frame, console, a few river tiles read
from --tiles); it is only for checking the look and never goes into the client.

All geometry below is in canvas units (1 texel = 1 unit at the 1920x1080 reference) and must match the
constants in Assets/Scripts/Screens/TableScreen.cs (TableFrame*, Console*).
"""
import math
import os
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- geometry (mirrors TableScreen.cs)
FRAME_W, FRAME_H = 1280, 704           # outer size of the wooden frame
FRAME_MARGIN = 48                      # transparent margin around the frame that holds its drop shadow
WOOD = 30                              # width of the wood rail
FELT_W, FELT_H = FRAME_W - 2 * WOOD, FRAME_H - 2 * WOOD   # 1220 x 644 visible felt
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


# ---------------------------------------------------------------- preview mock-up (not shipped)
def font(size):
    return ImageFont.truetype(FONT_PATH, size)


def preview(frame, felt, shade, console, tiles_dir, path):
    CW, CH = 1920, 1080
    scene = Image.new("RGBA", (CW, CH), (0xFF, 0xF4, 0xE0, 255))
    cx, cy = CW // 2, CH // 2 - 16                 # table centre (canvas y is up: +16 raised)
    fx, fy = cx - FELT_W // 2, cy - FELT_H // 2

    felt_area = Image.new("RGBA", (FELT_W + 20, FELT_H + 20))
    for ty in range(0, FELT_H + 20, felt.height):
        for tx in range(0, FELT_W + 20, felt.width):
            felt_area.paste(felt, (tx, ty))
    felt_area = felt_area.crop((0, 0, FELT_W + 20, FELT_H + 20))
    sh = shade.resize((FELT_W + 20, FELT_H + 20), Image.BILINEAR)
    felt_area = Image.alpha_composite(felt_area, sh)
    scene.alpha_composite(felt_area, (fx - 10, fy - 10))
    scene.alpha_composite(frame, (cx - frame.width // 2, cy - frame.height // 2))
    scene.alpha_composite(console, (cx - console.width // 2, cy - console.height // 2))

    d = ImageDraw.Draw(scene)
    ccx, ccy = cx - CONSOLE_W // 2, cy - CONSOLE_H // 2     # console top-left
    # compass lamps (centre of the compass screen, one lamp per relative seat: 0 bottom, 1 right, 2 top, 3 left)
    px = ccx + SCREEN_COMPASS[0] + SCREEN_COMPASS[2] // 2
    py = ccy + SCREEN_COMPASS[1] + SCREEN_COMPASS[3] // 2
    lamps = {2: (0, -31, "南", "unlit"), 1: (31, 0, "北", "unlit"), 0: (0, 31, "東", "dealer"), 3: (-31, 0, "西", "turn")}
    for rel, (dx, dy, ch, state) in lamps.items():
        lx, ly = px + dx, py + dy
        fill = {"unlit": (44, 60, 52), "dealer": (255, 216, 77), "turn": (190, 230, 207)}[state]
        txt = {"unlit": (150, 176, 162), "dealer": (74, 50, 38), "turn": (74, 50, 38)}[state]
        if state == "turn":
            d.ellipse((lx - 17, ly - 17, lx + 17, ly + 17), outline=(255, 244, 224), width=3)
        d.rounded_rectangle((lx - 14, ly - 14, lx + 14, ly + 14), radius=8, fill=fill)
        d.text((lx, ly), "莊" if state == "dealer" else ch, font=font(20), fill=txt, anchor="mm")
    ix = ccx + SCREEN_INFO[0] + 16
    iy = ccy + SCREEN_INFO[1]
    d.text((ix, iy + 26), "東風圈·第 1 局", font=font(30), fill=(255, 244, 224), anchor="lm")
    d.text((ix, iy + 68), "剩餘 55 張", font=font(30), fill=(255, 216, 77), anchor="lm")
    tx = ccx + SCREEN_TURN[0] + SCREEN_TURN[2] // 2
    ty = ccy + SCREEN_TURN[1] + SCREEN_TURN[3] // 2
    d.text((tx, ty), "輪到你：點一張牌，再點一次打出", font=font(20), fill=(255, 244, 224), anchor="mm")

    # rivers (tile images scaled to the Small size 42x56)
    if tiles_dir and os.path.isdir(tiles_dir):
        codes = ["1m", "9p", "E", "5s", "RD", "3m", "7p", "2s", "N", "6m", "8p", "GD", "4s", "W", "1p", "9s", "S", "5m", "WD", "3p", "2m"]
        step_x, step_y = 44, 58

        def put(code, x, y):
            p = os.path.join(tiles_dir, code + ".png")
            if os.path.exists(p):
                t = Image.open(p).convert("RGBA").resize((42, 56), Image.LANCZOS)
                scene.alpha_composite(t, (int(x), int(y)))

        wide, narrow = 10, 8
        for i, c in enumerate(codes):              # bottom river (mine): top edge 85 below the centre
            put(c, cx - (wide * step_x - 2) / 2 + (i % wide) * step_x, cy + 85 + (i // wide) * step_y)
        for i, c in enumerate(codes[3:] + codes[:3]):  # top river: bottom edge 85 above the centre
            col, row = i % wide, i // wide
            put(c, cx - (wide * step_x - 2) / 2 + col * step_x, cy - 85 - 56 - row * step_y)
        side_x = (wide * step_x - 2) / 2 + 12
        for i, c in enumerate(codes[:16]):
            put(c, cx + side_x + (i % narrow) * step_x, cy - 58 + (i // narrow) * step_y)
            put(codes[(i + 5) % len(codes)], cx - side_x - (narrow * step_x - 2) + (i % narrow) * step_x, cy - 58 + (i // narrow) * step_y)
        # my hand, 75x100 tiles, below the table
        for i, c in enumerate(["1m", "2m", "3m", "5p", "5p", "6p", "7p", "2s", "3s", "4s", "E", "E", "RD"]):
            p = os.path.join(tiles_dir, c + ".png")
            if os.path.exists(p):
                t = Image.open(p).convert("RGBA").resize((75, 100), Image.LANCZOS)
                scene.alpha_composite(t, (296 + i * 79, CH - 20 - 100))
    mock_ui(scene, tiles_dir)
    scene.convert("RGB").save(path)


def mock_ui(scene, tiles_dir):
    """Rough picture of the waits hint bar and two action effects (what TableScreen / ActionFx draw); preview only."""
    CW, CH = scene.size
    INK, CARD, CORAL, GOLD, SKY, GRAY = (74, 50, 38), (255, 253, 247), (255, 158, 143), (255, 216, 77), (181, 224, 247), (221, 213, 204)
    d = ImageDraw.Draw(scene)

    def tile(code, x, y, w=33, h=44):
        p = os.path.join(tiles_dir or "", code + ".png")
        if os.path.exists(p):
            t = Image.open(p).convert("RGBA").resize((w, h), Image.LANCZOS)
            return t
        return None

    # --- waits hint bar (bottom-left origin y=222, 700 x 105 with the detail line)
    bx, by, bw, bh = 24, CH - 222 - 105, 700, 105
    d.rounded_rectangle((bx, by + 3, bx + bw, by + bh + 3), radius=20, fill=(120, 100, 80, 40))
    d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=20, fill=CARD, outline=(255, 158, 143), width=3)
    d.text((bx + 14, by + 29), "打出後聽", font=font(24), fill=INK, anchor="lm")
    d.text((bx + 14, by + 57), "數字為剩餘張數", font=font(16), fill=(107, 78, 61), anchor="lm")
    waits = [("2p", 2), ("5p", 1), ("8p", 4), ("3s", 0), ("6s", 3), ("9s", 1), ("E", 2), ("RD", 3), ("1m", 0)]
    for i, (code, left) in enumerate(waits):
        x, y = bx + 14 + 118 + i * 42, by + 7
        t = tile(code, x, y)
        if t:
            if left == 0:
                veil = Image.new("RGBA", t.size, (140, 120, 102, 90))
                t = Image.alpha_composite(t, veil)
                a = t.getchannel("A").point(lambda v: int(v * 0.45))
                t.putalpha(a)
            scene.alpha_composite(t, (x, y))
        pill = (x - 2, y + 46, x + 36, y + 66)
        d.rounded_rectangle(pill, radius=10, fill=GRAY if left == 0 else CORAL, outline=(107, 78, 61) if left == 0 else (217, 72, 15), width=2)
        d.text(((pill[0] + pill[2]) // 2, (pill[1] + pill[3]) // 2), f"剩 {left}", font=font(17), fill=INK, anchor="mm")
    d.text((bx + 18, by + 92), "五萬：場上已出現 3 張，你手上 1 張", font=font(22), fill=INK, anchor="lm")

    # --- action effects: 碰 by the opposite seat, 自摸 by the left seat (rays + glow)
    def plate(cx, cy, word, color, font_size, w, h, who):
        d.rounded_rectangle((cx - w // 2, cy - h // 2 + 6, cx + w // 2, cy + h // 2 + 6), radius=40, fill=(90, 70, 50, 70))
        d.rounded_rectangle((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2), radius=40, fill=color, outline=INK, width=5)
        d.text((cx, cy - 4), word, font=font(font_size), fill=INK, anchor="mm", stroke_width=3, stroke_fill=CARD)
        pw = max(84, min(260, 36 + 26 * len(who)))
        d.rounded_rectangle((cx - pw // 2, cy + h // 2 - 19, cx + pw // 2, cy + h // 2 + 19), radius=18, fill=CARD, outline=INK, width=3)
        d.text((cx, cy + h // 2), who, font=font(26), fill=INK, anchor="mm")

    plate(CW // 2, CH // 2 - 255, "碰", SKY, 104, 168, 150, "熊熊")
    cx, cy = CW // 2 - 430, CH // 2 - 215
    glow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((cx - 170, cy - 170, cx + 170, cy + 170), fill=(255, 216, 77, 77))
    for i in range(12):
        ang = math.radians(i * 30 + 8)
        r0, r1, wd = 105, 185 if i % 2 == 0 else 153, 8 if i % 2 == 0 else 5.5
        dx, dy = math.sin(ang), -math.cos(ang)
        px, py = -dy, dx
        gd.polygon([(cx + dx * r0 - px * wd, cy + dy * r0 - py * wd), (cx + dx * r0 + px * wd, cy + dy * r0 + py * wd),
                    (cx + dx * r1 + px * wd, cy + dy * r1 + py * wd), (cx + dx * r1 - px * wd, cy + dy * r1 - py * wd)], fill=(255, 216, 77, 140))
    scene.alpha_composite(glow)
    d = ImageDraw.Draw(scene)
    plate(cx, cy, "自摸", GOLD, 116, 296, 164, "小兔")


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
    if prev:
        preview(frame, felt, shade, console, tiles, prev)
    print("rendered felt, felt_shade, frame, console")


if __name__ == "__main__":
    main()
