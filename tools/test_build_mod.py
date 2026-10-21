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
        built = dict(strg.parse(open(os.path.join(out, f"{sid}.STRG"), "rb").read()))["ENGL"]
        assert stale == 1
        assert built[36] == "[Новая игра]" and built[22] == english[22]
        assert [s for i, s in enumerate(built) if i != 36] == [s for i, s in enumerate(english) if i != 36]
    print("build_mod: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "work"))
