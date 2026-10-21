"""Чтение диска GameCube и PAK Metroid Prime 1.

disc_files, pak_names и pak_resources взяты из tools/extract_textures.py
проекта Odrannnn/MetroidPrimePort (MIT, (c) 2026 Metroid Prime Port contributors).
"""

import struct
import zlib


def disc_files(iso):
    """(name, offset, size) for every file in a GameCube disc's FST."""
    iso.seek(0x424)
    fst_off, fst_size = struct.unpack(">II", iso.read(8))
    iso.seek(fst_off)
    fst = iso.read(fst_size)
    count = struct.unpack_from(">I", fst, 8)[0]
    names = fst[count * 12:]
    for i in range(1, count):
        word, off, size = struct.unpack_from(">III", fst, i * 12)
        if word >> 24:
            continue  # directory
        name_off = word & 0xFFFFFF
        name = names[name_off:names.index(b"\0", name_off)].decode("ascii", "replace")
        yield name, off, size


def pak_names(pak):
    """{id: name} from a Prime 1 PAK's named-resource table."""
    names = {}
    pos = 12
    for _ in range(struct.unpack_from(">I", pak, 8)[0]):
        rid, name_len = struct.unpack_from(">II", pak, pos + 4)
        names.setdefault(rid, pak[pos + 12:pos + 12 + name_len].decode("ascii", "replace"))
        pos += 12 + name_len
    return names


def pak_resources(pak):
    """(type, id, data) for every resource in a Prime 1 PAK."""
    named = struct.unpack_from(">I", pak, 8)[0]
    pos = 12
    for _ in range(named):
        name_len = struct.unpack_from(">I", pak, pos + 8)[0]
        pos += 12 + name_len
    count = struct.unpack_from(">I", pak, pos)[0]
    pos += 4
    for _ in range(count):
        compressed, rtype, rid, size, off = struct.unpack_from(">I4sIII", pak, pos)
        pos += 20
        data = pak[off:off + size]
        if compressed:
            data = zlib.decompress(data[4:])
        yield rtype.decode("ascii", "replace"), rid, data
