"""Watchers for disk space that builds up while agents work: stale Xcode
DerivedData, idle simulators, abandoned git worktrees, stray build folders,
and temp/swap growth that only a reboot clears.

Everything here is read-only. Each check returns plain dataclasses that the
menu bar app renders; deleting is left to explicit, confirmed menu actions.
"""

import calendar
import json
import os
import plistlib
import subprocess
import time
from dataclasses import dataclass, field

HOME = os.path.expanduser('~')
DERIVED_DATA_DIR = os.path.join(HOME, 'Library/Developer/Xcode/DerivedData')
# Where repos (and their worktrees / ad-hoc -derivedDataPath folders) live
SCAN_ROOTS = [os.path.join(HOME, 'dev')]
SCAN_MAX_DEPTH = 6
SCAN_PRUNE = {'node_modules', '.git', 'Pods', '.venv', 'venv', '__pycache__',
              'DerivedData', 'Mobile Documents', 'CloudStorage'}

# Caches aren't stale, just big: list any top-level cache folder over this size
CACHE_DIRS = [os.path.join(HOME, 'Library/Caches'), os.path.join(HOME, '.cache')]
CACHE_EXTRA = [os.path.join(HOME, '.npm'), os.path.join(HOME, 'Library/pnpm/store')]
MIN_CACHE_BYTES = 1_000_000_000
MODEL_CACHES = {'torch', 'whisper', 'huggingface'}

STALE_DERIVED_DATA_DAYS = 7
STALE_SIM_DAYS = 14
STALE_WORKTREE_DAYS = 7
STALE_BUILD_DIR_DAYS = 7
MIN_SIM_BYTES = 50_000_000
# Temp + swap at or above this suggests a reboot (both are cleared on boot)
REBOOT_RECLAIM_BYTES = 15_000_000_000

DAY = 86400


@dataclass
class Item:
    """A folder or simulator that looks reclaimable."""
    kind: str            # 'derived_data' | 'simulator' | 'worktree' | 'build_dir' | 'cache'
    label: str
    path: str
    size: int
    idle_days: float
    note: str = ''
    removable: bool = True   # False = only safe to reveal (e.g. dirty worktree)
    flagged: bool = True     # False = listed for context only (e.g. DerivedData in active use)
    extra: dict = field(default_factory=dict)


@dataclass
class TempStatus:
    tmp_bytes: int
    user_temp_bytes: int
    swap_bytes: int
    uptime_days: float

    @property
    def reclaimable(self):
        return self.tmp_bytes + self.user_temp_bytes + self.swap_bytes

    @property
    def reboot_due(self):
        return self.reclaimable >= REBOOT_RECLAIM_BYTES


@dataclass
class Report:
    derived_data: list
    simulators: list
    runtimes: list       # info only: [(label, size, last_used_days, device_count)]
    worktrees: list
    build_dirs: list
    caches: list
    temp: TempStatus
    scanned_at: float

    @property
    def cleanable_bytes(self):
        # Caches are excluded: they're in use and refill, so they shouldn't trigger the badge
        items = self.derived_data + self.simulators + self.worktrees + self.build_dirs
        return sum(i.size for i in items if i.removable and i.flagged)


def du_bytes(path):
    """Allocated size of a path via `du`, ignoring unreadable subfolders."""
    result = subprocess.run(['du', '-sk', path], capture_output=True, text=True)
    try:
        return int(result.stdout.split()[0]) * 1024
    except (IndexError, ValueError):
        return 0


def mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0


def idle_days(ts, now):
    return (now - ts) / DAY if ts else float('inf')


def walk_projects(roots=SCAN_ROOTS, max_depth=SCAN_MAX_DEPTH):
    """One pass over the project tree. Returns (git repo dirs, build dirs).

    Build dirs are Xcode `-derivedDataPath` folders (e.g. run-on-device's
    build/device) and SwiftPM `.build` folders.
    """
    repos, build_dirs = [], []
    for root in roots:
        base_depth = root.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, _ in os.walk(root):
            if os.path.isdir(os.path.join(dirpath, '.git')):
                repos.append(dirpath)
            is_xcode_build = os.path.isdir(os.path.join(dirpath, 'Build', 'Intermediates.noindex'))
            if is_xcode_build or os.path.basename(dirpath) == '.build':
                build_dirs.append(dirpath)
                dirnames[:] = []
                continue
            if dirpath.count(os.sep) - base_depth >= max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if d not in SCAN_PRUNE and not os.path.islink(os.path.join(dirpath, d))]
    return repos, build_dirs


