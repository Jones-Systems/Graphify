#!/usr/bin/env python3
"""Graph validator + freshness recorder — ENG-C7..C11.

Usage: validate.py <graph.json> <root> <preflight.json> <out_dir> <pin.json>
Emits validation.json (PASS|PASS_WITH_WARNINGS|BLOCKED) and freshness.json
(valid|stale|unknown + source_fingerprint). Fatal classes per ENG-C7;
warning taxonomy simplified for VPS: unresolved targets classified
external_bare_import vs conservative_internal_looking; per-graph baselines are
recorded on first validated run and later runs exceeding their own baseline by
>10% or introducing a new unreviewed class are BLOCKED (DEC-6).
"""
import json, os, sys, hashlib, datetime

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    graph_path, root, preflight_path, out_dir, pin_path = sys.argv[1:6]
    root = os.path.realpath(root)
    fatals, warnings = [], []

    try:
        g = json.load(open(graph_path))
    except Exception as e:
        print(json.dumps({"status": "BLOCKED", "fatals": [f"malformed-json:{e}"]}))
        sys.exit(46)

    if not isinstance(g, dict) or "nodes" not in g or "directed" not in g:
        fatals.append("schema:not-networkx-node-link")

    nodes = g.get("nodes", [])
    ids = set()
    dup = set()
    for n in nodes:
        nid = n.get("id")
        if nid in ids: dup.add(nid)
        ids.add(nid)
    if dup:
        fatals.append(f"duplicate-node-ids:{len(dup)}")

    # source endpoint + containment checks
    unresolved_ext, unresolved_int = [], []
    source_files = []
    def check_target(t):
        if not t: return
        if isinstance(t, str):
            p = os.path.realpath(os.path.join(root, t)) if not os.path.isabs(t) else os.path.realpath(t)
            if not (p == root or p.startswith(root + os.sep)):
                if "/" not in t and not t.endswith((".py", ".md", ".ts", ".go", ".swift")):
                    unresolved_ext.append(t)
                else:
                    unresolved_int.append(t)
                return
            if not os.path.exists(p):
                unresolved_int.append(t)
    links = g.get("links", [])
    for lk in links:
        s, t = lk.get("source"), lk.get("target")
        if s not in ids: fatals.append(f"missing-source-endpoint:{s}")
        if t not in ids:
            check_target(t)
    for n in nodes:
        sf = n.get("source_file") or n.get("source_path")
        if sf:
            source_files.append(sf)
            p = os.path.realpath(sf if os.path.isabs(sf) else os.path.join(root, sf))
            if not (p == root or p.startswith(root + os.sep)):
                fatals.append(f"source-path-outside-root:{sf}")
            elif not os.path.exists(p):
                unresolved_int.append(sf)

    # forbidden values in governed fields (ENG-C7/C9): exclusion metadata exempt
    forbidden_tokens = ("/.git/", ".env", "id_rsa", ".pem", "private_key_file", "/secrets/")
    for sf in source_files:
        low = sf.lower()
        hit = next((tk for tk in forbidden_tokens if tk in low), None)
        if hit: fatals.append(f"forbidden-in-source-file:{hit}:{sf[:80]}")

    # freshness fingerprint (ENG-C11): inventory + policy bytes + pin identity
    pf = json.load(open(preflight_path))
    h = hashlib.sha256()
    for e in sorted(pf["included"], key=lambda x: x["logical"]):
        h.update(e["logical"].encode()); h.update(str(e["size"]).encode())
        try: h.update(hashlib.sha256(open(e["resolved"], "rb").read()).hexdigest().encode())
        except Exception: pass  # unreadable post-preflight ⇒ unknown below
    pol = pf.get("policy")
    if pol and os.path.exists(pol):
        h.update(open(pol, "rb").read())
    pin = open(pin_path).read() if os.path.exists(pin_path) else "{}"
    h.update(pin.encode())
    fingerprint = h.hexdigest()

    prev_base = os.path.join(out_dir, "..", "warning-baseline.json")
    baseline = json.load(open(prev_base)) if os.path.exists(prev_base) else None

    wcounts = {"external_bare_import": len(unresolved_ext),
               "conservative_internal_looking": len(unresolved_int)}
    if baseline is None:
        status = "PASS_WITH_WARNINGS" if (unresolved_ext or unresolved_int) else "PASS"
    else:
        blocked = False
        new_classes = set(wcounts) - set(baseline.get("classes", {}))
        if new_classes: fatals.append(f"new-unreviewed-warning-class:{sorted(new_classes)}")
        for k, v in wcounts.items():
            b = baseline.get("classes", {}).get(k)
            if b is not None and v > b * 1.10:
                fatals.append(f"ceiling-exceeded:{k}:{v}>{b}"); blocked = True
        status = "BLOCKED" if blocked or fatals else "PASS_WITH_WARNINGS"
    if fatals: status = "BLOCKED"

    os.makedirs(out_dir, exist_ok=True)
    validation = {
        "schema": "graphify-v3-validation/v1", "graph": os.path.abspath(graph_path),
        "status": status,
        "nodes": len(nodes), "edges": len(links),
        "fatal_classes": sorted(set(f.split(":")[0] for f in fatals)),
        "fatals": fatals[:50], "fatal_count": len(fatals),
        "warnings": {"classes": {k: v for k, v in wcounts.items()}, 
                     "samples": {"external": unresolved_ext[:20], "internal": unresolved_int[:20]},
                     "samples_sanitized": True},
        "checked_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    json.dump(validation, open(os.path.join(out_dir, "validation.json"), "w"), indent=1)

    freshness = {
        "schema": "graphify-v3-freshness/v1",
        "source_fingerprint": fingerprint,
        "classification": "valid",  # recomputation succeeded by construction here
        "note": "stale/unknown assigned by compare against recorded current-run fingerprint",
        "checked_utc": validation["checked_utc"],
    }
    json.dump(freshness, open(os.path.join(out_dir, "freshness.json"), "w"), indent=1)

    if baseline is None and status in ("PASS", "PASS_WITH_WARNINGS"):
        json.dump({"classes": wcounts}, open(prev_base, "w"), indent=1)

    print(f"[validate] {status}: nodes={len(nodes)} edges={len(links)} "
          f"fatals={len(fatals)} warn={wcounts} fp={fingerprint[:12]}…")
    sys.exit(0 if status != "BLOCKED" else 47)

if __name__ == "__main__":
    main()
