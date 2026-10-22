"""Собирает мод: text/ru.json + исходные STRG + шрифты с кириллицей -> mod/russian/.

    python -I tools/build_mod.py work/res text/ru.json mod/russian [--base DIR]

ru.json: { "<STRG id>": { "<index>": { "en": "<sha1 исходника, 8 hex>", "ru": "<перевод>" } } }
Русский пишется в секцию ENGL (ADR 0001). База таблиц — STRG диска (`work/res/STRG`), либо
`--base DIR` с уже изменёнными таблицами (Remastered `text/`, ADR 0004): из базы берутся все
прочие секции, а хеш сверяется с её ENGL.
Строка с устаревшим хешем не пишется (остаётся английской) и печатается: перевод надо обновить.
"""

import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cyrillic  # noqa: E402
import strg  # noqa: E402


def en_hash(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def patch_frames(res, out, panes_path="text/panes.json"):
    """Кадры FRME, где правило panes.json задаёт полю свой шрифт («font»): копия кадра диска
    со сменой fontId этого поля (frme.set_pane_font) кладётся в мод."""
    import csv
    import frme
    names = {r["name"]: r["id"] for r in csv.DictReader(open(os.path.join(os.path.dirname(res), "inventory.tsv")),
                                                         delimiter="\t") if r["type"] == "FRME" and r["name"]}
    patched = {}
    for name, r in json.load(open(panes_path, encoding="utf-8")).items():
        if name.startswith("_") or "font" not in r:
            continue
        for want in r["panes"]:
            frame, _, pane = want.rpartition("/")
            for fid, pname in frme.all_panes(res):
                if pname == pane and (not frame or names.get(frame) == fid):
                    data = patched.get(fid) or open(os.path.join(res, "FRME", f"{fid}.FRME"), "rb").read()
                    patched[fid] = frme.set_pane_font(data, pane, int(r["font"], 16))
    for fid, data in patched.items():
        open(os.path.join(out, f"{fid}.FRME"), "wb").write(data)
    return sorted(patched)


def pad_to_32(out):
    """Ресурсы мода — кратно 32 байтам, как в PAK диска. Порт 0.31.1 отдаёт ресурс, добавленный в
    NoARAM.pak, с размером, округлённым вниз до 32: хвост шрифта 52550001 терялся, следующий ресурс
    читался со сдвигом (вылет при загрузке мира). Нули в конце FONT/TXTR игра не читает."""
    for name in os.listdir(out):
        path = os.path.join(out, name)
        n = os.path.getsize(path)
        if n % 32:
            fill = b"\xff" if name.endswith(".STRG") else b"\x00"
            with open(path, "ab") as f:
                f.write(fill * (32 - n % 32))


def build(res, ru_path, out, base=None):
    ru = json.load(open(ru_path, encoding="utf-8"))
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    written = stale = 0
    for sid, entries in sorted(ru.items()):
        src = os.path.join(base, f"{sid}.STRG") if base else None
        if not src or not os.path.isfile(src):
            src = os.path.join(res, "STRG", f"{sid}.STRG")
        data = open(src, "rb").read()
        english = dict(strg.parse(data))["ENGL"]
        strings = list(english)
        for idx, e in entries.items():
            i = int(idx)
            if en_hash(english[i]) != e["en"]:
                print(f"stale {sid}:{i}: {english[i]!r}")
                stale += 1
                continue
            strings[i] = e["ru"]
            written += 1
        open(os.path.join(out, f"{sid}.STRG"), "wb").write(strg.replace_language(data, "ENGL", strings))
    cyrillic.main(res, out)
    patch_frames(res, out)
    pad_to_32(out)
    print(f"mod: {len(ru)} tables, {written} strings, {stale} stale -> {out}")
    return stale


if __name__ == "__main__":
    args = sys.argv[1:]
    base = None
    if "--base" in args:
        k = args.index("--base")
        base = args[k + 1]
        del args[k:k + 2]
    build(*args, base=base)
