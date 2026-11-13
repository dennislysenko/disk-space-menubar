#!/bin/bash
# Report regenerable ("ephemeral") disk space on a Mac. Read-only: deletes nothing.
# Output: one line per finding:  <GB>|<category>|<path>|<note>
# Each finding is also appended to $DATA_DIR/findings.tsv (date, category, path, KB)
# so recurring.sh can spot what keeps coming back.
# Usage: scan.sh [--dev-root ~/dev] [--idle-days 30] [--no-log]
set -u
shopt -s nullglob

DEV_ROOT="$HOME/dev"
IDLE_DAYS=30
DATA_DIR="${MAC_DISK_CLEANUP_DATA:-$HOME/.local/share/mac-disk-cleanup}"
LOG="$DATA_DIR/findings.tsv"
RUN=$(date '+%Y-%m-%d %H:%M')
while [ $# -gt 0 ]; do
  case "$1" in
    --dev-root) DEV_ROOT="$2"; shift 2 ;;
    --idle-days) IDLE_DAYS="$2"; shift 2 ;;
    --no-log) LOG=""; shift ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done

kb() { du -sk "$@" 2>/dev/null | awk '{s+=$1} END{print s+0}'; }
if [ -n "$LOG" ]; then
  mkdir -p "$DATA_DIR"
  [ -f "$LOG" ] || printf 'date\tcategory\tpath\tkb\n' > "$LOG"
fi
emit() { # kb category path note
  [ "$1" -lt 51200 ] && return   # skip anything under 50 MB
  [ -n "$LOG" ] && printf '%s\t%s\t%s\t%s\n' "$RUN" "$2" "$3" "$1" >> "$LOG"
  awk -v k="$1" -v c="$2" -v p="$3" -v n="$4" 'BEGIN{printf "%.1f|%s|%s|%s\n", k/1048576, c, p, n}'
}

TMP=$(getconf DARWIN_USER_TEMP_DIR); TMP=${TMP%/}
VARX="${TMP%/T}/X"
XC="$HOME/Library/Developer/Xcode"
SIMDEV="$HOME/Library/Developer/CoreSimulator/Devices"

echo "# free: $(df -h /System/Volumes/Data | awk 'NR==2{print $4}')  trash: $(du -sh "$HOME/.Trash" 2>/dev/null | cut -f1 || echo '?')  swap: $(sysctl -n vm.swapusage | awk '{print $6}')"
echo "# live: builds=$(pgrep -f 'xcodebuild|XCBBuildService|swift-build' | wc -l | tr -d ' ') booted_sims=$(xcrun simctl list devices booted 2>/dev/null | grep -c Booted)"

# --- Xcode ---
for d in "$XC"/DerivedData/*/; do
  d=${d%/}; n=${d##*/}
  ws=""; [ -f "$d/info.plist" ] && ws=$(/usr/libexec/PlistBuddy -c 'Print :WorkspacePath' "$d/info.plist" 2>/dev/null)
  if [ -z "$ws" ]; then note="shared module cache, rebuilt on next build"
  elif [ ! -e "$ws" ]; then note="ORPHAN: project gone ($ws)"
  else note="project: $ws (last built $(stat -f %Sm -t %F "$d"))"; fi
  emit "$(kb "$d")" DerivedData "$d" "$note"
done
for d in "$XC"/iOS\ DeviceSupport/* "$XC"/watchOS\ DeviceSupport/*; do
  emit "$(kb "$d")" DeviceSupport "$d" "symbols for a connected device OS; re-copied when that device is plugged in"
done
emit "$(kb "$HOME/Library/Containers/com.apple.CoreDevice.CoreDeviceService/Data/Library/Caches/AppInstallationBinaryDeltas")" InstallDeltas \
  "$HOME/Library/Containers/com.apple.CoreDevice.CoreDeviceService/Data/Library/Caches/AppInstallationBinaryDeltas" "device install cache; next install is a full copy"
k=$(kb "$TMP"/XcodeDistPipeline.*); emit "$k" XcodeExportTemp "$TMP/XcodeDistPipeline.*" "leftovers from archive export/upload"
emit "$(kb "$XC/Archives")" Archives "$XC/Archives" "NOT ephemeral: holds dSYMs; only remove older builds of the same version"

# --- Simulators ---
xcrun simctl list devices unavailable 2>/dev/null | grep -q '(' && echo "0.0|Simulators|unavailable devices|run: xcrun simctl delete unavailable"
for dev in "$SIMDEV"/*/; do
  st=$(/usr/libexec/PlistBuddy -c 'Print :state' "$dev/device.plist" 2>/dev/null); [ "$st" = 3 ] && continue
  name=$(/usr/libexec/PlistBuddy -c 'Print :name' "$dev/device.plist" 2>/dev/null)
  k=$(kb "$dev/data/Library/Caches/com.apple.containermanagerd/Dead" "$dev/data/var/db/diagnostics" "$dev/data/var/db/uuidtext")
  emit "$k" SimLeftovers "$dev" "$name: old app containers (Caches/com.apple.containermanagerd/Dead) + logs (var/db/diagnostics, uuidtext)"
