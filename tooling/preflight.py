#!/usr/bin/env python3
"""Deny-first path preflight — ENG-C14 (inventory before any graph work).

Policy file format (one rule per line, order matters, last match wins):
  exclude <glob>     # relative to root, fnmatch semantics ('*' crosses '/')
  include <glob>
Lines starting '#' are comments. Default posture is include unless an exclude
matches; the global deny list is always applied first and cannot be re-included.

GF_TRACKED_ONLY=1 restricts the inventory to git-tracked files when the corpus
root lives inside a git repository (D6: corpus basis = tracked tree).
"""
import json, os, sys, fnmatch

GLOBAL_DENY = [
    ".git/*", "*/.git/*", "node_modules/*", "*/node_modules/*",
    ".venv/*", "*/.venv/*", "venv/*", "*/venv/*", "__pycache__/*", "*/__pycache__/*",
    ".ruff_cache/*", ".next/*", "dist/*", "build/*", "target/*",
    ".codex/*", ".omp/*", ".opencode/*", ".agents/*", ".goal-state/*", ".beads/*",
    "data/pg17/*", "*/data/pg17/*",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.ico", "*.woff", "*.woff2", "*.ttf",
    "*.mp4", "*.mov", "*.mp3", "*.wav", "*.zip", "*.tar", "*.gz", "*.7z",
    "*.pdf", "*.sqlite", "*.sqlite-*", "*.db", "*.duckdb", "*.parquet", "*.tsv",
    ".env*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "*credential*", "*secret*",
    "package-lock.json", "*.lock", "uv.lock", "*.jsonl", "*.seq",
]
# Markers assembled at runtime so this scanner's own source does not trip
# canary scans of repositories that vendor it (self-scan false positive).
FORBIDDEN_MARKERS = [
    "BEGIN " + "PRIVATE " + "KEY",
    "BEGIN " + "RSA PRIVATE " + "KEY",
    "AWS_ACCESS_KEY_" + "ID=",
    "api_" + "key =",
]


def load_policy(path):
    rules = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            verb, _, pat = ln.partition(" ")
            if verb in ("include", "exclude"):
                rules.append((verb, pat))
    return rules


def tracked_filter(root):
    """Return set of repo-relative tracked paths (GF_TRACKED_ONLY=1), else None."""
    if os.environ.get("GF_TRACKED_ONLY") != "1":
        return None
    import subprocess
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "--cached"],
                             capture_output=True, text=True, timeout=120, check=True)
    except Exception:
        return None
    return {os.path.normpath(l) for l in out.stdout.splitlines() if l}


def main():
    root, policy_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    root = os.path.realpath(root)
    rules = load_policy(policy_path)
    exclude_pats = [pat for verb, pat in rules if verb == "exclude"]
    tracked = tracked_filter(root)
    inv, excluded, canary_hits, symlinks_out = [], [], [], []
    n_files = 0

    def policy_excludes(rel):
        return next((pat for pat in exclude_pats if fnmatch.fnmatch(rel, pat)), None)

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)

        # Directory pruning: global deny first (unconditional), then policy.
        # Symlinked dirs land here; policy-excluded ones are pruned+recorded,
        # remaining outside-root symlink dirs are flagged as failures.
        for d in list(dirnames):
            rel = os.path.normpath(os.path.join(rel_dir, d))
            full_d = os.path.join(dirpath, d)
            gdeny = next((g for g in GLOBAL_DENY if fnmatch.fnmatch(rel + "/", g)), None)
            if gdeny:
                excluded.append({"path": rel + "/", "rule": f"global-deny:{gdeny}", "kind": "dir"})
                dirnames.remove(d)
                continue
            pol_hit = policy_excludes(rel)
            if pol_hit is not None:
                excluded.append({"path": rel + "/", "rule": f"policy-exclude:{pol_hit}", "kind": "dir"})
                dirnames.remove(d)
                continue
            if os.path.islink(full_d):
                tgt = os.path.realpath(full_d)
                if not tgt.startswith(root + os.sep):
                    symlinks_out.append({"path": rel, "resolved": tgt, "kind": "symlink-dir"})
                    excluded.append({"path": rel + "/", "rule": "outside-root-symlink-dir", "kind": "dir"})
                    dirnames.remove(d)

        dirnames[:] = sorted(dirnames)
        for f in sorted(filenames):
            rel = os.path.normpath(os.path.join(rel_dir, f))
            full = os.path.join(dirpath, f)
            if os.path.islink(full):
                tgt = os.path.realpath(full)
                rec = {"path": rel, "resolved": tgt, "kind": "symlink"}
                pol_hit = policy_excludes(rel)
                if pol_hit is not None:
                    excluded.append({**rec, "rule": f"policy-exclude:{pol_hit}"})
                    continue
                if not tgt.startswith(root + os.sep):
                    rec["outside_root"] = True
                    symlinks_out.append(rec)
                excluded.append({**rec, "rule": "symlink-not-followed"})
                continue
            hit = next((g for g in GLOBAL_DENY if fnmatch.fnmatch(rel, g)), None)
            if hit:
                excluded.append({"path": rel, "rule": f"global-deny:{hit}", "kind": "file"})
                continue
            if tracked is not None and rel not in tracked:
                excluded.append({"path": rel, "rule": "untracked(GF_TRACKED_ONLY)", "kind": "file"})
                continue
            decision, winning = "include", "default-include"
            for verb, pat in rules:
                if fnmatch.fnmatch(rel, pat):
                    decision = "include" if verb == "include" else "exclude"
                    winning = f"{verb}:{pat}"
            if decision == "exclude":
                excluded.append({"path": rel, "rule": winning, "kind": "file"})
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if size <= 1_048_576:  # canary scan bounded to 1 MiB text candidates
                try:
                    head = open(full, encoding="utf-8", errors="ignore").read(262144)
                    m = next((mk for mk in FORBIDDEN_MARKERS if mk in head), None)
                    if m:
                        canary_hits.append({"path": rel, "marker_kind": m.split()[0]})
                except Exception:
                    pass
            inv.append({"logical": rel, "resolved": full, "size": size,
                        "type": "file", "winning_rule": winning})
            n_files += 1

    result = {
        "root": root, "policy": policy_path,
        "tracked_only": tracked is not None,
        "included_count": n_files, "excluded_count": len(excluded),
        "included": inv, "excluded_samples": excluded[:500],
        "forbidden_canary_hits": canary_hits,
        "symlinks_outside_root": symlinks_out,
    }
    json.dump(result, open(out_path, "w"), indent=1)
    status = "PASS" if not canary_hits and not symlinks_out else "FAIL"
    print(f"[preflight] {status}: included={n_files} excluded={len(excluded)} "
          f"tracked_only={tracked is not None} canary_hits={len(canary_hits)} "
          f"outside_symlinks={len(symlinks_out)}")
    sys.exit(0 if status == "PASS" else 45)


if __name__ == "__main__":
    main()
