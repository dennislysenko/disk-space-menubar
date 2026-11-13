#!/bin/bash
# Move approved paths to the Trash and record them in $DATA_DIR/cleaned.tsv.
# Usage: clean.sh <category> <path>...     (category = the scan.sh category, e.g. ChromeClones)
# Never deletes outright: uses `trash` (macOS 26+ /usr/bin/trash, or `brew install trash`),
# falling back to Finder via osascript.
set -u
[ $# -ge 2 ] || { echo "usage: clean.sh <category> <path>..." >&2; exit 2; }
CATEGORY="$1"; shift
DATA_DIR="${MAC_DISK_CLEANUP_DATA:-$HOME/.local/share/mac-disk-cleanup}"
LOG="$DATA_DIR/cleaned.tsv"
mkdir -p "$DATA_DIR"
[ -f "$LOG" ] || printf 'date\tcategory\tpath\tkb\n' > "$LOG"
RUN=$(date '+%Y-%m-%d %H:%M')

to_trash() {
  if command -v trash >/dev/null 2>&1; then
    trash "$1"
  else
    osascript -e 'on run argv' -e 'tell application "Finder" to delete (POSIX file (item 1 of argv) as alias)' -e 'end run' "$1" >/dev/null
  fi
}

total=0; moved=0; failed=0
for p in "$@"; do
  if [ ! -e "$p" ]; then echo "skip (missing): $p" >&2; continue; fi
  k=$(du -sk "$p" 2>/dev/null | cut -f1); k=${k:-0}
  if to_trash "$p" 2>/dev/null && [ ! -e "$p" ]; then
    printf '%s\t%s\t%s\t%s\n' "$RUN" "$CATEGORY" "$p" "$k" >> "$LOG"
    total=$((total + k)); moved=$((moved + 1))
  else
    echo "failed: $p" >&2; failed=$((failed + 1))
  fi
done
awk -v k="$total" -v m="$moved" -v f="$failed" -v c="$CATEGORY" \
  'BEGIN{printf "%s: moved %d item(s), %.1f GB to the Trash%s\n", c, m, k/1048576, (f ? sprintf(", %d failed", f) : "")}'
