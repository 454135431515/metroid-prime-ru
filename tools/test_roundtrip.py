"""Round-trip: build(parse(x)) == x побайтно для всех извлечённых ресурсов.

    python -I tools/test_roundtrip.py work
Без work/res (образ не распакован) — пропуск с сообщением, не ошибка.
"""

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font  # noqa: E402
import strg  # noqa: E402


def check(pattern, parse, build):
    paths = sorted(glob.glob(pattern))
    bad = [p for p in paths if build(parse(open(p, "rb").read())) != open(p, "rb").read()]
    for p in bad:
        print("round-trip mismatch:", p)
    return len(paths), len(bad)


def main(work):
    res = os.path.join(work, "res")
    if not os.path.isdir(res):
        print(f"test_roundtrip: {res} нет, пропуск (запусти tools/extract.py)")
        return 0
    failed = 0
    for kind, (parse, build) in {"STRG": (strg.parse, strg.build),
                                 "FONT": (font.parse_font, font.build_font),
                                 "TXTR": (font.parse_txtr, font.build_txtr)}.items():
        n, bad = check(os.path.join(res, kind, f"*.{kind}"), parse, build)
        print(f"{kind}: {n - bad}/{n} ok")
        failed += bad
    # замена секции сохраняет число строк и читается обратно
    sample = sorted(glob.glob(os.path.join(res, "STRG", "*.STRG")))[0]
    data = open(sample, "rb").read()
    (lang, strings), = strg.parse(data)
    swapped = [s + "ё" for s in strings]
    assert strg.parse(strg.replace_language(data, lang, swapped)) == [(lang, swapped)]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "work"))
