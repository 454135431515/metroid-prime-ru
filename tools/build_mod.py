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
