# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['通用-GPS-CEP计算-图形界面-20250514-调试自定义-260414完成.py'],
    pathex=[],
    binaries=[],
    datas=[('cep_tool_icon.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='通用-GPS-CEP计算-图形界面-20250514-调试自定义-260414完成',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    icon='cep_tool_icon.ico',
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
