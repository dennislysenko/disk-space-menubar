#!/usr/bin/env python3
"""Disk Space Menu Bar - shows free disk space with color-coded SF Symbols."""

import subprocess
import rumps
from AppKit import (
    NSBundle, NSImage, NSImageSymbolConfiguration, NSColor,
)
from Foundation import NSURL

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


class DiskSpaceApp(rumps.App):
    def __init__(self):
        info = get_disk_info()
        if info:
            _, _, _, available = info
            title = f" {available:.0f}GB"
        else:
            title = "??GB"
        super().__init__(title, quit_button=None)
        self._total_item = rumps.MenuItem("")
        self._used_item = rumps.MenuItem("")
        self._available_item = rumps.MenuItem("")
        self._unallocated_item = rumps.MenuItem("")
        self.menu = [
            self._total_item,
            self._used_item,
            self._available_item,
            self._unallocated_item,
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]
        if info:
            self._update_menu_items(*info)

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
        if info:
            total, used, unallocated, available = info
            self.title = f" {available:.0f}GB"
            symbol_name, color = status_config(available)
            icon = create_tinted_icon(symbol_name, color)
            if icon:
                self._set_icon_direct(icon)
            self._update_menu_items(total, used, unallocated, available)
        else:
            self.title = "??GB"


if __name__ == '__main__':
    DiskSpaceApp().run()
