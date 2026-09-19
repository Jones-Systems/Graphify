#!/usr/bin/env python3
"""SCIP index -> Graphify node-link converter (R2, capsule W1-c).

Input: the proto-JSON form of a scip.Index as emitted by `scip print --json`,
passed as a file path or `-` for stdin. Output: NetworkX node-link JSON
accepted by tooling/validate.py (unique node ids, resolvable link endpoints,
root-relative source_file values that exist under --root):

    {"directed": false, "multigraph": false, "graph": {...},
     "nodes": [{"id": <symbol>, "kind": <str>, "source_file": <relpath>?}],
     "links": [{"source": .., "target": .., "kind": "ref|implements|type-def"}]}

Composition semantics (SCIP fixes the data, not the graph shape):
- One node per distinct symbol string occurring anywhere in the index. A
  node's source_file is the relative_path of the FIRST document holding a
  defining occurrence. `symbol_roles` may arrive as a name array or as an
  int bitmask (Definition bit = 1); both are accepted.
- Function-local variables (scip-python's opaque `local N` symbols) are
  dropped entirely - they are not code entities and never link across files.
- implements / type-def links come from SymbolInformation.relationships
  (roles Implementation / TypeDefinition): owner -> related symbol.
  scip-python 0.6.6 emits no relationships and no kind field, so those
  links and node kinds appear only with richer indexers; nodes then fall
  back to kind="symbol".
- ref links encode cross-file use: a reference to symbol T in document D is
  anchored on D's module symbol (descriptor ending "/__init__:"), falling
  back to D's first defined symbol, whenever def-doc(T) != D. Intra-document
  references are structural noise and skipped. Symbols never defined in the
  corpus (stdlib, third-party) still get dependency-seed ref links and are
  reported under the unresolved-class external_bare_symbol warning.

Pure stdlib by design. The `scip` CLI itself is a hash-pinned Go binary - see
tooling/requirements-scip.txt. NEVER `pip install scip`: PyPI `scip` is an
unrelated GPL cytometry package, not the code-intelligence CLI.

Usage:
    python3 scip_convert.py <index.json|-> <out.graph.json> --root /canonical/root
"""

from __future__ import annotations

import argparse
import json
import os
import sys

DEFINITION_ROLES = frozenset({1, "Definition"})
RELATIONSHIP_KINDS = {
    1: "implements", "Implementation": "implements",
    2: "ref", "References": "ref",
    3: "type-def", "TypeDefinition": "type-def",
}
UNSPECIFIED_KINDS = frozenset({"", "unspecifiedkind"})
LOCAL_PREFIX = "local "
MODULE_DESCRIPTOR_SUFFIX = "/__init__:"


def is_defining(roles) -> bool:
    """True when an occurrence carries the Definition symbol-role bit."""
    if isinstance(roles, int):  # scip-python 0.6.6 emits an int bitmask
        return bool(roles & 1)
    return any(r in DEFINITION_ROLES or r == 1 for r in roles or ())


def relationship_kind(role):
    return RELATIONSHIP_KINDS.get(role)


def normalize_relpath(path, root):
    """Root-relative forward-slash document path; absolute paths resolved."""
    path = (path or "").replace("\\", "/")
    if os.path.isabs(path):
        path = os.path.relpath(os.path.realpath(path), root)
    while path.startswith("./"):
        path = path[2:]
    return path


def declared_kind(info):
    kind = str((info or {}).get("kind") or "").lower()
    return None if kind in UNSPECIFIED_KINDS else kind


