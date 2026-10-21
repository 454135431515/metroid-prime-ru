"""Проверка text/ru.json против таблиц диска (CONSTRAINTS.md, «Перевод»).

    python -I tools/validate.py work/res text/ru.json

Ошибки (выход 1): индекс вне таблицы; исходник изменился (хеш); пустой перевод; набор тегов
`&…;` не совпадает с английским; символ, которого нет в шрифтах; переведённых строк меньше,
чем в ratchet CONSTRAINTS.md. Предупреждения: перевод длиннее английского > LONG раз (может не
влезть), число ручных переносов `\\n` другое (переносы под английскую длину).
"""

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_mod  # noqa: E402
import cyrillic  # noqa: E402
import font  # noqa: E402
import strg  # noqa: E402

TAG = re.compile(r"&[a-z\-]+(?:=[^;]*)?;")
LONG = 1.5
RATCHET = re.compile(r"\| Переведённых вхождений строк \| (\d+) из")


def drawable(res):
    """Символы, которые есть во всех пяти шрифтах Deface после генерации (латиница диска + рецепты)."""
    chars = None
    for fid in cyrillic.FONTS:
        f = font.parse_font(open(os.path.join(res, "FONT", f"{fid}.FONT"), "rb").read())
        have = {chr(g.char) for g in f.glyphs} | set(cyrillic.RECIPES)
        chars = have if chars is None else chars & have
    return chars | {"\n"}


def load_layout(res, path):
    """[(множество ключей, [(advance-словарь, max px)], строк)] из text/layout.json."""
    import json
    if not os.path.isfile(path):
        return []
    rules = []
    for name, r in json.load(open(path, encoding="utf-8")).items():
        if name == "_":
            continue
        keys = set()
        for spec in r["keys"]:
            sid, _, rng = spec.partition(":")
            lo, _, hi = rng.partition("-")
            keys |= {f"{sid}:{i}" for i in range(int(lo), int(hi or lo) + 1)}
        fonts = []
        for fid, limit in r["fonts"].items():
            f = font.parse_font(open(os.path.join(res, "FONT", f"{fid}.FONT"), "rb").read())
            adv = {chr(g.char): g.a + g.b + g.c for g in f.glyphs}
            fonts.append((adv, limit))
        rules.append((name, keys, fonts, r["lines"]))
    return rules


def wrap(text, adv, limit):
    """Строки, как их разобьёт игра: по ручным \n, затем по пробелам; слово шире окна рвётся."""
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            cand = word if not cur else cur + " " + word
            if cur and sum(adv.get(c, 0) for c in cand) > limit:
                lines.append(cur)
                cur = word
            else:
                cur = cand
        lines.append(cur)
    return lines


def check(res, ru_path, constraints="CONSTRAINTS.md", layout="text/layout.json"):
    import json
    ru = json.load(open(ru_path, encoding="utf-8"))
    chars = drawable(res)
    rules = load_layout(cyrillic_res(res), layout)
    errors, warnings, count = [], [], 0
    for sid, entries in sorted(ru.items()):
        path = os.path.join(res, "STRG", f"{sid}.STRG")
        if not os.path.isfile(path):
            errors.append(f"{sid}: нет такой таблицы")
            continue
        english = dict(strg.parse(open(path, "rb").read()))["ENGL"]
        for idx, e in sorted(entries.items(), key=lambda kv: int(kv[0])):
            key = f"{sid}:{idx}"
            i = int(idx)
            if not 0 <= i < len(english):
                errors.append(f"{key}: индекс вне таблицы ({len(english)} строк)")
                continue
            en, text = english[i], e.get("ru", "")
            count += 1
            if build_mod.en_hash(en) != e.get("en"):
                errors.append(f"{key}: исходник изменился: {en!r}")
            if not text.strip() and en.strip():
                errors.append(f"{key}: пустой перевод")
            if collections.Counter(TAG.findall(en)) != collections.Counter(TAG.findall(text)):
                errors.append(f"{key}: теги не совпадают: {TAG.findall(en)} vs {TAG.findall(text)}")
            missing = sorted(set(TAG.sub("", text)) - chars)
            if missing:
                errors.append(f"{key}: нет в шрифтах: {''.join(missing)!r}")
            plain_en, plain_ru = len(TAG.sub("", en)), len(TAG.sub("", text))
            in_layout = any(key in k for _, k, _, _ in rules)
            if plain_en >= 8 and plain_ru > plain_en * LONG and not in_layout:
                warnings.append(f"{key}: длиннее английского в {plain_ru / plain_en:.1f} раза")
            for name, keys, fonts, max_lines in rules:
                if key not in keys:
                    continue
                for adv, limit in fonts:
                    lines = wrap(TAG.sub("", text), adv, limit)
                    wide = [ln for ln in lines if sum(adv.get(c, 0) for c in ln) > limit]
                    if wide or len(lines) > max_lines:
                        errors.append(f"{key}: не влезает в {name}: {lines}")
                        break
            if en.count("\n") != text.count("\n") and not in_layout:
                warnings.append(f"{key}: переносов {text.count(chr(10))}, в английском {en.count(chr(10))}")
    if os.path.isfile(constraints):
        m = RATCHET.search(open(constraints, encoding="utf-8").read())
        if m and count < int(m.group(1)):
            errors.append(f"ratchet: переведено {count}, в CONSTRAINTS.md {m.group(1)} — перевод пропал")
    return errors, warnings, count


def cyrillic_res(res):
    """Шрифты с кириллицей для замеров ширины: генерируются во временную папку один раз."""
    import tempfile
    out = os.path.join(tempfile.gettempdir(), "mp-russian-fonts")
    cyrillic_main_quiet(res, os.path.join(out, "FONT"))
    return out


def cyrillic_main_quiet(res, out):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        cyrillic.main(res, out)


def main(res, ru_path):
    if not os.path.isdir(res) or not os.path.isfile(ru_path):
        print(f"validate: нет {res} или {ru_path}, пропуск")
        return 0
    errors, warnings, count = check(res, ru_path)
    for w in warnings:
        print("warning:", w)
    for e in errors:
        print("error:", e)
    print(f"validate: {count} строк, {len(errors)} ошибок, {len(warnings)} предупреждений")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
