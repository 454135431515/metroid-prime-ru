"""Проверка text/ru.json против таблиц диска (CONSTRAINTS.md, «Перевод»).

    python -I tools/validate.py work/res text/ru.json [--quiet]   # --quiet: без списка предупреждений

Ошибки (выход 1): индекс вне таблицы; исходник изменился (хеш); пустой перевод; набор тегов
`&…;` не совпадает с английским; символ, которого нет в шрифтах; переведённых строк меньше,
чем в ratchet CONSTRAINTS.md. Предупреждения: перевод длиннее английского > LONG раз (может не
влезть), число ручных переносов `\\n` другое (переносы под английскую длину).
"""

import collections
import glob
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


def expand(spec):
    sid, _, rng = spec.partition(":")
    lo, _, hi = rng.partition("-")
    return [f"{sid}:{i}" for i in range(int(lo), int(hi or lo) + 1)]


def groups(res):
    """@pickups — окна подбора предметов (CScriptHUDMemo), @hints — подсказки «…обнаружено»."""
    out = {"@pickups": [], "@hints": []}
    for path in glob.glob(os.path.join(res, "STRG", "*.STRG")):
        sid = os.path.basename(path)[:8]
        strings = dict(strg.parse(open(path, "rb").read()))["ENGL"]
        keys = [f"{sid}:{i}" for i in range(len(strings))]
        if strings[0].startswith("&font=B7BBD0B4;") and "acquired" in strings[0]:
            out["@pickups"] += keys
        elif sid != "0552A456" and all(x.startswith("&just=center;") for x in strings):
            out["@hints"] += keys
    return out


def load_panes(res, path):
    """[(имя правила, ключи, [(advance, ширина, перенос, строк в высоту, шрифт)], max, scroll)]."""
    import csv
    import json
    if not os.path.isfile(path):
        return []
    import frme
    names = {}
    inv = os.path.join(os.path.dirname(res), "inventory.tsv")
    for r in csv.DictReader(open(inv), delimiter="\t"):
        if r["type"] == "FRME" and r["name"]:
            names[r["id"]] = r["name"]
    panes = frme.all_panes(res)
    fonts = {}

    def font_info(fid):
        if fid not in fonts:
            f = font.parse_font(open(os.path.join(cyrillic_res(res), "FONT", f"{fid}.FONT"), "rb").read())
            fonts[fid] = ({chr(g.char): g.a + g.b + g.c for g in f.glyphs}, f.mono_h + f.line_margin)
        return fonts[fid]

    grp = groups(res)
    rules = []
    for name, r in json.load(open(path, encoding="utf-8")).items():
        if name == "_":
            continue
        keys = set()
        for spec in r["keys"]:
            keys |= set(grp[spec]) if spec.startswith("@") else set(expand(spec))
        boxes = []
        for want in r["panes"]:
            frame, _, pane = want.rpartition("/")
            for (fid, pname), (font_id, wrap, _, ex, ey) in panes.items():
                if pname == pane and (not frame or names.get(fid) == frame):
                    boxes.append((font_id, wrap, ex, ey))
        if not boxes:
            raise ValueError(f"panes.json {name}: поле {r['panes']} не найдено в FRME")
        rules.append((name, keys, sorted(set(boxes)), r.get("max"), r.get("lines"), r.get("scroll", False), font_info))
    return rules


def wrap(text, adv, limit):
    """Строки, как их разобьёт игра: по ручным \\n, затем по пробелам; слово шире окна рвётся."""
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


FONT_TAG = re.compile(r"&font=([0-9A-F]{8});")


