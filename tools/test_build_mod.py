"""build_mod: перевод попадает в ENGL, перевод с устаревшим хешем не пишется.

    python -I tools/test_build_mod.py work
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_mod  # noqa: E402
import strg  # noqa: E402


def main(work):
    res = os.path.join(work, "res")
    if not os.path.isdir(res):
        print(f"test_build_mod: {res} нет, пропуск")
        return 0
    sid = "0552A456"
    english = dict(strg.parse(open(os.path.join(res, "STRG", f"{sid}.STRG"), "rb").read()))["ENGL"]
    with tempfile.TemporaryDirectory() as tmp:
        ru = {sid: {"36": {"en": build_mod.en_hash(english[36]), "ru": "[Новая игра]"},
                    "22": {"en": "00000000", "ru": "Да"}}}
        path = os.path.join(tmp, "ru.json")
        json.dump(ru, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        out = os.path.join(tmp, "mod")
        stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")
        try:
            stale = build_mod.build(res, path, out)
        finally:
            sys.stdout = stdout
        # порт 0.31.1 режет добавленный в NoARAM ресурс до кратного 32 размера (вылет у лифта)
        assert all(os.path.getsize(os.path.join(out, n)) % 32 == 0 for n in os.listdir(out))
        built = dict(strg.parse(open(os.path.join(out, f"{sid}.STRG"), "rb").read()))["ENGL"]
        assert stale == 1
        assert built[36] == "[Новая игра]" and built[22] == english[22]
        assert [s for i, s in enumerate(built) if i != 36] == [s for i, s in enumerate(english) if i != 36]
        # кадры с узким шрифтом поля босса: от диска отличаются ровно ссылкой на шрифт (4 байта)
        import cyrillic
        import font
        frames = [n[:8] for n in os.listdir(out) if n.endswith(".FRME")]
        assert frames, "нет кадров с полем босса"
        for fid in frames:
            a = open(os.path.join(res, "FRME", f"{fid}.FRME"), "rb").read()
            b = open(os.path.join(out, f"{fid}.FRME"), "rb").read()
            assert len(b) - len(a) < 32 and not b[len(a):].strip(b"\0"), fid
            assert sum(x != y for x, y in zip(a, b)) <= 4, fid
        nf = font.parse_font(open(os.path.join(out, f"{cyrillic.NARROW_FONT:08X}.FONT"), "rb").read())
        base = font.parse_font(open(os.path.join(out, f"{cyrillic.NARROW_BASE}.FONT"), "rb").read())
        adv = lambda f: {g.char: g.a + g.b + g.c for g in f.glyphs}
        na, ba = adv(nf), adv(base)
        assert set(na) == set(ba) and all(na[c] <= ba[c] for c in na), "узкий шрифт шире обычного"
        assert nf.texture_id == cyrillic.NARROW_TXTR
    print("build_mod: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "work"))
