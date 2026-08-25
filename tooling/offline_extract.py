#!/usr/bin/env python3
"""Offline structural extraction — DEC-10 default.

Runs the pinned library's per-file extractors (AST for code, regex link graph
for markdown) WITHOUT any LLM backend: no API key, no network. Semantic doc
enrichment (concept nodes) is deferred to a future owner-gated decision.
Graph JSON schema matches the CLI (node-link, edges="links").
"""
import json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # unused; venv python carries graphify

def main():
    staging_root, out_json = Path(sys.argv[1]).resolve(), sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 8

    from graphify import build as gb
    from graphify import extract as gx

    files = [p for p in staging_root.rglob("*") if p.is_file() and not p.is_symlink()]
    extractions = []
    empty, errors = 0, 0
    for i, p in enumerate(sorted(files)):
        extractor = gx._get_extractor(p)
        if extractor is None:
            continue
        try:
            res = gx._safe_extract_with_xaml_root(extractor, p, staging_root)
        except Exception as e:
            errors += 1
            print(f"[offline] error {p.relative_to(staging_root)}: {e}", file=sys.stderr)
            continue
        if res.get("nodes"):
            extractions.append(res)
        else:
            empty += 1
        if (i + 1) % 200 == 0:
            print(f"[offline] {i+1}/{len(files)} scanned, {len(extractions)} productive")

    G = gb.build(extractions, root=str(staging_root))
    from networkx.readwrite import json_graph
    data = json_graph.node_link_data(G, edges="links")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    json.dump(data, open(out_json, "w"))
    print(f"[offline] wrote {out_json}: {len(data.get('nodes', []))} nodes, "
          f"{len(data.get('links', []))} links (files={len(files)}, empty={empty}, errors={errors})")

if __name__ == "__main__":
    main()
