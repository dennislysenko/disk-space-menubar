#!/bin/bash
# Which cleanup categories keep coming back? Reads $DATA_DIR/cleaned.tsv (what was
# trashed, by clean.sh) and $DATA_DIR/findings.tsv (what each scan.sh run found).
# Prints one line per category that was cleaned before and has been found again since.
set -u
DATA_DIR="${MAC_DISK_CLEANUP_DATA:-$HOME/.local/share/mac-disk-cleanup}"
CLEANED="$DATA_DIR/cleaned.tsv"; FOUND="$DATA_DIR/findings.tsv"
[ -s "$CLEANED" ] || { echo "No cleanups recorded yet (history starts with the first clean.sh run)."; exit 0; }

awk -F'\t' '
  FNR == 1 { next }                                   # headers
  FILENAME == ARGV[1] {                               # cleaned.tsv
    c = $2; n[c]++; gb[c] += $4 / 1048576
    if (!(c in first) || $1 < first[c]) first[c] = $1
    if ($1 > last[c]) last[c] = $1
    runs[c, substr($1, 1, 16)] = 1
    next
  }
  {                                                   # findings.tsv
    c = $2; if (!(c in n) || $1 <= first[c]) next     # only findings after a cleanup
    seen[c, $1] += $4 / 1048576
    if ($1 > newest[c]) newest[c] = $1
  }
  END {
    for (c in n) {
      times = 0; for (k in runs) { split(k, a, SUBSEP); if (a[1] == c) times++ }
      back = (c in newest) ? seen[c, newest[c]] : 0
      if (times < 2 && back < 0.5) continue
      printf "%-16s cleaned %d time(s) since %s, %.1f GB total; found again: %.1f GB (%s)\n",
             c, times, substr(first[c], 1, 10), gb[c], back, (c in newest) ? newest[c] : "not since"
    }
  }' "$CLEANED" "$FOUND" | sort -t',' -k2 -rn
