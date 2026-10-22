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
    """@pickups — окна подбора (CScriptHUDMemo), @hints — подсказки «…обнаружено»,
    @worlds — названия регионов (имя MLVL: строка слота, CFrontEndUI), @scan-short / @scan-long —
    строка 0 и 2 таблиц сканов (CScanDisplay: короткий текст и прокрутка)."""
    out = {"@pickups": [], "@hints": [], "@worlds": [], "@scan-short": [], "@scan-long": []}
    scans = set()
    scan_tsv = os.path.join(os.path.dirname(res), "scans.tsv")
    if os.path.isfile(scan_tsv):
        scans = {line.split("\t")[1] for line in open(scan_tsv).read().splitlines()[1:]}
    regions = {"Space Pirate Frigate", "Tallon Overworld", "Chozo Ruins", "Phendrana Drifts", "Phazon Mines",
               "Magmoor Caverns", "Impact Crater", "Frigate Orpheon"}
    for path in glob.glob(os.path.join(res, "STRG", "*.STRG")):
        sid = os.path.basename(path)[:8]
        strings = dict(strg.parse(open(path, "rb").read()))["ENGL"]
        keys = [f"{sid}:{i}" for i in range(len(strings))]
        if sid in scans:
            out["@scan-short"].append(f"{sid}:0")
            if len(strings) > 2:
                out["@scan-long"].append(f"{sid}:2")
        if len(strings) == 1 and strings[0].strip() in regions:
            out["@worlds"].append(f"{sid}:0")
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
        if name.startswith("_"):
            continue
        keys = set()
        for spec in r.get("keys", []):
            keys |= set(grp[spec]) if spec.startswith("@") else set(expand(spec))
        boxes = []
        for want in r["panes"]:
            frame, _, pane = want.rpartition("/")
            for (fid, pname), (font_id, wrap, _, ex, ey) in panes.items():
                if pname == pane and (not frame or names.get(fid) == frame):
                    boxes.append((r.get("font", font_id), wrap, ex, ey))
        if not boxes:
            raise ValueError(f"panes.json {name}: поле {r['panes']} не найдено в FRME")
        rules.append((name, keys, sorted(set(boxes)), r.get("max"), r.get("lines"), r.get("scroll", False), font_info,
                      r.get("suffix", "")))
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
IMAGE_TAG = re.compile(r"&image=([^;]*);")
IMAGE_FALLBACK_PX = 32  # значок с id из твиков игры (кнопки карты): размер текстуры неизвестен — допущение
_TXTR_SIZES = {}


def image_px(tag_args, res):
    """Ширина значка &image= в пикселях шрифта: ширина текстуры (первой) × масштаб по X из тега.
    SI,sx,sy,id / SA,fps,sx,sy,id… / A,fps,id… / id — как CTextParser."""
    if not _TXTR_SIZES:
        path = os.path.join(os.path.dirname(res), "txtr_sizes.tsv")
        if os.path.isfile(path):
            for line in open(path).read().splitlines()[1:]:
                tid, w, _ = line.split("\t")
                _TXTR_SIZES[tid] = int(w)
    parts = [p.strip() for p in tag_args.split(",")]
    kind, scale, ids = parts[0], 1.0, parts
    if kind == "SI":
        scale, ids = float(parts[1]), parts[3:]
    elif kind == "SA":
        scale, ids = float(parts[2]), parts[4:]
    elif kind == "A":
        ids = parts[2:]
    tex = ids[0].upper() if ids else ""
    return int(_TXTR_SIZES.get(tex, IMAGE_FALLBACK_PX) * scale)


def text_px(text, adv, res):
    """Ширина строки текста в пикселях шрифта: глифы + значки &image=; прочие теги не рисуются."""
    total = 0
    for m in IMAGE_TAG.finditer(text):
        total += image_px(m.group(1), res)
    return total + sum(adv.get(c, 0) for c in TAG.sub("", text))


def layout_errors(rule, key, en, ru, english_of):
    """(ошибки, «проверить в игре») для перевода `ru` в полях правила.

    Ошибка — превышен замеренный в игре предел (`max` px без переноса, `lines` строк с переносом)
    или слово шире поля с переносом. «Проверить» — шире/длиннее английского оригинала этого поля,
    а замера нет: FRME не ограничивает видимую область (текст вылезает за extent и выглядит нормально).
    """
    name, keys, boxes, max_px, max_lines, scroll, font_info, suffix = rule
    en, ru = en + suffix, ru + suffix
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
            elif max_px and any(width(ln) > max_px for ln in lines):
                errs.append(f"строка шире замеренного {max_px} px в поле {name}: "
                            f"{[(ln, width(ln)) for ln in lines if width(ln) > max_px]}")
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