def check_derived_data(now):
    """Every DerivedData folder, largest first. Stale or orphaned ones are flagged."""
    items = []
    try:
        entries = os.listdir(DERIVED_DATA_DIR)
    except OSError:
        return items
    for name in entries:
        path = os.path.join(DERIVED_DATA_DIR, name)
        if not os.path.isdir(path):
            continue
        if name.endswith('.noindex') or name == 'SDKExplicitPrecompiledModules':
            # Shared across projects; Xcode rebuilds them, but they're never "stale"
            items.append(Item('derived_data', f'Shared: {name}', path, du_bytes(path),
                              idle_days(mtime(path), now), 'module cache', flagged=False))
            continue
        workspace, last = '', 0
        try:
            with open(os.path.join(path, 'info.plist'), 'rb') as f:
                info = plistlib.load(f)
            accessed = info.get('LastAccessedDate')
            last = accessed.timestamp() if accessed else 0
            workspace = info.get('WorkspacePath', '')
        except Exception:
            pass  # some projects have no info.plist; fall back to build-log activity
        if not last:
            last = max(mtime(path), mtime(os.path.join(path, 'Logs', 'Build')),
                       mtime(os.path.join(path, 'Build')))
        orphaned = bool(workspace) and not os.path.exists(workspace)
        idle = idle_days(last, now)
        stale = orphaned or idle >= STALE_DERIVED_DATA_DAYS
        if orphaned:
            note = 'stale: project gone'
        elif stale:
            note = f'stale: unused {idle:.0f}d'
        else:
            note = 'used today' if idle < 1 else f'used {idle:.0f}d ago'
        items.append(Item('derived_data', name.rsplit('-', 1)[0], path, du_bytes(path), idle,
                          note, flagged=stale, extra={'workspace': workspace}))
    # Worktrees of one repo share a project name; tell them apart by checkout folder
    labels = [i.label for i in items]
    for i in items:
        if labels.count(i.label) > 1 and i.extra.get('workspace'):
            i.label += f" ({os.path.basename(os.path.dirname(i.extra['workspace']))})"
    return sorted(items, key=lambda i: -i.size)


def check_simulators(now):
    """Idle simulator devices, plus runtime info (runtimes are never offered for deletion)."""
    devices, runtimes = [], []
    try:
        out = subprocess.run(['xcrun', 'simctl', 'list', 'devices', '--json'],
                             capture_output=True, text=True, timeout=60).stdout
        by_runtime = json.loads(out).get('devices', {})
    except Exception:
        by_runtime = {}
    device_counts = {}
    for runtime_id, devs in by_runtime.items():
        version = runtime_id.rsplit('.', 1)[-1].replace('-', ' ', 1).replace('-', '.')
        device_counts[runtime_id] = len(devs)
        for d in devs:
            size = d.get('dataPathSize') or 0
            data_path = d.get('dataPath', '')
            device_dir = os.path.dirname(data_path)
            # simctl's lastBootedAt is often empty; device.plist is rewritten on boot/shutdown
            last = mtime(os.path.join(device_dir, 'device.plist'))
            idle = idle_days(last, now)
            unavailable = not d.get('isAvailable', True)
            if d.get('state') == 'Booted':
                continue
            if not unavailable and (idle < STALE_SIM_DAYS or size < MIN_SIM_BYTES):
                continue
            note = 'unavailable: runtime missing' if unavailable else f'idle {idle:.0f}d'
            devices.append(Item('simulator', f"{d.get('name')} ({version})", device_dir,
                                size, idle, note,
                                extra={'udid': d.get('udid'), 'unavailable': unavailable}))
    try:
        out = subprocess.run(['xcrun', 'simctl', 'runtime', 'list', '--json'],
                             capture_output=True, text=True, timeout=60).stdout
        for r in json.loads(out).values():
            last_used = r.get('lastUsedAt')
            last_ts = calendar.timegm(time.strptime(last_used, '%Y-%m-%dT%H:%M:%SZ')) \
                if last_used else 0
            runtimes.append((f"iOS {r.get('version')}", r.get('sizeBytes') or 0,
                             idle_days(last_ts, now),
                             device_counts.get(r.get('runtimeIdentifier'), 0)))
    except Exception:
        pass
    return devices, runtimes


def check_worktrees(repos, now):
    items = []
    for repo in repos:
        wt_meta_root = os.path.join(repo, '.git', 'worktrees')
        try:
            names = os.listdir(wt_meta_root)
        except OSError:
            continue
        for name in names:
            meta = os.path.join(wt_meta_root, name)
            try:
                with open(os.path.join(meta, 'gitdir')) as f:
                    wt_path = os.path.dirname(f.read().strip())
            except OSError:
                continue
            repo_label = os.path.relpath(repo, HOME)
            if not os.path.isdir(wt_path):
                items.append(Item('worktree', f'{repo_label}: {name}', wt_path, 0, float('inf'),
                                  'folder gone (prunable)', extra={'repo': repo}))
                continue
            last = max(mtime(os.path.join(meta, 'logs', 'HEAD')), mtime(os.path.join(meta, 'HEAD')),
                       mtime(os.path.join(meta, 'index')))
            idle = idle_days(last, now)
            if idle < STALE_WORKTREE_DAYS:
                continue
            status = subprocess.run(['git', '-C', wt_path, 'status', '--porcelain'],
                                    capture_output=True, text=True).stdout
            dirty = bool(status.strip())
            note = f'idle {idle:.0f}d' + (', uncommitted changes' if dirty else '')
            items.append(Item('worktree', f'{repo_label}: {name}', wt_path, du_bytes(wt_path),
                              idle, note, removable=not dirty, extra={'repo': repo}))
    return items


