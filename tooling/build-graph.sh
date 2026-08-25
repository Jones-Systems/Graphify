#!/usr/bin/env bash
# Staged graph build runner — SPEC §4; ENG-C12/C14, WR-C16..C21, INV-1 bands.
# VPS-7: extraction runs on a STAGING VIEW built from the preflight inventory
# (repos with default-deny .gitignore are invisible to direct scans; staging
# also isolates read-only checkouts). DEC-10: structural offline extraction —
# no LLM key, no network (offline_extract.py).
# usage: build-graph.sh <corpus-name> <repo-root> <chunk-subdir|''> [policy-file]
set -euo pipefail

CORPUS="$1"; REPO="$2"; CHUNK="${3:-}"; POLICY="${4:-}"
GF_ROOT="${GF_ROOT:-$HOME/.agent-references/graphify}"
ENV="$GF_ROOT/tool/env"
TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCK="/tmp/graphify-build.lock"

mem_avail_mib() { awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo; }
mem_guard() {
  local phase="$1" m; m=$(mem_avail_mib)
  echo "[build $CORPUS] MemAvailable($phase): ${m} MiB"
  if [ "$m" -lt 3072 ]; then echo "[build] HALT: floor breach"; exit 42; fi
  if [ "$m" -lt 4096 ]; then echo "[build] WARN: warning band"; fi
}

exec 9>"$LOCK"
flock -n 9 || { echo "[build] deferred_lock: another build holds the host lock (WR-C21)"; exit 0; }

ROOT="$REPO${CHUNK:+/$CHUNK}"
[ -d "$ROOT" ] || { echo "missing root $ROOT"; exit 2; }
POLICY="${POLICY:-$GF_ROOT/$CORPUS/policy/ignore.rules}"
RUN="$GF_ROOT/$CORPUS/runs/$(date -u +%Y%m%dT%H%M%SZ)-$(echo "${CHUNK:-full}" | tr '/' '-')"
STAGE="$GF_ROOT/$CORPUS/staging/view"
mkdir -p "$STAGE" "$RUN/graphify-out" "$GF_ROOT/$CORPUS/policy"
[ -f "$POLICY" ] || printf '# corpus policy: see WORK-NOTE D6 + global denies\n' > "$POLICY"

mem_guard start
python3 "$TOOL_DIR/preflight.py" "$ROOT" "$POLICY" "$RUN/preflight.json" || {
  echo "[build] preflight FAILED — no staging or extraction performed (C14)"; exit 45; }
mem_guard post-preflight

# Stage included files only (preflight inventory is authoritative)
python3 - "$RUN/preflight.json" "$ROOT" "$STAGE" <<'EOF'
import json, os, shutil, sys
pf, root, stage = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
n = 0
for e in pf["included"]:
    src, dst = e["resolved"], os.path.join(stage, e["logical"])
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst); n += 1
print(f"[stage] {n} files copied to staging view")
EOF

mem_guard post-stage
"$ENV/bin/python" "$TOOL_DIR/offline_extract.py" "$STAGE" "$RUN/graphify-out/graph.json" 8 \
  || { echo "[build] offline extraction failed"; exit 46; }
mem_guard post-extract

python3 "$TOOL_DIR/validate.py" "$RUN/graphify-out/graph.json" "$STAGE" "$RUN/preflight.json" "$RUN" "$GF_ROOT/tool/PIN.json" \
  || { echo "[build] BLOCKED by validator"; exit 47; }

printf '%s\n' "{\"corpus\":\"$CORPUS\",\"chunk\":\"${CHUNK:-full}\",\"source_root\":\"$ROOT\",\"staging\":\"$STAGE\",\"run\":\"$RUN\",\"built_utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"mode\":\"structural-offline\",\"status\":\"built-validation-recorded\"}" > "$RUN/build-meta.json"
: # staging kept at fixed path — deterministic extractor IDs (L63 fix)
echo "[build] complete: $RUN"
echo "[build] NOT promoted — repoint current only via promote.sh after independent verification (ENG-C13)"
mem_guard end
