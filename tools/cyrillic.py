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

class Metrics:
    """Мерки шрифта по его латинице: всё, что нужно, чтобы рисовать в стиле Deface."""

    def __init__(self, cells):
        self.cells = cells
        hm = self.mask("H")
        self.s = stem_width(hm)                        # толщина стема
        self.w = len(hm[0])                            # ширина заглавной
        self.h = len(hm)                               # высота заглавной
        full = [j for j, r in enumerate(hm) if all(r)]
        self.mid, self.t = full[0], len(full)          # средняя перекладина: начало, толщина
        self.xh = len(self.mask("n"))                  # x-высота
        self.desc = max(len(self.mask("p")) - self.xh, 2)  # выносной элемент вниз

    def mask(self, ch):
        if ch in self.overrides:
            return self.overrides[ch]
        return ink_mask(self.cells[ch])

    overrides = {}

    def lower(self):
        """Те же мерки на x-высоте: конструкторы заглавных рисуют строчные (Deface — капитель).
        Латинские образцы конструкторов заменяются строчными или сжатыми до x-высоты."""
        lo = _copy.copy(self)
        lo.h = self.xh
        lo.mid = (self.xh - self.t) // 2
        lo.overrides = {"U": self.mask("u"), "W": self.mask("w"), "C": self.mask("c"),
                        "O": self.mask("o"), "E": self.mask("e"),
                        "K": shrink_rows(self.mask("K"), self.xh)}
        return lo


class Drawn:
    """Маска заливки нарисованного глифа. `above`/`below` — строки над/под корпусом образца."""

    def __init__(self, mask, above=0, below=0):
        self.mask, self.above, self.below = mask, above, below


def canvas(w, h):
    return blank(w, h)


def chamfer(m, *corners):
    """Срезает внешние угловые пиксели (так скруглены замкнутые формы Deface): (x, y) пары."""
    for x, y in corners:
        if 0 <= y < len(m) and 0 <= x < len(m[0]):
            m[y][x] = False


def hjoin(*masks, gap=0):
    """Маски одной высоты рядом слева направо."""
    h = len(masks[0])
    out = [[] for _ in range(h)]
    for k, mk in enumerate(masks):
        for j in range(h):
            out[j] += ([False] * gap if k else []) + mk[j]
    return out


def overlay(a, b, dx):
    """b поверх a со сдвигом dx; ширина — объединение."""
    w = max(len(a[0]), dx + len(b[0]))
    out = [r + [False] * (w - len(r)) for r in a]
    for j, r in enumerate(b):
        for i, v in enumerate(r):
            out[j][dx + i] = out[j][dx + i] or v
    return out


def soft_box(m, x0, y0, x1, y1, s, t):
    """Прямоугольная рамка со скруглёнными внешними углами (как O в Deface)."""
    rect(m, x0, y0, x1, y0 + t)
    rect(m, x0, y1 - t, x1, y1)
    rect(m, x0, y0, x0 + s, y1)
    rect(m, x1 - s, y0, x1, y1)
    chamfer(m, (x0, y0), (x1 - 1, y0), (x0, y1 - 1), (x1 - 1, y1 - 1))


def soft_sign(P, w, h, mid):
    """Ь: стем, средняя перекладина, чаша справа снизу."""
    s, t = P.s, P.t
    m = canvas(w, h)
    rect(m, 0, 0, s, h)
    rect(m, 0, mid, w, mid + t)
    rect(m, w - s, mid, w, h)
    rect(m, 0, h - t, w, h)
    chamfer(m, (w - 1, mid), (w - 1, h - 1))
    return m


