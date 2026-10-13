#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3。"
  exit 1
fi

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
  echo "缺少 Python 图形界面组件 tkinter。"
  echo
  echo "Ubuntu / Debian / Linux Mint：sudo apt install python3-tk"
  echo "Fedora / RHEL：sudo dnf install python3-tkinter"
  echo "Arch Linux：sudo pacman -S tk"
  echo
  echo "安装完成后重新运行本脚本。"
  exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
  echo "未找到 nmcli，请先安装并启动 NetworkManager。"
  exit 1
fi

if ! command -v iw >/dev/null 2>&1; then
  echo "警告：未找到 iw，程序可以启动，但无法准确检测网卡的热点模式和频段能力。"
fi

exec python3 wifi_hotspot_gui.py
