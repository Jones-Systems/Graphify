## Cassandra anti-entropy repair

**Anti-entropy repair** is Cassandra’s mechanism for reconciling replicas that may have diverged. Hinted handoff and read repair are best-effort; repair provides a systematic comparison of replicas for their common token ranges. Cassandra uses **Merkle trees**—hierarchical hashes—to locate ranges that differ, then streams the differing data between replicas. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html?highlight=consistency&utm_source=openai))

The main commands are:

```bash
# Incremental repair; default in current Cassandra documentation
nodetool repair

# Full repair
nodetool repair --full

# Repair only primary ranges owned by this node
nodetool repair -pr

# Estimate streaming without changing data
nodetool repair -prv

# Validate already-repaired data without streaming
nodetool repair -vd
```

A repair initiated on one node covers the ranges replicated by that node; it does not automatically mean that the entire cluster has been repaired. `-pr` is commonly used when coordinating repairs across all nodes, to avoid repeatedly repairing the same replica ranges. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/repair.html?utm_source=openai))

---

## How the Merkle-tree comparison works

Conceptually, repair proceeds like this:

1. Cassandra selects a token range and its replica set.
2. Each participating replica reads the relevant data and builds a Merkle tree.
3. The root and lower-level hashes are compared.
4. If a subtree has the same hash on all replicas, that entire subtree is assumed to match.
5. If a subtree differs, Cassandra descends into its children to localize the mismatch.
6. The mismatching token ranges are synchronized by streaming data from the replica with the required current data.

A Merkle tree therefore avoids comparing every partition byte-for-byte across the network. Equal hashes allow Cassandra to skip large matching sections. The tradeoff is tree resolution: if a leaf represents a large token range, a small mismatch can cause more data than strictly necessary to be streamed. Cassandra supports sub-range repair to make trees more precise for smaller ranges. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html?highlight=consistency&utm_source=openai))

A simplified tree might look like:

```text
                         root hash
                       /            \
                 hash A              hash B
                /     \             /     \
            range 1  range 2    range 3  range 4
```

If `hash A` matches between replicas, Cassandra does not need to inspect ranges 1 and 2 further. If `hash B` differs, it compares ranges 3 and 4 individually and streams only the mismatching section—or a broader section if the tree cannot distinguish the exact partition.

The actual tree is built during validation work on the selected data. Cassandra exposes repair-related work through the `AntiEntropyStage`, and metrics include validated bytes, validated partitions, anticompaction time, and synchronization time. ([cassandra.apache.org](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html?utm_source=openai))

---

## Full repair versus incremental repair

### Full repair

A full repair considers **all data** in the selected token ranges:

```bash
nodetool repair --full
```

It is appropriate when you need to check data that Cassandra previously considered repaired—for example:

- after suspected disk corruption;
- after operator error or accidental data deletion;
- after certain topology or replication-factor changes;
- when repaired data is suspected to be inconsistent;
- as periodic defense against bugs or failures that incremental repair will not rediscover.

The important property is that full repair does not exclude data merely because it was repaired previously. Cassandra’s documentation explicitly states that incremental repair will not retry data once it has been marked repaired, so occasional full repairs are still recommended. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/repair.html?utm_source=openai))

### Incremental repair

Incremental repair considers the **unrepaired data set**, generally corresponding to data written or changed since the relevant previous incremental repair:

```bash
nodetool repair
```

The benefit is that repeated repairs process a smaller amount of data, reducing validation, disk I/O, and streaming cost. However, “incremental” does not mean that Cassandra keeps a per-row timestamp saying “this row was repaired.” It relies primarily on SSTable repair state and the repaired/unrepaired data separation. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/repair.html?utm_source=openai))

---

## How incremental repair works internally

For modern Cassandra’s consistent incremental repair, the important sequence is approximately:

