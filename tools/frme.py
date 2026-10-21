"""Текстовые поля (TXPN) из кадров интерфейса FRME: имя, шрифт, перенос, область вёрстки.

    python -I tools/frme.py work/res        # таблица всех полей

Формат виджета TXPN (src/GuiSys/CGuiTextPane.cpp, CGuiWidget::ReadWidgetHeader), big endian:
    char[4] "TXPN", заголовок: name\\0, parent\\0, 4 x u8 (anim, vis, active, cull), f32[4] цвет, u32 флаги;
    f32 dimX, dimY, f32[3] vec, u32 fontId, u8 wordWrap, u8 horizontal, u32 just, u32 vjust,
    f32[4] цвет, f32[4] цвет контура, f32 extentX, f32 extentY.
extentX/extentY — область вёрстки текста в пикселях шрифта: по ней игра переносит строки.
Дальше ParseBaseInfo (CGuiWidget.cpp): u8 isWorker, [i16 workerId], f32[3] перенос, f32[9] поворот, …
Текст рисуется с масштабом dimX / extentX мировых единиц на пиксель шрифта (CGuiTextPane::Draw),
от левого края поля (перенос + pivot - dimX/2), с выравниванием just: 0 влево, 1 по центру, 2 вправо.
Виджеты других типов не разбираются: TXPN ищется по метке типа и проверяется на правдоподобие.
"""

import glob
import os
import struct
import sys


def cstr(data, pos):
    end = data.index(b"\0", pos)
    return data[pos:end].decode("ascii"), end + 1


def text_panes(data, full=False):
    """[(name, fontId, wordWrap, just, extentX, extentY)] для всех TXPN кадра;
    full=True добавляет (parent, dimX, dimY, pivotX, pivotZ, повёрнуто ли)."""
    out = []
    pos = 0
    while True:
        pos = data.find(b"TXPN", pos)
        if pos < 0:
            return out
        try:
            name, p = cstr(data, pos + 4)
            parent, p = cstr(data, p)
            if not name.isprintable() or not name:
                raise ValueError
            p += 4 + 16 + 4            # bools, цвет, флаги
            dim_x, dim_y, piv_x, _, piv_z = struct.unpack_from(">5f", data, p)
            p += 8 + 12                # dimX, dimY, vec
            font, wrap, horiz, just, vjust = struct.unpack_from(">IBBII", data, p)
            p += 14 + 32               # шрифт…vjust, два цвета
            ex, ey = struct.unpack_from(">ff", data, p)
            p += 8
            if 0 < ex < 4096 and 0 < ey < 4096:
                row = (name, font, bool(wrap), just, int(ex), int(ey))
                if full:
                    worker = data[p]
                    p += 1 + (2 if worker else 0)
                    tx, ty, tz = struct.unpack_from(">fff", data, p)
                    rot = struct.unpack_from(">9f", data, p + 12)
                    turned = any(abs(v - (1.0 if i in (0, 4, 8) else 0.0)) > 1e-3 for i, v in enumerate(rot))
                    row += (parent, dim_x, dim_y, piv_x, piv_z, turned)
                out.append(row)
        except (ValueError, struct.error):
            pass
        pos += 4


def all_panes(res, full=False):
    """{(frameId, name): (fontId, wrap, just, extentX, extentY[, parent, dimX, dimY, x, z, turned])}."""
    panes = {}
    for path in sorted(glob.glob(os.path.join(res, "FRME", "*.FRME"))):
        fid = os.path.basename(path)[:8]
        for row in text_panes(open(path, "rb").read(), full):
            name, font = row[0], row[1]
            panes[(fid, name)] = (f"{font:08X}",) + row[2:]
    return panes


if __name__ == "__main__":
    for (fid, name), (font, wrap, just, ex, ey) in sorted(all_panes(sys.argv[1]).items()):
        print(f"{fid}\t{name}\t{font}\twrap={int(wrap)}\tjust={just}\t{ex}x{ey}")


