# Source of Truth - Disk Space Menu Bar

**Last Updated:** 2026-04-05

Master reference for all features and behavior. Update this file when adding or modifying functionality.

---

## What It Does

Disk Space Menu Bar is a macOS menu bar app that shows your real free disk space at a glance, using accurate APFS container data instead of the misleading `df` output.

---

## Core Features

### Menu Bar Display
- Shows free disk space in GB (e.g., "49GB")
- Native SF Symbol icon changes based on severity
- Refreshes every 60 seconds
- No dock icon — runs as a pure menu bar utility

### Color-Coded Status Icons

| Free Space | Icon | Color | SF Symbol |
|---|---|---|---|
| > 30 GB | Drive | Green | `internaldrive.fill` |
| 20-30 GB | Drive | Yellow | `internaldrive.fill` |
| 10-20 GB | Warning | Orange | `exclamationmark.triangle.fill` |
| < 10 GB | Error | Red | `xmark.circle.fill` |

Icons are rendered using `NSImageSymbolConfiguration.configurationWithHierarchicalColor_` for native color tinting without bitmap hacking.

### Dropdown Menu
Click the menu bar item to see:
- **Total:** full APFS container capacity in GB
- **Used:** space consumed by all volumes, with percentage
- **Free:** unallocated space in GB
- Separator
- Quit button

### Disk Space Source
- Uses `diskutil apfs list` to read the APFS container directly
- Parses `Size (Capacity Ceiling)`, `Capacity In Use By Volumes`, and `Capacity Not Allocated`
- This gives accurate numbers that account for snapshots, purgeable space, and multi-volume containers — unlike `df` which reports misleading figures on APFS

---

## Architecture

### Tech Stack
- **Python 3** with `rumps` for menu bar abstraction
- **PyObjC / AppKit** for SF Symbols and direct status item access
- **LaunchAgent** for auto-start on login and crash recovery

### Files

| File | Purpose |
|---|---|
| `disk_space.py` | Main app (~125 lines) |
| `requirements.txt` | Python dependencies (just `rumps`) |
| `com.diskspace.menubar.plist` | LaunchAgent config |
| `restart_service.sh` | Service restart helper |

### Key Implementation Details
- Dock icon hidden via `LSUIElement` in the bundle info dict
- SF Symbol icons are set directly on the NSStatusBarButton via `_set_icon_direct()`, bypassing rumps' built-in icon handling which forces 20x20 resize
- A one-shot 1-second timer (`first_run`) sets the icon after the run loop starts, since `_nsapp` isn't available during `__init__`
- 60-second refresh timer updates both the title text and the icon

---

## Service Management

### Install as LaunchAgent
```bash
cp com.diskspace.menubar.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.diskspace.menubar.plist
```

### Restart
```bash
./restart_service.sh
```

### Logs
- stdout: `~/Library/Logs/diskspace-output.log`
- stderr: `~/Library/Logs/diskspace-error.log`
