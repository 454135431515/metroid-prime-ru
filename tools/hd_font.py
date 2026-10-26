"""HD-шрифт с кириллицей для импорта Remastered: `deface.sdfont` (поле расстояний, формат порта
platform/include/port_hd_font.h) дополняется русскими буквами.

    python -I tools/hd_font.py <deface.sdfont из импорта> <out.sdfont> [preview.png]

В шрифте Remastered только латиница и знаки (195 символов, кириллицы нет), и порт рисует русский
текст растровым шрифтом диска. Здесь латинские глифы восстанавливаются в 4 раза крупнее (поле
расстояний увеличивается и обрезается по краю), русские собираются теми же рецептами, что растровые
(tools/cyrillic.py: копии, зеркала, конструкторы по меркам H), и снова переводятся в поле расстояний.
Латиница и раскладка атласа не меняются, новые глифы дописываются полками ниже.
Шрифт строится только из файла импорта владельца — без импорта Remastered его нет.
"""

import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import cyrillic  # noqa: E402

U = 4          # во сколько раз крупнее восстанавливаются глифы
HEAD = "<4sIIIffI"
GLYPH = "<I9f"


def read(path):
    b = open(path, "rb").read()
    magic, ver, w, h, pad, per, n = struct.unpack_from(HEAD, b, 0)
    if magic != b"SDFT" or ver != 1:
        raise ValueError(f"{path}: не SDFT v1")
    pos = struct.calcsize(HEAD)
    glyphs = []
    for _ in range(n):
        glyphs.append(list(struct.unpack_from(GLYPH, b, pos)))
        pos += struct.calcsize(GLYPH)
    dist = np.frombuffer(b, np.uint8, w * h, pos).reshape(h, w).copy()
    return w, h, pad, per, glyphs, dist


def write(path, w, h, pad, per, glyphs, dist):
    glyphs = sorted(glyphs, key=lambda g: g[0])
    out = struct.pack(HEAD, b"SDFT", 1, w, h, pad, per, len(glyphs))
    out += b"".join(struct.pack(GLYPH, *g) for g in glyphs)
    open(path, "wb").write(out + dist.astype(np.uint8).tobytes())


def region(g, w, h):
    """(x0, y0, x1, y1) коробки глифа в атласе; строки в атласе — по возрастанию v, глиф вверх ногами."""
    _, left, top, gw, gh, u0, v0, u1, v1, adv = g
    x0, x1 = sorted((round(u0 * w), round(u1 * w)))
    y0, y1 = sorted((round(v0 * h), round(v1 * h)))
    return x0, y0, x1, y1


def hires_cell(g, w, h, dist):
    """Глиф прямо, в U раз крупнее: ячейка cyrillic (INK внутри, 0 снаружи), начало — левый верх коробки."""
    x0, y0, x1, y1 = region(g, w, h)
    img = Image.fromarray(dist[y0:y1, x0:x1][::-1])
    big = np.asarray(img.resize(((x1 - x0) * U, (y1 - y0) * U), Image.BICUBIC))
    return [[cyrillic.INK if v > 127 else 0 for v in row] for row in big]


def sdf(mask, pad, per):
    """Поле расстояний для маски (U px на пиксель атласа), с полями pad пикселей атласа вокруг;
    байт = 255·(0.5 + d·per), d — пиксели атласа, плюс внутри."""
    m = np.array(mask, bool)
    p = int(pad * U)
    m = np.pad(m, p)
    h, w = m.shape
    edge = m ^ np.pad(m, 1, mode="edge")[1:-1, 2:] | m ^ np.pad(m, 1, mode="edge")[2:, 1:-1]
    ey, ex = np.nonzero(edge)
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.full((h, w), np.inf)
    for k in range(0, len(ey), 256):  # ближайшая граница, кусками
        dy = yy[..., None] - ey[None, None, k:k + 256]
        dx = xx[..., None] - ex[None, None, k:k + 256]
        d = np.minimum(d, np.sqrt(dy * dy + dx * dx).min(-1))
    d = np.where(m, d, -d) / U
    # уменьшаем до пикселей атласа: среднее по клеткам U×U
    hh, ww = h // U, w // U
    d = d[:hh * U, :ww * U].reshape(hh, U, ww, U).mean((1, 3))
    return np.clip(np.round(255 * (0.5 + d * per)), 0, 255).astype(np.uint8)


class Ref:
    """Глиф-образец в крупном масштабе: коробка от пера (left, top — пиксели атласа) и ячейка."""

    def __init__(self, g, w, h, dist):
        self.g = g
        self.cell = hires_cell(g, w, h, dist)


