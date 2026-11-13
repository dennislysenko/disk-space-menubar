#!/bin/bash
# Build "Disk Space.app" (a small launcher around disk_space.py) and install the
# LaunchAgent that starts it at login. Re-run after changing launcher/ or moving the repo.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
APP="$REPO/build/Disk Space.app"
LABEL="com.diskspace.menubar"
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "Building $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
swiftc -O -o "$APP/Contents/MacOS/DiskSpace" "$REPO/launcher/main.swift"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key><string>$LABEL</string>
    <key>CFBundleName</key><string>Disk Space</string>
    <key>CFBundleExecutable</key><string>DiskSpace</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>LSUIElement</key><true/>
    <key>DSRepoPath</key><string>$REPO</string>
</dict>
</plist>
PLIST

# Ad-hoc signature: privacy grants stick to it, so a rebuild needs a fresh grant
codesign --force --sign - "$APP"

sed -e "s|__APP__|$APP/Contents/MacOS/DiskSpace|" -e "s|__REPO__|$REPO|" -e "s|__HOME__|$HOME|g" \
    "$REPO/$LABEL.plist" > "$AGENT"
echo "Installed $AGENT"

"$REPO/restart_service.sh"
echo ""
echo "To show Trash size: System Settings > Privacy & Security > Full Disk Access > +"
echo "  and add: $APP"
