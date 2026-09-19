# Deploy - systemd-native batch governor (zero packages)

This is an inherited, unvalidated deployment example for Graphify batch
refreshes (KG rebuilds and embedding backfills). Repaired L83 evidence supports
parameterized resource-control experiments; it does not select these values or
establish deployment readiness. The example uses stock systemd plus one POSIX
shell script and has no package or cgroup-tooling dependency.

The entry gate samples `MemAvailable` before launch, the slice limits the batch
cgroup, and payload-side guards check between stages. Those controls do not
prove that a host-wide memory floor is continuously preserved after launch.

## Units and install paths

| Repo file                    | Installed to                              | Mode |
|------------------------------|-------------------------------------------|------|
| `deploy/batch-refresh.slice` | `/etc/systemd/system/batch-refresh.slice` | 0644 |
| `deploy/kg-refresh.service`  | `/etc/systemd/system/kg-refresh.service`  | 0644 |
| `deploy/kg-refresh.timer`    | `/etc/systemd/system/kg-refresh.timer`    | 0644 |
| `deploy/gate-memavailable`   | `/usr/local/sbin/gate-memavailable`       | 0755 |

The refresh payload is expected at `$GRAPHIFY_ROOT/tooling/build-all.sh`
(default `GRAPHIFY_ROOT=/opt/graphify`; adjust `Environment=` or
`ExecStart=` in `kg-refresh.service` if the checkout lives elsewhere).

## Install

```bash
sudo install -m 0755 deploy/gate-memavailable /usr/local/sbin/gate-memavailable
sudo cp deploy/batch-refresh.slice deploy/kg-refresh.service deploy/kg-refresh.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kg-refresh.timer
systemctl list-timers kg-refresh.timer
```

Ad-hoc manual refresh inside the identical budget (never bypass the slice):

```bash
sudo systemd-run --scope --slice=batch-refresh.slice \
  -p Nice=19 -p CPUSchedulingPolicy=idle -p IOSchedulingClass=idle \
  "$GRAPHIFY_ROOT/tooling/build-all.sh"
```

## Escalation ladder - what each layer buys

1. **Politeness first** - `CPUWeight=20`, `Nice=19`,
   `CPUSchedulingPolicy=idle`, `IOSchedulingClass=idle`: the batch loses
   every fair-share contest to interactive agents without hard limits.
2. **Slice ceilings** (`batch-refresh.slice`) - `MemoryHigh=8G` throttles
   the batch through reclaim; `MemoryMax=12G` is a hard cgroup wall
   (kernel OOM kills stay confined to the batch cgroup);
   `CPUQuota=600%` caps burst width; `IOWeight=20` protects agent IO
   latency.
3. **Entry gate** - `ExecStartPre=/usr/local/sbin/gate-memavailable
   10240 3600 30` polls `/proc/meminfo` every 30 s for up to 1 h, holding
   the start condition at `MemAvailable >= 10240 MiB`. On timeout it exits
   `75` (`EX_TEMPFAIL`).
4. **Bounded retry** - `Restart=on-failure` + `RestartSec=15min` under
   `StartLimitIntervalSec=12h` / `StartLimitBurst=4`: a gated or failed
   refresh backs off 15 minutes, gives up after 4 attempts per 12 h, and
   the next timer fire resumes the schedule.
5. **Whole-box OOM bias** - `OOMScoreAdjust=500` nominates the batch as
   the preferred victim if the host ever hits global OOM, shielding
   interactive sessions.
6. **Payload-side stage guards** - `tooling/build-graph.sh` checks available
   memory at stage boundaries and exits when its configured floor is not met.
   It does not continuously monitor memory inside a running stage.

## Timer shape

`OnCalendar=*-*-* 03:30:00` plus `RandomizedDelaySec=45min` with
`FixedRandomDelay=true` (stable per-boot jitter spreads load without
re-randomizing every event) and `Persistent=true` (runs missed while the
host was down catch up at next boot).

## Inherited example values

These repository values are implementation inputs awaiting public-fixture and
target-host validation; they are not selected by the repaired research record.

| Threshold               | Value                        | Enforced by                     |
|-------------------------|------------------------------|---------------------------------|
| Agent interactive floor | `MemAvailable >= 3072 MiB`   | `install.sh` / `preflight.py`   |
| Batch entry gate        | `MemAvailable >= 10240 MiB`  | `gate-memavailable` (exit 75)   |
| Batch reclaim throttle  | `MemoryHigh=8G`              | slice                           |
| Batch hard wall         | `MemoryMax=12G`              | slice (cgroup-local OOM)        |
