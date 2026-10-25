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

from PIL import Image

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
    w, h, items = spec
    big = Image.new("L", (w * SS, h * SS))
    for text, x, top, height, gap, just in items:
        img, cap_top = word(masks, cap, text, height, gap)
        left = {"left": x, "right": x + 1 - img.width / SS, "center": x - img.width / SS / 2}[just]
        big.paste(img, (round(left * SS), top * SS - cap_top))
    return big.resize((w, h), Image.LANCZOS)


def dds(img):
    """DDS DX10, R8G8B8A8_UNORM, полная цепочка мипов; RGB = интенсивность, альфа 255 (как дамп)."""
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
    body = b"".join(bytes(b for v in lv.get_flattened_data() for b in (v, v, v, 255)) for lv in levels)
    return head + pf + caps + dx10 + body


def main(mod_dir, sheet=None):
    masks, cap = glyph_masks(mod_dir)
    imgs = {}
    for tid, spec in TEXTURES.items():
        img = draw(masks, cap, spec)
        imgs[tid] = img
        open(os.path.join(mod_dir, f"{tid}.dds"), "wb").write(dds(img.transpose(Image.FLIP_TOP_BOTTOM)))
    if sheet:
        s = 4
        out = Image.new("L", (max(i.width for i in imgs.values()) * s, sum(i.height * s + 8 for i in imgs.values())), 60)
        y = 0
        for img in imgs.values():
            out.paste(img.resize((img.width * s, img.height * s), Image.NEAREST), (0, y))
            y += img.height * s + 8
        out.save(sheet)
    print(f"hud textures: {', '.join(TEXTURES)}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
