# Unassigned namespace-strategy candidate

Date recorded: 2026-08-25.

## Evidence status

This file path is assigned to L69, whose manifest question is an evaluation
A/B protocol. The reviewed input instead contains public-source namespace and
identifier research. The content below is a misrouted, unassigned design
candidate and does not satisfy canonical L69.

## Public comparison

| Item | Type | URL | License | Maturity | Key evidence or tradeoff |
| --- | --- | --- | --- | --- | --- |
| Composite key `(corpus_id, local_key)` | strategy | https://www.w3.org/TR/rdf11-concepts/ and https://www.sqlite.org/withoutrowid.html | W3C terms / public-domain documentation | established pattern | Keeps corpus scope explicit and supports an integer surrogate for joins without requiring a global flat string identifier. |
| CURIE display form `corpus:local-key` | technique | https://www.w3.org/TR/curie/ | W3C document terms | established pattern | Provides a compact, readable prefix/reference form; uniqueness still depends on stable corpus and local-key rules. |
| Logical key `relative/path#slug@h8` | candidate strategy | repository design note | n/a | unvalidated | Separates logical identity from absolute paths and execution timestamps. The short suffix is only a collision disambiguator; the scheme needs corpus-specific validation before adoption. |
| Content-addressed primary identifiers | technique | https://git-scm.com/book/en/v2/Git-Internals-Git-Objects | n/a | established for immutable objects | Poor default identity for mutable source nodes because edits mint new identifiers; useful as an attribute or for immutable content. |
| UUIDv5 namespaced identifiers | technique | https://www.rfc-editor.org/rfc/rfc9562.html | IETF standard | established | Deterministic within a namespace but opaque to humans and still dependent on a stable logical name. |
| BLAKE3 digest attribute | tool | https://pypi.org/project/blake3/ | CC0-1.0 or Apache-2.0 | active on recorded date | Candidate digest primitive for immutable content or entity evidence, not proof of a primary-key policy. |
| Alias/remap table | migration strategy | https://www.sqlite.org/lang_createtable.html | public-domain documentation | standard relational pattern | An append-only mapping from old identifiers to new identifiers can preserve references across a deliberate scheme migration. |

## Design lead

A composite `(corpus_id, local_key)` key with a CURIE display form and an
alias/remap table is the recorded candidate. No repository-specific defect,
scale, migration duration, or adoption decision is established. The canonical
L69 A/B-protocol result remains unknown.
