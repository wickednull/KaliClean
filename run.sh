#!/usr/bin/env bash
# KaliClean launcher
cd "$(dirname "$0")" || exit 1
exec python3 kaliclean.py "$@"
