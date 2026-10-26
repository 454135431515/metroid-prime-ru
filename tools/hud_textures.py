"""Надписи, нарисованные на текстурах (не в STRG): «[ ENERGY ]» над полоской энергии, «[ PRESS START ]»
на титульном экране, «NEXT / BACK / EXIT» внизу паузы. Порт подменяет текстуру файлом
`<id TXTR>.dds` в моде (docs/MODS.md порта: native texture), поэтому рисуем каждую заново.

    python -I tools/hud_textures.py <папка мода с FONT/TXTR> [out.png]   # out.png — лист для проверки

Оригиналы — белые сглаженные буквы на чёрном (интенсивность, альфа 255), это уменьшенный Deface;
русские буквы берутся из нашего Deface24B (FE94BD23, с кириллицей) и уменьшаются до высоты букв
оригинала. Места и высоты замерены по дампу MP_DUMP_TEXTURES (порт 0.33.1). Дампы и DDS порта —
вверх ногами относительно экрана, поэтому картинка переворачивается перед записью.
"""

import os
import struct
import sys

from PIL import Image, ImageChops, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font  # noqa: E402

FONT_ID = "FE94BD23"  # Deface24B: заглавная H — 22 px; у текстур 14–16 px
SS = 8                # рисуем в 8 раз крупнее и уменьшаем — сглаживание как у оригинала

# id TXTR: (ширина, высота, [(текст, x, верх букв, высота заглавной, зазор, выравнивание)])
# x — левый край (just="left") или центр (just="center"); зазор — px между буквами в итоговом масштабе.
TEXTURES = {
    "BCBA7570": (128, 32, [("[", 1, 4, 21, 0, "left"), ("]", 126, 4, 21, 0, "right"),
                           ("ЭНЕРГИЯ", 64, 9, 14, 4, "center")]),
    "D411B6BB": (256, 32, [("[", 14, 4, 24, 0, "left"), ("]", 241, 4, 24, 0, "right"),
                           ("НАЖМИТЕ START", 128, 9, 16, 1, "center")]),
    # билборды лифтов: белое 14 px, обводка, слева с x=3; длинные — с меньшим зазором, чтобы влезть в 250 px
    "0C8F3C63": (256, 32, [("Ледники Фендраны", 3, 8, 14, ("fit", 8, 250), "left")], "halo"),
    "2AF13ACD": (256, 32, [("Руины Чозо", 3, 8, 14, ("fit", 8, 250), "left")], "halo"),
    "C74CCFA5": (256, 32, [("Кратер", 3, 8, 14, ("fit", 8, 250), "left")], "halo"),
    "D79A78E1": (256, 32, [("Фазоновые Шахты", 3, 8, 14, ("fit", 8, 250), "left")], "halo"),
    "FEE1E54F": (256, 32, [("Поверхность Таллона", 3, 8, 14, ("fit", 8, 250), "left")], "halo"),
    # Магмур — 320 px шириной (TXTR_LavaBillboard), буквы с x=6
    "38D3B39B": (320, 32, [("Пещеры Магмура", 6, 8, 14, ("fit", 8, 300), "left")], "halo"),
    # подписи галереи (бонусы главного меню): I4 — прозрачность равна яркости
    "0037F8DC": (128, 32, [("Галерея 1", 6, 9, 13, 1, "left")], "alpha"),
    "86A38A72": (128, 32, [("Галерея 2", 6, 9, 13, 1, "left")], "alpha"),
    "4DFF59D7": (128, 32, [("Галерея 3", 6, 9, 13, 1, "left")], "alpha"),
    "50FA696F": (128, 32, [("Галерея 4", 6, 9, 13, 1, "left")], "alpha"),
    "89E7453F": (128, 128, [("ВЫХОД", 61.5, 10, 16, 1, "center"),
                            ("НАЗАД", 18, 40, 16, 1, "left"),
                            ("ДАЛЕЕ", 18, 70, 16, 1, "left")]),
}


def glyph_masks(font_dir):
    f = font.parse_font(open(os.path.join(font_dir, f"{FONT_ID}.FONT"), "rb").read())
    a = font.parse_txtr(open(os.path.join(font_dir, f"{f.texture_id:08X}.TXTR"), "rb").read())
    out = {}
    for g in f.glyphs:
        cx, cy, cw, ch = font.cell_rect(g, a)
        m = Image.new("L", (cw, ch))
        m.putdata([255 if a.pixels[(cy + y) * a.width + cx + x] == 1 else 0 for y in range(ch) for x in range(cw)])
        box = m.getbbox()
        if box:
            # (заливка, её верх относительно верха заглавной H): буквы стоят на общей базовой линии
            out[chr(g.char)] = (m.crop(box), f.baseline - g.baseline + box[1])
    h_mask, h_top = out["H"]
    return {c: (m, top - h_top) for c, (m, top) in out.items()}, h_mask.height


