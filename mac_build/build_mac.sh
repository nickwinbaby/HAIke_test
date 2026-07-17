#!/bin/bash
set -e

cd "$(dirname "$0")"

python3 -m PyInstaller --clean --windowed --onefile \
  --name "串口log过滤 V11.0" \
  --icon "icon.icns" \
  --add-data "icon.icns:." \
  "串口log过滤 - V11.0-Mac.py"
