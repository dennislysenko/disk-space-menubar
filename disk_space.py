#!/usr/bin/env python3
"""Disk Space Menu Bar - shows free disk space with color-coded SF Symbols."""

import os
import subprocess
import threading
import time
import rumps
from AppKit import (
    NSBundle, NSImage, NSImageSymbolConfiguration, NSColor,
)
from Foundation import NSURL, NSFileManager

import watchers

# The cleanup scan walks ~/dev and runs du, so it runs off the main thread
SCAN_INTERVAL_SECONDS = 15 * 60
# Title gets a "•" once this much is reclaimable, and "↻" when a reboot would help
CLEANABLE_BADGE_BYTES = 5_000_000_000

# Matches what Finder / System Settings report (includes purgeable space:
# snapshots, evictable iCloud files, caches, etc.)
NSURLVolumeAvailableCapacityForImportantUsageKey = "NSURLVolumeAvailableCapacityForImportantUsageKey"

# Hide dock icon
bundle = NSBundle.mainBundle()
info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
if info:
    info['LSUIElement'] = '1'


# Apple switched all user-facing storage figures to decimal in OS X 10.6, so
# Finder/System Settings/`df -H`/diskutil all report decimal GB. Using 1024^3
# (GiB) here would show ~86 where macOS shows ~92.
BYTES_PER_GB = 1_000_000_000


def get_available_gb():
    """Available space as macOS reports it (unallocated + purgeable), in GB."""
    url = NSURL.fileURLWithPath_('/')
    ok, val, _ = url.getResourceValue_forKey_error_(
        None, NSURLVolumeAvailableCapacityForImportantUsageKey, None
    )
    if not ok or val is None:
        return None
    return int(val) / BYTES_PER_GB


def get_disk_info():
    """Get disk space info in GB. Returns (total, used, unallocated, available) or None.

    - total/used/unallocated come from `diskutil apfs list` (strict container view)
    - available comes from the same Foundation API Finder/System Settings use,
      which adds purgeable space (snapshots, caches) on top of unallocated.
    """
    result = subprocess.run(
        ['diskutil', 'apfs', 'list'],
        capture_output=True, text=True
    )
    total = used = unallocated = None
    for line in result.stdout.splitlines():
        if 'Size (Capacity Ceiling)' in line:
            parts = line.split()
            total = int(parts[parts.index('B') - 1]) / BYTES_PER_GB
        elif 'Capacity In Use By Volumes' in line:
            parts = line.split()
            used = int(parts[parts.index('B') - 1]) / BYTES_PER_GB
        elif 'Capacity Not Allocated' in line:
            parts = line.split()
            unallocated = int(parts[parts.index('B') - 1]) / BYTES_PER_GB
        if all(v is not None for v in (total, used, unallocated)):
            break
    if total is None or used is None or unallocated is None:
        return None
    available = get_available_gb()
    if available is None:
        available = unallocated
    return total, used, unallocated, available


def status_config(gb):
    """Return (sf_symbol_name, NSColor) based on free space."""
    if gb > 30:
        return "internaldrive.fill", NSColor.systemGreenColor()
    elif gb > 20:
        return "internaldrive.fill", NSColor.systemYellowColor()
    elif gb > 10:
        return "exclamationmark.triangle.fill", NSColor.systemOrangeColor()
    else:
        return "xmark.circle.fill", NSColor.systemRedColor()


def create_tinted_icon(symbol_name, color):
    """Create a colored SF Symbol NSImage using native symbol configuration."""
    symbol = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol_name, None)
    if symbol is None:
        return None
    config = NSImageSymbolConfiguration.configurationWithHierarchicalColor_(color)
    tinted = symbol.imageWithSymbolConfiguration_(config)
    tinted.setTemplate_(False)
    return tinted


def fmt_size(num_bytes):
    if num_bytes >= BYTES_PER_GB:
        return f"{num_bytes / BYTES_PER_GB:.1f} GB"
    return f"{num_bytes / 1_000_000:.0f} MB"


def fmt_age(seconds):
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds / 60:.0f} min ago"
    return f"{seconds / 3600:.0f} h ago"


def move_to_trash(path):
    """Move to the Trash (recoverable with Put Back), not a permanent delete."""
    ok, _, err = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
        NSURL.fileURLWithPath_(path), None, None
    )
    return ok, (err.localizedDescription() if err else '')


