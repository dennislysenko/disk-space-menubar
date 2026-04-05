# Disk Space Menu Bar - Agent Guide

## Project Overview
Minimal macOS menu bar app showing free disk space with color-coded SF Symbol icons. Single Python file (~125 lines), runs as a LaunchAgent.

## Tech Stack
- Python 3 + `rumps` (menu bar framework) + PyObjC/AppKit (SF Symbols)
- No database, no config files, no external APIs

## Key Files
- `disk_space.py` — entire app
- `com.diskspace.menubar.plist` — LaunchAgent config (currently has hardcoded paths)
- `restart_service.sh` — service restart helper
- `docs/SOT.md` — source of truth for all features and thresholds

## Architecture Notes
- SF Symbol icons are set directly on `NSStatusBarButton` via `_set_icon_direct()` because rumps forces all icons to 20x20
- A one-shot 1-second timer sets the icon after the run loop starts (`_nsapp` unavailable during `__init__`)
- Disk info comes from parsing `diskutil apfs list` output (not `df`, which lies on APFS)
- Dock icon hidden via `LSUIElement` in bundle info dict

## Thresholds (defined in `status_config()`)
| Free GB | Symbol | Color |
|---------|--------|-------|
| > 30 | `internaldrive.fill` | Green |
| 20-30 | `internaldrive.fill` | Yellow |
| 10-20 | `exclamationmark.triangle.fill` | Orange |
| < 10 | `xmark.circle.fill` | Red |

## Development
```bash
# Run directly
venv/bin/python disk_space.py

# Restart as service
./restart_service.sh

# Logs
tail -f ~/Library/Logs/diskspace-error.log
```

## TODO
- [ ] Replace hardcoded `/Users/dennis/...` paths in `com.diskspace.menubar.plist` with an install script that auto-detects the user's home directory and project path
