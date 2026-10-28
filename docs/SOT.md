# Source of Truth - Disk Space Menu Bar

**Last Updated:** 2026-10-28

Master reference for all features and behavior. Update this file when adding or modifying functionality.

---

## What It Does

Disk Space Menu Bar is a macOS menu bar app that shows your real free disk space at a glance, using accurate APFS container data instead of the misleading `df` output.

---

## Core Features

### Menu Bar Display
- Shows available disk space in GB (e.g., "80GB"), matching Finder / System Settings
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
- **Available:** what Finder/System Settings reports — unallocated + purgeable (snapshots, evictable iCloud files, caches)
- **Unallocated:** strict "right now, no reclaiming needed" free space from the APFS container
- Separator
- Cleanup sections (see below), then **Rescan now**
- Separator
- Quit button

### Cleanup Watchers
Space that builds up while coding agents build apps and run simulators. Scanned by `watchers.py` on a background thread at launch and every 15 minutes (~10 s per scan). The header shows the total reclaimable and when it was last scanned. Each section lists its items with size and reason, and is hidden when empty.

| Section | Flagged when | Clicking an item |
|---|---|---|
| Stale DerivedData | `~/Library/Developer/Xcode/DerivedData/<Project>-<hash>` whose `info.plist` `LastAccessedDate` is 7+ days old, or whose `WorkspacePath` no longer exists (e.g. a removed worktree) | Move to Trash |
| Stray build folders | Xcode `-derivedDataPath` folders (anything containing `Build/Intermediates.noindex`) and SwiftPM `.build` folders under `~/dev`, unused 7+ days | Move to Trash |
| Idle simulators | Devices not booted for 14+ days (by `device.plist` mtime) using 50+ MB, or whose runtime is missing. Also lists installed runtimes with size, device count and last use (info only) | `simctl delete` |
| Stale worktrees | Git worktrees under `~/dev` repos idle 7+ days, or whose folder is gone | `git worktree remove` (no `--force`; branch kept). Dirty worktrees are reveal-only |
| Big caches | Any folder in `~/Library/Caches` or `~/.cache`, plus `~/.npm` and the pnpm store, over 1 GB | Move to Trash. macOS-managed caches and the pnpm store are reveal-only |
| Temp & swap | Always shown: `/private/tmp`, `$TMPDIR`, swap used, uptime. Becomes **Reboot recommended** at 15 GB combined, since a reboot clears all three | Info only |

Every removal asks for confirmation (with a "Reveal in Finder" option), and sections with 2+ removable items get a **Clean up all…** entry. Caches are not counted toward "reclaimable" since they're in use and refill.

The menu bar title gets a `•` when 5+ GB is reclaimable and a `↻` when a reboot is recommended.

Thresholds are constants at the top of `watchers.py` (`STALE_*_DAYS`, `MIN_CACHE_BYTES`, `REBOOT_RECLAIM_BYTES`, `SCAN_ROOTS`) and `disk_space.py` (`SCAN_INTERVAL_SECONDS`, `CLEANABLE_BADGE_BYTES`).

### Disk Space Sources
- `diskutil apfs list` for `Size (Capacity Ceiling)`, `Capacity In Use By Volumes`, and `Capacity Not Allocated` (the strict container view)
- `NSURL` resource key `NSURLVolumeAvailableCapacityForImportantUsageKey` on `/` for the "Available" figure — this matches what Finder, System Settings, and `df` show because it adds purgeable space (Time Machine local snapshots, evictable iCloud content, etc.) on top of unallocated bytes
- The menu bar title and color thresholds use the **Available** number, since that's what users see elsewhere in macOS

---

## Architecture

### Tech Stack
- **Python 3** with `rumps` for menu bar abstraction
- **PyObjC / AppKit** for SF Symbols and direct status item access
- **LaunchAgent** for auto-start on login and crash recovery

### Files

| File | Purpose |
|---|---|
| `disk_space.py` | Main app: menu, icon, cleanup actions |
| `watchers.py` | Read-only cleanup scans; run directly to print a report |
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
