# L73 — T11 federation: Namespace/prefix strategy for multi-corpus node IDs

INTEGRATION SKETCH (Python 3.13, offline, low-RAM, 16-core VPS):
1) nodes(id TEXT PRIMARY KEY, corpus TEXT, path TEXT, qualname TEXT, lang TEXT, rev_hash TEXT, kind TEXT) — id := f'{corpus}:{path}#{qualname}' (CURIE syntax). Decomposition columns are load-bearing insurance: they make any future scheme change a computable function over stored attributes.
2) edges(src_id TEXT, dst_id TEXT, type TEXT) — endpoints are ALWAYS global logical IDs, never engine rowids or autoincrement ints (Glean "fact ID not globally portable"; Neo4j CDC "use business keys").
3) Cross-corpus edges: store both prefixed endpoints directly; allow transiently dangling endpoints; resolve via LEFT JOIN on nodes(id) — no runtime prefix-lookup service needed because uniqueness lives in the string itself.
4) rev_hash := blake3(canonical_text).hexdigest()[:32] as ATTRIBUTE ONLY (blake3==1.0.9 wheel, ms per node on 16 cores, streaming hash constant memory).
5) Migration kit shipped day 1: _meta(key,id_scheme='l73-v1'); id_aliases(old_id TEXT PK, new_id TEXT, reason). Scheme change = one-pass UPDATE via derivation function + alias backfill; O(N) minutes at ~1e6 nodes.

WHY NOT THE ALTERNATIVES:
- Pure content-addressed (Unison-style body hashes): renames free BUT every edit mints a new node, orphaning foreign-corpus edges; needs the alias layer we get cheaper with logical IDs. Use only as rev attribute.
- Hash(repo+local-id) opaque flat IDs: loses decomposition → future scheme change requires full re-index + fuzzy symbol rematch (~10x cost, lossy). Decisive anti-pattern.
- RDF/named-graphs (pyoxigraph): viable federation substrate (graph-per-corpus, owl:sameAs stitching, TriG export) but adds a second query paradigm for marginal gain when edges already carry global IDs; keep as optional export format.
- SCIP/Kythe wholesale adoption: borrow only the identity grammar (zero dependency; Apache-2.0/MIT-documented conventions, ~50 lines of Python).

MIGRATION-COST ASYMMETRY (core finding): scheme changes are cheap iff (a) IDs are decomposable or accompanied by component columns, and (b) an alias table exists from day 1. Both cost ~nothing upfront. Retrofitting after opaque IDs ship costs a full corpus re-crawl with ER heuristics. Adopt hybrid logical-ID scheme NOW even before cross-corpus edges exist.
