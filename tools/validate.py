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


def check(res, ru_path, constraints="CONSTRAINTS.md"):
    import json
    ru = json.load(open(ru_path, encoding="utf-8"))
    chars = drawable(res)
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
            if plain_en >= 8 and plain_ru > plain_en * LONG:
                warnings.append(f"{key}: длиннее английского в {plain_ru / plain_en:.1f} раза")
            if en.count("\n") != text.count("\n"):
                warnings.append(f"{key}: переносов {text.count(chr(10))}, в английском {en.count(chr(10))}")
    if os.path.isfile(constraints):
        m = RATCHET.search(open(constraints, encoding="utf-8").read())
        if m and count < int(m.group(1)):
            errors.append(f"ratchet: переведено {count}, в CONSTRAINTS.md {m.group(1)} — перевод пропал")
    return errors, warnings, count


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
