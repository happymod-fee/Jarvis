#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "==================================================="
echo "    VAX Voice Assistant (Unix Launcher)"
echo "==================================================="

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 was not found in PATH."
    exit 1
fi

python3 main.py "$@"