def layout_errors(rule, key, en, ru, english_of):
    """(ошибки, «проверить в игре») для перевода `ru` в полях правила.

    Ошибка — превышен замеренный в игре предел (`max` px без переноса, `lines` строк с переносом)
    или слово шире поля с переносом. «Проверить» — шире/длиннее английского оригинала этого поля,
    а замера нет: FRME не ограничивает видимую область (текст вылезает за extent и выглядит нормально).
    """
    name, keys, boxes, max_px, max_lines, scroll, font_info = rule
    errs, todo = [], []
    for font_id, wrapping, ex, ey in boxes:
        m = FONT_TAG.search(ru)
        adv, _ = font_info(m.group(1) if m else font_id)
        width = lambda t: sum(adv.get(c, 0) for c in t)
        plain_ru, plain_en = TAG.sub("", ru), TAG.sub("", en)
        if wrapping:
            lines = wrap(plain_ru, adv, ex)
            wide = [ln for ln in lines if width(ln) > ex]
            en_lines = len(wrap(plain_en, adv, ex))
            if len(lines) > 1 and lines[-1].strip() and sum(c.isalnum() for c in lines[-1]) < 3:
                errs.append(f"висячая строка в поле {name}: {lines}")
            if wide:
                errs.append(f"слово шире поля {name} ({ex} px): {wide}")
            elif scroll:
                pass
            elif max_lines and len(lines) > max_lines:
                errs.append(f"{len(lines)} строк в поле {name}, замерено {max_lines}: {lines}")
            elif not max_lines and len(lines) > en_lines:
                todo.append(f"{name}: {len(lines)} строк против {en_lines} у оригинала: {lines}")
        else:
            en_max = max([ex] + [width(TAG.sub("", english_of(k))) for k in keys if english_of(k) is not None])
            ru_lines, en_lines = plain_ru.count("\n") + 1, plain_en.count("\n") + 1
            if max_lines and ru_lines > max_lines:
                errs.append(f"{ru_lines} строк в поле {name}, замерено {max_lines}")
            elif not max_lines and ru_lines > en_lines:
                todo.append(f"{name}: {ru_lines} строк против {en_lines} у оригинала: {plain_ru!r}")
            for ln in plain_ru.split("\n"):
                if max_px and width(ln) > max_px:
                    errs.append(f"шире поля {name}: {width(ln)} px, замерено {max_px}: {ln!r}")
                elif not max_px and width(ln) > en_max:
                    todo.append(f"{name}: {width(ln)} px, оригинал до {en_max}: {ln!r}")
        if errs:
            break
    return errs, todo


def check(res, ru_path, constraints="CONSTRAINTS.md", layout="text/panes.json"):
    import json
    ru = json.load(open(ru_path, encoding="utf-8"))
    chars = drawable(res)
    rules = load_panes(res, layout)
    english_cache = {}

    def english_of(key):
        sid, idx = key.split(":")
        if sid not in english_cache:
            path = os.path.join(res, "STRG", f"{sid}.STRG")
            english_cache[sid] = dict(strg.parse(open(path, "rb").read()))["ENGL"] if os.path.isfile(path) else []
        tbl = english_cache[sid]
        return tbl[int(idx)] if int(idx) < len(tbl) else None
    errors, warnings, todo, count = [], [], [], 0
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
            in_layout = any(key in r[1] for r in rules)
            if plain_en >= 8 and plain_ru > plain_en * LONG and not in_layout:
                warnings.append(f"{key}: длиннее английского в {plain_ru / plain_en:.1f} раза")
            for rule in rules:
                if key in rule[1]:
                    errs, tds = layout_errors(rule, key, en, text, english_of)
                    errors += [f"{key}: {e}" for e in errs]
                    todo += [f"{key}: {t}" for t in tds]
            if en.count("\n") != text.count("\n") and not in_layout:
                warnings.append(f"{key}: переносов {text.count(chr(10))}, в английском {en.count(chr(10))}")
    if os.path.isfile(constraints):
        m = RATCHET.search(open(constraints, encoding="utf-8").read())
        if m and count < int(m.group(1)):
            errors.append(f"ratchet: переведено {count}, в CONSTRAINTS.md {m.group(1)} — перевод пропал")
    return errors, warnings + [f"проверить в игре: {t}" for t in todo], count


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


def main(res, ru_path, quiet=False):
    if not os.path.isdir(res) or not os.path.isfile(ru_path):
        print(f"validate: нет {res} или {ru_path}, пропуск")
        return 0
    errors, warnings, count = check(res, ru_path)
    for w in warnings:
        if not quiet:
            print("warning:", w)
    by_pane = collections.Counter(w.split(": ")[2] for w in warnings if w.startswith("проверить в игре"))
    warnings = [w for w in warnings if not w.startswith("проверить в игре")] + \
        [w for w in warnings if w.startswith("проверить в игре")]
    if by_pane:
        print("скриншоты к проверке (поле: строк):", dict(by_pane))
    for e in errors:
        print("error:", e)
    print(f"validate: {count} строк, {len(errors)} ошибок, {len(warnings)} предупреждений")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3], quiet="--quiet" in sys.argv))
