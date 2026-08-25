#!/usr/bin/env bash
# Graphify V3 toolchain installer — SPEC §2/D8/D2 (PRD-C3, fail closed on hash mismatch)
set -euo pipefail

GF_ROOT="${GF_ROOT:-$HOME/.agent-references/graphify}"
ENV_DIR="$GF_ROOT/tool/env"
TOOL_DIR="$GF_ROOT/tool"
V="0.9.16"
WHEEL_SHA256="24eefd6cd8e0f47eb8167671fbe3aceb31b49a6508b91fe1b60c4fd1978e32bc"
SDIST_SHA256="a43294922aa07ffe5d2f0c3e00b0413f089cf8b1bbff37f946bc586920843100"

mem_avail_mib() { awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo; }
MEM0=$(mem_avail_mib)
echo "[install] MemAvailable at start: ${MEM0} MiB (floor 3072, warn 4096)"
if [ "$MEM0" -lt 4096 ]; then echo "[install] WARN: below warning band"; fi
if [ "$MEM0" -lt 3072 ]; then echo "[install] HALT: below floor"; exit 42; fi

mkdir -p "$TOOL_DIR/dl/wheel" "$TOOL_DIR/dl/sdist"

fetch() { # url dest
  if command -v curl >/dev/null; then curl -fsSL "$1" -o "$2"; else wget -qO "$2" "$1"; fi
}

verify() { # file expected-sha256 label
  echo "$2  $1" | sha256sum -c - >/dev/null || { echo "[install] FATAL: $3 hash mismatch"; exit 43; }
  echo "[install] verified $3"
}

WHEEL="$TOOL_DIR/dl/wheel/graphifyy-$V-py3-none-any.whl"
SDIST="$TOOL_DIR/dl/sdist/graphifyy-$V.tar.gz"
[ -f "$WHEEL" ] || fetch "https://files.pythonhosted.org/packages/source/g/graphifyy/graphifyy-$V.tar.gz" "$WHEEL" || true
# Prefer PyPI-normalized URLs via pip download when direct fetch missing/mismatched:
if ! echo "$WHEEL_SHA256  $WHEEL" | sha256sum -c - >/dev/null 2>&1; then
  python3 -m venv --without-pip "$TOOL_DIR/.bootstrap-venv"
  fetch https://bootstrap.pypa.io/get-pip.py "$TOOL_DIR/get-pip.py"
  "$TOOL_DIR/.bootstrap-venv/bin/python" "$TOOL_DIR/get-pip.py" -q
  "$TOOL_DIR/.bootstrap-venv/bin/pip" download "graphifyy==$V" --no-deps -d "$TOOL_DIR/dl/wheel" -q
  rm -rf "$TOOL_DIR/.bootstrap-venv" "$TOOL_DIR/get-pip.py"
fi
verify "$WHEEL" "$WHEEL_SHA256" "wheel"
if [ -f "$SDIST" ]; then verify "$SDIST" "$SDIST_SHA256" "sdist"; fi

# Persistent venv (Debian lacks ensurepip → bootstrap pip inside target venv directly)
if [ ! -x "$ENV_DIR/bin/python" ]; then
  python3 -m venv --without-pip "$ENV_DIR"
  fetch https://bootstrap.pypa.io/get-pip.py "$TOOL_DIR/get-pip.py"
  "$ENV_DIR/bin/python" "$TOOL_DIR/get-pip.py" -q
  rm -f "$TOOL_DIR/get-pip.py"
fi

"$ENV_DIR/bin/pip" install --no-input -q "$WHEEL"
"$ENV_DIR/bin/pip" freeze > "$TOOL_DIR/resolver-lock.txt"
"$ENV_DIR/bin/pip" show graphifyy | sed -n '1,3p' > "$TOOL_DIR/installed-version.txt"

cat > "$TOOL_DIR/PIN.json" <<EOF
{
  "package": "graphifyy",
  "version": "$V",
  "upstream_commit": "a0e4a1c6bd3a99edfdd84ad30927003f51face6a",
  "wheel_sha256": "$WHEEL_SHA256",
  "sdist_sha256": "$SDIST_SHA256",
  "requires_python": ">=3.10",
  "host_python": "$(python3 --version 2>&1)",
  "installed_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "policy": "fail-closed on hash mismatch; never use upstream codex installers (PRD-C4)"
}
EOF

# Smoke: entrypoint works from absolute path (ENG-C5)
"$ENV_DIR/bin/graphify" --help >/dev/null
echo "[install] OK: $(readlink -f "$ENV_DIR")"
echo "[install] MemAvailable at end: $(mem_avail_mib) MiB"