TYPES = {b"HWIG", b"BWIG", b"CAMR", b"GRUP", b"MODL", b"SLGP", b"TBGP", b"PANE", b"TXPN", b"LITE",
         b"ENRG", b"METR", b"IMGP"}


def widget_starts(data):
    """[(offset, type, name, parent)] всех виджетов кадра по порядку (CGuiFrame::LoadWidgetsInGame)."""
    out = []
    pos = 20  # version, a, b, c, count
    count = struct.unpack_from(">I", data, 16)[0]
    while len(out) < count:
        if data[pos:pos + 4] in TYPES:
            try:
                name, p = cstr(data, pos + 4)
                parent, _ = cstr(data, p)
                if name and name.isprintable() and parent.isprintable():
                    out.append((pos, data[pos:pos + 4].decode(), name, parent))
                    pos = p
                    continue
            except ValueError:
                pass
        pos += 1
        if pos >= len(data):
            raise ValueError(f"нашлось {len(out)} виджетов из {count}")
    return out


def mat_mul(a, b):
    """3x4 (поворот 3x3 + перенос) a * b."""
    r = [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    t = [sum(a[i][k] * b[k][3] for k in range(3)) + a[i][3] for i in range(3)]
    return [r[i] + [t[i]] for i in range(3)]


def world_transforms(data):
    """{имя виджета: мировая матрица 3x4}. Хвост каждого виджета — ParseBaseInfo
    (u8 isWorker, [i16], f32[3] перенос, f32[9] поворот по строкам, f32[3], u32, i16),
    он кончается там, где начинается следующий виджет; конец файла добит 0xFF."""
    starts = widget_starts(data)
    end_file = len(data.rstrip(b"\xff"))
    local, parent_of = {}, {}
    for i, (pos, typ, name, parent) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else end_file
        tail = 1 + 12 + 36 + 12 + 4 + 2
        if data[end - tail] == 0:
            base = end - tail + 1
        elif data[end - tail - 2] == 1:
            base = end - tail - 2 + 3
        else:
            raise ValueError(f"{name}: хвост ParseBaseInfo не найден")
        t = struct.unpack_from(">3f", data, base)
        m = struct.unpack_from(">9f", data, base + 12)
        local[name] = [[m[0], m[1], m[2], t[0]], [m[3], m[4], m[5], t[1]], [m[6], m[7], m[8], t[2]]]
        parent_of[name] = parent
    world = {}

    def resolve(name, depth=0):
        if name in world:
            return world[name]
        if name not in local or depth > 64:
            return [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]
        w = mat_mul(resolve(parent_of[name], depth + 1), local[name])
        world[name] = w
        return w

    for name in local:
        resolve(name)
    return world


def apply(m, x, z):
    """Точка (x, 0, z) локальной системы виджета -> мировые (x, z)."""
    return (m[0][0] * x + m[0][2] * z + m[0][3], m[2][0] * x + m[2][2] * z + m[2][3])


def text_box(world, pane, text_px, lines=1, line_px=0):
    """Мировой прямоугольник (x0, x1, z0, z1), который займёт текст шириной text_px пикселей шрифта.
    pane — значение all_panes(full=True). По вертикали — высота поля, а если строк больше одной —
    lines * line_px пикселей, по центру поля (так ведёт себя рамка босса: две строки ушли вверх и вниз)."""
    _, _, just, ex, ey, _, dim_x, dim_y, piv_x, piv_z, _ = pane
    sx = dim_x / ex
    w = text_px * sx
    left = piv_x - dim_x / 2
    x0 = {0: left, 1: piv_x - w / 2, 2: left + dim_x - w}[just]
    h = max(dim_y, lines * line_px * dim_y / ey) if lines > 1 else dim_y
    pts = [apply(world, x, z) for x in (x0, x0 + w) for z in (piv_z - h / 2, piv_z + h / 2)]
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), max(xs), min(zs), max(zs)
