#!/usr/bin/env bash
# Graphify integration toggle — SPEC §5; mechanics per INACT-C24..C31 (Aug-12 blueprint)
# Vocabulary only: proposed | implementation-applied-verification-pending |
#   temporarily-inactive-verified | reactivation-proposed | reactivation-approved |
#   restored-verification-pending | active-verified
set -euo pipefail

GF_ROOT="${GF_ROOT:-$HOME/.agent-references/graphify}"
SKILL_NAME="graphify-corpus-navigation"
ACTIVE="$GF_ROOT/skills/$SKILL_NAME"
DISABLED="$GF_ROOT/skills-disabled/$SKILL_NAME"   # non-discovery sibling (C27)
STATE="$GF_ROOT/toggled.state"
PRESERVE="$GF_ROOT/toggle-preserve"
WIRING_D="$GF_ROOT/wiring.d"

mem_avail_mib() { awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo; }

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

die() { echo "[toggle] FATAL: $*" >&2; exit 44; }

preserve_bundle() { # label dir-to-preserve
  local label="$1" src="$2"
  local dest="$PRESERVE/$(date -u +%Y%m%dT%H%M%SZ)-$label"
  mkdir -p "$dest"
  cp -a "$src" "$dest/"
  ( cd "$(dirname "$src")" && find "$(basename "$src")" -type f -print0 \
      | sort -z | xargs -0 sha256sum ) > "$dest/SHA256SUMS"
  ( cd "$dest" && sha256sum -c SHA256SUMS >/dev/null ) || die "preservation self-check failed; aborting before any live change (C26)"
  echo "$dest"
}

run_wiring() { # verb
  local verb="$1"
  if [ -d "$WIRING_D" ]; then
    for hook in "$WIRING_D"/*.sh; do
      [ -x "$hook" ] || continue
      "$hook" "$verb" || die "wiring hook $(basename "$hook") failed during $verb"
    done
  fi
}

set_state() {
  printf '%s\n' "state=$1 utc=$(now_utc) mem_available_mib=$(mem_avail_mib)" > "$STATE"
}

cmd_status() {
  if [ -f "$STATE" ]; then cat "$STATE"; else echo "state=unconfigured (never toggled; install-time default is active-by-construction)"; fi
}

cmd_disable() {
  [ -d "$ACTIVE" ] || die "active skill dir not found: $ACTIVE"
  [ -e "$DISABLED" ] && die "disabled sibling already exists: $DISABLED (refusing ambiguous state)"
  local bundle; bundle=$(preserve_bundle "pre-disable" "$ACTIVE")
  mkdir -p "$(dirname "$DISABLED")"
  mv "$ACTIVE" "$DISABLED"          # same-filesystem rename: bytes+inode preserved (C27)
  set_state "implementation-applied-verification-pending"
  run_wiring disable
  echo "[toggle] disabled (preserved: $bundle)"
  echo "[toggle] status now implementation-applied-verification-pending; fresh-session verification required to declare temporarily-inactive-verified (C28)"
}

cmd_enable() {
  [ -d "$DISABLED" ] || die "disabled skill dir not found: $DISABLED"
  [ -e "$ACTIVE" ] && die "active dir already exists (refusing partial activation)"
  preserve_bundle "pre-enable-inactive-state" "$DISABLED" >/dev/null   # C30: manifest inactive state first
  mv "$DISABLED" "$ACTIVE"
  set_state "restored-verification-pending"
  run_wiring enable
  echo "[toggle] enabled; fresh-session verification required to declare active-verified (C28)"
}

cmd_verify() { # records verified terminal states after an external fresh-session check
  local st; st=$(sed -n 's/^state=\([^ ]*\).*/\1/p' "$STATE" 2>/dev/null)
  case "$st" in
    implementation-applied-verification-pending) set_state "temporarily-inactive-verified"; echo "[toggle] verified inactive" ;;
    restored-verification-pending)               set_state "active-verified";             echo "[toggle] verified active" ;;
    *) die "state not in a verification-pending position; nothing to record" ;;
  esac
}

case "${1:-status}" in
  status)  cmd_status ;;
  disable) cmd_disable ;;
  enable)  cmd_enable ;;
  verify)  cmd_verify ;;
  *) echo "usage: toggle.sh {status|disable|enable|verify}"; exit 2 ;;
esac
