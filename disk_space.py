#!/usr/bin/env python3
"""Disk Space Menu Bar - shows free disk space with color-coded SF Symbols."""

import subprocess
import rumps
from AppKit import (
    NSBundle, NSImage, NSImageSymbolConfiguration, NSColor,
)

# Hide dock icon
bundle = NSBundle.mainBundle()
info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
if info:
    info['LSUIElement'] = '1'


def get_disk_info():
    """Get disk space info in GB using diskutil. Returns (total, used, free) or None."""
    result = subprocess.run(
        ['diskutil', 'apfs', 'list'],
        capture_output=True, text=True
    )
    total = used = free = None
    for line in result.stdout.splitlines():
        if 'Size (Capacity Ceiling)' in line:
            parts = line.split()
            total = int(parts[parts.index('B') - 1]) / (1024 ** 3)
        elif 'Capacity In Use By Volumes' in line:
            parts = line.split()
            used = int(parts[parts.index('B') - 1]) / (1024 ** 3)
        elif 'Capacity Not Allocated' in line:
            parts = line.split()
            free = int(parts[parts.index('B') - 1]) / (1024 ** 3)
        if all(v is not None for v in (total, used, free)):
            return total, used, free
    return None


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
            _, _, free = info
            title = f" {free:.0f}GB"
        else:
            title = "??GB"
        super().__init__(title, quit_button=None)
        self._total_item = rumps.MenuItem("")
        self._used_item = rumps.MenuItem("")
        self._free_item = rumps.MenuItem("")
        self.menu = [
            self._total_item,
            self._used_item,
            self._free_item,
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
            _, _, free = info
            symbol_name, color = status_config(free)
            icon = create_tinted_icon(symbol_name, color)
            if icon:
                self._set_icon_direct(icon)
        sender.stop()

    def _update_menu_items(self, total, used, free):
        pct_used = used / total * 100
        self._total_item.title = f"Total:  {total:.0f} GB"
        self._used_item.title = f"Used:   {used:.0f} GB  ({pct_used:.0f}%)"
        self._free_item.title = f"Free:   {free:.0f} GB"

    @rumps.timer(60)
    def refresh(self, _):
        info = get_disk_info()
        if info:
            total, used, free = info
            self.title = f" {free:.0f}GB"
            symbol_name, color = status_config(free)
            icon = create_tinted_icon(symbol_name, color)
            if icon:
                self._set_icon_direct(icon)
            self._update_menu_items(total, used, free)
        else:
            self.title = "??GB"


if __name__ == '__main__':
    DiskSpaceApp().run()
