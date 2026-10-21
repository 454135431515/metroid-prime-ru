"""Генерирует шрифты с кириллицей в out/res и рисует проверочный лист всеми кеглями.

    python -I tools/preview_cyrillic.py work/res work/fonts out.png "строка" ["строка"...]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cyrillic  # noqa: E402
import preview_font  # noqa: E402


def main(res, out_dir, png, *lines):
    fonts = os.path.join(out_dir, "FONT")
    txtrs = os.path.join(out_dir, "TXTR")
    cyrillic.main(res, fonts)
    os.makedirs(txtrs, exist_ok=True)
    for name in os.listdir(fonts):
        if name.endswith(".TXTR"):
            os.replace(os.path.join(fonts, name), os.path.join(txtrs, name))
    preview_font.sheet(fonts, txtrs, cyrillic.FONTS, lines, png)


if __name__ == "__main__":
    main(*sys.argv[1:])