```text
1. Select token ranges and participating replicas
2. Prepare the incremental repair session
3. Anti-compact relevant SSTables
4. Mark the resulting data as pending repair
5. Build Merkle trees over the repair data
6. Compare the trees
7. Stream mismatching data
8. Finalize the repair
9. Mark successfully repaired data as repaired
```

### 1. Select the repair data

Cassandra identifies SSTables containing unrepaired data overlapping the token ranges being repaired. It must account for the complete relevant SSTables when estimating work because incremental repair may need to rewrite them during anticompaction. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/auto_repair.html?utm_source=openai))

### 2. Anti-compaction

**Anticompaction** splits SSTables so that data in the repair range can be separated from data outside the range. The resulting SSTables are logically separated into categories such as:

```text
repaired data
unrepaired data
pending-repair data
```

This is necessary because ordinary compaction must not freely mix repaired and unrepaired data again. Cassandra runs separate compaction handling for those sets. ([cassandra.apache.org](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html?utm_source=openai))

For example, an SSTable may contain partitions across a broad token range:

```text
SSTable X:
  tokens: 0 ------------------------------ 100

Repair range:
  tokens:             40 -------- 70
```

Anticompaction may rewrite it into something conceptually like:

```text
SSTable X1: unrepaired, tokens 0 -------- 40
SSTable X2: pending repair, tokens 40 --- 70
SSTable X3: unrepaired, tokens 70 ------- 100
```

This rewrite can be expensive, particularly when:

- SSTables are large;
- many SSTables overlap the same partitions;
- repairs are too broad;
- compaction strategy produces substantial overlap.

The Cassandra documentation specifically warns that the first transition to incremental repair on an existing large cluster can create significant anticompaction work. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/auto_repair.html?utm_source=openai))

### 3. Pending repair protects correctness

The data selected for the repair is initially marked **pending repair**, rather than immediately being declared successfully repaired. This prevents the data from being treated as complete before all replicas have participated successfully.

The consistent incremental-repair design performs anticompaction before Merkle-tree validation and streaming. After streaming succeeds, the session is finalized and the data becomes repaired; if the session fails, the pending state can be released or the session can be failed rather than incorrectly marking the data as repaired. ([issues.apache.org](https://issues.apache.org/jira/browse/CASSANDRA-14685?focusedCommentId=16599086&page=com.atlassian.jira.plugin.system.issuetabpanels%3Acomment-tabpanel&utm_source=openai))

### 4. Build and compare Merkle trees

Merkle trees are then built over the repair data—not necessarily over every byte stored in the table. Matching subtrees are skipped; mismatching subtrees become candidate ranges for synchronization. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html?highlight=consistency&utm_source=openai))

### 5. Stream differences

For mismatching ranges, Cassandra streams the required partitions or SSTable sections between replicas. The data is reconciled using Cassandra’s normal timestamp/tombstone semantics, so newer values and deletes take precedence according to Cassandra’s conflict-resolution rules.

### 6. Mark data repaired

Once the repair session completes successfully, the participating data is marked repaired. Future incremental repairs exclude that data and concentrate on data that remains unrepaired. This is the main reason incremental repair becomes cheaper over time—provided it is run continuously. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/repair.html?utm_source=openai))

---

## Why repairs must continue regularly

Incremental repair is not a one-time operation. New writes continually create unrepaired SSTables. Cassandra must continue running incremental repairs so those SSTables can be reconciled and eventually compacted with the repaired data appropriately.

If incremental repair is run once and then abandoned, old repaired SSTables can remain separate from newer unrepaired SSTables. That separation can prevent compaction from dropping obsolete data and tombstones efficiently. ([cassandra.apache.org](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html?utm_source=openai))

Repair also needs to run frequently enough that `gc_grace_seconds` does not expire on unrepaired data. If a tombstone disappears on one replica before another replica has been repaired, deleted data can potentially be resurrected during later reconciliation. The Cassandra repair guide recommends scheduling repairs with enough margin before that expiration window. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/repair.html?utm_source=openai))

---

