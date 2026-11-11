#!/bin/sh
# Запускает хук на первом найденном Python 3.10+ (python3 или python).
# Нужен, потому что на Windows python3 часто — заглушка Microsoft Store, а на macOS нет python.
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
    exec "$py" "$@"
  fi
done
echo "strat hooks: Python 3.10+ не найден — хук пропущен" >&2
exit 0
