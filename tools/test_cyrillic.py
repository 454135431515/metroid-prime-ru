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
    return test_hd_font(os.path.join(os.path.dirname(os.path.abspath(work)), "mod", "remastered-models",
                                     "font", "deface.sdfont"))


def test_hd_font(src):
    """HD-шрифт: латиница побайтно та же, все русские буквы есть и лежат в атласе."""
    if not os.path.isfile(src):
        print("hd font: импорта Remastered нет, пропуск")
        return 0
    import tempfile
    import hd_font
    dst = os.path.join(tempfile.mkdtemp(), "deface.sdfont")
    hd_font.build(src, dst)
    w, h, _, _, old, d0 = hd_font.read(src)
    nw, nh, _, _, new, d1 = hd_font.read(dst)
    by = {g[0]: g for g in new}
    for g in old:
        x0, y0, x1, y1 = hd_font.region(g, w, h)
        n = by[g[0]]
        assert n[1:5] == g[1:5] and n[9] == g[9], chr(g[0])
        assert (hd_font.region(n, nw, nh) == (x0, y0, x1, y1)
                and (d1[y0:y1, x0:x1] == d0[y0:y1, x0:x1]).all()), chr(g[0])
    for ch in {**cyrillic.CAPITALS, **cyrillic.LOWERCASE}:
        x0, y0, x1, y1 = hd_font.region(by[ord(ch)], nw, nh)
        assert 0 <= x0 < x1 <= nw and 0 <= y0 < y1 <= nh and (d1[y0:y1, x0:x1] > 127).any(), ch
    os.remove(dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "work"))
