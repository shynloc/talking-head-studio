#!/bin/bash
set -e
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
python_bin="$(command -v python3.12 || command -v python3 || true)"
if [ -z "$python_bin" ]; then
    printf '%s\n' '请先安装 Python 3.12，再运行安装脚本。' >&2
    exit 1
fi
exec "$python_bin" -X utf8 scripts/install_app.py "$@"