def convert(index, root):
    """Fold a scip.Index proto-JSON object into (node_link_graph, stats)."""
    root = os.path.realpath(root)
    def_doc = {}     # symbol -> defining document (first wins)
    kind_of = {}     # symbol -> declared kind
    rels = {}        # symbol -> [(target symbol, edge kind)]
    doc_refs = {}    # document -> set of referenced foreign symbols
    doc_defs = {}    # document -> defining symbols in occurrence order
    occurring = set()
    stats = {"docs": 0, "skipped_docs": 0, "self_links_dropped": 0,
             "locals_dropped": 0}

    def take_relationships(symbol, info):
        for relationship in info.get("relationships") or ():
            target = relationship.get("symbol")
            if not target:
                continue
            for role in relationship.get("roles") or ():
                edge_kind = relationship_kind(role)
                if edge_kind:
                    rels.setdefault(symbol, []).append((target, edge_kind))

    def take_document(doc):
        path = normalize_relpath(doc.get("relative_path"), root)
        if not path:
            stats["skipped_docs"] += 1
            return
        stats["docs"] += 1
        for info in doc.get("symbols") or ():
            symbol = info.get("symbol")
            if not symbol or symbol.startswith(LOCAL_PREFIX):
                continue
            kind = declared_kind(info)
            if kind:
                kind_of.setdefault(symbol, kind)
            take_relationships(symbol, info)
        defined = []
        for occ in doc.get("occurrences") or ():
            symbol = occ.get("symbol")
            if not symbol:
                continue
            if symbol.startswith(LOCAL_PREFIX):
                stats["locals_dropped"] += 1
                continue
            occurring.add(symbol)
            if is_defining(occ.get("symbol_roles")):
                defined.append(symbol)
                def_doc.setdefault(symbol, path)
            else:
                doc_refs.setdefault(path, set()).add(symbol)
        if defined:
            doc_defs[path] = defined

    for doc in index.get("documents") or ():
        take_document(doc)
    for info in index.get("external_symbols") or ():
        symbol = info.get("symbol")
        if not symbol or symbol.startswith(LOCAL_PREFIX):
            continue
        kind = declared_kind(info)
        if kind:
            kind_of.setdefault(symbol, kind)
        take_relationships(symbol, info)

    def anchor_of(path):
        """Module symbol of a document, else its first definition, else None."""
        defined = doc_defs.get(path) or ()
        for symbol in defined:
            if symbol.endswith(MODULE_DESCRIPTOR_SUFFIX):
                return symbol
        return defined[0] if defined else None

    links = {}

    def add_link(source, target, kind):
        if source == target:
            stats["self_links_dropped"] += 1
            return
        key = (source, target, kind)
        if key not in links:
            links[key] = {"source": source, "target": target, "kind": kind}

    for owner, pairs in rels.items():
        for target, kind in pairs:
            add_link(owner, target, kind)

    external = set()
    anchorless = 0
    for path in sorted(doc_refs):
        anchor = anchor_of(path)
        for symbol in sorted(doc_refs[path]):
            home = def_doc.get(symbol)
            if home == path:
                continue                    # intra-document reference
            if anchor is None:
                anchorless += 1             # nothing in this file to anchor
                continue
            if home is None:
                external.add(symbol)        # stdlib / third-party seed
            add_link(anchor, symbol, "ref")

    nodes = []
    for symbol in sorted(occurring | set(kind_of) | set(rels)):
        node = {"id": symbol, "kind": kind_of.get(symbol, "symbol")}
        if symbol in def_doc:
            node["source_file"] = def_doc[symbol]
        nodes.append(node)

    graph = {
        "directed": False,
        "multigraph": False,
        "graph": {
            "schema": "graphify-v3-node-link/v1",
            "generator": "tooling/scip_convert.py",
            "root": root,
        },
        "nodes": nodes,
        "links": [links[key] for key in sorted(links)],
    }
    kinds = {}
    for link in graph["links"]:
        kinds[link["kind"]] = kinds.get(link["kind"], 0) + 1
    stats.update({
        "kinds": kinds,
        "external_targets": len(external),
        "external_sample": sorted(external)[:20],
        "anchorless_refs": anchorless,
    })
    return graph, stats


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert a SCIP index (`scip print --json`) to Graphify node-link JSON.")
    parser.add_argument("index", help="scip.Index proto-JSON file path, or '-' for stdin")
    parser.add_argument("output", help="destination node-link JSON path")
    parser.add_argument("--root", required=True,
                        help="canonical repository root used to resolve source_file paths")
    args = parser.parse_args(argv)

    try:
        if args.index == "-":
            index = json.load(sys.stdin)
        else:
            with open(args.index, "r", encoding="utf-8") as fh:
                index = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"[scip-convert] cannot read index: {exc}", file=sys.stderr)
        return 1
    if not isinstance(index, dict) or not isinstance(index.get("documents"), list):
        print("[scip-convert] not a scip.Index proto-JSON object with documents[]",
              file=sys.stderr)
        return 1

    graph, stats = convert(index, args.root)

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=1)
        fh.write("\n")

    print(f"[scip-convert] wrote {args.output}: nodes={len(graph['nodes'])} "
          f"links={len(graph['links'])} kinds={stats['kinds']} "
          f"(docs={stats['docs']} skipped_docs={stats['skipped_docs']} "
          f"locals_dropped={stats['locals_dropped']} "
          f"external_targets={stats['external_targets']} "
          f"anchorless_refs={stats['anchorless_refs']} "
          f"self_links_dropped={stats['self_links_dropped']})")
    if stats["external_sample"]:
        print("[scip-convert] WARNING unresolved-class external_bare_symbol: "
              f"count={stats['external_targets']} sample={stats['external_sample']}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
