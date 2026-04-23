#!/bin/bash
# Package the built .app into a .dmg installer with a proper layout.
# Requires the .app to exist at dist/Through the Wall.app (run pyinstaller first).
set -euo pipefail

APP_NAME="Through the Wall"
APP_PATH="dist/${APP_NAME}.app"
DMG_PATH="dist/${APP_NAME}.dmg"

cd "$(dirname "$0")"

if [ ! -d "$APP_PATH" ]; then
  echo "Error: $APP_PATH not found. Build the app first:"
  echo "  .venv/bin/pyinstaller ThroughTheWall.spec --noconfirm"
  exit 1
fi

# Regenerate the DMG background (idempotent)
.venv/bin/python scripts/make_dmg_bg.py

rm -f "$DMG_PATH"
.venv/bin/dmgbuild -s scripts/dmg_settings.py "$APP_NAME" "$DMG_PATH"

SIZE=$(du -h "$DMG_PATH" | cut -f1)
echo ""
echo "Done: $DMG_PATH ($SIZE)"
