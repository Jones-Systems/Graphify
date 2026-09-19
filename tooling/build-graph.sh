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
mkdir -p "$RUN/graphify-out" "$GF_ROOT/$CORPUS/policy"
[ -f "$POLICY" ] || printf '# corpus policy: see WORK-NOTE D6 + global denies\n' > "$POLICY"

mem_guard start
python3 "$TOOL_DIR/preflight.py" "$ROOT" "$POLICY" "$RUN/preflight.json" || {
  echo "[build] preflight FAILED — no staging or extraction performed (C14)"; exit 45; }
mem_guard post-preflight

# Stage included files only (preflight inventory is authoritative)
python3 - "$RUN/preflight.json" "$ROOT" "$STAGE" "$GF_ROOT" <<'EOF'
import json, os, shutil, stat, sys
pf, root, stage, owned_root = json.load(open(sys.argv[1])), *sys.argv[2:5]
# The fixed staging path gives extractors stable IDs, but every run must still
# be an exact materialization of the current admitted inventory.
stage, owned_root = map(os.path.abspath, (stage, owned_root))
source_root = os.path.realpath(root)
if os.path.commonpath((stage, owned_root)) != owned_root or stage == owned_root:
    raise RuntimeError(f"refusing staging target outside owned root: {stage}")
overlap = os.path.commonpath((stage, source_root))
if overlap in {stage, source_root}:
    raise RuntimeError(f"refusing staging/source overlap: {stage} and {source_root}")
if os.path.basename(stage) != "view" or os.path.basename(os.path.dirname(stage)) != "staging":
    raise RuntimeError(f"refusing unexpected staging shape: {stage}")
staging_parent = os.path.dirname(stage)

def open_absolute_directory_no_follow(path):
    descriptor = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in [part for part in path.split(os.sep) if part]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise

parent_fd = open_absolute_directory_no_follow(owned_root)
parent_created = False
try:
    relative_parent = os.path.relpath(staging_parent, owned_root)
    for component in relative_parent.split(os.sep):
        try:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            created = False
        except FileNotFoundError:
            os.mkdir(component, mode=0o700, dir_fd=parent_fd)
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            created = True
        os.close(parent_fd)
        parent_fd = child
        parent_created = created

    marker_name = ".graphify-view-owner"
    marker_bytes = b"graphify-staging-v1\n"
    if parent_created:
        marker_fd = os.open(
            marker_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        with os.fdopen(marker_fd, "wb") as handle:
            handle.write(marker_bytes)
    else:
        try:
            marker_fd = os.open(
                marker_name,
                os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            with os.fdopen(marker_fd, "rb") as handle:
                marker_owned = (
                    stat.S_ISREG(os.fstat(handle.fileno()).st_mode)
                    and handle.read(len(marker_bytes) + 1) == marker_bytes
                )
        except OSError:
            marker_owned = False
        if not marker_owned:
            raise RuntimeError(f"refusing unowned staging contents: {staging_parent}")

    try:
        stage_stat = os.stat("view", dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        stage_stat = None
    if stage_stat is not None:
        if not stat.S_ISDIR(stage_stat.st_mode):
            raise RuntimeError(f"refusing unsafe staging target: {stage}")
        if not shutil.rmtree.avoids_symlink_attacks:
            raise RuntimeError("refusing staging replacement without safe rmtree support")
        shutil.rmtree("view", dir_fd=parent_fd)
    os.mkdir("view", mode=0o700, dir_fd=parent_fd)
finally:
    os.close(parent_fd)
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
