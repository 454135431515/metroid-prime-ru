"""Пачки перевода: компактный экспорт непереведённого и импорт перевода в text/ru.json.

    python -I tools/batch.py export <отбор> out.tsv
        отбор: kind=ui | region=<Region> | category=<N> | <STRG id>[:<от>-<до>],...
    python -I tools/batch.py import in.tsv
    python -I tools/batch.py apply out.tsv map.json   # map: {английский текст: перевод}

Экспорт: одна строка на уникальный английский текст: `ключи<TAB>текст`, ключи `id:idx` через запятую,
перевод строки внутри текста — `\\n`. Уже переведённые вхождения пропускаются.
Импорт: `ключи<TAB>перевод` (тот же формат); перевод ложится на каждое вхождение с хешем исходника.
Строка, которой нужен разный перевод по месту, импортируется отдельными ключами.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_mod  # noqa: E402

EN, RU = "text/en.json", "text/ru.json"


def select(tables, spec):
    """{STRG id: множество индексов или None (вся таблица)}; диапазоны одной таблицы объединяются."""
    if spec.startswith("kind="):
        return {k: None for k, v in tables.items() if v["kind"] == spec[5:]}
    if spec.startswith("region="):
        return {k: None for k, v in tables.items() if spec[7:] in v["regions"]}
    if spec.startswith("category="):
        return {k: None for k, v in tables.items() if v.get("category") == int(spec[9:])}
    out = {}
    for part in spec.split(","):
        sid, _, rng = part.partition(":")
        lo, _, hi = rng.partition("-")
        if not rng:
            out[sid] = None
        elif out.get(sid, set()) is not None:
            out[sid] = out.get(sid, set()) | set(range(int(lo), int(hi or lo) + 1))
    return out


def export(spec, out):
    tables = json.load(open(EN, encoding="utf-8"))
    ru = json.load(open(RU, encoding="utf-8")) if os.path.isfile(RU) else {}
    groups = {}
    for sid, rng in sorted(select(tables, spec).items()):
        for i, text in enumerate(tables[sid]["strings"]):
            if (rng is not None and i not in rng) or str(i) in ru.get(sid, {}) or not text.strip():
                continue
            groups.setdefault(text, []).append(f"{sid}:{i}")
    with open(out, "w", encoding="utf-8") as f:
        for text, keys in groups.items():
            f.write(",".join(keys) + "\t" + text.replace("\n", "\\n") + "\n")
    print(f"export: {len(groups)} unique, {sum(map(len, groups.values()))} occurrences -> {out}")


def import_(path):
    tables = json.load(open(EN, encoding="utf-8"))
    ru = json.load(open(RU, encoding="utf-8")) if os.path.isfile(RU) else {}
    n = 0
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        keys, text = line.split("\t", 1)
        text = text.replace("\\n", "\n")
        for key in keys.split(","):
            sid, idx = key.split(":")
            en = tables[sid]["strings"][int(idx)]
            ru.setdefault(sid, {})[idx] = {"en": build_mod.en_hash(en), "ru": text}
            n += 1
    ordered = {sid: dict(sorted(e.items(), key=lambda kv: int(kv[0]))) for sid, e in sorted(ru.items())}
    with open(RU, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"import: {n} occurrences -> {RU}")


def apply(export_path, map_path):
    """Перевод словарём {английский: русский} по ключам экспорта; без перевода — печатается."""
    mapping = json.load(open(map_path, encoding="utf-8"))
    lines, skipped = [], []
    for line in open(export_path, encoding="utf-8"):
        keys, text = line.rstrip("\n").split("\t", 1)
        en = text.replace("\\n", "\n")
        if en in mapping:
            lines.append(keys + "\t" + mapping[en].replace("\n", "\\n"))
        else:
            skipped.append(en)
    tmp = export_path + ".import"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    import_(tmp)
    os.remove(tmp)
    for en in skipped:
        print("не переведено:", repr(en))


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    {"export": export, "import": import_, "apply": apply}[cmd](*args)