done
for dev in "$SIMDEV"/*/; do
  last=$(stat -f %m "$dev/data" 2>/dev/null || echo 0)
  if [ $(( ($(date +%s) - last) / 86400 )) -gt "$IDLE_DAYS" ]; then
    name=$(/usr/libexec/PlistBuddy -c 'Print :name' "$dev/device.plist" 2>/dev/null)
    emit "$(kb "$dev")" IdleSimulator "$dev" "$name idle >${IDLE_DAYS}d; xcrun simctl delete <udid>"
  fi
done

# --- Temp ---
k=$(kb "$VARX"/com.google.Chrome.code_sign_clone/*); emit "$k" ChromeClones "$VARX/com.google.Chrome.code_sign_clone" "Chrome copies left by killed (often Playwright) launches; keep the newest if Chrome is running"
emit "$(kb /private/tmp)" Tmp /private/tmp "check contents; cleared on reboot"

# --- Package / tool caches ---
for p in "$HOME/Library/Caches/org.swift.swiftpm|SwiftPM cache; re-downloaded (don't remove mid-build)" \
         "$HOME/Library/Caches/ms-playwright|Playwright browser downloads; re-downloaded" \
         "$HOME/Library/Caches/CocoaPods|pod cache; pod cache clean --all" \
         "$HOME/Library/Caches/Homebrew|brew cleanup -s" \
         "$HOME/.npm/_cacache|npm cache clean --force" \
         "$HOME/Library/Caches/Yarn|yarn cache clean" \
         "$HOME/Library/Caches/pip|pip3 cache purge" \
         "$HOME/.cache/uv|uv cache clean" \
         "$HOME/.bun/install/cache|bun pm cache rm" \
         "$HOME/.gradle/caches|Gradle caches; re-downloaded" \
         "$HOME/Library/pnpm/store|pnpm store prune (never trash the store directly)" \
         "$HOME/Library/Caches/JetBrains|IDE caches"; do
  path=${p%%|*}; note=${p#*|}; emit "$(kb "$path")" ToolCache "$path" "$note"
done
command -v docker >/dev/null && echo "0.0|Docker|docker system df|check: docker system prune (images/build cache)"

# --- Project build output in DEV_ROOT ---
if [ -d "$DEV_ROOT" ]; then
  now=$(date +%s)
  while IFS= read -r d; do
    p=$(dirname "$d")
    last=$(git -C "$p" log -1 --format=%ct 2>/dev/null || stat -f %m "$p")
    idle=$(( (now - ${last:-now}) / 86400 ))
    [ "$idle" -gt "$IDLE_DAYS" ] && emit "$(kb "$d")" "$(basename "$d")" "$d" "project idle ${idle}d; reinstall/rebuild"
  done < <(find "$DEV_ROOT" -maxdepth 6 \( -name node_modules -o -name .build -o -name Pods -o -name .next -o -name .gradle \) -type d -prune 2>/dev/null)

  # git worktrees: report only, never auto-remove
  while IFS= read -r g; do
    r=$(dirname "$g")
    git -C "$r" worktree list --porcelain 2>/dev/null | awk '/^worktree /{print substr($0,10)}' | tail -n +2 | while IFS= read -r w; do
      [ -d "$w" ] || continue
      dirty=$(git -C "$w" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
      emit "$(kb "$w")" Worktree "$w" "uncommitted files: $dirty; last change $(stat -f %Sm -t %F "$w")"
    done
  done < <(find "$DEV_ROOT" -maxdepth 4 -name .git -type d -not -path '*/node_modules/*' 2>/dev/null)
fi
