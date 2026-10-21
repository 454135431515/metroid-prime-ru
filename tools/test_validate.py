"""validate ловит каждую ошибку ровно один раз.

    python -I tools/test_validate.py work
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_mod  # noqa: E402
import strg  # noqa: E402
import validate  # noqa: E402


def main(work):
    res = os.path.join(work, "res")
    if not os.path.isdir(res):
        print(f"test_validate: {res} нет, пропуск")
        return 0
    sid = "0552A456"
    en = dict(strg.parse(open(os.path.join(res, "STRG", f"{sid}.STRG"), "rb").read()))["ENGL"]
    h = build_mod.en_hash
    ru = {sid: {
        "36": {"en": h(en[36]), "ru": "[Новая игра]"},       # ок
        "37": {"en": h(en[37]), "ru": "Бонусы ☃"},           # нет в шрифтах
        "81": {"en": h(en[81]), "ru": "ОК"},                 # потерян &image
        "22": {"en": "deadbeef", "ru": "Да"},                # исходник изменился
        "23": {"en": h(en[23]), "ru": ""},                   # пусто
        "999": {"en": "x", "ru": "y"},                       # вне таблицы
    }}
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "ru.json")
        json.dump(ru, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        errors, _, count = validate.check(res, p, constraints=os.path.join(tmp, "none"))
        keys = sorted(e.split(":")[1] for e in errors)
        assert keys == ["22", "23", "37", "81", "999"], errors
        with open(os.path.join(tmp, "c.md"), "w", encoding="utf-8") as c:
            c.write("| Переведённых вхождений строк | 100 из 2323 | только растёт |")
        errors, _, _ = validate.check(res, p, constraints=os.path.join(tmp, "c.md"))
        assert any(e.startswith("ratchet") for e in errors), errors
        # кнопка снаряжения: слово шире окна
        inv = {"500EC6A0": {"11": {"en": h(dict(strg.parse(open(os.path.join(res, "STRG", "500EC6A0.STRG"), "rb").read()))["ENGL"][11]),
                                   "ru": "Морфо-шар"}}}
        json.dump(inv, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        errors, _, _ = validate.check(res, p, constraints=os.path.join(tmp, "none"))
        assert any("шире поля" in e for e in errors), errors
        # висячий обрывок «A?» на последней строке
        en8 = dict(strg.parse(open(os.path.join(res, "STRG", "19C3F7F7.STRG"), "rb").read()))["ENGL"][8]
        json.dump({"19C3F7F7": {"8": {"en": h(en8), "ru": "Сохранить прогресс на карту памяти в слоте A?"}}},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False)
        errors, _, _ = validate.check(res, p, constraints=os.path.join(tmp, "none"))
        assert any("висячая" in e for e in errors), errors
        # наложение соседних полей: полные «Обычный режим» и «Сложный режим» в строке выбора режима
        e0 = dict(strg.parse(open(os.path.join(res, "STRG", "0552A456.STRG"), "rb").read()))["ENGL"]
        json.dump({sid: {"101": {"en": h(e0[101]), "ru": "Обычный режим"}, "102": {"en": h(e0[102]), "ru": "Сложный режим"}}},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False)
        errors, _, _ = validate.check(res, p, constraints=os.path.join(tmp, "none"))
        assert any("наложение" in e for e in errors), errors
    print("validate: negative ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "work"))