## Important operational distinction

### Incremental repair protects against:

- missed writes;
- replicas that were temporarily unavailable;
- ordinary replica divergence since the last incremental repair;
- unrepaired data that has not yet been synchronized.

### Incremental repair does not reliably protect against:

- disk corruption;
- data removed by an operator;
- data-loss bugs;
- Cassandra bugs that caused already-repaired replicas to agree on incorrect data;
- inconsistencies introduced after data was marked repaired.

That is why full repair, or at least validation of repaired data followed by full repair when inconsistencies are found, remains necessary. `nodetool repair -vd` compares repaired data without streaming and is useful for detecting this class of problem. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/repair.html?utm_source=openai))

---

## Repaired SSTable metadata

Repaired state is stored in SSTable metadata, commonly represented by a `repairedAt` value. The `sstablerepairedset` tool can inspect or modify this state, but it must be used carefully:

```bash
sstablerepairedset --is-repaired ...
sstablerepairedset --is-unrepaired ...
```

Running `nodetool repair` and manually changing SSTable repaired metadata are not equivalent operations. The Cassandra documentation warns that `sstablerepairedset` should be run with Cassandra stopped, and manually marking data repaired can bypass the consistency guarantees that a real repair provides. ([cassandra.apache.org](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/sstablerepairedset.html?utm_source=openai))

---

## Practical mental model

Think of incremental repair as a moving boundary:

```text
older data                         newer data
|--------------------------------------|
        repaired       |    unrepaired
                       ^
                next repair window
```

A successful repair moves some data from:

```text
unrepaired -> pending repair -> repaired
```

The Merkle tree determines whether the selected replicas agree. Anticompaction makes the selected data independently trackable. Streaming fixes mismatches. Finalization records that the synchronized data is now repaired.

So the concise answer is:

> **Merkle trees identify which token-range sections differ; incremental repair restricts that comparison to unrepaired data, first isolating it with anticompaction and then marking it repaired only after the repair session succeeds.**

## Recommended Apache Cassandra documentation

- **Repair guide** — full versus incremental repair, `nodetool repair`, scheduling, primary ranges, preview, and validation. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/repair.html?utm_source=openai))
- **Dynamo architecture** — anti-entropy repair, Merkle trees, sub-range repair, and incremental repair conceptually. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html?highlight=consistency&utm_source=openai))
- **Compaction overview** — anticompaction and repaired/unrepaired SSTable behavior. ([cassandra.apache.org](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html?utm_source=openai))
- **Auto Repair guide** — scheduling, range splitting, incremental-repair sizing, and migration considerations. ([cassandra.apache.org](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/auto_repair.html?utm_source=openai))
- **Repair metrics** — validation, anticompaction, synchronization, and repaired-byte metrics. ([cassandra.apache.org](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html?utm_source=openai))

## Sources
21 sources
[1] Repair | Apache Cassandra Documentation
    https://cassandra.apache.org/doc/latest/cassandra/managing/operating/repair.html
    when coordinating repairs across all nodes, to avoid repeatedly repairing the same replica ranges. (cassandra.apache.org)

---

## How the Merkle-tree comparison works

Conceptually, repair proceeds like this:

1. Cassand
[2] Dynamo | Apache Cassandra Documentation
    https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html?highlight=consistency
    hierarchical hashes—to locate ranges that differ, then streams the differing data between replicas. (cassandra.apache.org)

The main commands are:

```bash
# Incremental repair; default in current Cassandra documentation
n
[3] Auto Repair | Apache Cassandra Documentation
    https://cassandra.apache.org/doc/latest/cassandra/managing/operating/auto_repair.html
    les when estimating work because incremental repair may need to rewrite them during anticompaction. (cassandra.apache.org)

### 2. Anti-compaction

**Anticompaction** splits SSTables so that data in the repair range can be
[4] Compaction overview | Apache Cassandra Documentation
    https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html
    mix repaired and unrepaired data again. Cassandra runs separate compaction handling for those sets. (cassandra.apache.org)

For example, an SSTable may contain partitions across a broad token range:

```text
SSTable X:
  t
