#!/bin/bash
cd "$(dirname "$0")" || exit 1
if command -v python3.11 >/dev/null 2>&1; then
    python3.11 instalar.py
elif command -v python3 >/dev/null 2>&1; then
    python3 instalar.py
else
    echo "Instala Python 3.11 antes de continuar."
    exit 1
fi
estado=$?
if [ "$estado" -ne 0 ]; then
    read -r -p "Pulsa Intro para cerrar..." _
fi
exit "$estado"
