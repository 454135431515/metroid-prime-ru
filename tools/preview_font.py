"""PNG атласа шрифта (x4) с рамками глифов и строка текста этим шрифтом.

    python -I tools/preview_font.py work/res/FONT/<id>.FONT work/res/TXTR out.png ["текст"]
"""

import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font  # noqa: E402

COLORS = {0: (20, 20, 30), 1: (255, 255, 255), 2: (200, 60, 60)}


def atlas_image(a):
    img = Image.new("RGB", (a.width, a.height))
    img.putdata([COLORS.get(v, (255, 0, 255)) for v in a.pixels])
    return img


def render(f, a, text):
    """Текст по метрикам игры (a+b+c, кернинг), как CRasterFont::DrawString."""
    kern = {(k[0], k[1]): k[2] for k in f.kerning}
    glyphs = {g.char: g for g in f.glyphs}
    src = atlas_image(a)
    width = sum(glyphs[ord(c)].a + glyphs[ord(c)].b + glyphs[ord(c)].c for c in text if ord(c) in glyphs) + 8
    img = Image.new("RGB", (max(width, 8), f.mono_h + 8), COLORS[0])
    x, prev = 4, None
    for ch in text:
        g = glyphs.get(ord(ch))
        if g is None:
            x += f.mono_w // 2  # нет глифа: игра его просто пропускает; рисуем пробел-метку
            ImageDraw.Draw(img).rectangle([x - f.mono_w // 2, 4, x - 2, 4 + f.mono_h], outline=(255, 0, 255))
            prev = None
            continue
        if prev is not None:
            x += kern.get((prev.char, g.char), 0)
        box = (round(g.u0 * a.width), round(g.v0 * a.height), round(g.u1 * a.width), round(g.v1 * a.height))
        cell = src.crop(box)
        img.paste(cell, (x + g.a, 4 + f.baseline - g.baseline))
        x += g.a + g.b + g.c
        prev = g
    return img


def main(font_path, txtr_dir, out, text="Metroid Prime: New Game"):
    f = font.parse_font(open(font_path, "rb").read())
    a = font.parse_txtr(open(os.path.join(txtr_dir, f"{f.texture_id:08X}.TXTR"), "rb").read())
    sheet = atlas_image(a)
    d = ImageDraw.Draw(sheet)
    for g in f.glyphs:
        d.rectangle([g.u0 * a.width, g.v0 * a.height, g.u1 * a.width - 1, g.v1 * a.height - 1], outline=(60, 160, 255))
    line = render(f, a, text)
    w = max(sheet.width, line.width)
    out_img = Image.new("RGB", (w, sheet.height + line.height + 4), (0, 0, 0))
    out_img.paste(sheet, (0, 0))
    out_img.paste(line, (0, sheet.height + 4))
    out_img.resize((out_img.width * 4, out_img.height * 4), Image.NEAREST).save(out)


if __name__ == "__main__":
    main(*sys.argv[1:])
