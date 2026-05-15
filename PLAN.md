# CLI Load Tester — Implementation Plan

## Goal
Wrap Locust load tests in a `dr_load` CLI so the team can run tests without knowing Locust syntax.
Includes preflight checks, background log monitoring, job polling, and structured reporting.

---

## Task List

| # | Task | Status |
|---|------|--------|
| 7  | Create Python virtualenv and install all dependencies                 | ✅ done (v0.02) |
| 8  | Confirm and fix target host in .env                                    | ✅ done — `192.168.58.128:8443` |
| 1  | Resolve job monitoring endpoint                                        | ✅ done (v0.03) — `taskManager/getTasks([taskHandle])`, `dateCompleted` flag; `taskHandle` returned from `corpusManager/createRepresentation` |
| 10 | Fix locustfile_indexing.py — endpoints, auth flow, template attrs      | ✅ done (v0.03) — see CHANGELOG; rewrite based on May 11 capture |
| 9  | Determine representation_state enum values                             | ✅ done — 0=NONE, 1=COMPLETE (encoded in `helpers/monitor.py:8-11`). Obsoleted for per-workflow polling by v0.03's REST approach. |
| 2  | Phase 1: Add CLI config to config.py                                   | ✅ done (v0.02) |
| 3  | Phase 2: Build preflight checks (helpers/preflight.py)                 | ✅ done (v0.02) |
| 12 | Add orphan project cleanup to preflight and post-run                   | ✅ done (v0.02) — `run_orphan_sweep` invoked from `dr_load indexing` |
| 4  | Phase 3: Build log watcher + job poller (helpers/monitor.py)           | ✅ done (v0.02) — `LogWatcher` + SQL `JobPoller` |
| 11 | Create setup.cfg with dr_load entry point                              | ✅ done (v0.02) |
| 5  | Phase 4: Build CLI entry point (cli.py)                                | ✅ done (v0.02) |
| 6  | Update .env.example and README                                         | ✅ done (v0.03) — added `DR_INDEX_POLL_INTERVAL`/`DR_INDEX_POLL_TIMEOUT`; documented auto-resolution in README; preserved pytest-only handles |
| 13 | Smoke-test `dr_load indexing -u 1 -d 90s` end-to-end against live box  | ✅ done (2026-05-11) — 3 workflows, 50 reqs, 0 failures; report at `/tmp/dr_smoke.csv` |

---

## Task 7 — Create Python virtualenv and install all dependencies  [HARD BLOCKER]

No virtualenv exists. `locust`, `typer`, and other deps are not installed anywhere on this system.

```bash
cd /home/auraria/scripts/ediscovery_tests
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add to `requirements.txt` before installing:
- `typer>=0.9.0`
- `psycopg2` is already a system package but should be listed explicitly

Verify:
```bash
locust --version
python -c "import typer, psycopg2, locust"
```

**Blocks:** tasks 2, 3, 4, 9, 10

---

## Task 8 — Confirm and fix target host in .env  [BLOCKER]

`.env` currently points at `172.31.240.84:8443`. Project overview and all locustfile
comments reference `192.168.58.128`. The `env.txt` file has separate connector/role handles
for each host — these are not interchangeable.

Confirm the intended target with the user, then:
- Uncomment the correct `DR_BASE_URL` line
- Ensure `DR_NFS_CONNECTOR_HANDLE` and `DR_ADMIN_ROLE_HANDLE` match that host's values

**Blocks:** tasks 2, 3, 9, 10

---

## Task 1 — Resolve job monitoring endpoint

Find `openStatusManagement` function body in:
`/home/auraria/AHS/jboss/standalone/tmp/vfs/temp/tempf63cbbc160a0c634/content-c1bae609197f9fc/main.js`

Known:
- Button calls `openStatusManagement("Monitoring")`
- App has route `status-management/monitoring` (MonitoringComponent)
- REST base: `https://192.168.58.128:8443/ediscovery/rest/`
- Candidate endpoints: `statusLogManager/listSystemStatus`, `projectManager/getUpdateStatus`

Determine whether one of those is sufficient for programmatic job polling, or if there
is a separate REST endpoint behind the UI route.

**Blocks:** task 4

---

## Task 10 — Fix locustfile_indexing.py  [HIGH — currently broken]

`locustfile_indexing.py` diverges from the known-working `fullWorkflow.py` in multiple ways:

| Issue | locustfile_indexing.py (wrong) | fullWorkflow.py (correct) |
|---|---|---|
| Data area creation | `orgManager/createDataArea` | `ecaManager/createDataArea` |
| Corpus creation | `orgManager/createCorpus` | `indexManager/createCorpus` |
| Org context switch | missing | `realmManager/initializeOrganization` (org, then project) |
| Member add | inline `membersRequestMessage` in createCase | separate `addCaseMember` calls |
| Template attrs | reads `DR_TEMPLATE_*` env vars (not in .env) | hardcoded numeric IDs |

Fix all five issues to match `fullWorkflow.py`. For template attributes, hardcode the
numeric IDs (same as fullWorkflow.py) rather than env vars — those IDs are per-environment
and already in `.env` via `DR_ADMIN_ROLE_HANDLE` pattern, but the `DR_TEMPLATE_*` vars
have never been set.

**Blocks:** task 9

---

## Task 9 — Determine representation_state enum values

