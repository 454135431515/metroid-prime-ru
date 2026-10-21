"""Генератор кириллицы не портит латиницу и пишет глифы, которые игра прочтёт.

    python -I tools/test_cyrillic.py work
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cyrillic  # noqa: E402
import font  # noqa: E402


def main(work):
    res = os.path.join(work, "res")
    if not os.path.isdir(res):
        print(f"test_cyrillic: {res} нет, пропуск")
        return 0
    for fid in cyrillic.FONTS:
        f = font.parse_font(open(os.path.join(res, "FONT", f"{fid}.FONT"), "rb").read())
        a = font.parse_txtr(open(os.path.join(res, "TXTR", f"{f.texture_id:08X}.TXTR"), "rb").read())
        before = {g.char: cyrillic.cell_pixels(a, g) for g in f.glyphs}
        cyrillic.add_glyphs(f, a, cyrillic.RECIPES)
        # через байты, как прочтёт игра
        f = font.parse_font(font.build_font(f))
        a = font.parse_txtr(font.build_txtr(a))
        glyphs = {g.char: g for g in f.glyphs}
        for ch, cell in before.items():
            assert cyrillic.cell_pixels(a, glyphs[ch]) == cell, (fid, chr(ch))
        assert a.height & (a.height - 1) == 0, (fid, a.height)
        for ch in cyrillic.RECIPES:
            g = glyphs[ord(ch)]
            assert g.kern_start <= len(f.kerning), (fid, ch)
            x, y, w, h = font.cell_rect(g, a)
            assert 0 < x and x + w < a.width and 0 < y and y + h < a.height, (fid, ch)
            assert any(v == cyrillic.INK for r in cyrillic.cell_pixels(a, g) for v in r), (fid, ch)
    print(f"cyrillic: {len(cyrillic.FONTS)} fonts ok, +{len(cyrillic.RECIPES)} glyphs each")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "work"))
