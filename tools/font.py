"""FONT (v2) и атлас TXTR формата C4 Metroid Prime 1: чтение и запись.

FONT (src/Kyoto/Text/CRasterFont.cpp), big endian:
    "FONT", u32 version (2), i32 monoW, monoH, baseline, lineMargin,
    u8 infoA, u8 infoB, i32 infoC, i32 fontSize, char[] name (с нулём),
    u32 textureId, i32 mode (0 заливка, 1 заливка+контур), u32 glyphCount,
    glyphCount x { u16 char, f32 u0, v0, u1, v1, i32 a, b, c, cellW, cellH, baseline, kernStart },
    u32 kernCount, kernCount x { u16 first, u16 second, i32 amount }
Глифы идут по возрастанию char (игра всё равно сортирует).
Advance глифа = a + b + c; b — ширина ячейки с чернилами, a/c — отступы.

TXTR: u32 format (4 = C4), u16 w, h, u32 mips; палитра u32 format, u16 w, h,
w*h x u16; затем пиксели C4 тайлами 8x8 (4 бита, старший полубайт левее).
В атласах шрифтов: 0 — фон, 1 — заливка, 2 — контур.
"""

import struct
from dataclasses import dataclass, field

GLYPH = struct.Struct(">H4f7i")


@dataclass
class Glyph:
    char: int
    u0: float
    v0: float
    u1: float
    v1: float
    a: int
    b: int
    c: int
    cell_w: int
    cell_h: int
    baseline: int
    kern_start: int


@dataclass
class Font:
    version: int
    mono_w: int
    mono_h: int
    baseline: int
    line_margin: int
    info_a: int
    info_b: int
    info_c: int
    font_size: int
    name: str
    texture_id: int
    mode: int
    glyphs: list = field(default_factory=list)
    kerning: list = field(default_factory=list)  # (first, second, amount)
    tail: bytes = b""  # добивка файла


def parse_font(data):
    if data[:4] != b"FONT":
        raise ValueError("not a FONT")
    version, mono_w, mono_h, baseline, margin = struct.unpack_from(">I4i", data, 4)
    if version != 2:
        raise ValueError(f"FONT v{version}, only v2 handled")
    info_a, info_b, info_c, size = struct.unpack_from(">BBii", data, 24)
    end = data.index(b"\0", 34)
    name = data[34:end].decode("ascii")
    pos = end + 1
    tex, mode, count = struct.unpack_from(">IiI", data, pos)
    pos += 12
    glyphs = []
    for _ in range(count):
        glyphs.append(Glyph(*GLYPH.unpack_from(data, pos)))
        pos += GLYPH.size
    kcount = struct.unpack_from(">I", data, pos)[0]
    pos += 4
    kerning = [struct.unpack_from(">HHi", data, pos + 8 * i) for i in range(kcount)]
    pos += 8 * kcount
    return Font(version, mono_w, mono_h, baseline, margin, info_a, info_b, info_c, size, name,
                tex, mode, glyphs, kerning, data[pos:])


def build_font(f):
    out = bytearray(b"FONT")
    out += struct.pack(">I4i", f.version, f.mono_w, f.mono_h, f.baseline, f.line_margin)
    out += struct.pack(">BBii", f.info_a, f.info_b, f.info_c, f.font_size)
    out += f.name.encode("ascii") + b"\0"
    out += struct.pack(">IiI", f.texture_id, f.mode, len(f.glyphs))
    for g in sorted(f.glyphs, key=lambda g: g.char):
        out += GLYPH.pack(g.char, g.u0, g.v0, g.u1, g.v1, g.a, g.b, g.c, g.cell_w, g.cell_h,
                          g.baseline, g.kern_start)
    out += struct.pack(">I", len(f.kerning))
    for k in f.kerning:
        out += struct.pack(">HHi", *k)
    out += f.tail
    return bytes(out)


@dataclass
class Atlas:
    width: int
    height: int
    palette_format: int
    palette: list          # 16 x u16
    pixels: bytearray      # width*height индексов 0..15, построчно
    tail: bytes = b""


def parse_txtr(data):
    fmt, w, h, mips = struct.unpack_from(">IHHI", data)
    if fmt != 4 or mips != 1:
        raise ValueError(f"TXTR format {fmt} mips {mips}, only C4 single level handled")
    pf, pw, ph = struct.unpack_from(">IHH", data, 12)
    palette = list(struct.unpack_from(f">{pw * ph}H", data, 20))
    pos = 20 + 2 * pw * ph
    raw = data[pos:pos + w * h // 2]
    pixels = bytearray(w * h)
    i = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for y in range(8):
                row = (ty + y) * w + tx
                for x in range(0, 8, 2):
                    b = raw[i]
                    i += 1
                    pixels[row + x] = b >> 4
                    pixels[row + x + 1] = b & 15
    return Atlas(w, h, pf, palette, pixels, data[pos + w * h // 2:])


def build_txtr(a):
    if a.width % 8 or a.height % 8:
        raise ValueError("C4 atlas must be a multiple of 8 on each side")
    out = bytearray(struct.pack(">IHHI", 4, a.width, a.height, 1))
    out += struct.pack(">IHH", a.palette_format, 1, len(a.palette))
    out += struct.pack(f">{len(a.palette)}H", *a.palette)
    w = a.width
    for ty in range(0, a.height, 8):
        for tx in range(0, w, 8):
            for y in range(8):
                row = (ty + y) * w + tx
                for x in range(0, 8, 2):
                    out.append(a.pixels[row + x] << 4 | a.pixels[row + x + 1])
    out += a.tail
    return bytes(out)


def cell_rect(g, atlas):
    """Пиксельная ячейка глифа (x, y, w, h). UV на диске выступают на полпикселя
    за ячейку с каждой стороны: u0 = (x - 0.5) / W, u1 = (x + cell_w + 0.5) / W."""
    return round(g.u0 * atlas.width + 0.5), round(g.v0 * atlas.height + 0.5), g.cell_w, g.cell_h


def set_cell_uv(g, atlas, x, y):
    """UV глифа для ячейки в (x, y), по той же схеме, что на диске."""
    g.u0 = (x - 0.5) / atlas.width
    g.u1 = (x + g.cell_w + 0.5) / atlas.width
    g.v0 = (y - 0.5) / atlas.height
    g.v1 = (y + g.cell_h + 0.5) / atlas.height
