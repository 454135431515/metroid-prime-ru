# T4a: тонкий срез — «Новая игра» в игре

Ветка: `t4a-slice` · Статус: done · Размер: M
Зависит от: T2, T3

## Цель
Доказать в игре, что порт берёт наши FONT/TXTR и рисует кириллицу, до генерации всего алфавита.

## Критерии приёмки
- [x] `[New Game]` → `[Новая игра]` на экране сохранений
- [x] лог порта: мод загружен, ошибок мода нет
- [x] латиница шрифтов не изменилась (тест)

## Проверка
- [x] `tools/test.sh` зелёный (`tools/test_cyrillic.py`: латинские ячейки побайтно те же, POT, kern_start, UV в атласе)
- [x] скриншот владельца: `work/preview/t4a_ingame.webp` (вне git)

## Файлы
- `tools/cyrillic.py`, `tools/test_cyrillic.py`, `tools/font.py` (`cell_rect`, `set_cell_uv`), `tools/preview_font.py`

## Итог
- Лог: `mods: russian: 0 file(s), 11 resource(s)`; порт дорастил атласы своими 56 буквами с
  диакритикой поверх нашего POT-атласа — без сбоев.
- SPEC A1, A2, A3 закрыты в игре.
- Мод среза собирался вручную; сборщик — T5.
- Запуск для проверки: `MP_USER_PATH=work/user MP_MODS=mod work/port/squashfs-root/AppRun "Metroid Prime (USA).iso"`
  (распакованный AppImage: карта памяти лежит у исполняемого файла, т.е. тоже в `work/`).