def remove_item(item):
    """Perform the cleanup for one watchers.Item. Returns (ok, error message)."""
    if item.kind == 'simulator':
        r = subprocess.run(['xcrun', 'simctl', 'delete', item.extra['udid']],
                           capture_output=True, text=True)
        return r.returncode == 0, r.stderr.strip()
    if item.kind == 'worktree':
        repo = item.extra['repo']
        # No --force: git refuses if the worktree has changes. The branch is kept.
        cmd = ['git', '-C', repo, 'worktree', 'remove', item.path] if os.path.isdir(item.path) \
            else ['git', '-C', repo, 'worktree', 'prune']
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode == 0, r.stderr.strip()
    return move_to_trash(item.path)


# (section title, Report attribute, confirm button) in menu order
SECTIONS = [
    ("Stale DerivedData", 'derived_data', "Move to Trash"),
    ("Stray build folders", 'build_dirs', "Move to Trash"),
    ("Idle simulators", 'simulators', "Delete"),
    ("Stale worktrees", 'worktrees', "Remove"),
    ("Big caches", 'caches', "Move to Trash"),
]
KIND_VERBS = {'derived_data': "Move to Trash", 'build_dir': "Move to Trash",
              'simulator': "Delete", 'worktree': "Remove", 'cache': "Move to Trash"}


