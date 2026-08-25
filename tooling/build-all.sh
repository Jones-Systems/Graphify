#!/usr/bin/env bash
# Sequential build wave over corpora.manifest — WR-C18 one worker, INV-1 guards.
# Skips corpora whose `current` pointer already exists unless FORCE=1.
set -uo pipefail
TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
GF_ROOT="${GF_ROOT:-$HOME/.agent-references/graphify}"
MANIFEST="${1:-$TOOL_DIR/corpora.manifest}"
LOG="$GF_ROOT/build-log.txt"
echo "[build-all] wave started $(date -u +%FT%TZ)" >> "$LOG"

pass=0; fail=0; skip=0; failed=""
while IFS=$'\t' read -r corpus root tracked; do
  [ -z "$corpus" ] && continue; case "$corpus" in \#*) continue ;; esac
  if [ -e "$GF_ROOT/$corpus/current" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "[build-all] SKIP $corpus (current exists)"; skip=$((skip+1)); continue
  fi
  echo "[build-all] BUILD $corpus ($root)"
  if GF_TRACKED_ONLY="$tracked" "$TOOL_DIR/build-graph.sh" "$corpus" "$root" "" >> "$LOG" 2>&1; then
    pass=$((pass+1))
  else
    rc=$?
    echo "[build-all] FAIL $corpus rc=$rc" >> "$LOG"
    fail=$((fail+1)); failed="$failed $corpus(rc=$rc)"
  fi
done < <(grep -v '^\s*$' "$MANIFEST" | grep -v '^#')

SUMMARY=$(printf '{"wave_utc":"%s","passed":%d,"failed":%d,"skipped":%d,"failed_list":"%s"}' \
  "$(date -u +%FT%TZ)" "$pass" "$fail" "$skip" "$(echo "$failed" | xargs)")
echo "$SUMMARY" | tee -a "$LOG"
[ "$fail" -eq 0 ]
