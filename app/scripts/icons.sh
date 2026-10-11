#!/usr/bin/env bash
# Builds the app icon: draws it (make_icon.py), renders the flat light icon into the files Tauri bundles
# (icon.icns, icon.ico, PNGs), and compiles the Icon Composer document into Assets.car, which macOS 26+
# uses to show the light or dark icon with the system appearance.
set -euo pipefail

APP="$(cd "$(dirname "$0")/.." && pwd)"
ICONS="$APP/src-tauri/icons"
TAURI="$APP/ui/node_modules/.bin/tauri"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 "$APP/scripts/make_icon.py"

"$TAURI" icon "$ICONS/icon.svg" -o "$WORK/tauri" >/dev/null
for f in 32x32.png 128x128.png 128x128@2x.png icon.icns icon.ico icon.png; do
  cp "$WORK/tauri/$f" "$ICONS/$f"
done

mkdir -p "$WORK/out"
xcrun actool "$ICONS/AppIcon.icon" --compile "$WORK/out" --platform macosx --minimum-deployment-target 11.0 \
  --app-icon AppIcon --output-partial-info-plist "$WORK/partial.plist" --errors --warnings \
  --output-format human-readable-text | grep -v -e "compilation-results" -e "^/" || true
cp "$WORK/out/Assets.car" "$ICONS/Assets.car"
echo "icons written to $ICONS"
