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
        # сжатые кадры (squeeze): от диска отличаются только extentX полей (до 4 байт на поле), длина та же;
        # новых id мод не добавляет (порт 0.31.1 ломает таблицу NoARAM.pak с добавленными id, T7f)
        import frme
        frames = [n[:8] for n in os.listdir(out) if n.endswith(".FRME")]
        assert frames, "нет кадров с полем босса"
        for fid in frames:
            a = open(os.path.join(res, "FRME", f"{fid}.FRME"), "rb").read()
            b = open(os.path.join(out, f"{fid}.FRME"), "rb").read()
            assert len(a) == len(b) and sum(x != y for x, y in zip(a, b)) <= 4 * a.count(b"TXPN"), fid
        disc = {n.split(".")[0] for d in os.listdir(res) for n in os.listdir(os.path.join(res, d))}
        assert {n.split(".")[0] for n in os.listdir(out)} <= disc, "мод добавляет новые id"
    print("build_mod: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "work"))