def check_build_dirs(build_dirs, now):
    items = []
    for path in build_dirs:
        try:
            children = [os.path.join(path, c) for c in os.listdir(path)]
        except OSError:
            continue
        last = max([mtime(path), mtime(os.path.join(path, 'Logs', 'Build'))] +
                   [mtime(c) for c in children])
        idle = idle_days(last, now)
        if idle < STALE_BUILD_DIR_DAYS:
            continue
        items.append(Item('build_dir', os.path.relpath(path, HOME), path, du_bytes(path),
                          idle, f'unused {idle:.0f}d'))
    return items


def check_caches(now):
    paths = list(CACHE_EXTRA)
    for root in CACHE_DIRS:
        try:
            paths += [os.path.join(root, name) for name in os.listdir(root)]
        except OSError:
            pass
    items = []
    for path in paths:
        if not os.path.isdir(path) or os.path.islink(path):
            continue
        size = du_bytes(path)
        if size < MIN_CACHE_BYTES:
            continue
        name = os.path.basename(path)
        note, removable = '', True
        if name in MODEL_CACHES:
            note = 'downloaded models, re-download on next use'
        elif name.startswith('com.apple.') or name == 'CloudKit':
            note, removable = 'managed by macOS', False
        elif path.endswith('pnpm/store'):
            note, removable = 'run `pnpm store prune` instead', False
        items.append(Item('cache', os.path.relpath(path, HOME), path, size,
                          idle_days(mtime(path), now), note, removable))
    return sorted(items, key=lambda i: -i.size)


def check_temp(now):
    tmpdir = os.environ.get('TMPDIR', '')
    # $TMPDIR is .../T/; its parent also holds C/ (caches) which survive reboots
    user_temp = du_bytes(tmpdir) if tmpdir else 0
    swap = 0
    out = subprocess.run(['sysctl', '-n', 'vm.swapusage'], capture_output=True, text=True).stdout
    # "total = 3072.00M  used = 1385.81M  free = 1686.19M  (encrypted)"
    parts = out.split()
    if 'used' in parts:
        value = parts[parts.index('used') + 2]
        units = {'K': 1e3, 'M': 1e6, 'G': 1e9}
        try:
            swap = int(float(value[:-1]) * units.get(value[-1], 1))
        except ValueError:
            pass
    boot = subprocess.run(['sysctl', '-n', 'kern.boottime'], capture_output=True, text=True).stdout
    # "{ sec = 1793204195, usec = 0 } ..."
    try:
        boot_ts = int(boot.split('sec =')[1].split(',')[0])
    except (IndexError, ValueError):
        boot_ts = now
    return TempStatus(du_bytes('/private/tmp'), user_temp, swap, (now - boot_ts) / DAY)


def scan():
    now = time.time()
    repos, build_dirs = walk_projects()
    devices, runtimes = check_simulators(now)
    return Report(
        derived_data=check_derived_data(now),
        simulators=devices,
        runtimes=runtimes,
        worktrees=check_worktrees(repos, now),
        build_dirs=check_build_dirs(build_dirs, now),
        caches=check_caches(now),
        temp=check_temp(now),
        scanned_at=now,
    )


if __name__ == '__main__':
    t0 = time.time()
    report = scan()
    gb = lambda b: f'{b / 1e9:.1f} GB'
    for title, items in (('DerivedData', report.derived_data), ('Simulators', report.simulators),
                         ('Worktrees', report.worktrees), ('Build folders', report.build_dirs),
                         ('Caches', report.caches)):
        print(f'== {title}')
        for i in items:
            print(f'  {gb(i.size):>8}  {i.label}  ({i.note}){"" if i.removable else "  [reveal only]"}')
    print('== Runtimes')
    for label, size, idle, n in report.runtimes:
        print(f'  {gb(size):>8}  {label}  last used {idle:.0f}d ago, {n} devices')
    t = report.temp
    print(f'== Temp: /private/tmp {gb(t.tmp_bytes)}, $TMPDIR {gb(t.user_temp_bytes)}, '
          f'swap {gb(t.swap_bytes)}, up {t.uptime_days:.1f}d, reboot due: {t.reboot_due}')
    print(f'cleanable {gb(report.cleanable_bytes)}, scan took {time.time() - t0:.1f}s')
