#!/bin/sh
# Все проверки проекта. Падает на первой ошибке.
set -e
cd "$(dirname "$0")/.."

# Данные Nintendo и бинарники не должны попасть в индекс.
if git diff --cached --name-only | grep -E -i '\.(iso|rvz|gcm|appimage|pak|strg|font|txtr)$|^(work|mod)/|^text/en\.json$'; then
  echo "test.sh: в индексе данные игры/бинарники (см. выше)" >&2
  exit 1
fi

python -I tools/test_roundtrip.py work
python -I tools/test_cyrillic.py work
python -I tools/test_build_mod.py work
