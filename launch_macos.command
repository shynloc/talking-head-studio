#!/bin/bash
set -e
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [ -x .venv/bin/python ]; then
    python_bin=".venv/bin/python"
elif [ -x ../runtime/bin/python ]; then
    python_bin="../runtime/bin/python"
else
    python_bin="$(command -v python3.12 || command -v python3 || true)"
fi
if [ -z "$python_bin" ]; then
    printf '%s\n' '请先安装 Python 3.12，再打开工作台。' >&2
    exit 1
fi
exec "$python_bin" -X utf8 scripts/launch.py "$@"