def word(masks, cap, text, height, gap):
    """Слово в масштабе SS: буквы по ширине своей заливки, зазор gap, пробел — ширина «I» + зазор."""
    k = height * SS / cap
    parts = []
    for c in text:
        if c == " ":
            parts.append(None)
            continue
        m, top = masks[c]
        parts.append((m.resize((max(1, round(m.width * k)), max(1, round(m.height * k))), Image.NEAREST), round(top * k)))
    space = round(masks["I"][0].width * k) + gap * SS
    w = sum(p[0].width if p else space for p in parts) + gap * SS * (len(parts) - 1)
    lo = min(p[1] for p in parts if p)
    h = max(p[1] + p[0].height for p in parts if p) - lo
    img = Image.new("L", (w, h))
    x = 0
    for p in parts:
        if p:
            img.paste(p[0], (x, p[1] - lo))
        x += (p[0].width if p else space) + gap * SS
    return img, -lo  # -lo: на сколько верх заглавных ниже верха картинки (скобки выше букв)


def draw(masks, cap, spec):
    """RGBA-текстура по описанию: стиль plain — белое на чёрном (альфа 255), alpha — белое, прозрачность
    равна яркости (I4 галереи), halo — белое с мягкой чёрной обводкой ~2 px на прозрачном (билборды лифтов)."""
    w, h, items = spec[:3]
    style = spec[3] if len(spec) > 3 else "plain"
    big = Image.new("L", (w * SS, h * SS))
    for text, x, top, height, gap, just in items:
        if isinstance(gap, tuple):  # ("fit", наибольший зазор, ширина): длинное слово — зазор меньше
            _, most, room = gap
            gap = most
            while gap > 0 and word(masks, cap, text, height, gap)[0].width / SS > room:
                gap -= 1
        img, cap_top = word(masks, cap, text, height, gap)
        left = {"left": x, "right": x + 1 - img.width / SS, "center": x - img.width / SS / 2}[just]
        big.paste(img, (round(left * SS), top * SS - cap_top))
    m = big.resize((w, h), Image.LANCZOS)
    if style == "plain":
        return Image.merge("RGBA", (m, m, m, Image.new("L", m.size, 255)))
    if style == "alpha":
        return Image.merge("RGBA", (m, m, m, m))
    halo = big.filter(ImageFilter.MaxFilter(4 * SS + 1)).filter(ImageFilter.BoxBlur(SS)).resize((w, h), Image.LANCZOS)
    halo = halo.point(lambda v: v * 218 // 255)  # у оригинала тень до альфы 218
    return Image.merge("RGBA", (m, m, m, ImageChops.lighter(halo, m)))


def dds(img):
    """DDS DX10, R8G8B8A8_UNORM, полная цепочка мипов."""
    levels = [img]
    while levels[-1].width > 1 or levels[-1].height > 1:
        p = levels[-1]
        levels.append(p.resize((max(1, p.width // 2), max(1, p.height // 2)), Image.BOX))
    w, h = img.size
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x8  # caps, height, width, pixelformat, mipmapcount, pitch
    head = struct.pack("<4sIIIIIII11I", b"DDS ", 124, flags, h, w, w * 4, 0, len(levels), *([0] * 11))
    pf = struct.pack("<II4sIIIII", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
    caps = struct.pack("<IIIII", 0x1000 | 0x8 | 0x400000, 0, 0, 0, 0)
    dx10 = struct.pack("<IIIII", 28, 3, 0, 1, 0)
    return head + pf + caps + dx10 + b"".join(lv.convert("RGBA").tobytes() for lv in levels)


def main(mod_dir, sheet=None):
    masks, cap = glyph_masks(mod_dir)
    imgs = {}
    for tid, spec in TEXTURES.items():
        img = draw(masks, cap, spec)
        imgs[tid] = img
        open(os.path.join(mod_dir, f"{tid}.dds"), "wb").write(dds(img.transpose(Image.FLIP_TOP_BOTTOM)))
    if sheet:
        s = 4
        out = Image.new("RGBA", (max(i.width for i in imgs.values()) * s, sum(i.height * s + 8 for i in imgs.values())),
                        (90, 0, 90, 255))
        y = 0
        for img in imgs.values():
            bg = Image.new("RGBA", img.size, (90, 0, 90, 255))
            bg.alpha_composite(img)
            out.paste(bg.resize((img.width * s, img.height * s), Image.NEAREST), (0, y))
            y += img.height * s + 8
        out.save(sheet)
    print(f"hud textures: {', '.join(TEXTURES)}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
