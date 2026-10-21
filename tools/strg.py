"""STRG Metroid Prime 1 (версия 0): чтение и запись.

Формат (src/Kyoto/Text/CStringTable.cpp декомпиляции), big endian:
    u32 0x87654321, u32 version (0), u32 langCount, u32 strCount
    langCount x { char[4] language, u32 offset }   offset от конца этой таблицы
    секция: u32 size, u32[strCount] смещений строк от начала секции,
            строки UTF-16BE с нулём в конце
Файл добит 0xFF до кратного 32 размера.
"""

import struct

MAGIC = 0x87654321


def parse(data):
    """[(language, [строки])] в порядке таблицы языков."""
    magic, version, lang_count, str_count = struct.unpack_from(">4I", data)
    if magic != MAGIC or version != 0:
        raise ValueError(f"not a v0 STRG: {magic:08X} v{version}")
    base = 16 + 8 * lang_count
    out = []
    for i in range(lang_count):
        lang, off = struct.unpack_from(">4sI", data, 16 + 8 * i)
        size = struct.unpack_from(">I", data, base + off)[0]
        sec = data[base + off + 4:base + off + 4 + size]
        strings = []
        for o in struct.unpack_from(f">{str_count}I", sec):
            end = o
            while sec[end:end + 2] != b"\0\0":
                end += 2
            strings.append(sec[o:end].decode("utf-16-be"))
        out.append((lang.decode("ascii"), strings))
    return out


def build(sections):
    """Обратное к parse: секции подряд в порядке списка, добивка 0xFF до 32."""
    str_count = len(sections[0][1])
    blobs = []
    for lang, strings in sections:
        if len(strings) != str_count:
            raise ValueError(f"{lang}: {len(strings)} strings, expected {str_count}")
        encoded = [s.encode("utf-16-be") + b"\0\0" for s in strings]
        offsets, pos = [], 4 * str_count
        for e in encoded:
            offsets.append(pos)
            pos += len(e)
        sec = struct.pack(f">{str_count}I", *offsets) + b"".join(encoded)
        blobs.append(struct.pack(">I", len(sec)) + sec)
    out = bytearray(struct.pack(">4I", MAGIC, 0, len(sections), str_count))
    off = 0
    for (lang, _), blob in zip(sections, blobs):
        out += struct.pack(">4sI", lang.encode("ascii"), off)
        off += len(blob)
    for blob in blobs:
        out += blob
    out += b"\xff" * (-len(out) % 32)
    return bytes(out)


def replace_language(data, language, strings):
    """Таблица `data` с секцией `language`, замененной на `strings`; прочие секции как есть."""
    sections = parse(data)
    for i, (lang, _) in enumerate(sections):
        if lang == language:
            sections[i] = (lang, list(strings))
            return build(sections)
    raise KeyError(f"no {language} section")
