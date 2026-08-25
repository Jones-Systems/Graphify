#!/usr/bin/env bash
# Promotion — repoint <corpus>/current only after independent verification (ENG-C13).
# usage: promote.sh <corpus> <run-dir> --verified-by "<verifier session + evidence ref>"
set -euo pipefail
CORPUS="$1"; RUN="$2"; VERBY="${4:-}"
[ -n "$VERBY" ] || { echo "refusing to promote without --verified-by evidence (ENG-C13)"; exit 48; }
GF_ROOT="${GF_ROOT:-$HOME/.agent-references/graphify}"
python3 - <<EOF
import json, sys
v = json.load(open("$RUN/validation.json")); f = json.load(open("$RUN/freshness.json"))
if v["status"] == "BLOCKED": sys.exit("run is BLOCKED; never promotable")
print("[promote] validation:", v["status"], "| freshness:", f["classification"])
EOF
ln -sfn "$RUN" "$GF_ROOT/$CORPUS/current"
printf '%s\n' "{\"promoted_utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"verified_by\":\"$VERBY\"}" > "$RUN/promotion.json"
echo "[promote] current -> $RUN"
