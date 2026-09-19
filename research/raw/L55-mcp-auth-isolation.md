# LANE L55 - T8 MCP: auth/isolation for a shared local graph-query server
Research date: 2026-08-25. The table retains public protocol, framework,
database, and operating-system controls as recorded. No deployed endpoint,
identity provider, token source, resource limit, or logging policy is
established.

Protocol context: MCP spec 2025-06-18 lets servers omit Mcp-Session-Id
(stateless mode). A recorded 2026-07-28 release-candidate post proposed
removing the initialize handshake and Mcp-Session-Id; it is retained as RC
evidence, not a claim about a final specification. The authorization section
describes OAuth 2.1 resource servers, RFC 8707 audience binding, and a
prohibition on token passthrough. Sources:
modelcontextprotocol.io/specification/2025-06-18/basic/transports,
modelcontextprotocol.io/specification/2025-06-18/basic/authorization, and
blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/.

| Item | Type | URL | License | Maturity | StackFit | EffGain | EffectGain | QualGain | AdoptCost | Conf | KeyEvidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Stateless Streamable HTTP (no Mcp-Session-Id, no sticky session store) | technique | https://modelcontextprotocol.io/specification/2025-06-18/basic/transports | spec | stable in the recorded 2025-06-18 specification; later RC noted separately | 5 | 3 | 3 | 4 | 1 | H | The 2025-06-18 server may omit the session identifier; the recorded 2026-07-28 RC proposed removing protocol sessions. |
| Per-client opaque bearer tokens + FastMCP StaticTokenVerifier | strategy | https://gofastmcp.com/servers/auth/token-verification | Apache-2.0 (LICENSE checked 2026-08-25) | production-documented, FastMCP 3.x/4.x | 5 | 4 | 3 | 3 | 1 | H | StaticTokenVerifier maps an opaque key to claims such as subject and scopes; token issuance and delivery remain outside this report. JWTVerifier applies to signed JWTs. |
| Full MCP-native OAuth 2.1 + RFC 8707 aud binding + RFC 9728 metadata | technique | https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization | spec | ratified, SDK-mature | 2 | 2 | 5 | 5 | 3 | H | Mandated for remote servers and designed to prevent confused-deputy token passthrough; fit depends on the selected deployment topology and threat model. |
| Unix domain socket + SO_PEERCRED peer creds | technique | https://man7.org/linux/man-pages/man7/unix.7.html | n/a | kernel-stable | 3 | 2 | 4 | 4 | 2 | M | SCM_CREDENTIALS give kernel-verified UID, zero-token local auth; needs UDS-to-loopback shim since most MCP clients speak HTTP |
| FastMCP RateLimitingMiddleware / SlidingWindowRateLimitingMiddleware with get_client_id | tool | https://gofastmcp.com/servers/middleware | Apache-2.0 | shipped since 2.9.0, recorded in 3.x/4.x | 5 | 3 | 3 | 3 | 1 | H | Parameters include rate and burst capacity; a custom client key can use an authenticated subject. In-process counters avoid an external store but still need measured memory and concurrency bounds. |
| nginx limit_req / Caddy edge limits in front of loopback port | strategy | https://nginx.org/en/docs/http/ngx_http_limit_req_module.html | BSD-2 / Apache-2.0 | boring-stable | 3 | 2 | 3 | 3 | 2 | H | request-size + concurrency caps independent of app code; second wall vs framework bugs |
| agentgateway: mcpAuthentication strict JWT, CEL mcpAuthorization per tool/target, localRateLimit bucket; denied tools stripped from tools/list and blocked on direct call | tool | https://agentgateway.dev/docs/standalone/main/configuration/security/mcp-authz/ | Apache-2.0 (LICENSE checked 2026-08-25) | young, active, AGNTCY/Linux Foundation, Rust | 2 | 2 | 4 | 4 | 3 | M | full policy plane; per-tool global quotas need external Envoy RL service + Redis; worth it only multi-upstream |
| SQLite kill-switches: SQLITE_OPEN_READONLY open flag + PRAGMA query_only + sqlite3_set_authorizer SELECT-only allowlist (deny INSERT/UPDATE/DELETE/DDL/ATTACH/DETACH/PRAGMA) | technique | https://www.sqlite.org/c3ref/open.html ; https://www.sqlite.org/pragma.html#pragma_query_only ; https://www.sqlite.org/c3ref/set_authorizer.html | public domain | ancient-stable; authorizer fires at prepare/re-prepare | 5 | 4 | 5 | 5 | 1 | H | sqlite.org documents that query_only alone is not a true read-only connection, READONLY is file-level, and the authorizer is the SQL policy hook. |
| Kuzu containment: Database(read_only=True) + conn.set_query_timeout(ms) + conn.interrupt(), capped threads | technique | https://kuzudb.github.io/api-docs/python/kuzu.html | MIT | repo/docs archived 2025-10-10 | 4 | 4 | 4 | 4 | 1 | H | The recorded API documents read-only opening, per-connection timeout, interruption, and thread controls. Package-version compatibility requires fresh verification. |
| Parameterized systemd sandbox: DynamicUser, measured memory and CPU controls, ProtectSystem=strict, read-only corpus paths, restricted address families, and restart policy | technique | https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html | LGPL-2.1 | documented systemd controls | 5 | 4 | 4 | 4 | 1 | H | OS-level containment can bound one service. Exact values and restart behavior must come from current capacity, failure, and recovery requirements. |
| FastMCP 4.x authenticated state namespacing | technique | https://gofastmcp.com/servers/sessions | Apache-2.0 | new in 4.0.0 on the recorded date | 4 | 3 | 4 | 4 | 1 | H | The public documentation keys state to an authenticated subject so a handle resolves only within that identity namespace; unauthenticated operation is described as single-tenant. |
| Server-managed scratch namespaces separated from a read-only corpus | strategy | https://www.sqlite.org/lang_attach.html | n/a | standard mechanics | 4 | 3 | 3 | 3 | 2 | M | A verified subject can select a server-owned scratch namespace while corpus storage remains read-only; client-supplied namespace identifiers and direct ATTACH operations should not determine authority. |
| Content-free rate counters and circuit breaker | strategy | https://gofastmcp.com/servers/middleware | Apache-2.0 | documented hooks | 5 | 3 | 3 | 3 | 1 | M | Middleware can reject over-budget requests using authenticated-subject counters. Request bodies, query text, paths, and returned content are outside this candidate and must not be captured implicitly. |
| Docker MCP Gateway isolation: --cpus/--memory/--block-network/--block-secrets, no-new-privileges, read-only binds default, exec interceptors, Bearer default on HTTP | tool | https://github.com/docker/mcp-gateway/blob/main/docs/security.md | MIT (LICENSE checked 2026-08-25) | active; advisory GHSA-g879-4j4f-6vj7 published 2026-07-09, unauthenticated access container-mode HTTP >=0.25.0, fixed 0.43.1 | 2 | 2 | 3 | 3 | 3 | M | strong walls, no native rate limiting (docs front with proxy), adds Docker dep; interceptors operator-trusted not security boundary |

The recorded candidate is layered containment: authenticated client identity,
rate and concurrency bounds, a strictly read-only corpus connection,
server-owned scratch isolation when writes are required, and an
operating-system sandbox. Loopback reachability is not authentication. Exact
token issuance, OAuth use, namespace lifetime, counters, resource limits, and
content-free observability require a separate deployment design.

No concrete endpoint, tool list, middleware order, token-delivery mechanism,
or resource ceiling is accepted by this lane.
