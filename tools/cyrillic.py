"""Кириллица для растровых шрифтов Deface (ADR 0002): новые глифы из латинских ячеек того же шрифта.

    python -I tools/cyrillic.py work/res out_dir
Пишет out_dir/<id>.FONT и out_dir/<id>.TXTR для каждого шрифта из FONTS.

Глиф строится из маски заливки (bool-строки) и латинского «образца», от которого берутся
метрики (a, b, c, высота ячейки, baseline) и место заливки в ячейке:
- copy(L)        — ячейка латинской буквы L как есть;
- mirror(L)      — зеркальная по горизонтали заливка L;
- small(L, ref)  — заглавная L, сжатая до высоты заливки строчной ref удалением повторяющихся
                   строк (прямые участки укорачиваются, толщина штрихов сохраняется);
- функция        — рисование штрихами в рамке заливки образца.
Контурный шрифт (mode 1): контур = 8-связная дилатация заливки (так устроена латиница диска).
"""

import copy as _copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font  # noqa: E402

FONTS = ["B5BC844E", "C29C51F1", "192BB274", "B7BBD0B4", "FE94BD23"]
INK, OUTLINE = 1, 2


# --- маски ---------------------------------------------------------------

def cell_pixels(a, g):
    x, y, w, h = font.cell_rect(g, a)
    return [[a.pixels[(y + j) * a.width + x + i] for i in range(w)] for j in range(h)]


def ink_box(cell):
    """(x0, y0, x1, y1) заливки в ячейке, x1/y1 не включительно."""
    ys = [j for j, r in enumerate(cell) if INK in r]
    xs = [i for i in range(len(cell[0])) if any(r[i] == INK for r in cell)]
    return xs[0], ys[0], xs[-1] + 1, ys[-1] + 1


def ink_mask(cell):
    x0, y0, x1, y1 = ink_box(cell)
    return [[cell[j][i] == INK for i in range(x0, x1)] for j in range(y0, y1)]


