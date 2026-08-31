# SCIP pilot protocol — public-fixture symbol edges

This is a public-safe protocol for one small, authorized public fixture. It
does not identify a protected repository, provide a runnable pilot, or
authorize access, installation, execution, promotion, or deployment. A prior
uncommitted run report is historical context only: its source commit, inputs,
outputs, and transcript are unavailable, so none of its reported results are
acceptance evidence.

## Protocol state: unexecutable

This repository deliberately does not contain a complete run lock, sandbox
configuration, installer, bootstrapper, or executable runbook. The protocol
must remain fail-closed and unexecutable until an operator supplies and
independently verifies every immutable input described below. Repository text,
package names, version strings, release URLs, and a subset of digests are not a
complete execution authorization or lock.

No step may resolve mutable packages or download code at run time. In
particular, a remote Python bootstrap, `npx`, `npm install`, a registry-resolved
package, or a launcher that downloads a JVM is prohibited.

## Immutable execution gate

Before any pilot process starts, one immutable, operator-supplied run lock must
bind all of the following:

- an immutable local source-object bundle for the authorized public fixture,
  including its path, byte count, digest, one exact full commit and tree
  identity, and a complete reachable-object manifest;
- the exact Graphify tool revision and the exact blob identity, byte count, and
  cryptographic digest of the executed `tooling/scip_convert.py` and
  `tooling/validate.py` bytes;
- the SCIP indexer package name and version plus the local package artifact's
  path, byte count, and cryptographic digest;
- the exact indexer runner path, version output, byte count, and cryptographic
  digest;
- the Python executable and immutable runtime/dependency closure, including
  exact versions, local paths, byte counts, and cryptographic digests;
- the exact JVM distribution, version, path, byte count, and cryptographic
  digest when any runner can invoke Java;
- the Go `scip` CLI path, version, byte count, and cryptographic digest;
- the shell and every control-plane binary used for source resolution,
  temporary-directory allocation, tree inspection, archive creation and
  validation, extraction, filesystem inspection, hashing, permission changes,
  sandbox launch, and cleanup, each with an exact absolute path, version or
  immutable build identity, byte count, and cryptographic digest;
- the dynamic loader, shared libraries, plugins, helper scripts, and executable
  runtime closure reachable by every process above, with exact local identity,
  byte count, and cryptographic digest;
- any fixture-preparation patch as a pre-locked patch with exact bytes and
  digest, plus the expected canonical final fixture manifest and its digest;
- the exact argv and bounded environment for every process;
- the sandbox implementation, immutable configuration, mount and namespace
  plan, descendant process policy, capability/no-new-privileges policy,
  network denial, resource bounds, and their evidence format; and
- a cryptographic digest over the canonical run-lock record itself.

The executed converter and validator must come from the exact locked Graphify
revision, not from a working tree or an unbound copy. The operator must verify
every locked path and digest immediately before use. Any omitted executable or
script, mutable resolution, unexpected helper, path mismatch, digest mismatch,
or environment variance blocks the run. Only after the complete gate passes
may the run record assert that every executable byte was immutably bound.

## Exact source binding and isolated copy

The containment boundary in the next section must already be active before
source verification or resolution begins. The source checkout is never
mounted. Instead, the sandbox receives the lock-bound local source-object
bundle in its own ephemeral filesystem. The operator-owned runbook must
implement these conditions without weakening them:

1. Prove the source is complete local, non-promisor input before resolving any
   selector: reject shallow or partial-clone state, promisor configuration,
   missing reachable objects, object alternates, and any lazy fetch path. Walk
   the exact commit's full reachable tree/blob closure and verify every object
   locally by identity against the locked reachable-object manifest. Network
   denial must make an attempted fetch fail closed rather than populate it.
2. Resolve the supplied full source commit as a commit and require exact
   equality with the lock. Never resolve or archive `HEAD`, a branch, a tag, or
   another mutable selector.
3. Inspect the locked tree before archiving. Reject every Git symlink entry
   (mode `120000`) and every gitlink/submodule entry (mode `160000`).
4. Allocate a new private run root with the locked `mktemp -d` implementation.
   Install a cleanup trap through the locked shell before creating run
   material. The trap may remove only that newly returned run root; an
   operator-selected or pre-existing cleanup path is never accepted.
5. Create the fixture destination beneath that run root and prove it is an
   empty destination owned by this run. Never reuse a pre-existing path, even
   when it appears empty.
6. Create an archive from the exact resolved commit with the locked archive
   tool. Before extraction, reject absolute or traversal paths, symlinks, hard
   links, devices, FIFOs, sockets, gitlinks, and every other non-regular entry.
7. Extract only through the locked extractor into the new empty destination.
   After extraction, reject every symlink and non-regular entry, prove every
   resolved path remains beneath the run root, and verify the extracted tree
   against the locked source tree identity. An empty fixture also fails.

## Pre-locked preparation and complete final fixture identity

Optional preparation is not an operator-time editing allowance. If an indexer
requires static package metadata, the immutable run lock must contain the
pre-locked patch, its exact base-tree identity, byte count, digest, exact
lock-bound applicator and argv, and a complete expected post-patch fixture
manifest. A no-change run records an explicit empty-patch identity. Missing,
additional, reordered, context-mismatched, or fuzz-applied changes fail closed.

The final fixture manifest must canonically enumerate every final relative
path with its entry type, mode, byte count, and cryptographic digest. Regular
files use a content digest. Directory entries use the byte count and digest of
their canonical sorted child-record encoding. Symlinks and other non-regular
entries remain prohibited. The manifest must include its own canonical digest
in the run lock.

