# Disk Space Menu Bar

At-a-glance disk space monitoring that lives in your macOS menu bar, with progressive color-coded alerts as you approach your limits.

Built for people who are always flirting with a full disk — maybe you bought the smaller drive, maybe Xcode and Docker keep filling your caches, maybe you just have a lot of projects. Either way, you shouldn't have to remember to check.

The icon changes color and shape based on how much space you have left:

- **Green drive** — more than 30 GB free
- **Yellow drive** — 20-30 GB
- **Orange warning** — 10-20 GB
- **Red error** — under 10 GB

It's always there, it refreshes every 60 seconds, and it stays out of your way until it has something worth saying. Click to see the full breakdown.

## Install

Requires **macOS 12+** and **Python 3**.

```bash
git clone https://github.com/dennislysenko/disk-space-menubar.git
cd disk-space-menubar
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python disk_space.py
```

### Run on login

```bash
./install.sh
```

This builds `build/Disk Space.app`, a small launcher that runs `disk_space.py`, and installs a LaunchAgent for it. To let the menu show how much is in the Trash, add `build/Disk Space.app` under System Settings › Privacy & Security › Full Disk Access. The permission belongs to that app only, not to Python. Rebuilding the app (re-running `install.sh`) needs the permission granted again.

Restart after changes:

```bash
./restart_service.sh
```

### Logs

```
~/Library/Logs/diskspace-output.log
~/Library/Logs/diskspace-error.log
```

## Claude Code skill

This repo is also a Claude Code plugin with a `mac-disk-cleanup` skill. It crawls a Mac for space that rebuilds by itself (DerivedData, simulator leftovers, temp Chrome copies, package caches, stale `node_modules`, worktrees), lists it in a few lines, moves only what you approve to the Trash, and can install this menu bar app for you.

In Claude Code (terminal or the desktop app):

```
/plugin install mac-disk-cleanup --marketplace dennislysenko/disk-space-menubar
```

On older Claude Code versions, add the marketplace first:

```
/plugin marketplace add dennislysenko/disk-space-menubar
/plugin install mac-disk-cleanup@disk-space-menubar
```

Then ask "free up disk space" or run `/mac-disk-cleanup`.

## License

MIT
