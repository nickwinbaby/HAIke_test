# -*- coding: utf-8 -*-
"""把桌面壳 + index.html 打成一个单文件 exe。

用法（在 desktop 目录下）：
    E:/python/python.exe build_exe.py

产物：上级目录下的 JT808离线工具.exe（双击即开，无需装 Python）。

注意：外壳会**优先读 exe 同目录的 index.html**，所以平时改页面只要刷新即可，
不打包也生效。只有要把 exe 单独拷到别的机器（不带 index.html）时，才需要重跑本脚本，
把新页面塞进包内做兜底。
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

APP_NAME = "JT808离线工具"
ENTRY = "jt808_desktop.py"
ICON = "app.ico"
PAGE = os.path.join("..", "index.html")
# 编解码与平台共用一份，放在 tools/shared/，页面上以 ../shared/xxx.js 引用
SHARED = os.path.join("..", "..", "shared")
# V1.2 地图资源：Leaflet 本地文件 + 标记图标，页面用 ./vendor/、./assets/ 引用
VENDOR = os.path.join("..", "vendor")
ASSETS = os.path.join("..", "assets")

for f in (ENTRY, ICON, PAGE):
    if not os.path.isfile(f):
        sys.exit("缺少文件：" + os.path.abspath(f))
for d in (SHARED, VENDOR, ASSETS):
    if not os.path.isdir(d):
        sys.exit("缺少目录：" + os.path.abspath(d))

import PyInstaller.__main__  # noqa: E402  （放在文件检查之后，报错更清楚）

args = [
    ENTRY,
    "--onefile",
    "--noconsole",
    "--noconfirm",
    "--clean",
    "--name", APP_NAME,
    "--icon", ICON,
    "--add-data", PAGE + os.pathsep + ".",
    # 打进包内 shared/：外壳解包后按 /shared/ 提供，单 exe 拷走也能用
    "--add-data", SHARED + os.pathsep + "shared",
    "--add-data", VENDOR + os.pathsep + "vendor",
    "--add-data", ASSETS + os.pathsep + "assets",
    "--distpath", "..",
    "--workpath", "_build",
    "--specpath", ".",
]
print("PyInstaller " + " ".join(args))
PyInstaller.__main__.run(args)

exe = os.path.join(HERE, "..", APP_NAME + ".exe")
print("\n产物：%s  %.1f MB" % (os.path.abspath(exe),
                              os.path.getsize(exe) / 1048576.0))

# 清掉中间目录，只留 exe 和 .spec
if os.path.isdir("_build"):
    shutil.rmtree("_build", ignore_errors=True)