`datamining_corpus_representation.representation_state` is an integer. All current rows
show `1` but the meaning is unknown.

Run a test index job (via `fullWorkflow.py` or direct API calls), then poll:
```sql
SELECT handle, corpus_handle, representation_state, representation_type
FROM datamining_corpus_representation
ORDER BY handle DESC LIMIT 10;
```
every few seconds to catch state transitions. Document the full enum:
`0=QUEUED? 1=RUNNING? 2=COMPLETE? -1=ERROR?`

Also check `bpel_processes_dr` during the run — currently empty but may populate
during active indexing jobs.

**Blocks:** task 4

---

## Phase 1 (Task 2) — `config.py` additions

Blocked by: tasks 7, 8.

Extend `Config` (or add `CLIConfig`) with new env vars:

| Env var | Default | Purpose |
|---------|---------|---------|
| `DR_PG_HOST` | `localhost` | Postgres host |
| `DR_PG_DB` | `auraria_mgmt` | Postgres database |
| `DR_PG_USER` | `auraria` | Postgres user |
| `DR_PG_PASSWORD` | `auraria` | Postgres password |
| `DR_LOG_DIR` | `/home/auraria/AHS/output` | App log directory |
| `DR_POLL_INTERVAL` | `10` | Seconds between job status polls |
| `DR_REPORT_OUTPUT` | `dr_report.csv` | Report output path |

Note: Postgres uses peer auth via `sudo -u auraria psql`. Password field kept for
completeness but connection is socket-based.

---

## Phase 2 (Task 3) — `helpers/preflight.py`

Blocked by: tasks 7, 8.

Four checks; return structured pass/fail; abort on any failure:

1. **App reachable** — GET/POST `realmManager/getVersion`; confirms host, SSL, basic auth
2. **Postgres connectivity** — `sudo -u auraria psql -d auraria_mgmt -c "\conninfo"` via subprocess
3. **NFS readability** — `sudo -u auraria stat /data/import/<DR_NFS_IMPORT_PATH>`
4. **Log dir access** — `DR_LOG_DIR/*.log` readable, at least one file present
5. **Connector UUID** (optional) — call `listConnectors`, verify `DR_NFS_CONNECTOR_HANDLE` appears

---

## Task 12 — Orphan project cleanup

Blocked by: task 3 (preflight infrastructure).

Add to the preflight sweep: list all projects in the `training` org matching `load-test-*`,
request + approve deletion of each via DRSysAdmin before the test run starts.

Also wrap the indexing scenario's workflow in try/finally so partial runs always attempt
cleanup even on crash/interrupt.

---

## Phase 3 (Task 4) — `helpers/monitor.py`

Blocked by: tasks 1 (endpoint), 9 (state enum).

Two background threads launched at the start of a Locust run:

**LogWatcher thread:**
- Target files: `192.168.58.128_SERVER.log` and `192.168.58.128_MGMTAGT.log` (primary),
  plus `ARCHIVE`, `DOCPREP`, `VECTORCOMPUTE` as secondary
- "Newest by mtime" strategy works for rolled logs; for concurrent active files, watch
  all files modified within the last 10 minutes
- Emit lines containing ERROR, WARN, job state keywords to a shared queue

**JobPoller thread:**
- Poll resolved endpoint (task 1) every `DR_POLL_INTERVAL` seconds
- Track per-project state transitions using representation_state values (task 9)
- Stop when all tracked jobs reach COMPLETE or ERROR, or load test ends

Both write to a shared `MonitorResult` for the final report.

---

## Task 11 — `setup.cfg` with `dr_load` entry point

Create `setup.cfg` in `ediscovery_tests/`:

```ini
[metadata]
name = ediscovery-tests
version = attr: __version__.__version__

[options]
packages = find:
install_requires =
    # mirror requirements.txt

[options.entry_points]
console_scripts =
    dr_load = cli:app
```

After Phase 4 is complete: `pip install -e .` registers `dr_load` in the venv.

---

## Phase 4 (Task 5) — `cli.py`

Blocked by: tasks 2, 3, 4, 11.

Typer CLI entry point. Commands:

```
dr_load preflight
    Run preflight checks only and report results.

dr_load indexing [--users N] [--duration Ns] [--spawn-rate N] [--report FILE]
    Preflight → orphan sweep → locustfile_indexing.py headless → monitor → report.

dr_load browsing [--users N] [--duration Ns] [--spawn-rate N] [--report FILE]
    Preflight → locustfile.py headless → report.
```

Execution flow (indexing/browsing):
1. Load config; validate required env vars
2. Run preflight; print results table; abort on failure
3. Orphan sweep (indexing only)
4. Start LogWatcher + JobPoller background threads
5. Invoke Locust: `locust -f <file> --headless -u N -r R --run-time Ts --csv=<stem>`
6. Stream Locust stdout/stderr to terminal in real time
7. On Locust exit, stop monitor threads, collect MonitorResult
8. Print summary: Locust stats + error count from log watcher + job completion status
9. Write `--report` CSV combining Locust output with monitor data

---

## Task 6 — Docs

Blocked by: task 5.

- `.env.example`: add all new `DR_PG_*`, `DR_LOG_DIR`, `DR_POLL_INTERVAL`, `DR_REPORT_OUTPUT`
- `README.md`: add "CLI Usage" section with `dr_load` examples, venv setup instructions,
  preflight requirements
