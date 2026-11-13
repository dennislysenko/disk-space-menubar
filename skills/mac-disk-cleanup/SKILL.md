---
name: mac-disk-cleanup
description: Find and safely reclaim regenerable disk space on a Mac, especially a developer Mac (Xcode DerivedData, simulators, temp Chrome copies, package caches, stale node_modules, worktrees). Reports first, moves only approved items to the Trash. Also installs the Disk Space menubar app that keeps watching for this. Use when the user asks to install the disk space menubar app, or when the user says "disk is full", "free up space", "crawl for disk opportunities", "what can I clean up", or asks why free space keeps shrinking.
---

# Mac disk cleanup

Find space that rebuilds or re-downloads by itself, show a short list, and move only what the user approves to the Trash.

## Rules

1. **Report first, delete nothing** until the user picks items.
2. **Trash, never `rm`.** Use `clean.sh` (below), which calls `trash <path>…` (built into macOS 26+ at `/usr/bin/trash`; on older macOS use `brew install trash`, or `osascript -e 'tell application "Finder" to delete POSIX file "<path>"'`). Tool-native cleanup commands (`brew cleanup -s`, `pnpm store prune`, `xcrun simctl delete unavailable`, `npm cache clean --force`) are fine.
3. **Never remove the only copy of something.** Photos, Messages, Notes, WhatsApp, Mail, Documents, Downloads, chat/session logs and app data are not "ephemeral" even when large. Ask whether the Mac has a backup; if not, say so.
4. **Check for live use before trashing shared build state.** Run `pgrep -fl 'xcodebuild|XCBBuildService|swift-build'` and `xcrun simctl list devices booted`. If anything is building or booted, skip SwiftPM caches, DerivedData and simulator data (or ask). Removing a SwiftPM cache mid-build leaves half-cloned packages.
5. **Report as short bullets, 15–20 lines max**: number, what, size, how it comes back. Lead with the safe items; put "your call" items in a line or two.
6. After trashing, report **how much went to the Trash** and the Trash total. Space is only freed when the Trash is emptied; don't empty it for the user.

## Steps

All scripts sit next to this SKILL.md, in this skill's base directory (`$SKILL` below). History lives in `~/.local/share/mac-disk-cleanup/` (`findings.tsv`, `cleaned.tsv`).

