"""Достаёт из ISO все STRG, FONT и TXTR шрифтов в work/res/<TYPE>/<id>.<TYPE>.

    python -I tools/extract.py "Metroid Prime (USA).iso" work

Пишет work/inventory.tsv: type, id, pak, имя из таблицы имён PAK, размер,
и work/scans.tsv: SCAN id, STRG id, категория логбука (0 нет, 1 пираты,
2 Чозо, 3 существа, 4 исследования), важность — для контекста перевода.
Один и тот же ресурс лежит в нескольких PAK; файл пишется один раз, а
расхождение содержимого между PAK — ошибка (тогда подмена по id неоднозначна).
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mp  # noqa: E402

KEEP = {"STRG", "FONT"}


def main(iso_path, out):
    seen = {}      # (type, id) -> bytes
    rows = []
    font_textures = set()
    textures = {}  # id -> bytes (все TXTR, нужные отберём после)
    scans = {}
    with open(iso_path, "rb") as iso:
        for name, off, size in mp.disc_files(iso):
            if not name.lower().endswith(".pak"):
                continue
            iso.seek(off)
            pak = iso.read(size)
            names = mp.pak_names(pak)
            for rtype, rid, data in mp.pak_resources(pak):
                if rtype == "SCAN":
                    # CScannableObjectInfo: version, magic, frame, string, speed, category, important
                    strg_id, category = struct.unpack_from(">I4xI", data, 12)
                    important = data[24] if struct.unpack_from(">I", data)[0] > 4 else 0
                    scans[rid] = (strg_id, category, important)
                    continue
                if rtype == "TXTR":
                    textures.setdefault(rid, data)
                    continue
                if rtype not in KEEP:
                    continue
                key = (rtype, rid)
                if key in seen and seen[key] != data:
                    sys.exit(f"{rtype} {rid:08X} differs between PAKs ({name})")
                seen.setdefault(key, data)
                rows.append((rtype, f"{rid:08X}", name, names.get(rid, ""), str(len(data))))
                if rtype == "FONT":
                    font_textures.add(font_texture_id(data))
    for tid in font_textures:
        seen[("TXTR", tid)] = textures[tid]
        rows.append(("TXTR", f"{tid:08X}", "", "font atlas", str(len(textures[tid]))))
    for (rtype, rid), data in seen.items():
        d = os.path.join(out, "res", rtype)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{rid:08X}.{rtype}"), "wb") as f:
            f.write(data)
    with open(os.path.join(out, "inventory.tsv"), "w") as f:
        f.write("type\tid\tpak\tname\tsize\n")
        for r in sorted(rows):
            f.write("\t".join(r) + "\n")
    with open(os.path.join(out, "scans.tsv"), "w") as f:
        f.write("scan\tstrg\tcategory\timportant\n")
        for rid, (sid, cat, imp) in sorted(scans.items()):
            f.write(f"{rid:08X}\t{sid:08X}\t{cat}\t{imp}\n")
    counts = {"SCAN": len(scans)}
    for rtype, _ in seen:
        counts[rtype] = counts.get(rtype, 0) + 1
    print(" ".join(f"{k}={v}" for k, v in sorted(counts.items())))


def font_texture_id(data):
    """Id атласа из заголовка FONT (CRasterFont: после имени шрифта)."""
    version = struct.unpack_from(">I", data, 4)[0]
    pos = 16 + (4 if version >= 1 else 0) + (4 if version >= 2 else 0)
    pos += 2 + 8  # fInfoA, fInfoB, fInfoC, fontSize
    end = data.index(b"\0", pos)
    return struct.unpack_from(">I", data, end + 1)[0]


if __name__ == "__main__":
    main(*sys.argv[1:3])
