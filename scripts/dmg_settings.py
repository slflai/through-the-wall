"""dmgbuild settings for Through the Wall.
Invoked by make-dmg.sh via:  dmgbuild -s scripts/dmg_settings.py "Through the Wall" dist/ThroughTheWall.dmg
"""
import os
from pathlib import Path

# dmgbuild exec()'s this file so __file__ isn't set — use CWD (make-dmg.sh cd's to project root)
ROOT = Path(os.getcwd()).resolve()

# Volume settings
format = "UDZO"
compression_level = 9
size = None  # auto

# Contents: the app + a symlink pointing at /Applications
files = [str(ROOT / "dist" / "Through the Wall.app")]
symlinks = {"Applications": "/Applications"}

# Layout: classic two-icon installer window
window_rect = ((100, 100), (600, 400))
icon_size = 128
text_size = 13
icon_locations = {
    "Through the Wall.app": (150, 200),
    "Applications": (450, 200),
}

# Background
_bg = ROOT / "assets" / "dmg-bg.png"
if _bg.exists():
    background = str(_bg)
else:
    background = "builtin-arrow"

# Volume icon (same as app icon)
_vol_icon = ROOT / "assets" / "icon.icns"
if _vol_icon.exists():
    badge_icon = str(_vol_icon)

# No default_view override: uses icon view
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
sidebar_width = 180
