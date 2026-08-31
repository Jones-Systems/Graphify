# L83 — Refresh scheduling under a memory floor

Date recorded: 2026-08-25.

## Evidence boundary

Only the parameterized, public systemd and cgroup design is retained. No
operating-system version, memory capacity, swap state, unit installation,
numeric limit, or deployment readiness is established.

Target constraints: Linux with systemd and cgroup v2, CPU-only execution, and an explicit `MemAvailable` floor. The design uses admission gates, soft throttles, hard caps, scheduling bias, and single-writer serialization.

## Candidate components

| Component | Public reference | Purpose | Configuration rule |
| --- | --- | --- | --- |
| Dedicated batch slice | https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html | Bound aggregate refresh memory, CPU, and I/O | Derive `MemoryHigh`, `MemoryMax`, `CPUWeight`, `CPUQuota`, and `IOWeight` from measured workload and current capacity; do not copy recorded literals. |
| `MemAvailable` admission gate | https://docs.kernel.org/filesystems/proc.html | Delay a run when the declared floor plus working-set allowance is unavailable | Minimum admission = floor + measured stage headroom; time out with a temporary-failure status and re-evaluate later. |
| Per-stage floor guard and checkpoints | https://docs.kernel.org/filesystems/proc.html | Recheck between lexical, vector, graph, fusion, and entity-resolution stages | Pause before a stage if current available memory is below the floor; resume only from a durable stage boundary. |
| CPU and I/O deprioritization | https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html | Let interactive workloads win under contention | Use `Nice`, scheduling policy, weights, and quotas as measured controls; I/O priority is scheduler-dependent. |
| PSI-aware throttling | https://docs.kernel.org/accounting/psi.html | Respond to sustained memory stalls | Treat a PSI threshold and observation window as deployment parameters; validate the pause policy under load. |
| OOM bias and cgroup-local ceiling | https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html | Contain a runaway refresh | `MemoryHigh` throttles first; `MemoryMax` is the last-resort ceiling. Apply any `OOMScoreAdjust` only after verifying the wider OOM policy. |
| Scheduled catch-up | https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html | Run calendar jobs after downtime | Use `OnCalendar`, `Persistent=true`, and a measured randomized delay; distinguish timer accuracy from jitter. |
| Single-writer lock | https://man7.org/linux/man-pages/man1/flock.1.html | Prevent concurrent writers to one index | Lock by index target; both scheduled and ad-hoc invocations must enter the same budget and lock path. |

## Parameterized unit shape

```ini
# batch-refresh.slice
[Slice]
MemoryAccounting=yes
CPUAccounting=yes
IOAccounting=yes
MemoryHigh=<measured-soft-limit>
MemoryMax=<measured-hard-limit>
CPUWeight=<measured-batch-weight>
CPUQuota=<measured-batch-quota>
IOWeight=<measured-batch-weight>
```

```ini
# graph-refresh.service
[Service]
Type=oneshot
Slice=batch-refresh.slice
Nice=<batch-nice>
CPUSchedulingPolicy=idle
IOSchedulingClass=idle
OOMScoreAdjust=<validated-batch-bias>
ExecStartPre=<gate-command> <floor-plus-headroom> <max-wait> <poll-interval>
ExecStart=<refresh-command>
Restart=on-failure
RestartSec=<backoff>
```

```ini
# graph-refresh.timer
[Timer]
OnCalendar=<deployment-schedule>
RandomizedDelaySec=<deployment-jitter>
FixedRandomDelay=true
Persistent=true
Unit=graph-refresh.service
```

The gate reads `MemAvailable` from `/proc/meminfo`, admits only when it meets the parameterized threshold, and returns a temporary-failure code after the bounded wait. The refresh rechecks the declared floor between stages, serializes each writer with `flock`, and may pause when a validated PSI threshold is exceeded.

## Verdict

The recorded candidate is a capped batch slice plus a `MemAvailable` admission gate, stage-level floor checks with checkpoints, and OOM bias toward the batch. The structure is supported by the cited kernel and systemd interfaces; every numeric limit, threshold, schedule, command path, and unit location remains deployment-specific and requires validation. No cloud service or external API key is required.
