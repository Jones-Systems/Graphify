# LANE L84 - Staleness signaling formats for agents (T12 freshness): freshness headers/badges on query results, real-system precedents, minimal schema for navigate skill

Date: 2026-08-25. Lane: L84. Program phase: 1 (graph/semantic search upgrade across 18 VPS repos).
Stack assumptions: Debian VPS, 16-core CPU-only, Python 3.13; BM25 via tantivy-class engine; vectors via embedded LanceDB; PPR over pinned graphifyy==0.9.16 node-link graphs. Offline, permissive licenses only, no API keys.

## Findings

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|HTTP `Age` header|technique/spec|https://www.rfc-editor.org/rfc/rfc9111.html|IETF standard (free)|core HTTP since 1997; normative in RFC 9111 (June 2022)|5|2|4|3|1|H|Age estimates how long ago the response was generated or validated by the origin, incl. cache residence; caches MUST emit computed Age when serving stored responses; fresh iff current_age < freshness_lifetime (Age:700 vs max-age=600 => stale). Direct template for our age_s field|
|Cache-Control max-age + stale-while-revalidate + stale-if-error|spec/policy|https://www.rfc-editor.org/rfc/rfc9111.html + https://www.rfc-editor.org/rfc/rfc5861.html|IETF standard (free)|SWR/SIE RFC 5861 (2010); referenced extension in RFC 9111 (2022)|5|4|5|3|1|H|Three-phase lifecycle: fresh to max_age; then serve-stale WHILE async revalidate (latency optimization); SIE extends stale-serving on errors (availability). must-revalidate prohibits stale reuse even under SWR. NOTE: RFC 9111 obsoleted Warning header - do not copy old RFC 5861 examples requiring it. Exactly the serve-stale+rebuild policy we want|
|Validators + conditional requests (ETag/Last-Modified/If-None-Match)|spec|https://www.rfc-editor.org/rfc/rfc9110.html|IETF standard (free)|RFC 9110 June 2022 (sec 8.8 validators, sec 13 conditionals); ETag practice since 1995|4|3|4|4|2|H|Client echoes validator; server answers 304 empty-body when unchanged => revalidation without recompute. Maps to our if_fresh_rev token: agent sends back last-seen rev; navigate returns freshness-block-only when unchanged, skipping the expensive multi-way query|
|Consul blocking-query headers X-Consul-Index / KnownLeader / LastContact|system pattern|https://developer.hashicorp.com/consul/api-docs/features/blocking + .../features/consistency|BUSL-1.1 impl (pattern free)|production pattern; docs current as of 2026-08|4|2|4|4|2|H|Only mainstream API separating AGE-staleness from INFRA-doubt: KnownLeader=false or LastContact above threshold => response may be stale due to replication health => clients fail closed/retry. Documented caveat: streaming backend omits health headers - absence of freshness signal must mean UNKNOWN, never VALID. Index moving backward => reset to 0 (rev-mismatch recovery)|
|Vault lease_duration / lease_renewable (TTL inside payload)|system pattern|https://developer.hashicorp.com/vault/docs/concepts/lease|BUSL-1.1 impl (pattern free)|current docs 2026; system default TTL 32 days|3|1|2|2|1|H|TTL carried IN the payload next to the data (lease_duration=3600, lease_renewable=true); renewal returns granted duration, requested is advisory. Key admission: KV/static secrets get NO enforced expiry - duration there is only a refresh hint => static corpora must CHOOSE max_age explicitly|
|Kubernetes resourceVersion + resourceVersionMatch=NotOlderThan + 410 Gone|system pattern|https://kubernetes.io/docs/reference/using-api/api-concepts|Apache-2.0 impl|current k8s docs (v1.33-era), pattern stable since 2015|2|1|2|2|1|H|Opaque server-maintained revision tokens; watch-history compaction => 410 Gone => client MUST discard cache and re-LIST, never resume blind. Precedent: rev tokens are opaque strings; compacted/rotated indexes force full rebuild => state=unknown until rebuilt|
|LanceDB native dataset versioning (table.version, list_versions, checkout, restore)|tool/native token|https://docs.lancedb.com/tables/versioning|Apache-2.0|GA; REST POST /v1/table/{id}/version/list documented 2025/2026|4|2|3|3|2|M-H|table.version -> monotonic u64 + timestamp per commit; checkout(version=N) pins reads (time travel); restore creates NEW version. Exact rev token for the vector side free of charge; versions GC'd by optimize() unless tagged - pin served version in freshness.rev|
|tantivy searcher.generation() + ReloadPolicy::OnCommitWithDelay|tool/native token|https://docs.rs/tantivy/latest/tantivy/struct.SearcherGeneration.html + enum.ReloadPolicy.html|MIT|tantivy 0.26.1 current release (docs.rs, checked 2026-08-25)|5|2|3|3|1|H|Every Searcher exposes generation(): generation_id u64 + segment->delete-opstamp map; docs warn generation_id is a SNAPSHOT identifier, NOT a persisted application-level commit number - pair with our own build counter. OnCommitWithDelay auto-reloads within tens of ms of commit; existing Searchers never see later commits => capture generation at query start, report in freshness block|
|MCP resources/subscribe + notifications/resources/updated + _meta bucket|protocol surface|https://modelcontextprotocol.io/specification/2025-11-25/schema|open specification (SDKs MIT)|spec 2025-11-25 released; draft 2026-07-28 replaces subscription model (subscriptions/listen)|3|2|2|3|1|M|MCP has NO freshness/TTL concept anywhere in 2025-11-25: change signaling is push-only (subscribe => updated{uri}, client re-reads); _meta is the sanctioned free-form metadata bucket on resource descriptors, ReadResourceResult, ResourceUpdatedNotificationParams; keys SHOULD be namespaced, mcp/modelcontextprotocol prefixes reserved. If navigate exposed over MCP: _meta:{codex-v3/freshness:{...}}; do not build against draft 2026-07-28 yet|
|Atom atom:updated / RSS pubDate|format precedent|https://www.rfc-editor.org/rfc/rfc4287.html|IETF standard (free)|RFC 4287 December 2005 (sec 4.2.2 atom:updated required per entry/feed)|2|0|1|1|0|H|Syndication's ENTIRE staleness model is one required timestamp. Proof that a single as_of field is the load-bearing minimum; everything else is policy|
|Sitemap lastmod|format precedent|https://www.sitemaps.org/protocol.html|open royalty-free|protocol v0.90, W3C datetime, ubiquitous since 2006|2|0|1|1|0|H|Corpus-level dateModified analog feeding crawler recency decisions. Our equivalent: per-file git commit timestamp stored at index time - input to rev detection, not the response envelope itself|
|DNS TTL + resolver-reported remaining TTL|format precedent|https://www.rfc-editor.org/rfc/rfc1035|IETF standard (free)|RFC 1035 (1987), still universal|3|1|2|2|1|H|Origin attaches validity window to each record; CONSUMER counts down and decides. Division of labor worth copying: indexer stamps max_age once at build; navigate computes state per query - no shared mutable clock state|
|Recency-decay ranking (ES function_score gauss/exp/linear on date fields; distance_feature)|technique|https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-function-score-query.html|Elastic-2.0/SSPL server (evidence only)|decay functions GA ~decade; current ES reference 8.x/9.x era|4|1|3|4|2|H|ORTHOGONAL AXIS: doc-age decay adjusts SCORE, not truth-state. gauss{origin:now,scale:30d,offset:7d,decay:0.5} = no penalty within offset, half-weight at scale; boost_mode:multiply preserves text relevance; MISSING date => decay factor 1 (no penalty). Apply post-fusion as w_age*decay(doc.mtime) multiplier in gated weighted RRF; distance_feature cited cheaper than script_score at volume|