def make_glyphs(P, refs, have, pad, per):
    """Русские глифы: [(символ, запись глифа без UV, поле расстояний или None — копия латинского)]."""
    recipes = {c: r for c, r in {**cyrillic.CAPITALS, **cyrillic.LOWERCASE}.items() if c not in have}
    new = []  # (символ, запись глифа без UV, поле расстояний)
    for ch, (ref_ch, (how, arg)) in recipes.items():
        ref = refs[ref_ch]
        if how == "copy":
            g = list(have[arg])
            g[0] = ord(ch)
            new.append((ch, g, None))
            continue
        rx0, ry0, rx1, ry1 = cyrillic.ink_box(ref.cell)
        if how == "mirror":
            drawn = cyrillic.Drawn([r[::-1] for r in P.mask(arg)])
        elif how == "small_mirror":
            drawn = cyrillic.Drawn([r[::-1] for r in cyrillic.shrink_rows(P.mask(arg), ry1 - ry0)])
        elif how == "draw":
            drawn = arg(P)
        else:
            raise ValueError(how)
        mask = drawn.mask
        mh, mw = len(mask), len(mask[0])
        field = sdf(mask, pad, per)
        _, left, top, gw, gh, *_uv, adv = ref.g
        # заливка — на месте заливки образца, поднята на `above` строк
        nleft = left + rx0 / U - pad
        ntop = top - (ry0 - drawn.above) / U + pad
        nadv = adv + (mw - (rx1 - rx0)) / U
        new.append((ch, [ord(ch), nleft, ntop, field.shape[1], field.shape[0], 0, 0, 0, 0, nadv], field))
    return new


def build(src, dst, preview=None):
    w, h, pad, per, glyphs, dist = read(src)
    have = {chr(g[0]): g for g in glyphs}
    refs = {c: Ref(g, w, h, dist) for c, g in have.items() if c.isascii() and c.strip()}
    P = cyrillic.Metrics({c: r.cell for c, r in refs.items()})
    # мелкие отступы рецептов — в «пикселях растрового шрифта»: у растровых Deface стем 2 px
    unit, cyrillic.UNIT = cyrillic.UNIT, max(1, round(P.s / 2))
    P.desc = max(len(P.mask("p")) - P.xh, 2 * cyrillic.UNIT)
    try:
        new = make_glyphs(P, refs, have, pad, per)
    finally:
        cyrillic.UNIT = unit
    # полки ниже атласа, с зазором 1 пиксель
    x, y, shelf, spots = 1, h + 1, 0, []
    for ch, g, field in new:
        if field is None:
            spots.append(None)
            continue
        fh, fw = field.shape
        if x + fw + 1 > w:
            x, y, shelf = 1, y + shelf + 1, 0
        spots.append((x, y))
        x += fw + 1
        shelf = max(shelf, fh)
    nh = y + shelf + 1
    atlas = np.zeros((nh, w), np.uint8)
    atlas[:h] = dist
    for g in glyphs:  # старые UV под новую высоту
        g[6] = g[6] * h / nh
        g[8] = g[8] * h / nh
    for (ch, g, field), spot in zip(new, spots):
        if field is None:
            g[6] = g[6] * h / nh
            g[8] = g[8] * h / nh
            glyphs.append(g)
            continue
        sx, sy = spot
        fh, fw = field.shape
        atlas[sy:sy + fh, sx:sx + fw] = field[::-1]  # как у Remastered: низ глифа первой строкой
        g[5], g[7] = sx / w, (sx + fw) / w
        g[6], g[8] = (sy + fh) / nh, sy / nh  # v0 — больший
        glyphs.append(g)
    write(dst, w, nh, pad, per, glyphs, atlas)
    if preview:
        render_preview(dst, preview)
    print(f"hd font: +{len(new)} glyphs, atlas {w}x{nh} -> {dst}")


def render_preview(path, out, lines=("Пещеры Магмура — Ледники Фендраны", "Сканирующее забрало обнаружено.",
                                      "Ёлка, щука, ЪЫЬЭЮЯ, бвгджзийклмнопрстуфхцчшщъыьэюя", "Magmoor Caverns 121 °C")):
    w, h, pad, per, glyphs, dist = read(path)
    by = {g[0]: g for g in glyphs}
    ink = Image.fromarray(np.where(dist > 127, 255, 0).astype(np.uint8))
    out_img = Image.new("L", (1400, 60 * len(lines) + 20), 0)
    for n, text in enumerate(lines):
        x, base = 10, 50 + 60 * n
        for c in text:
            g = by.get(ord(c))
            if not g:
                x += 12
                continue
            x0, y0, x1, y1 = region(g, w, h)
            glyph = ink.crop((x0, y0, x1, y1)).transpose(Image.FLIP_TOP_BOTTOM)
            out_img.paste(glyph, (round(x + g[1]), round(base - g[2])))
            x += g[9]
    out_img.save(out)


if __name__ == "__main__":
    build(*sys.argv[1:4])