def stems_diag(P, w, h):
    """И: два стема и ступенчатая диагональ снизу слева вверх направо.
    Диагональ тоньше стема (s - 1, не меньше 2), иначе в узкой букве не остаётся просвета."""
    s = P.s
    d = max(s - 1, 2)
    m = canvas(w, h)
    rect(m, 0, 0, s, h)
    rect(m, w - s, 0, w, h)
    e = min(P.t, h // 4)  # концы диагонали отступают от краёв, как у X
    diagonal(m, s - 1, h - 1 - e, w - s - d + 1, e, d)
    return m


def tail(m, x0, x1, below):
    """Выносной хвост под базовой линией (Д, Ц, Щ)."""
    w = len(m[0])
    for _ in range(below):
        m.append([x0 <= i < x1 for i in range(w)])
    return m


def cap_Б(P):
    m = soft_sign(P, P.w, P.h, P.mid)
    rect(m, 0, 0, P.w, P.t)
    return Drawn(m)


def cap_Г(P):
    m = canvas(P.w, P.h)
    rect(m, 0, 0, P.s, P.h)
    rect(m, 0, 0, P.w, P.t)
    return Drawn(m)


def cap_Д(P):
    s, t, w, h = P.s, P.t, P.w + 2, P.h
    m = canvas(w, h)
    rect(m, 2, 0, w - s, t)
    rect(m, 2, 0, 2 + s, h)
    rect(m, w - s - 0, 0, w, h)
    rect(m, 0, h - t, w, h)
    chamfer(m, (2, 0))
    tail(m, 0, s - 1, P.desc)
    for row in m[h:]:
        for i in range(w - s + 1, w):
            row[i] = True
    return Drawn(m, below=P.desc)


def cap_Ж(P):
    k = P.mask("K")
    return Drawn(overlay([r[::-1] for r in k], k, len(k[0]) - P.s))


def cap_И(P):
    return Drawn(stems_diag(P, P.w + 2, P.h))


def cap_Й(P):
    w = P.w + 2
    m = stems_diag(P, w, P.h)
    above = P.t + 1
    breve = canvas(w, above)
    rect(breve, P.s, 0, w - P.s, above - 1)
    return Drawn(breve + m, above=above)


def cap_Л(P):
    """Л: левая нога со ступенькой — сверху сдвинута внутрь, внизу у края (иначе читается как П)."""
    s, t, w, h = P.s, P.t, P.w, P.h
    k = max(s // 2, 2)
    knee = h * 2 // 3
    m = canvas(w, h)
    rect(m, k, 0, w, t)
    rect(m, k, 0, k + s, knee)
    rect(m, 0, knee - 1, s, h)
    rect(m, w - s, 0, w, h)
    chamfer(m, (k, 0), (w - 1, 0))
    return Drawn(m)


def cap_У(P):
    s, t, w, h, mid = P.s, P.t, P.w, P.h, P.mid
    m = canvas(w, h)
    rect(m, 0, 0, s, mid + t)
    rect(m, w - s, 0, w, h)
    rect(m, 0, mid, w, mid + t)
    rect(m, 0, h - t, w, h)
    chamfer(m, (0, mid + t - 1), (w - 1, h - 1), (0, h - 1))
    return Drawn(m)


def cap_Ф(P):
    s, t, h = P.s, P.t, P.h
    w = P.w + 4
    m = canvas(w, h)
    soft_box(m, 0, 1, w, h - 1, s, t)
    c = (w - s) // 2
    rect(m, c, 0, c + s, h)
    return Drawn(m)


def cap_Ц(P, base=None):
    s, t, h = P.s, P.t, P.h
    body = base if base is not None else P.mask("U")
    w0 = len(body[0])
    m = [r + [False] * 2 for r in body]
    for j in range(h - t, h):
        for i in range(w0 - 1, w0 + 2):
            m[j][i] = True
    for j in range(h - t, h):  # угол без скругления: перекладина уходит в хвост
        m[j][w0 - 1] = True
    tail(m, w0, w0 + 2, P.desc)
    return Drawn(m, below=P.desc)


def cap_Щ(P):
    return cap_Ц(P, P.mask("W"))


def cap_Ъ(P):
    k = 2
    w = P.w + k
    m = canvas(w, P.h)
    sign = soft_sign(P, P.w, P.h, P.mid)
    m = overlay(m, sign, k)
    rect(m, 0, 0, k + P.s, P.t)
    return Drawn(m)


def cap_Ы(P):
    sign = soft_sign(P, P.w - 2, P.h, P.mid)
    stem = canvas(P.s, P.h)
    rect(stem, 0, 0, P.s, P.h)
    return Drawn(hjoin(sign, stem, gap=2))


def cap_Ь(P):
    return Drawn(soft_sign(P, P.w, P.h, P.mid))


def cap_Э(P):
    m = [r[::-1] for r in P.mask("C")]
    w = len(m[0])
    rect(m, w // 3, P.mid, w, P.mid + P.t)
    return Drawn(m)


def cap_Ю(P):
    o = P.mask("O")
    stem = canvas(P.s + 2, P.h)
    rect(stem, 0, 0, P.s, P.h)
    rect(stem, P.s, P.mid, P.s + 2, P.mid + P.t)
    return Drawn(hjoin(stem, o))


def cap_Ё(P):
    above = P.t + 1
    dots = canvas(P.w, above)
    d = max(P.s - 1, 2)
    rect(dots, 1, 0, 1 + d, above - 1)
    rect(dots, P.w - 1 - d, 0, P.w - 1, above - 1)
    return Drawn(dots + P.mask("E"), above=above)


# символ -> (образец метрик, способ)
CAPITALS = {
    "А": ("A", ("copy", "A")), "В": ("B", ("copy", "B")), "Е": ("E", ("copy", "E")),
    "К": ("K", ("copy", "K")), "М": ("M", ("copy", "M")), "Н": ("H", ("copy", "H")),
    "О": ("O", ("copy", "O")), "Р": ("P", ("copy", "P")), "С": ("C", ("copy", "C")),
    "Т": ("T", ("copy", "T")), "Х": ("X", ("copy", "X")),
    "П": ("N", ("copy", "N")), "Ш": ("W", ("copy", "W")), "З": ("3", ("copy", "3")),
    "Ч": ("4", ("copy", "4")), "Я": ("R", ("mirror", "R")),
    "Б": ("H", ("draw", cap_Б)), "Г": ("E", ("draw", cap_Г)), "Д": ("H", ("draw", cap_Д)),
    "Ж": ("K", ("draw", cap_Ж)), "И": ("H", ("draw", cap_И)), "Й": ("H", ("draw", cap_Й)),
    "Л": ("H", ("draw", cap_Л)), "У": ("H", ("draw", cap_У)), "Ф": ("H", ("draw", cap_Ф)),
    "Ц": ("U", ("draw", cap_Ц)), "Щ": ("W", ("draw", cap_Щ)), "Ъ": ("H", ("draw", cap_Ъ)),
    "Ы": ("H", ("draw", cap_Ы)), "Ь": ("H", ("draw", cap_Ь)), "Э": ("C", ("draw", cap_Э)),
    "Ю": ("H", ("draw", cap_Ю)), "Ё": ("E", ("draw", cap_Ё)),
}

def low(fn):
    """Конструктор заглавной, вызванный на x-высоте."""
    return lambda P: fn(P.lower())


def low_ф(P):
    """ф: стем от высоты заглавных до низа выносного, чаша на x-высоте."""
    lo = P.lower()
    up, s, t = P.h - P.xh, P.s, P.t
    w = P.w + 4
    bowl = canvas(w, P.xh)
    soft_box(bowl, 0, 0, w, P.xh, s, t)
    m = canvas(w, up) + bowl + canvas(w, P.desc)
    c = (w - s) // 2
    rect(m, c, 0, c + s, len(m))
    return Drawn(m, above=up, below=P.desc)


def low_б(P):
    """б: чаша строчной «о» внизу и флажок над ней — ступенчатая диагональ от верха чаши слева
    вверх направо, как у рукописной «б» (у «Б» верх плоский и во всю ширину, у латинской b флажка нет).
    Ступени по строке, шириной как штрих диагоналей Deface (Z)."""
    s, w, h, xh = P.s, P.w, P.h, P.xh
    m = canvas(w, h)
    asc = h - xh
    bowl = P.mask("o")
    for j, row in enumerate(bowl):
        for i, v in enumerate(row):
            if v and i < w:
                m[asc + j][i] = True
    seg = max(s + 1, w * 2 // 5)
    for j in range(asc):
        frac = (asc - 1 - j) / (asc - 1) if asc > 1 else 1.0
        x0 = round(frac * (w - seg))
        rect(m, x0, j, x0 + seg, j + 1)
    return Drawn(m)


def low_small(L):
    """Заглавная латинская L, сжатая до x-высоты."""
    return lambda P: Drawn(shrink_rows(P.mask(L), P.xh))


LOWERCASE = {
    "а": ("a", ("copy", "a")), "е": ("e", ("copy", "e")), "о": ("o", ("copy", "o")),
    "р": ("p", ("copy", "p")), "с": ("c", ("copy", "c")), "у": ("y", ("copy", "y")),
    "х": ("x", ("copy", "x")), "п": ("n", ("copy", "n")), "м": ("m", ("copy", "m")),
    "ш": ("w", ("copy", "w")), "г": ("r", ("copy", "r")), "б": ("6", ("draw", low_б)),
    "в": ("n", ("draw", low_small("B"))), "з": ("n", ("draw", low_small("3"))),
    "к": ("n", ("draw", low_small("K"))), "н": ("n", ("draw", low_small("H"))),
    "т": ("n", ("draw", low_small("T"))), "ч": ("n", ("draw", low_small("4"))),
    "я": ("n", ("small_mirror", "R")),
    "д": ("n", ("draw", low(cap_Д))), "ж": ("n", ("draw", low(cap_Ж))),
    "и": ("n", ("draw", low(cap_И))), "й": ("n", ("draw", low(cap_Й))),
    "л": ("n", ("draw", low(cap_Л))), "ф": ("n", ("draw", low_ф)),
    "ц": ("u", ("draw", low(cap_Ц))), "щ": ("w", ("draw", low(cap_Щ))),
    "ъ": ("n", ("draw", low(cap_Ъ))), "ы": ("n", ("draw", low(cap_Ы))),
    "ь": ("n", ("draw", low(cap_Ь))), "э": ("c", ("draw", low(cap_Э))),
    "ю": ("n", ("draw", low(cap_Ю))), "ё": ("e", ("draw", low(cap_Ё))),
}


def chevron(h, d, left=True):
    """Уголок высотой h (нечётная), штрих d по горизонтали."""
    half = h // 2
    w = half + d
    m = canvas(w, h)
    for j in range(h):
        x = abs(half - j)
        if not left:
            x = half - x
        rect(m, x, j, x + d, j + 1)
    return m


def quote(P, left):
    """« »: два уголка по центру x-высоты, ячейка образца 'n' (x-высота)."""
    hc = P.xh * 2 // 3 | 1
    d = max(P.s // 2 + 1, 2)
    one = chevron(hc, d, left)
    pair = hjoin(one, one, gap=1)
    top = (P.xh - hc) // 2
    m = canvas(len(pair[0]), top) + pair + canvas(len(pair[0]), P.xh - top - hc)
    return Drawn(m)


def dash(P):
    """—: дефис шрифта, растянутый до ширины заглавной + 4."""
    hy = P.mask("-")
    w = P.w + 4
    return Drawn([[v for v in [r[0]] * w] for r in hy])


def ellipsis(P):
    dot = P.mask(".")
    return Drawn(hjoin(dot, dot, dot, gap=max(P.s // 2, 1)))


def degree(P):
    """°: кольцо со скруглёнными углами (как O) у верха заглавной, ячейка образца 'H'."""
    d = max(3 * P.s + 1, P.h * 2 // 5)  # дырка не уже стема, иначе на мелких кеглях кольцо — точка
    m = canvas(d, P.h)
    soft_box(m, 0, 0, d, d, P.s, P.s)
    return Drawn(m)


PUNCTUATION = {
    "°": ("H", ("draw", degree)),
    "«": ("n", ("draw", lambda P: quote(P, True))),
    "»": ("n", ("draw", lambda P: quote(P, False))),
    "—": ("-", ("draw", dash)),
    "…": (".", ("draw", ellipsis)),
}

RECIPES = {**CAPITALS, **LOWERCASE, **PUNCTUATION}


# --- сборка --------------------------------------------------------------

def place(drawn, ref, ref_cell, outlined):
    """Глиф и ячейка: маска на месте заливки образца, поля ячейки как у образца;
    ширина и высота растут по маске, advance (b) — на прирост ширины, baseline — на `above`."""
    rh, rw = len(ref_cell), len(ref_cell[0])
    x0, y0, x1, y1 = ink_box(ref_cell)
    mask = drawn.mask
    mh, mw = len(mask), len(mask[0])
    if mh != (y1 - y0) + drawn.above + drawn.below:
        raise ValueError(f"mask height {mh} != ref ink {y1 - y0} + {drawn.above} + {drawn.below}")
    w = x0 + mw + (rw - x1)
    h = y0 + mh + (rh - y1)
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
    g = _copy.copy(ref)
    g.b = ref.b + mw - (x1 - x0)
    g.baseline = ref.baseline + drawn.above
    return g, cell


def build_glyph(ch, recipe, glyphs, cells, outlined, P):
    ref_ch, (how, arg) = recipe
    ref, ref_cell = glyphs[ref_ch], cells[ref_ch]
    if how == "copy":
        return glyphs[arg], [list(r) for r in cells[arg]]
    rx0, ry0, rx1, ry1 = ink_box(ref_cell)
    if how == "mirror":
        drawn = Drawn([r[::-1] for r in P.mask(arg)])
    elif how in ("small", "small_mirror"):
        mask = shrink_rows(P.mask(arg), ry1 - ry0)
        drawn = Drawn([r[::-1] for r in mask] if how == "small_mirror" else mask)
    elif how == "draw_x":
        drawn = Drawn(stems_diag(P, rx1 - rx0, ry1 - ry0))
    elif how == "draw":
        drawn = arg(P)
    else:
        raise ValueError(how)
    return place(drawn, ref, ref_cell, outlined)


def add_glyphs(f, a, recipes):
    """Новые глифы в шрифт `f` и атлас `a`: ячейки дописываются полками ниже атласа,
    с зазором в 1 пиксель (UV выступают на полпикселя). Латинские пиксели не меняются."""
    glyphs = {chr(g.char): g for g in f.glyphs}
    cells = {ch: cell_pixels(a, g) for ch, g in glyphs.items()}
    outlined = f.mode == 1
    P = Metrics(cells)
    new = []
    for ch, recipe in recipes.items():
        if ch in glyphs:
            raise ValueError(f"{f.name} already has {ch!r}")
        ref, cell = build_glyph(ch, recipe, glyphs, cells, outlined, P)
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


NARROW_FONT, NARROW_TXTR = 0x52550001, 0x52550002  # нет ни в одном PAK диска (проверено по всем id)
NARROW_BASE = "B5BC844E"


def narrow_cell(cell):
    """Ячейка на 1 колонку уже: из самой длинной серии одинаковых соседних колонок внутри буквы
    (не крайних) убирается одна — сужаются просветы и перекладины, стемы остаются прежними.
    None, если таких колонок нет."""
    w = len(cell[0])
    cols = [tuple(row[i] for row in cell) for i in range(w)]
    best, start = 1, None
    i = 1
    while i < w - 1:
        k = i
        while k + 1 < w - 1 and cols[k + 1] == cols[i]:
            k += 1
        if k - i + 1 > best:
            best, start = k - i + 1, i
        i = k + 1
    if start is None:
        return None
    drop = start + best // 2
    return [row[:drop] + row[drop + 1:] for row in cell]


def narrow_font(f, a):
    """Сжатая копия шрифта `f` с атласом `a` (новые id): каждый глиф по возможности на 1 px уже,
    advance уменьшается на столько же. Атлас собирается заново полками, высота — степень двойки."""
    f2 = _copy.deepcopy(f)
    f2.name = f.name + "_Narrow"
    f2.texture_id = NARROW_TXTR
    cells = []
    for g in f2.glyphs:
        cell = cell_pixels(a, g)
        if g.cell_w > 2:
            n = narrow_cell(cell)
            if n is not None:
                cell = n
                g.b -= 1
        cells.append(cell)
    gap, x, y, shelf, spots = 1, 1, 1, 0, []
    for cell in cells:
        h, w = len(cell), len(cell[0])
        if x + w + gap > a.width:
            x, y, shelf = 1, y + shelf + gap, 0
        spots.append((x, y))
        x += w + gap
        shelf = max(shelf, h)
    height = 1 << (y + shelf + gap - 1).bit_length()
    a2 = font.Atlas(a.width, height, a.palette_format, list(a.palette), bytearray(a.width * height), a.tail)
    for g, cell, (x, y) in zip(f2.glyphs, cells, spots):
        for j, row in enumerate(cell):
            for i, v in enumerate(row):
                a2.pixels[(y + j) * a2.width + x + i] = v
        g.cell_w, g.cell_h = len(cell[0]), len(cell)
        font.set_cell_uv(g, a2, x, y)
    return f2, a2


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
        if fid == NARROW_BASE:
            f2, a2 = narrow_font(f, a)
            open(os.path.join(out, f"{NARROW_FONT:08X}.FONT"), "wb").write(font.build_font(f2))
            open(os.path.join(out, f"{NARROW_TXTR:08X}.TXTR"), "wb").write(font.build_txtr(a2))
            print(f"{NARROW_FONT:08X} {f2.name}: узкая копия, atlas {a2.width}x{a2.height}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