def shrink_rows(mask, height):
    """Удаляет строки из середины самых длинных серий одинаковых строк, пока не станет `height`."""
    m = [list(r) for r in mask]
    while len(m) > height:
        best, start = 1, None
        j = 0
        while j < len(m):
            k = j
            while k + 1 < len(m) and m[k + 1] == m[j]:
                k += 1
            if k - j + 1 > best:
                best, start = k - j + 1, j
            j = k + 1
        if start is None:
            raise ValueError("nothing left to shrink")
        del m[start + best // 2]
    return m


def stem_width(mask):
    """Толщина вертикального штриха: первая серия заливки на четверти высоты (середина у H — перекладина)."""
    row = mask[len(mask) // 4]
    i = row.index(True)
    n = 0
    while i + n < len(row) and row[i + n]:
        n += 1
    return n


def blank(w, h):
    return [[False] * w for _ in range(h)]


def rect(m, x0, y0, x1, y1):
    for j in range(max(y0, 0), min(y1, len(m))):
        for i in range(max(x0, 0), min(x1, len(m[0]))):
            m[j][i] = True


def diagonal(m, x0, y0, x1, y1, thick):
    """Ступенчатая диагональ от (x0, y0) к (x1, y1) (пиксели, включительно), шириной `thick` по x."""
    steps = max(abs(y1 - y0), 1)
    for s in range(steps + 1):
        y = y0 + (y1 - y0) * s // steps
        x = x0 + round((x1 - x0) * s / steps)
        rect(m, x, y, x + thick, y + 1)


# --- рецепты -------------------------------------------------------------

def draw_i(w, h, s):
    """и: два стема и диагональ снизу слева вверх направо."""
    m = blank(w, h)
    rect(m, 0, 0, s, h)
    rect(m, w - s, 0, w, h)
    diagonal(m, s, h - 1 - s // 2, w - 2 * s, s // 2, s)
    return m


# символ -> (образец метрик, способ)
RECIPES = {
    "Н": ("H", ("copy", "H")),
    "о": ("o", ("copy", "o")),
    "а": ("a", ("copy", "a")),
    "р": ("p", ("copy", "p")),
    "г": ("r", ("copy", "r")),
    "в": ("n", ("small", "B")),
    "я": ("n", ("small_mirror", "R")),
    "и": ("n", ("draw", draw_i)),
}


# --- сборка --------------------------------------------------------------

def place(mask, ref_cell, outlined):
    """Ячейка размера образца с маской на месте его заливки; контур для контурного шрифта."""
    h, w = len(ref_cell), len(ref_cell[0])
    x0, y0, x1, y1 = ink_box(ref_cell)
    if (x1 - x0, y1 - y0) != (len(mask[0]), len(mask)):
        raise ValueError(f"mask {len(mask[0])}x{len(mask)} != ref ink {x1 - x0}x{y1 - y0}")
    cell = [[0] * w for _ in range(h)]
    for j, row in enumerate(mask):
        for i, v in enumerate(row):
            if v:
                cell[y0 + j][x0 + i] = INK
    if outlined:
        for j in range(h):
            for i in range(w):
                if cell[j][i] != INK and any(
                        0 <= j + dj < h and 0 <= i + di < w and cell[j + dj][i + di] == INK
                        for dj in (-1, 0, 1) for di in (-1, 0, 1)):
                    cell[j][i] = OUTLINE
    return cell


def build_glyph(ch, recipe, glyphs, cells, outlined):
    ref_ch, (how, arg) = recipe
    ref = glyphs[ref_ch]
    ref_cell = cells[ref_ch]
    if how == "copy":
        return glyphs[arg], [list(r) for r in cells[arg]]
    rx0, ry0, rx1, ry1 = ink_box(ref_cell)
    w, h = rx1 - rx0, ry1 - ry0
    if how == "mirror":
        mask = [r[::-1] for r in ink_mask(cells[arg])]
    elif how in ("small", "small_mirror"):
        mask = shrink_rows(ink_mask(cells[arg]), h)
        if how == "small_mirror":
            mask = [r[::-1] for r in mask]
    elif how == "draw":
        mask = arg(w, h, stem_width(ink_mask(cells["H"])))
    else:
        raise ValueError(how)
    return ref, place(mask, ref_cell, outlined)


def add_glyphs(f, a, recipes):
    """Новые глифы в шрифт `f` и атлас `a`: ячейки дописываются полками ниже атласа,
    с зазором в 1 пиксель (UV выступают на полпикселя). Латинские пиксели не меняются."""
    glyphs = {chr(g.char): g for g in f.glyphs}
    cells = {ch: cell_pixels(a, g) for ch, g in glyphs.items()}
    outlined = f.mode == 1
    new = []
    for ch, recipe in recipes.items():
        if ch in glyphs:
            raise ValueError(f"{f.name} already has {ch!r}")
        ref, cell = build_glyph(ch, recipe, glyphs, cells, outlined)
        new.append((ch, ref, cell))
    # раскладка полками: строка высотой с самую высокую ячейку
    gap, x, y, shelf = 1, 1, a.height + 1, 0
    spots = []
    for ch, ref, cell in new:
        h, w = len(cell), len(cell[0])
        if x + w + gap > a.width:
            x, y, shelf = 1, y + shelf + gap, 0
        spots.append((x, y))
        x += w + gap
        shelf = max(shelf, h)
    # Высота — степень двойки: порт сам наращивает атлас Deface под свои stand-in'ы
    # (PortAddAccents) и рассчитан на POT-вход.
    new_h = 1 << (y + shelf + gap - 1).bit_length()
    old_h = a.height
    a.pixels += bytearray(a.width * (new_h - old_h))
    a.height = new_h
    for g in f.glyphs:  # старые UV под новую высоту, пиксели те же
        g.v0 = g.v0 * old_h / new_h
        g.v1 = g.v1 * old_h / new_h
    for (ch, ref, cell), (x, y) in zip(new, spots):
        for j, row in enumerate(cell):
            for i, v in enumerate(row):
                a.pixels[(y + j) * a.width + x + i] = v
        g = _copy.copy(ref)
        g.char = ord(ch)
        g.cell_w, g.cell_h = len(cell[0]), len(cell)
        # Своих пар кернинга нет: kern_start = число пар, как у глифов диска без пар
        # (KernLookup индексирует таблицу с kern_start без проверки границ).
        g.kern_start = len(f.kerning)
        font.set_cell_uv(g, a, x, y)
        f.glyphs.append(g)
    f.glyphs.sort(key=lambda g: g.char)


def main(res, out):
    os.makedirs(out, exist_ok=True)
    for fid in FONTS:
        f = font.parse_font(open(os.path.join(res, "FONT", f"{fid}.FONT"), "rb").read())
        tpath = os.path.join(res, "TXTR", f"{f.texture_id:08X}.TXTR")
        a = font.parse_txtr(open(tpath, "rb").read())
        add_glyphs(f, a, RECIPES)
        open(os.path.join(out, f"{fid}.FONT"), "wb").write(font.build_font(f))
        open(os.path.join(out, f"{f.texture_id:08X}.TXTR"), "wb").write(font.build_txtr(a))
        print(f"{fid} {f.name}: +{len(RECIPES)} glyphs, atlas {a.width}x{a.height}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