class DiskSpaceApp(rumps.App):
    def __init__(self):
        info = get_disk_info()
        self._available = info[3] if info else None
        self._report = None
        self._pending_report = None
        self._scanning = False
        super().__init__(self._compose_title(), quit_button=None)
        self._total_item = rumps.MenuItem("")
        self._used_item = rumps.MenuItem("")
        self._available_item = rumps.MenuItem("")
        self._unallocated_item = rumps.MenuItem("")
        self._cleanup_header = rumps.MenuItem("Cleanup: scanning…")
        self._section_items = {attr: rumps.MenuItem(title) for title, attr, _ in SECTIONS}
        self._temp_item = rumps.MenuItem("Temp & swap")
        self.menu = [
            self._total_item,
            self._used_item,
            self._available_item,
            self._unallocated_item,
            None,
            self._cleanup_header,
            *self._section_items.values(),
            self._temp_item,
            rumps.MenuItem("Rescan now", callback=self._rescan),
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]
        for item in (*self._section_items.values(), self._temp_item):
            item.hidden = True
        if info:
            self._update_menu_items(*info)

    def _compose_title(self):
        if self._available is None:
            return "??GB"
        badge = ""
        if self._report:
            if self._report.cleanable_bytes >= CLEANABLE_BADGE_BYTES:
                badge += " •"
            if self._report.temp.reboot_due:
                badge += " ↻"
        return f" {self._available:.0f}GB{badge}"

    # --- cleanup scan (runs on a background thread, rendered on the main thread) ---

    def _start_scan(self):
        if self._scanning:
            return
        self._scanning = True
        self._cleanup_header.title = "Cleanup: scanning…"
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            self._pending_report = watchers.scan()
        except Exception as e:
            print(f"Cleanup scan failed: {e}")
        finally:
            self._scanning = False

    @rumps.timer(2)
    def apply_pending_report(self, _):
        if self._pending_report is None:
            return
        self._report, self._pending_report = self._pending_report, None
        self._render_report()
        self.title = self._compose_title()

    @rumps.timer(SCAN_INTERVAL_SECONDS)
    def periodic_scan(self, _):
        self._start_scan()

    def _rescan(self, _=None):
        self._start_scan()

    def _update_cleanup_header(self):
        if self._report and not self._scanning:
            total = fmt_size(self._report.cleanable_bytes)
            age = fmt_age(time.time() - self._report.scanned_at)
            self._cleanup_header.title = f"Cleanup: {total} reclaimable · scanned {age}"

    def _render_report(self):
        report = self._report
        for title, attr, _ in SECTIONS:
            items = getattr(report, attr)
            section = self._section_items[attr]
            if len(section):  # rumps' clear() crashes if no submenu exists yet
                section.clear()
            section.title = f"{title}: {len(items)} · {fmt_size(sum(i.size for i in items))}"
            for item in items:
                label = f"{item.label} · {fmt_size(item.size)}"
                if item.note:
                    label += f" · {item.note}"
                menu_item = rumps.MenuItem(label, callback=self._on_item)
                menu_item.cleanup_item = item
                section.add(menu_item)
            removable = [i for i in items if i.removable]
            if len(removable) > 1 and attr != 'caches':
                section.add(None)
                all_item = rumps.MenuItem(f"Clean up all {len(removable)}…", callback=self._on_section)
                all_item.section_attr = attr
                section.add(all_item)
            if attr == 'simulators' and report.runtimes:
                section.add(None)
                for label, size, idle, devices in report.runtimes:
                    section.add(rumps.MenuItem(
                        f"Runtime {label} · {fmt_size(size)} · {devices} devices · used {idle:.0f}d ago"))
                # Show the section for runtime info even when no device is idle
                items = items or report.runtimes
            section.hidden = not items

        t = report.temp
        if len(self._temp_item):
            self._temp_item.clear()
        if t.reboot_due:
            self._temp_item.title = f"Reboot recommended: {fmt_size(t.reclaimable)} in temp & swap"
        else:
            self._temp_item.title = f"Temp & swap: {fmt_size(t.reclaimable)}"
        self._temp_item.update([
            rumps.MenuItem(f"/private/tmp: {fmt_size(t.tmp_bytes)}"),
            rumps.MenuItem(f"Your temp folder: {fmt_size(t.user_temp_bytes)}"),
            rumps.MenuItem(f"Swap: {fmt_size(t.swap_bytes)}"),
            rumps.MenuItem(f"Up {t.uptime_days:.1f} days · all of the above clears on reboot"),
        ])
        self._temp_item.hidden = False
        self._update_cleanup_header()

    def _on_item(self, sender):
        item = sender.cleanup_item
        if not item.removable:
            subprocess.run(['open', '-R', item.path])
            return
        verb = KIND_VERBS[item.kind]
        message = f"{item.path}\n\n{fmt_size(item.size)}" + (f" · {item.note}" if item.note else "")
        choice = rumps.alert(title=f"{verb}: {item.label}?", message=message,
                             ok=verb, cancel="Cancel", other="Reveal in Finder")
        if choice == -1:
            subprocess.run(['open', '-R', item.path])
            return
        if choice != 1:
            return
        ok, err = remove_item(item)
        if not ok:
            rumps.alert(title=f"Couldn't clean up {item.label}", message=err or "Unknown error")
        self._start_scan()

    def _on_section(self, sender):
        attr = sender.section_attr
        title, verb = next((t, v) for t, a, v in SECTIONS if a == attr)
        items = [i for i in getattr(self._report, attr) if i.removable]
        listing = "\n".join(f"• {i.label} ({fmt_size(i.size)})" for i in items[:15])
        if len(items) > 15:
            listing += f"\n…and {len(items) - 15} more"
        total = fmt_size(sum(i.size for i in items))
        if rumps.alert(title=f"{verb} {len(items)} items ({total})?", message=listing,
                       ok=verb, cancel="Cancel") != 1:
            return
        failures = []
        for item in items:
            ok, err = remove_item(item)
            if not ok:
                failures.append(f"{item.label}: {err or 'unknown error'}")
        if failures:
            rumps.alert(title=f"Some {title.lower()} couldn't be cleaned up", message="\n".join(failures))
        self._start_scan()

    def _set_icon_direct(self, nsimage):
        """Set icon directly on the status item, bypassing rumps' 20x20 resize."""
        try:
            self._nsapp.nsstatusitem.button().setImage_(nsimage)
        except AttributeError:
            pass

    @rumps.timer(1)
    def first_run(self, sender):
        info = get_disk_info()
        if info:
            _, _, _, available = info
            symbol_name, color = status_config(available)
            icon = create_tinted_icon(symbol_name, color)
            if icon:
                self._set_icon_direct(icon)
        self._start_scan()
        sender.stop()

    def _update_menu_items(self, total, used, unallocated, available):
        pct_used = used / total * 100
        self._total_item.title = f"Total:        {total:.0f} GB"
        self._used_item.title = f"Used:         {used:.0f} GB  ({pct_used:.0f}%)"
        self._available_item.title = f"Available:    {available:.0f} GB  (incl. purgeable)"
        self._unallocated_item.title = f"Unallocated:  {unallocated:.0f} GB"

    @rumps.timer(60)
    def refresh(self, _):
        info = get_disk_info()
        self._available = info[3] if info else None
        self.title = self._compose_title()
        if info:
            total, used, unallocated, available = info
            symbol_name, color = status_config(available)
            icon = create_tinted_icon(symbol_name, color)
            if icon:
                self._set_icon_direct(icon)
            self._update_menu_items(total, used, unallocated, available)
        self._update_cleanup_header()


if __name__ == '__main__':
    DiskSpaceApp().run()