[5] https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/repair_admin.html
    https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/repair_admin.html
[6] Monitoring | Apache Cassandra Documentation
    https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html
    trics include validated bytes, validated partitions, anticompaction time, and synchronization time. (cassandra.apache.org)

---

## Full repair versus incremental repair

### Full repair

A full repair considers **all data
[7] sstablerepairedset | Apache Cassandra Documentation
    https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/sstablerepairedset.html
    d manually marking data repaired can bypass the consistency guarantees that a real repair provides. (cassandra.apache.org)

---

## Practical mental model

Think of incremental repair as a moving boundary:

```text
older d
[8] https://cassandra.apache.org/doc/latest/cassandra/managing/configuration/cass_yaml_file.html
    https://cassandra.apache.org/doc/latest/cassandra/managing/configuration/cass_yaml_file.html
[9] https://cassandra.apache.org/doc/stable/cassandra/architecture/index.html
    https://cassandra.apache.org/doc/stable/cassandra/architecture/index.html
[10] https://cassandra.apache.org/doc/latest/cassandra/developing/cql/indexing/sai/sai-read-write-paths.html
    https://cassandra.apache.org/doc/latest/cassandra/developing/cql/indexing/sai/sai-read-write-paths.html
[11] https://cassandra.apache.org/doc/stable/cassandra/managing/operating/index.html
    https://cassandra.apache.org/doc/stable/cassandra/managing/operating/index.html
[12] https://cassandra.apache.org/_/blog/Reaper-Anti-entropy-Repair-Made-Easy.html
    https://cassandra.apache.org/_/blog/Reaper-Anti-entropy-Repair-Made-Easy.html
[13] https://issues.apache.org/jira/browse/CASSANDRA-2699
    https://issues.apache.org/jira/browse/CASSANDRA-2699
[14] https://issues.apache.org/jira/browse/CASSANDRA-15027
    https://issues.apache.org/jira/browse/CASSANDRA-15027
[15] [CASSANDRA-14685] Incremental repair 4.0 : SSTables remain locked forever if the coordinator dies during streaming - ASF Jira
    https://issues.apache.org/jira/browse/CASSANDRA-14685?focusedCommentId=16599086&page=com.atlassian.jira.plugin.system.issuetabpanels%3Acomment-tabpanel
    can be released or the session can be failed rather than incorrectly marking the data as repaired. (issues.apache.org)

### 4. Build and compare Merkle trees

Merkle trees are then built over the repair data—not necess
[16] https://issues.apache.org/jira/browse/CASSANDRA-9143
    https://issues.apache.org/jira/browse/CASSANDRA-9143
[17] https://issues.apache.org/jira/browse/CASSANDRA-14763
    https://issues.apache.org/jira/browse/CASSANDRA-14763
[18] https://issues.apache.org/jira/browse/CASSANDRA-9143?subTaskView=unresolved
    https://issues.apache.org/jira/browse/CASSANDRA-9143?subTaskView=unresolved
[19] https://cassandra.apache.org/_/blog/Introducing-Transient-Replication.html
    https://cassandra.apache.org/_/blog/Introducing-Transient-Replication.html
[20] https://issues.apache.org/jira/secure/attachment/12459754/Partitionedcountersdesigndoc.pdf
    https://issues.apache.org/jira/secure/attachment/12459754/Partitionedcountersdesigndoc.pdf
[21] https://issues.apache.org/jira/secure/attachment/12940280/12940280_Looking%2Btowards%2Ban%2BOfficial%2BCassandra%2BSidecar%2B-%2BNetflix.pdf
    https://issues.apache.org/jira/secure/attachment/12940280/12940280_Looking%2Btowards%2Ban%2BOfficial%2BCassandra%2BSidecar%2B-%2BNetflix.pdf