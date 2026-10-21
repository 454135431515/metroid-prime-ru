"""Текстовые поля (TXPN) из кадров интерфейса FRME: имя, шрифт, перенос, область вёрстки.

    python -I tools/frme.py work/res        # таблица всех полей

Формат виджета TXPN (src/GuiSys/CGuiTextPane.cpp, CGuiWidget::ReadWidgetHeader), big endian:
    char[4] "TXPN", заголовок: name\\0, parent\\0, 4 x u8 (anim, vis, active, cull), f32[4] цвет, u32 флаги;
    f32 dimX, dimY, f32[3] vec, u32 fontId, u8 wordWrap, u8 horizontal, u32 just, u32 vjust,
    f32[4] цвет, f32[4] цвет контура, f32 extentX, f32 extentY.
extentX/extentY — область вёрстки текста в пикселях шрифта: по ней игра переносит строки и обрезает.
Виджеты других типов не разбираются: TXPN ищется по метке типа и проверяется на правдоподобие.
"""

import glob
import os
import struct
import sys


def cstr(data, pos):
    end = data.index(b"\0", pos)
    return data[pos:end].decode("ascii"), end + 1


def text_panes(data):
    """[(name, fontId, wordWrap, just, extentX, extentY)] для всех TXPN кадра."""
    out = []
    pos = 0
    while True:
        pos = data.find(b"TXPN", pos)
        if pos < 0:
            return out
        try:
            name, p = cstr(data, pos + 4)
            _, p = cstr(data, p)
            if not name.isprintable() or not name:
                raise ValueError
            p += 4 + 16 + 4            # bools, цвет, флаги
            p += 8 + 12                # dimX, dimY, vec
            font, wrap, horiz, just, vjust = struct.unpack_from(">IBBII", data, p)
            p += 14 + 32               # шрифт…vjust, два цвета
            ex, ey = struct.unpack_from(">ff", data, p)
            if 0 < ex < 4096 and 0 < ey < 4096:
                out.append((name, font, bool(wrap), just, int(ex), int(ey)))
        except (ValueError, struct.error):
            pass
        pos += 4


def all_panes(res):
    """{(frameId, name): (fontId, wrap, just, extentX, extentY)}."""
    panes = {}
    for path in sorted(glob.glob(os.path.join(res, "FRME", "*.FRME"))):
        fid = os.path.basename(path)[:8]
        for name, font, wrap, just, ex, ey in text_panes(open(path, "rb").read()):
            panes[(fid, name)] = (f"{font:08X}", wrap, just, ex, ey)
    return panes


if __name__ == "__main__":
    for (fid, name), (font, wrap, just, ex, ey) in sorted(all_panes(sys.argv[1]).items()):
        print(f"{fid}\t{name}\t{font}\twrap={int(wrap)}\tjust={just}\t{ex}x{ey}")
