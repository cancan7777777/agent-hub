# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：AgentHub 桌面单文件 exe。"""
import os

a = Analysis(
    ["..\\desktop.py"],
    pathex=["..\\core"],
    binaries=[],
    datas=[
        ("..\\ui", "ui"),
    ],
    hiddenimports=[
        "server", "registry", "scan", "consolidate", "mcp_hub",
        "plugin_hub", "watcher", "autostart", "fsutil",
        "jsonc_patch", "mcp_format",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr_loader", "clr_loader.netfx", "pythonnet",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PyQt5", "PySide6"],
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
    name="AgentHub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="..\\agenthub.ico",
    version="..\\tools\\version_info.txt",
)