def overlap_errors(res, layout, ru, english_of, font_info):
    """Соседние поля одного кадра: прямоугольники самого длинного текста не пересекаются по-русски,
    если не пересекаются по-английски (тени «…b» и задуманные наложения оригинала не считаются)."""
    import csv
    import json
    import frme
    names = {}
    for r in csv.DictReader(open(os.path.join(os.path.dirname(res), "inventory.tsv")), delimiter="\t"):
        if r["type"] == "FRME" and r["name"]:
            names[r["name"]] = r["id"]
    panes = frme.all_panes(res, full=True)
    grp = groups(res)
    cfg = json.load(open(layout, encoding="utf-8"))
    exclusive = {frozenset(x) for x in cfg.get("_exclusive", [])}
    unverified = {frozenset(x) for x in cfg.get("_unverified", [])}
    per_pane = {}
    for rname, r in json.load(open(layout, encoding="utf-8")).items():
        if rname.startswith("_"):
            continue
        keys = []
        suffix = r.get("suffix", "")
        for spec in r.get("keys", []):
            keys += grp[spec] if spec.startswith("@") else expand(spec)
        pairs = []  # (метка, английский, русский) — каждая строка со своим оригиналом
        for k in keys:
            en = english_of(k)
            if not en:
                continue
            tr = ru.get(k.split(":")[0], {}).get(k.split(":")[1], {}).get("ru") or en
            pairs.append((k, en + suffix, tr + suffix))
        pairs += [(t, t, t) for t in r.get("text", [])]
        # непереведённая строка (русский = английский) — временное состояние: её наложения не ошибка
        pairs = [(k, e, t) if t != e or k in r.get("text", []) else (k + "~", e, t) for k, e, t in pairs]
        for want in r["panes"]:
            frame, _, pane = want.rpartition("/")
            for (fid, pname) in panes:
                if pane == pname and (not frame or names.get(frame) == fid):
                    slot = per_pane.setdefault((fid, pname), ([], r.get("font"), r.get("scroll", False)))
                    slot[0].extend(pairs)
    worlds, boxes, px_world = {}, {}, {}
    for (fid, pname), (pairs, font_override, scroll) in per_pane.items():
        if fid not in worlds:
            worlds[fid] = frme.world_transforms(open(os.path.join(res, "FRME", f"{fid}.FRME"), "rb").read())
        pane = panes[(fid, pname)]
        if pane[-1]:
            continue  # повёрнуто в 3D (боковые панели паузы): плоская проекция неверна, не проверяется
        adv, line_h = font_info(font_override or pane[0])
        wrapping, ex = pane[1], pane[3]

        def lines_of(t):
            if wrapping:
                plain = IMAGE_TAG.sub("\u25a0", t)  # значок — как один широкий знак при переносе
                out = []
                for para in TAG.sub("", plain).split("\n"):
                    out += wrap(para, adv, ex) if para else [""]
                return out
            return t.split("\n")

        def box(t):
            ls = lines_of(t)
            w = max(text_px(ln, adv, res) if not wrapping else
                    sum(adv.get(c, 0) for c in ln) + ln.count("\u25a0") * IMAGE_FALLBACK_PX for ln in ls)
            if scroll:  # прокрутка: видно не больше окна поля
                return frme.text_box(worlds[fid][pname], pane, w)
            return frme.text_box(worlds[fid][pname], pane, w, len(ls), line_h)

        boxes[(fid, pname)] = [(k, box(e), box(t), t) for k, e, t in pairs]
        px_world[(fid, pname)] = (pane[6] / pane[3] * abs(worlds[fid][pname][0][0]),
                                  pane[7] / pane[4] * abs(worlds[fid][pname][2][2]))
    TOUCH_PX = 2  # касание (≤ 2 px шрифта) — не наложение: точность модели ~ пиксель

    def hit(a, b, eps_x, eps_z):
        return (min(a[1], b[1]) - max(a[0], b[0]) > eps_x and
                min(a[3], b[3]) - max(a[2], b[2]) > eps_z)
    errs, todo = [], []
    items = sorted(boxes.items())
    for i, ((fa, na), la) in enumerate(items):
        for (fb, nb), lb in items[i + 1:]:
            if fa != fb or na.rstrip("b") == nb.rstrip("b") or frozenset((na, nb)) in exclusive:
                continue
            ex_ = TOUCH_PX * min(px_world[(fa, na)][0], px_world[(fb, nb)][0])
            ez_ = TOUCH_PX * min(px_world[(fa, na)][1], px_world[(fb, nb)][1])
            bad = [(ka, ta, kb, tb) for ka, ea, ra, ta in la for kb, eb, rb, tb in lb
                   if hit(ra, rb, ex_, ez_) and not hit(ea, eb, ex_, ez_)]
            untranslated = [x for x in bad if x[0].endswith("~") or x[2].endswith("~")]
            todo += [f"наложение с непереведённой строкой в кадре {fa}: {na} [{ka}] и {nb} [{kb}]"
                     for ka, _, kb, _ in untranslated]
            bad = [x for x in bad if x not in untranslated]
            sink = todo if frozenset((na, nb)) in unverified else errs
            for ka, ta, kb, tb in bad[:3]:
                sink.append(f"наложение текста в кадре {fa}: {na} [{ka}] {ta!r} и {nb} [{kb}] {tb!r}")
            if len(bad) > 3:
                sink.append(f"наложение текста в кадре {fa}: {na} и {nb} — ещё {len(bad) - 3}")
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
    if rules:
        o_err, o_todo = overlap_errors(res, layout, ru, english_of, rules[0][6])
        errors += o_err
        todo += [f"overlap: {t}" for t in o_todo]
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
