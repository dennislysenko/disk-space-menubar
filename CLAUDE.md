# Disk Space Menu Bar - Agent Guide

## Project Overview
Minimal macOS menu bar app showing free disk space with color-coded SF Symbol icons, plus cleanup watchers (stale DerivedData, old Xcode archives, idle simulators, simulator leftovers, Trash size, stale worktrees, stray build folders, big caches, temp/swap growth). Runs as a LaunchAgent.

## Tech Stack
- Python 3 + `rumps` (menu bar framework) + PyObjC/AppKit (SF Symbols)
- No database, no config files, no external APIs

## Key Files
- `disk_space.py` — menu bar app and cleanup actions
- `watchers.py` — read-only cleanup scans; `venv/bin/python watchers.py` prints a report
- `com.diskspace.menubar.plist` — LaunchAgent config (currently has hardcoded paths)
- `restart_service.sh` — service restart helper
- `docs/SOT.md` — source of truth for all features and thresholds

## Architecture Notes
- SF Symbol icons are set directly on `NSStatusBarButton` via `_set_icon_direct()` because rumps forces all icons to 20x20
- A one-shot 1-second timer sets the icon after the run loop starts (`_nsapp` unavailable during `__init__`)
- Disk info comes from parsing `diskutil apfs list` output (not `df`, which lies on APFS)
- Dock icon hidden via `LSUIElement` in bundle info dict
- The cleanup scan (`watchers.scan()`) runs on a background thread every 15 min; a 2s main-thread timer renders the finished report, since AppKit menus must only be touched on the main thread
- Don't name app attributes `_title` etc.: `rumps.App` uses them internally. `MenuItem.clear()` crashes on an item that has never had a submenu, so guard with `len(item)`
- DerivedData and Xcode archives list everything (sizes + total); only stale/orphaned DerivedData and archives past the newest 2 per app are `flagged` and count toward the badge (`LIST_ALL_SECTIONS`). Simulator leftovers (dead app containers + logs) are trashed folder by folder, never on a booted device. Unavailable simulators get a one-click `simctl delete unavailable`
- Reading `~/.Trash` is TCC-protected: the LaunchAgent's Python.app needs Full Disk Access, otherwise `check_trash()` returns None and the menu says so
- Cleanup actions are confirmed per item. Folders go to the Trash (`NSFileManager.trashItemAtURL`), simulators via `simctl delete`, worktrees via `git worktree remove` without `--force` (git refuses if dirty; the branch is kept). Simulator runtimes, macOS-managed caches, and the pnpm store are shown but never removed

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