## Verdict (top pick)
Top pick: HTTP-cache-shaped freshness envelope (rows Age+max-age/SWR+validators) backed by native rev tokens from tantivy generation_id + LanceDB table.version + repo git SHA. Integration sketch: indexer writes build manifest {git_sha, tantivy_generation, lancedb_version, as_of}; navigate compares at query time in O(1), emits freshness block on every response (~40 lines stdlib Python, zero deps); stale => serve results anyway + fire async reindex (SWR semantics); unknown whenever any precondition is unmeasurable.

## Minimal schema for navigate skill responses (deliverable)

```json
{
  "query": "...",
  "results": [ { "id": "...", "score": 0.82, "mtime": "2026-08-24T18:02:11Z", "...": "..." } ],
  "freshness": {
    "state": "valid",
    "as_of": "2026-08-25T09:14:03Z",
    "age_s": 412,
    "max_age_s": 900,
    "revalidate_after_s": 86400,
    "rev": { "git_sha": "a1b2c3d", "tantivy_generation": 47, "lancedb_version": 12 },
    "reason": null
  }
}
```

Field contract:
- as_of: UTC RFC3339 completion time of the index snapshot that served the query.
- age_s: server-computed now - as_of.
- max_age_s: configured freshness lifetime, stamped by indexer per corpus (DNS division of labor).
- revalidate_after_s: SWR window; beyond it state degrades to unknown (Consul-style fail-visible).
- rev: opaque-ish tokens compared against live sources at query time.

State machine (exactly three states):
- valid: stamps present AND age_s <= max_age_s AND rev matches live sources.
- stale: age_s > max_age_s OR rev mismatch; reason = age_exceeded | index_behind. Results STILL returned; async reindex triggered (RFC 5861 SWR semantics). Never silently presented as valid.
- unknown: any precondition unmeasurable - missing/corrupt manifest, negative age or clock drift > tolerance (Consul streaming-backend lesson: absence of signal means unknown, not valid), index compacted/rotated (k8s 410-Gone lesson: force full rebuild before claiming validity again).

Cheap client revalidation (ETag analog): request carries if_fresh_rev = last seen rev; if unchanged navigate returns ONLY the freshness block and omits results (304-analog), skipping BM25+vector+PPR entirely.

Defaults: max_age 900s for actively-committed repos, 86400s dormant (>90d quiet); SWR window 24h; clock-skew tolerance 5s.

HTTP-equivalence map (if navigate ever fronts HTTP/MCP): state comparison == Age vs max-age; max_age_s == Cache-Control max-age; revalidate_after_s == stale-while-revalidate; degrade-on-error == stale-if-error; rev/if_fresh_rev == ETag/If-None-Match; as_of == Date. No Warning header (obsoleted by RFC 9111); use reason instead.

Two-axis rule (do not conflate): staleness = is this ANSWER still true of corpus head (freshness block, corpus-level); recency = how OLD is each document (doc mtime, per-result, feeds row-13 decay multiplier inside weighted RRF). Keep both fields distinct.

MCP exposure note: same object under _meta:{"codex-v3/freshness":{...}} if skills are surfaced as MCP resources/resources-updated push replaces polling later; nothing to adopt from MCP today (no TTL concept in 2025-11-25).