1. **Start a full scan in the background** with the [disk-analyzer CLI](https://github.com/dennislysenko/macos-disk-analyzer) (takes ~3–10 min; its snapshots are what `changes` compares):
   ```bash
   SCANS=$(sed -n 's/^output_dir *= *"\(.*\)"/\1/p' ~/.config/disk-analyzer/config.toml 2>/dev/null); SCANS=${SCANS:-$HOME/.local/share/mac-disk-cleanup/scans}; SCANS=${SCANS/#\~/$HOME}
   disk-analyzer scan ~ -q -m 1 -o "$SCANS"      # run_in_background
   ```
   If `disk-analyzer` isn't installed, offer to install it once (`curl -fsSL https://raw.githubusercontent.com/dennislysenko/macos-disk-analyzer/main/install.sh | sh`) and skip this step if they decline.
2. **Run the quick scanner** (read-only, ~1 min; also appends to `findings.tsv`):
   ```bash
   bash "$SKILL/scan.sh"            # options: --dev-root ~/code --idle-days 30 --no-log
   ```
   Each line is `GB|category|path|note`. The first two lines show free space, Trash, swap, live builds and booted simulators.
3. **Check what keeps coming back and what grew:**
   ```bash
   bash "$SKILL/recurring.sh"                       # categories cleaned before that are back
   disk-analyzer changes --days 7 -o "$SCANS"      # after the background scan finishes
   ```
4. **Report** (bullets, rule 5): the safe items ranked by size (table below), then at most two extra lines: **Recurring** (category, how often, GB each time, and the likely cause from *Recurring culprits* below) and **Growing** (top 1–3 folders from `changes` that aren't already in the list, with what they are). Ask which numbers to remove.
5. **On approval:** re-run the live-use check, then move each group with
   ```bash
   bash "$SKILL/clean.sh" <Category> <path>...      # trashes and records in cleaned.tsv
   ```
   using the scan.sh category name, so `recurring.sh` can track it. For simulator leftovers, recreate the emptied `…/com.apple.containermanagerd/Dead` folder (`mkdir -p`). For worktrees, `git -C <repo> worktree prune` afterwards (the branch stays). Never `git worktree remove --force` a worktree with uncommitted changes. Tool-native commands (`brew cleanup -s`, `pnpm store prune`) don't go through clean.sh.
6. **Report:** what went, total size, Trash size, free space before/after.

## Recurring culprits (what to say when something keeps coming back)

- **ChromeClones**: an automation tool (Playwright, Puppeteer, Claude in Chrome) is killing Chrome instead of closing it. Close browsers cleanly at the end of runs, or use Playwright's bundled Chromium instead of the installed Chrome.
- **DerivedData** for the same project: parallel worktrees or agents each get their own DerivedData; trash ones whose worktree is gone.
- **SimLeftovers**: frequent reinstalls on the same simulator; reset that simulator (`xcrun simctl erase <udid>`) when it's not in use.
- **XcodeExportTemp**: archive exports/uploads; harmless to clear after each release.
- **Swap** above ~10 GB: too many simulators or apps at once for the RAM; a restart clears it.

## Install the Disk Space menubar app (optional, offer once)

[disk-space-menubar](https://github.com/dennislysenko/disk-space-menubar) shows free space in the menu bar and lists the same reclaimable items (stale DerivedData, old archives, idle simulators, simulator leftovers, worktrees, caches, temp/swap, Trash), moving items to the Trash only after a confirm. Offer it after a cleanup, or install when the user asks. Needs Python 3 and Xcode Command Line Tools (`xcode-select --install`, for `swiftc`).

```bash
git clone https://github.com/dennislysenko/disk-space-menubar.git ~/disk-space-menubar
cd ~/disk-space-menubar
python3 -m venv venv && venv/bin/pip install -r requirements.txt
./install.sh          # builds "build/Disk Space.app", installs a LaunchAgent, starts it at login
```

- Check it's running: a disk icon with free GB appears in the menu bar; logs are in `~/Library/Logs/diskspace-output.log` (a `scan:` line every few minutes).
- To show the Trash size, the user grants Full Disk Access to the app (not to Python): System Settings › Privacy & Security › Full Disk Access › **+** › choose `~/disk-space-menubar/build/Disk Space.app`. Open that pane for them with `open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"`. Re-running `install.sh` rebuilds the app and needs the grant again.
- Restart after changes: `./restart_service.sh`. Uninstall: `launchctl bootout gui/$(id -u)/com.diskspace.menubar`, then `trash ~/Library/LaunchAgents/com.diskspace.menubar.plist ~/disk-space-menubar`.

## What is safe (regenerates)

- **DerivedData** `~/Library/Developer/Xcode/DerivedData/<Project>-<hash>`: rebuilt on next build. ORPHAN ones (project path gone) are free wins. `ModuleCache.noindex` / `SDKExplicitPrecompiledModules` are shared: safe, but every app's next build is slower once.
- **Device install deltas** `~/Library/Containers/com.apple.CoreDevice.CoreDeviceService/Data/Library/Caches/AppInstallationBinaryDeltas`: next device install is a full copy.
- **iOS DeviceSupport** `~/Library/Developer/Xcode/iOS DeviceSupport/*`: old OS versions you no longer have devices on.
- **Xcode export temp** `$(getconf DARWIN_USER_TEMP_DIR)XcodeDistPipeline.*`: leftovers from archive upload/export.
- **Simulator leftovers** inside each non-booted device: `data/Library/Caches/com.apple.containermanagerd/Dead` (old app copies from reinstalls, never reaped), `data/var/db/diagnostics`, `data/var/db/uuidtext` (logs). Installed apps stay. Also `xcrun simctl delete unavailable`.
- **Chrome code-sign clones** `<var/folders>/X/com.google.Chrome.code_sign_clone/*`: ~1.4 GB each, left behind when Chrome (often a Playwright/automation launch) is killed instead of quit. Keep the newest if Chrome is running. They come back while automation keeps killing Chrome.
- **Package caches**: SwiftPM, CocoaPods, Homebrew, npm, Yarn, pip, uv, bun, Gradle, Playwright browser downloads (`~/Library/Caches/ms-playwright`). Use each tool's own clean command where it has one; `pnpm store prune`, never trash the pnpm store directly.
- **node_modules / .build / Pods / .next** in projects idle > 30 days: reinstall with the project's package manager.
- **Swap and temp**: only a restart clears swap (`/private/var/vm`); `purge` doesn't help.

## Your call (ask, explain trade-off)

- **Xcode archives**: hold the dSYMs for crash symbolication. Older builds of the *same version* are usually safe; the only archive of a shipped version is not, unless the crash reporter already has its dSYMs. Never touch an archive waiting to be uploaded.
- **Idle simulators / unused simulator runtimes** (`xcrun simctl runtime list`; ~8 GB each): only if the user won't test on that OS.
- **Git worktrees**: only clean ones whose branch is merged or pushed. Show branch, size, uncommitted-file count.
- **Old browser profiles** of browsers the user stopped using (export bookmarks/passwords first).
- **Playwright MCP profiles** `~/Library/Caches/ms-playwright-mcp/mcp-chrome-*`: these hold the automation browser's logins, not just cache.
- **ML model caches** (`~/.cache/torch`, `~/.cache/huggingface`, Ollama): re-download is slow; check recent use.

## Gotchas

- `du` on `/System/Volumes/Update` double-counts: during a macOS update prep it mounts the system volume at `Update/mnt1`. The real update payload is ~3 GB, cleared by installing the update.
- `xcrun simctl runtime list` can show stuck "Deleting" ghost entries sharing one path; don't count them twice.
- `~/.Trash` needs Full Disk Access for the terminal app to measure it.
- APFS frees space a minute or two after the Trash is emptied; re-check `df -h /System/Volumes/Data`.
- Free space that drops fast with nothing obvious: check swap (`sysctl vm.swapusage`), Chrome clones, and DerivedData rebuilt by parallel agent sessions.
