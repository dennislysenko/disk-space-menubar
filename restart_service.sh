#!/bin/bash
# Restart Disk Space menu bar service

PLIST_NAME="com.diskspace.menubar.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
DEST_PLIST="$LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo "Restarting Disk Space..."

launchctl unload "$DEST_PLIST" 2>/dev/null
echo "✓ Service stopped"

sleep 1

launchctl load "$DEST_PLIST"
echo "✓ Service started"

sleep 1
if launchctl list | grep -q "com.diskspace.menubar"; then
    echo "✓ Disk Space is running!"
    echo ""
    echo "Check your menu bar for the disk icon"
else
    echo "✗ Failed to start service"
    echo "Check logs at:"
    echo "  ~/Library/Logs/diskspace-error.log"
    exit 1
fi
