# dr-load Architecture

**Version 0.15 · 2026-05-20**

One-page system overview. For the design contract see
`memory/dr_load_monitor_vision.md`. For operator-facing detail see
[QA_README.md](QA_README.md).

---

## The stack

```
                          ┌──────────────────────────────────────┐
                          │  Operators · Developers · Managers   │
                          └─────────────────┬────────────────────┘
                                            │
          ┌─────────────────────────────────┼─────────────────────────────────┐
          │                                 │                                 │
          ▼                                 ▼                                 ▼
┌────────────────────┐         ┌────────────────────────┐         ┌─────────────────────┐
│  dr-load CLI       │         │  Textual TUI           │         │  Webhook alerts     │
│  (v0.15, today)    │         │  (Phase B+, planned)   │         │  (Phase D, planned) │
│  preflight │ admin │         │  ambient · incident    │         │  Slack · email      │
│  record · campaign │         │  reporting             │         │  PagerDuty          │
│  report · indexing │         │                        │         │                     │
│  browsing          │         │                        │         │                     │
└─────────┬──────────┘         └───────────┬────────────┘         └──────────┬──────────┘
          │                                │                                 │
          └────────────────────────────────┴─────────────────────────────────┘
                                           │
                                           ▼
                       ┌──────────────────────────────────────────┐
                       │  Shared core                             │
                       │  helpers/admin_ops  ·  helpers/api_client│
                       │  helpers/preflight  ·  helpers/style     │
                       │  (pure Python — unit-tested in isolation)│
                       └──────────────────┬───────────────────────┘
                                          │
                                          ▼
                       ┌──────────────────────────────────────────┐
                       │  SQLite TSDB  (single file, WAL mode)    │
                       │  /var/lib/dr-load-recorder/store.db      │
                       │  Tables: metrics │ events │ campaigns    │
                       └─────────────────┬────────────────────────┘
                                         │     read+write
                  ┌──────────────────────┴──────────────────────┐
                  │                                             │
                  ▼                                             ▼
   ┌──────────────────────────────┐         ┌──────────────────────────────┐
   │  Front-ends (read)           │         │  dr-load-recorder daemon     │
   │  CLI report · TUI · webhook  │         │  (systemd unit, runs as      │
   │                              │         │   `auraria` on the SUT)      │
   └──────────────────────────────┘         │  10s tick · SIGTERM-clean    │
                                            └──────────────┬───────────────┘
                                                           │
                              ┌────────────────────────────┼────────────────────────────┐
                              │                            │                            │
                              ▼                            ▼                            ▼
                  ┌────────────────────┐      ┌────────────────────────┐    ┌────────────────────┐
                  │  System collector  │      │  DR REST API poller    │    │  Log tailer        │
                  │  /proc, psutil     │      │  /ediscovery/rest      │    │  *.log → ERROR/    │
                  │  CPU · MEM · Disk  │      │  projects · tasks      │    │  WARN classifier   │
                  │  I/O · iops · load │      │  docs/min derived      │    │  13 cosmetic       │
                  │                    │      │                        │    │  patterns stripped │
                  └────────────────────┘      └───────────┬────────────┘    └────────────────────┘
                                                          │
                                                          ▼
                                              ┌──────────────────────┐
                                              │  Digital Reef SUT    │
                                              │  192.168.58.128:8443 │
                                              └──────────────────────┘
```

---

## Component scope at v0.15

| Component | Lines | Status | Notes |
|---|---|---|---|
| `commands/admin.py` | ~950 | Shipped | 12 operator subcommands |
| `commands/record.py` | ~280 | Shipped | Daemon control (start/stop/status/tail) |
| `commands/campaign.py` | ~150 | Shipped | Campaign lifecycle + annotation |
| `commands/report.py` | ~310 | Shipped | Markdown / CSV / Rich panel output |
| `recorder/store.py` | ~230 | Shipped | SQLite TSDB API |
| `recorder/daemon.py` | ~190 | Shipped | Main tick loop |
| `recorder/health.py` | ~95 | Shipped | 5-signal traffic-light derivation |
| `recorder/collectors/system.py` | ~95 | Shipped | psutil + /proc/diskstats |
| `recorder/collectors/dr_api.py` | ~70 | Shipped | DR REST polling |
| `recorder/collectors/logs.py` | ~110 | Shipped | Tailer + cosmetic suppression |
| `helpers/style.py` | ~110 | Shipped | DR brand palette + helpers |
| `helpers/admin_ops.py` | ~750 | Shipped | High-level ops (shared with tests) |
| `helpers/api_client.py` | ~250 | Shipped | EDiscoveryClient — auth + scope |
| `tests/test_recorder.py` | ~900 | Shipped | 112 unit tests |
| `packaging/` | — | Shipped | Spec + systemd unit + offline wheels |
| **Phase B**: Textual TUI | — | Planned | Ambient / incident / reporting surfaces |
| **Phase D**: Webhook alerts | — | Planned | Threshold-transition fan-out |
| **Phase E**: Retention roll-up | — | Planned | 24h raw → 1m 7d → 5m 90d → 1h 1y |

---

## Key design decisions (and the tradeoffs)

| Decision | Why | Cost |
|---|---|---|
| **SQLite, not Prometheus** | One file, no extra process, `cp` to a laptop, no scrape config | No multi-host federation; no PromQL |
| **10s tick, not 1s** | ~2% CPU steady; Phase C will adaptive-bump to 1s during yellow/red windows | Sub-10s spikes invisible until adaptive ships |
| **Same VM as the SUT** | Lowest latency to the data; one systemd unit to manage | Recorder shares fate with the SUT |
| **Five signals, moderate rule** | Operator-tested for noise floor; clear escalation path | Indexing baseline is hardcoded — needs Phase E roll-up |
| **Single-org polling** | Matches the test team's actual usage | Multi-SUT design deferred |
| **`auraria` system user** | Reuses the existing eDiscovery service account | Operators on locked-down hosts may need to create it |

---

## Where things live on disk (after RPM install)

```
/usr/bin/dr-load                                  CLI entry point
/usr/lib/python3.9/site-packages/{cli,commands,
                helpers,recorder}/...             Python modules
/usr/lib/systemd/system/dr-load-recorder.service  systemd unit
/etc/sysconfig/dr-load-recorder                   env file (DR_*)
/etc/logrotate.d/dr-load-recorder                 daily rotation, 14d retention
/var/lib/dr-load-recorder/                        state (the SQLite store)
/var/log/dr-load-recorder.log                     daemon log
/usr/share/dr-load/testload/{doc1,doc2}.txt       canonical fixture
/usr/share/dr-load/wheels/*.whl                   offline pip install cache
```
