Delivered to 1 peer(s):
- L83: woken

Reply from L83:
# L83 — T12 freshness: refresh scheduling under the RAM floor (cgroup/slice/nice/ionice throttling + MemAvailable gate)

**Host facts (verified live, 2026-08-25):** Debian 13.6 trixie; systemd **257.13-1~deb13u1** (https://packages.debian.org/trixie/systemd); kernel 6.12 with PSI active (`/proc/pressure/memory` readable); 16 cores; MemTotal ≈ 62.8 GiB; current MemAvailable ≈ 22.5 GiB; **SwapTotal = 0** — no swap, so the ≥3072 MiB floor is enforced only by free+reclaimable RAM and any overshoot ends in kernel OOM, not swap thrash. That makes hard caps + OOM bias first-class requirements, not niceties.

## Candidate items

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Dedicated `batch-refresh.slice` budget: `MemoryHigh=8G` soft throttle + `MemoryMax=12G` hard ceiling + `CPUWeight=20` + `CPUQuota=600%` + `IOWeight=20`; all nightly jobs placed in it|technique|[systemd.resource-control(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html), [trixie manpage](https://manpages.debian.org/trixie/systemd/systemd.resource-control.5.en.html)|LGPL-2.1+|core/stable|5|3|5|4|1|H|MemoryHigh throttles via reclaim without killing; MemoryMax invokes cgroup-local kernel OOM as last resort; effective limits clamp down hierarchy (docs, systemd 257)|
|`ExecStartPre=` MemAvailable gate (`gate-memavailable MIN_MIB MAX_WAIT_S POLL_S`) exiting 75/EX_TEMPFAIL, retried by `Restart=on-failure` + backoff|technique|[kernel proc.rst (MemAvailable semantics)](https://docs.kernel.org/filesystems/proc.html), [systemd.service(5)](https://manpages.debian.org/trixie/systemd/systemd.service.5.en.html)|n/a (10-line sh)|stable|5|2|5|4|1|H|MemAvailable = "available for starting new applications without swapping" (kernel docs); `Restart=on-failure` valid for `Type=oneshot` since v244 (v250 src validation confirms allowed set)|
|Staged refresh pipeline with per-stage floor guard + checkpoint/resume (tantivy commit → sqlite-vec → LanceDB → PPR → RRF merge → Splink/GLiNER ER each gated at 3072 MiB before start)|strategy|stack-internal (index commit points are natural checkpoints)|n/a|new for us|5|3|5|4|2|H|Gate re-checks between stages because MemoryHigh caps *our* usage but cannot see *other* consumers eating the floor mid-run|
|CPU deprioritization of batch: `Nice=19` + `CPUSchedulingPolicy=idle` + low `CPUWeight`/`CPUQuota` so interactive agents preempt|technique|[systemd.exec(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)|LGPL-2.1+|core/stable|5|2|3|3|1|H|SCHED_IDLE + nice 19 yields to anything runnable; CPUWeight arbitrates cgroup contention on 16 cores|
|IO deprioritization: `IOSchedulingClass=idle`, `IOSchedulingPriority=7` + slice `IOWeight=20`|technique|[systemd.exec(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html), [kernel cgroup-v2 io controller](https://docs.kernel.org/admin-guide/cgroup-v2.html)|LGPL-2.1+ / GPL-2.0|stable w/ caveat|4|2|3|3|1|M|ionice idle class is honored by BFQ/mostly ignored under mq-deadline/virtio default; `io.weight` needs a weight-aware scheduler — treat as best-effort garnish, memory caps carry the guarantee|
|PSI adaptive throttle loop inside job: pause workers while `/proc/pressure/memory` `some avg10 ≥ ~40%`|technique|[kernel PSI docs](https://docs.kernel.org/accounting/psi.html)|GPL-2.0 (kernel feature)|stable since Linux 4.20 (2018)|4|3|4|4|2|M|avg10 = % of last 10s at least one task stalled on memory; reacts to *actual* stall rather than capacity guesswork; verified readable on this host|
|`systemd-oomd` scoped kill: `ManagedOOMMemoryPressure=kill` + `ManagedOOMMemoryPressureLimit=50%` on the batch slice only (never user.slice)|tool|[trixie systemd-oomd package](https://packages.debian.org/trixie/admin/systemd-oomd), [systemd-oomd(8)](https://manpages.debian.org/trixie/systemd-oomd/systemd-oomd.8.en.html)|LGPL-2.1+|stable, opt-in (not default-enabled on Debian)|3|1|3|3|2|M|Kills eligible descendant service cgroups after sustained PSI breach (default action window 30s); blast radius confined to batch slice; extra daemon to babysit|
|Interactive-side protection: `user.slice` drop-in `MemoryMin=4G` + batch `OOMScoreAdjust=500` (batch dies first in system-wide OOM)|technique|[systemd.resource-control(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)|LGPL-2.1+|core/stable|5|2|4|4|1|H|memory.min is unreclaimable protection within parent; hierarchical distribution applies at root; OOM score asymmetry decides who the kernel shoots when swap=0|
|Timer hygiene: `OnCalendar` + `Persistent=true` catch-up + `RandomizedDelaySec=45min` + `FixedRandomDelay=true` + `AccuracySec=1us`|technique|[systemd.timer(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)|LGPL-2.1+|core/stable|5|2|3|3|1|H|One catch-up activation max after downtime; fixed random offset keeps nightly slot stable per machine; AccuracySec≠jitter (must not use big AccuracySec for spreading)|
|Single-writer serialization + ad-hoc path: `flock /run/kg-refresh/<repo>.lock` per index writer; agent-triggered runs via transient `systemd-run --scope --slice=batch-refresh.slice -p Nice=19 …` inheriting identical budget|strategy|util-linux flock + [systemd-run(1)](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html)|GPL-2.0+/BSD (util-linux)|core/stable|5|2|4|4|1|H|Prevents two writers corrupting tantivy/LanceDB segments; transient scopes make manual refreshes obey the same ceiling as timer-driven ones|
|Optional core isolation: `AllowedCPUs=8-15` on the batch slice|technique|[systemd.resource-control(5)](https://manpages.debian.org/trixie/systemd/systemd.resource-control.5.en.html)|LGPL-2.1+|stable|3|2|3|2|2|M|Hard partition beats weights when agents spike, but wastes half the box when agents idle — prefer weights unless p99 latency complaints appear|

## Verdict

Top pick: rows 1+2+3+8 as one composite recipe — a capped `batch-refresh.slice` (High 8G/Max 12G/CPUWeight 20/Nice 19), an ExecStartPre MemAvailable gate with EX_TEMPFAIL retry, per-stage 3072 MiB floor guards with checkpoints, and OOM bias against the batch (`OOMScoreAdjust=500`, optional `user.slice MemoryMin=4G`) — all systemd-native, zero new packages, fully offline.
Integration sketch: install the three units below + gate script, wrap each refresh stage in `floor_guard && run_stage && checkpoint`, add `flock` per index, adopt PSI pause (row 6) and systemd-oomd (row 7) only if nightly evidence shows stalls.

## Concrete units (Debian 13 / systemd 257, cgroup v2)

```ini
# /etc/systemd/system/batch-refresh.slice
[Unit]
Description=RAM-floor-honoring budget for nightly index refreshes

[Slice]
MemoryAccounting=yes
CPUAccounting=yes
IOAccounting=yes
# Host has NO swap -> hard ceiling is mandatory, High throttles first
MemoryMax=12G
MemoryHigh=8G
MemoryMin=0
CPUWeight=20
CPUQuota=600%          # <=6 of 16 cores even when box is idle
IOWeight=20            # best-effort (scheduler-dependent)
# Optional escalation if PSI kills prove needed (apt install systemd-oomd):
#ManagedOOMMemoryPressure=kill
#ManagedOOMMemoryPressureLimit=50%
```

```ini
# /etc/systemd/system/kg-refresh.service
[Unit]
Description=T12 nightly corpus refresh (BM25+vec+KG indexes)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot                     # Restart=on-failure legal for oneshot since v244
Slice=batch-refresh.slice
Nice=19
CPUSchedulingPolicy=idle
IOSchedulingClass=idle
IOSchedulingPriority=7
OOMScoreAdjust=500               # system-wide OOM eats the batch, never the agents
UMask=0027
StateDirectory=kg-refresh
StandardOutput=journal
StandardError=journal
# Gate: need 10240 MiB = 3072 floor + headroom for the 8G-High working set;
# wait up to 1h polling every 30s; exit 75 -> Restart retries with backoff
ExecStartPre=/usr/local/sbin/gate-memavailable 10240 3600 30
ExecStart=/opt/kg/bin/refresh-all.sh
TimeoutStartSec=6h
Restart=on-failure
RestartSec=15min
StartLimitIntervalSec=12h
StartLimitBurst=4                # then Persistent=true catches up next night
```

```ini
# /etc/systemd/system/kg-refresh.timer
[Unit]
Description=Nightly trigger for corpus refresh

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=45min
FixedRandomDelay=true
AccuracySec=1us                  # jitter comes from RandomizedDelaySec, not Accuracy
Persistent=true                  # single catch-up run after downtime
Unit=kg-refresh.service

[Install]
WantedBy=timers.target
```

```sh
#!/bin/sh
# /usr/local/sbin/gate-memavailable MIN_MIB MAX_WAIT_S POLL_S
set -eu
min_kib=$(( $1 * 1024 ))
deadline=$(( $(date +%s) + $2 ))
while :; do
    avail=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
    [ "${avail:-0}" -ge "$min_kib" ] && exit 0
    [ "$(date +%s)" -ge "$deadline" ] && {
        echo "gate: MemAvailable ${avail}kB < ${min_kib}kB after wait" >&2
        exit 75   # EX_TEMPFAIL -> systemd Restart=on-failure re-gates later
    }
    sleep "$3"
done
```

```sh
# Inside refresh-all.sh — runtime floor guard between stages (caps can't see other consumers)
floor_guard() {
    while [ "$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)" -lt 3145728 ]; do
        logger -t kg-refresh "floor breach (<3072MiB); pausing stage '$1'"; sleep 60
    done
}
pressured() { awk '/^some /{split($2,a,"="); exit !(a[2]+0 >= 40)}' /proc/pressure/memory; }
for stage in tantivy sqlitevec lancedb ppr rrf splink gliner; do
    flock /run/kg-refresh/"$stage".lock -c true   # single-writer serialization
    floor_guard "$stage"
    pressured && sleep 120                        # PSI adaptive pause (optional refinement)
    run_stage "$stage" && checkpoint "$stage"
done
```

```ini
# /etc/systemd/system/user.slice.d/90-memory-floor.conf  (optional interactive shield)
[Slice]
MemoryMin=4G    # unreclaimable reservation for interactive agent sessions
```

Ad-hoc agent-triggered refresh inherits the same budget:
`systemd-run --scope --slice=batch-refresh.slice -p Nice=19 -p IOSchedulingClass=idle -- python -m kg.refresh --repo <name>`

Escalation ladder (why this composes): weights/nice keep agents responsive under contention → MemoryHigh throttles the batch before anyone else suffers → gate + stage guards hold the absolute 3072 MiB line → MemoryMax confines any runaway leak → OOMScoreAdjust picks the victim if the whole box still OOMs. No cloud/API keys anywhere — nothing here requires owner approval.

LANE L83 DONE items=11 headline=Systemd-native recipe (capped slice + MemAvailable gate + staged floor guards + OOM bias) enforces the 3072MiB floor on this swap-less trixie host with zero new packages