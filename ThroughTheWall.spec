# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Through the Wall.
# Build:  .venv/bin/pyinstaller ThroughTheWall.spec
# Output: dist/Through the Wall.app   (macOS)
#         dist/Through the Wall/      (Windows — folder with .exe)

import sys
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[("ui", "ui")],
    hiddenimports=[
        "pywebview",
        "webview.platforms.cocoa" if IS_MAC else "webview.platforms.edgechromium",
        "yt_dlp",
        "gallery_dl",
        "browser_cookie3",
    ],
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
            "CFBundleShortVersionString": "0.5",
            "CFBundleVersion": "0.5",
            "NSHighResolutionCapable": True,
            # No Terminal window — real app
            "LSUIElement": False,
            # Allow network
            "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True},
        },
    )
