#!/usr/bin/env python3
"""Disk Space Menu Bar - shows free disk space with color coding."""

import subprocess
import rumps
from AppKit import NSBundle

# Hide dock icon
bundle = NSBundle.mainBundle()
info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
if info:
    info['LSUIElement'] = '1'


def get_free_gb():
    """Get free disk space in GB using diskutil."""
    result = subprocess.run(
        ['diskutil', 'apfs', 'list'],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if 'Capacity Not Allocated' in line:
            parts = line.split()
            bytes_idx = parts.index('B')
            raw_bytes = int(parts[bytes_idx - 1])
            return raw_bytes / (1024 ** 3)
    return None


def status_icon(gb):
    """Return an icon based on free space."""
    if gb > 30:
        return "💾"
    elif gb > 20:
        return "⚠️"
    elif gb > 10:
        return "🚨"
    else:
        return "⛔"


class DiskSpaceApp(rumps.App):
    def __init__(self):
        gb = get_free_gb()
        if gb is not None:
            title = f"{status_icon(gb)} {gb:.0f}GB"
        else:
            title = "💾 ??GB"
        super().__init__(title, quit_button=None)
        self.menu = [rumps.MenuItem("Quit", callback=rumps.quit_application)]

    @rumps.timer(60)
    def refresh(self, _):
        gb = get_free_gb()
        if gb is not None:
            self.title = f"{status_icon(gb)} {gb:.0f}GB"
        else:
            self.title = "💾 ??GB"


if __name__ == '__main__':
    DiskSpaceApp().run()