After applying the pre-locked patch inside the sandbox, rescan the complete
fixture and require exact equality with the locked final fixture manifest
immediately before indexing. Then make the fixture a read-only immutable
snapshot for the indexer and place all index/output writes in separate bounded
scratch space. No mutation, package resolution, lazy fetch, or metadata
generation may occur between final-manifest verification and indexing.
Preparation must not read the source bundle after archive creation. This
public protocol intentionally does not prescribe source-package names,
modules, tests, symbols, descriptors, or corpus statistics.

## All-stage network, process, filesystem, and resource containment

The lock-bound sandbox launcher is the only pre-boundary control-plane
process. Before the first pilot process, it must create a fresh credential-free
filesystem, user, mount, PID, network, and IPC namespace boundary or an
independently demonstrated stronger isolation boundary. Every pilot stage and
every descendant must remain inside that same boundary: source completeness
proof, source resolution, tree inspection, archive creation and validation,
extraction, preparation, final-manifest verification, indexing, conversion,
validation, evidence collection, and cleanup. A helper, hook, filter, archive
program, patch tool, compiler, indexer child, or validator child that can spawn
or execute outside the boundary blocks the run.

This credential-free filesystem sandbox is mandatory for the complete pilot,
not only for the indexer.

Network access must be denied before source verification and remain denied for
every stage and descendant. Deny all address families, DNS, proxies, inherited
network descriptors, and network-capable host or runtime sockets. A negative
connectivity test from inside the boundary and descendant-inheritance evidence
are required. Network denial must prevent Git, package managers, build tools,
indexers, and language runtimes from lazy-fetching code or objects; it is not a
substitute for the other containment controls.

The sandbox must have no host, home, or protected-repository mounts. It may see
only the locked tool bundle and locked local source-object bundle as read-only
seeded input, plus a new run root provisioned inside its own ephemeral
filesystem as bounded scratch space; that run root must not be a host bind
mount. Supply an empty isolated home and temporary directory. Remove
credentials and authentication variables, and expose no SSH/GPG agents,
credential stores, cloud configuration, container-engine sockets, host runtime
sockets, or unrelated filesystem trees.

Use a private process namespace. Deny the host `/proc`; if a process filesystem
is required, mount a namespace-private minimal `/proc` that exposes only
sandbox PIDs. Do not expose host `/sys`, host devices beyond an exact minimal
allowlist, host cgroup controls, or host process/debug interfaces. Drop every
capability, set no-new-privileges for the complete descendant tree, and bind an
immutable syscall/process policy that prevents namespace escape, privilege
gain, tracing of host processes, new mounts, and unapproved executable paths.

The run lock must set finite aggregate and per-process PID-count, CPU-time,
memory, output-file-size, open-file, scratch-space, and wall-clock bounds for
the sandbox and all descendants. The supervisor must enforce those bounds,
terminate the complete descendant tree on timeout or violation, and record the
limit configuration and terminal state. Missing, unlimited, unenforced, or
descendant-bypassable bounds block execution.

Before source verification, and again immediately before indexing, record from
inside the boundary the sandbox configuration digest, mount table, namespace
identities, process view, capability sets, no-new-privileges state, network
denial evidence, and effective resource bounds. Any unexpected mount,
credential, socket, environment entry, host PID/path visibility, capability,
process escape, or resource-policy variance blocks execution.

## Index, convert, and validate

After all gates pass, an operator-owned runbook may invoke only lock-bound
absolute paths and exact argv. It must:

1. verify the complete final fixture manifest, read-only fixture state, and
   all-stage containment evidence immediately before indexing;
2. run the verified indexer against only the isolated read-only fixture;
3. place `index.scip` inside the separate bounded output area;
4. verify the locked Go `scip` bytes again, record its version, and render the
   index to JSON inside the run root;
5. verify and run the locked `tooling/scip_convert.py` bytes with the isolated
   fixture as the declared root;
6. verify and run the locked `tooling/validate.py` bytes against that same
   fixture; and
7. preserve the source commit/tree/object-closure identity, final fixture
   manifest, Graphify revision, complete run-lock digest, sandbox, namespace,
   process, network, mount, and resource-bound evidence, exact argv and
   environment, input/output digests, validation output, and resource
   measurements as one run record.

No output filename, symbol count, graph fingerprint, module name, test name,
descriptor shape, or coupling statistic from a protected corpus belongs in
this protocol.

## Converter acceptance

Before a public-fixture run, a separately lock-bound check may exercise the
converter with a generated public synthetic index covering definitions,
references, relationships, self-reference filtering, and local-symbol
filtering. That check and all descendants remain under the same all-stage
containment and finite resource-bound requirements. Require byte-identical
output from file and standard-input paths and require the locked validator to
pass. Synthetic success proves converter mechanics only; it does not validate
an indexer, fixture, deployment profile, or broader corpus.

## Success criteria

Extension beyond the one public fixture remains out of scope unless a fresh,
independently reviewable run records all of the following:

1. the complete immutable execution gate passed with no omitted process or
   executable input;
2. the complete local non-promisor source closure, exact source commit,
   symlink-free fixture, pre-locked patch, complete final fixture manifest,
   isolated empty destination, and read-only final fixture were verified;
3. every stage and descendant remained in the credential-free network,
   filesystem, process, privilege, and finite-resource boundary;
4. validation had no new fatal class, with warnings recorded rather than
   silently accepted;
5. repeated conversion of the same locked index was byte-identical;
6. edge growth stayed below an operator-declared bound established from public
   fixture evidence;
7. peak memory, latency, and throughput were measured on the deployment target
   with the exact concurrency, thread, context, and measurement-boundary
   parameters recorded; and
8. symbol-alias behavior was either normalized or explicitly bounded by a
   public-fixture baseline.

Authority effect: none. This protocol does not authorize installation,
network access, protected-repository access, pilot execution, promotion, or
deployment.
