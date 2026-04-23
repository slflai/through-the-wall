# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Through the Wall.
# Build:  .venv/bin/pyinstaller ThroughTheWall.spec
# Output: dist/Through the Wall.app   (macOS)
#         dist/Through the Wall/      (Windows — folder with .exe)

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

block_cipher = None

# gallery-dl and yt-dlp load extractor modules dynamically, so every submodule
# must be declared explicitly — PyInstaller's static analysis won't see them.
_gdl_hidden = collect_submodules("gallery_dl")
_yt_hidden = collect_submodules("yt_dlp")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[("ui", "ui")] + collect_data_files("gallery_dl") + collect_data_files("yt_dlp"),
    hiddenimports=[
        "pywebview",
        "webview.platforms.cocoa" if IS_MAC else "webview.platforms.edgechromium",
        "browser_cookie3",
    ] + _gdl_hidden + _yt_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Through the Wall",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Through the Wall",
)

_icon = "assets/icon.icns" if IS_MAC and Path("assets/icon.icns").exists() else None

if IS_MAC:
    app = BUNDLE(
        coll,
        name="Through the Wall.app",
        icon=_icon,
        bundle_identifier="com.ericlai.throughthewall",
        info_plist={
            "CFBundleName": "Through the Wall",
            "CFBundleDisplayName": "Through the Wall",
            "CFBundleShortVersionString": "0.6",
            "CFBundleVersion": "0.6",
            "NSHighResolutionCapable": True,
            # No Terminal window — real app
            "LSUIElement": False,
            # Allow network
            "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True},
        },
    )
