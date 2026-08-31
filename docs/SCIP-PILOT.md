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

- the authorized public-fixture repository identity and one exact full source
  commit, with the expected tree identity;
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
- the exact argv and bounded environment for every process;
- the sandbox implementation, immutable configuration, mount plan, network
  denial, and their evidence format; and
- a cryptographic digest over the canonical run-lock record itself.

The executed converter and validator must come from the exact locked Graphify
revision, not from a working tree or an unbound copy. The operator must verify
every locked path and digest immediately before use. Any omitted executable or
script, mutable resolution, unexpected helper, path mismatch, digest mismatch,
or environment variance blocks the run. Only after the complete gate passes
may the run record assert that every executable byte was immutably bound.

## Exact source binding and isolated copy

The operator-owned runbook must implement these conditions without weakening
them:

1. Resolve the supplied full source commit as a commit and require exact
   equality with the lock. Never resolve or archive `HEAD`, a branch, a tag, or
   another mutable selector.
2. Inspect the locked tree before archiving. Reject every Git symlink entry
   (mode `120000`) and every gitlink/submodule entry (mode `160000`).
3. Allocate a new private run root with the locked `mktemp -d` implementation.
   Install a cleanup trap through the locked shell before creating run
   material. The trap may remove only that newly returned run root; an
   operator-selected or pre-existing cleanup path is never accepted.
4. Create the fixture destination beneath that run root and prove it is an
   empty destination owned by this run. Never reuse a pre-existing path, even
   when it appears empty.
5. Create an archive from the exact resolved commit with the locked archive
   tool. Before extraction, reject absolute or traversal paths, symlinks, hard
   links, devices, FIFOs, sockets, gitlinks, and every other non-regular entry.
6. Extract only through the locked extractor into the new empty destination.
   After extraction, reject every symlink and non-regular entry, prove every
   resolved path remains beneath the run root, and verify the extracted tree
   against the locked source tree identity. An empty fixture also fails.

Fixture preparation, if an indexer requires static package metadata, is
limited to a deterministic patch inside the isolated copy. Record its exact
bytes and digest in the run evidence. The preparation must not read the source
checkout after archive creation. This public protocol intentionally does not
prescribe source-package names, modules, tests, symbols, descriptors, or corpus
statistics.

## Credential-free filesystem containment

Before the indexer starts, place the verified tool bundle and isolated fixture
inside a fresh credential-free filesystem sandbox with its own mount and user
isolation, or an independently demonstrated equivalent boundary. Network
denial alone is insufficient.

The sandbox must have no host, home, or protected-repository mounts. It may see
only the locked tool bundle as read-only input and a new run root provisioned
inside its own ephemeral filesystem as bounded scratch space; that run root
must not be a host bind mount. Supply an empty isolated home and temporary
directory. Remove credentials and authentication variables, and expose no
SSH/GPG agents, credential stores, cloud configuration, container-engine
sockets, host runtime sockets, or unrelated filesystem trees. The operator
must record the sandbox configuration digest and a mount table from inside the
boundary before indexing. Any unexpected mount, credential, socket,
environment entry, or ability to resolve a host/protected path blocks
execution.

Network access must be denied for indexing, conversion, and validation. The
recorded denial mechanism and an independent negative connectivity check are
evidence requirements, not substitutes for filesystem containment.

## Index, convert, and validate

After all gates pass, an operator-owned runbook may invoke only lock-bound
absolute paths and exact argv. It must:

1. run the verified indexer against only the isolated fixture;
2. place `index.scip` inside the run root;
3. verify the locked Go `scip` bytes again, record its version, and render the
   index to JSON inside the run root;
4. verify and run the locked `tooling/scip_convert.py` bytes with the isolated
   fixture as the declared root;
5. verify and run the locked `tooling/validate.py` bytes against that same
   fixture; and
6. preserve the source commit and tree identity, Graphify revision, complete
   run-lock digest, sandbox and mount evidence, exact argv and environment,
   input/output digests, validation output, and resource measurements as one
   run record.

No output filename, symbol count, graph fingerprint, module name, test name,
descriptor shape, or coupling statistic from a protected corpus belongs in
this protocol.

## Converter acceptance

Before a public-fixture run, a separately lock-bound check may exercise the
converter with a generated public synthetic index covering definitions,
references, relationships, self-reference filtering, and local-symbol
filtering. Require byte-identical output from file and standard-input paths and
require the locked validator to pass. Synthetic success proves converter
mechanics only; it does not validate an indexer, fixture, deployment profile,
or broader corpus.

## Success criteria

Extension beyond the one public fixture remains out of scope unless a fresh,
independently reviewable run records all of the following:

1. the complete immutable execution gate passed with no omitted process or
   executable input;
2. the exact source commit, symlink-free fixture, isolated empty destination,
   credential-free sandbox, mount boundary, and network denial were verified;
3. validation had no new fatal class, with warnings recorded rather than
   silently accepted;
4. repeated conversion of the same locked index was byte-identical;
5. edge growth stayed below an operator-declared bound established from public
   fixture evidence;
6. peak memory, latency, and throughput were measured on the deployment target
   with the exact concurrency, thread, context, and measurement-boundary
   parameters recorded; and
7. symbol-alias behavior was either normalized or explicitly bounded by a
   public-fixture baseline.

Authority effect: none. This protocol does not authorize installation,
network access, protected-repository access, pilot execution, promotion, or
deployment.
