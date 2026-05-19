# eDiscovery Test Suite & `dr-load` CLI

**Version 0.14**

This repository is the test-and-tooling layer for the **Digital Reef eDiscovery** product. It contains:

- **`dr-load`** — a command-line tool for creating, listing, indexing, and deleting projects against a live install, plus running headless load tests.
- A **pytest** suite that exercises every important REST endpoint and the end-to-end indexing lifecycle.
- Versioned **install scripts** for a fresh RHEL 9 VM.

It does **not** contain the Digital Reef product itself — that ships separately as `install.bin`.

---

## Which doc do I need?

Different jobs land on different docs. Pick yours:

| If your job today is… | Open… |
|---|---|
| **Install + run the smoke test on a fresh VM** (junior sysadmin handoff) | [QA_README.md](QA_README.md) — operator quick-start |
| **Operate the test environment** (create/delete projects, schedule auto-delete, watch dashboard) | [QA_README.md](QA_README.md) §3–4 |
| **Run sustained load campaigns** (hours, days, or weeks) with the recorder + campaign log | [QA_README.md §3b](QA_README.md#3b-dr-load-record--campaign--report--long-haul-monitoring-phase-a-v015) |
| **Install the toolkit as an RPM** (RHEL 9 / Rocky Linux 9 managed service) | [packaging/README.md](packaging/README.md) |
| **Triage a failing test or weird server behavior** | [BUG_LOG.md](BUG_LOG.md) — known issues + workarounds |
| **Write a new test against an endpoint I haven't used before** | [API_DICTIONARY.md](API_DICTIONARY.md) — every REST call with real request/response shapes |
| **Understand what the server does behind the scenes** (REST → Java → Postgres) | [DR_Workflow_Guide.md](DR_Workflow_Guide.md) — concepts + DB tables |
| **See what changed between versions** | [CHANGELOG.md](CHANGELOG.md) |
| **Install or re-install the product** | [`scripts/install/README.md`](scripts/install/README.md) |

If you're brand-new and not sure where to start, **start with [QA_README.md](QA_README.md)**.

---

## The shortest possible "is this working?"

After you've installed the product (see [scripts/install/README.md](scripts/install/README.md)) and the toolkit, the canonical health gate is:

```bash
source .venv/bin/activate
dr-load preflight          # 6 environment checks
pytest -m smoke            # ~16 seconds, must be all green
```

Both green = the install is healthy and the API is reachable. Both are what CI runs.

---

## What's in the repo

```
ediscovery_tests-master/
├── README.md               # this file — top-level entry
├── QA_README.md            # operator quick-start + CLI reference
├── API_DICTIONARY.md       # every endpoint with real shapes
├── DR_Workflow_Guide.md    # REST + Postgres concepts; DB table reference
├── BUG_LOG.md              # known issues + history
├── CHANGELOG.md            # per-release notes
├── packaging/              # RPM build files (spec, build script, systemd unit, logrotate)
├── scripts/install/        # versioned install wrappers for the DR product
├── cli.py                  # dr-load entry point
├── commands/               # dr-load subcommands (admin, record, campaign, report)
├── helpers/                # API client, preflight, monitoring, admin ops, style tokens
├── recorder/               # Phase A recorder daemon
├── tests/                  # pytest suite (includes test_recorder.py — 98 unit tests)
└── tests/fixtures/testload/ # canonical 2-document fixture (doc1.txt, doc2.txt)
```

For the full file-by-file layout, see [Project Structure](#project-structure-detailed) at the bottom of this file.

---

## Install (for the toolkit, not the product)

This installs the **test/CLI side only**. The product (`install.bin`) is a separate step — see [`scripts/install/README.md`](scripts/install/README.md).

```bash
# In the repo root
python3 -m venv .venv
source .venv/bin/activate
sudo dnf install -y python3-devel gcc       # gevent needs Python.h
pip install -e .
```

Verify:

```bash
dr-load --help
```

Then configure the environment — [QA_README.md §2](QA_README.md#2-environment-variables) lists every variable and which commands need each.

---

## Top-level commands

`dr-load` has three families. The first two are documented in detail in [QA_README.md](QA_README.md).

### Operator / admin commands

```bash
dr-load admin --help                       # list all 12 admin subcommands
dr-load admin list --org training          # what projects exist?
dr-load admin dashboard --org training     # live snapshot of jobs + deletes
dr-load admin create-project demo --org training --lifetime 1h
```

Full reference: [QA_README.md §3](QA_README.md#3-dr-load-admin--operator-reference).

### Long-haul monitoring (Phase A — v0.15+)

For sustained load campaigns lasting hours, days, or weeks, the
`dr-load record / campaign / report` verb-groups give you a persistent
recorder daemon plus a campaign event log and report renderer.

```bash
dr-load record start                       # fork the recorder daemon
dr-load campaign new soak-q2 --users 10    # start a tracked campaign
dr-load campaign adjust --users 50         # change load on the fly
dr-load report --audience mgmt             # weekly status report
dr-load record stop                        # clean shutdown
```

Full reference: [QA_README.md §3b](QA_README.md#3b-dr-load-record--campaign--report--long-haul-monitoring-phase-a-v015).

### Load tests

```bash
dr-load preflight                          # gate
dr-load browsing --users 5 --duration 60s  # read-only traffic mix
dr-load indexing --users 1 --duration 120s # full create+index+delete loop
```

The CSV report lands at `dr_report.csv` (override with `DR_REPORT_OUTPUT`).

### Functional tests (pytest)

```bash
pytest -m smoke                                 # ~16s health gate
pytest -m slow                                  # 3 full-lifecycle tests, ~22s
pytest tests/ --ignore=tests/test_indexing_workflow.py   # full non-slow surface
```

For the full marker list and what each test file covers, see [QA_README.md §5](QA_README.md#5-test-suite--what-pytest-proves).

---

## API client usage (Python scripting)

If you need to talk to the REST API outside the test suite, the same client is reusable:

```python
from config import config
from helpers.api_client import EDiscoveryClient

client = EDiscoveryClient(config)
client.login()

# System-scoped call — contextHandle stays at the configured org, so
# systemScope is auto-set to True.
data = client.post("realmManager/getRealmStatus")
print(data["realmStatus"])

# Project-scoped call — caller passes a project handle as contextHandle,
# so systemScope is auto-set to False. (If you ever need to force a
# value, pass system_scope= explicitly.)
client.post("orgManager/createCorpus", extra_body={
    "contextHandle": project_handle,
    "dataAreaHandles": [da_handle],
    "name": "my-corpus",
})

# Template-attribute IDs change per install — discover at runtime, never
# hardcode. Caller must have listTemplates permission (DRSysAdmin does;
# admin@training does not).
attrs = client.discover_template_attributes("training")
client.post("ecaManager/createCase", extra_body={"attributes": attrs, ...})
```

For every endpoint's exact request shape, see [API_DICTIONARY.md](API_DICTIONARY.md).

---

## CI / GitHub Actions

A self-hosted-runner workflow lives at `.github/workflows/smoke.yml`. It runs `pytest -m smoke` against the live server on every push to `main` or `master`.

To wire up a new runner, set these GitHub Secrets:

| Secret | Used for |
|---|---|
| `EDISCOVERY_URL` | `DR_BASE_URL` |
| `EDISCOVERY_USER` | `DR_USERNAME` |
| `EDISCOVERY_PASS` | `DR_PASSWORD` |
| `EDISCOVERY_ORG` | `DR_ORGANIZATION` |

---

## Project structure (detailed)

```
ediscovery_tests-master/
├── __version__.py            # single source of truth for the version string
├── config.py                 # loads environment + .env
├── conftest.py               # pytest fixtures (auth, clients, helpers)
├── cli.py                    # dr-load entry point (Typer)
├── commands/                 # admin subcommands (create-org, list, dashboard, …)
├── locustfile.py             # browsing load-test scenarios
├── locustfile_indexing.py    # full create→index→delete load test
├── helpers/
│   ├── api_client.py         # EDiscoveryClient — auth, scope, retries, error parsing
│   ├── admin_ops.py          # one-call helpers for create_project / wait_for_tasks / …
│   ├── preflight.py          # the 6 environment checks
│   └── monitor.py            # LogWatcher + JobPoller background threads for load tests
├── tests/
│   ├── test_e2e_bootstrap.py     # canonical create→import→index→delete (smoke gate)
│   ├── test_indexing_workflow.py # same path via the inline workflow class (slow)
│   ├── test_auth.py              # login / session / version
│   ├── test_status.py            # realm + system status
│   ├── test_organizations.py     # org listing + per-org resources
│   ├── test_connectors.py        # connector listing
│   ├── test_projects.py          # project listing, users, groups, roles
│   ├── test_billing.py           # billing + report settings
│   ├── test_ocr_report.py        # OCR usage report (Edge-recorded flow)
│   ├── test_workflows.py         # chained multi-click UI flows
│   ├── test_org_user.py          # org-scoped user paths (skip if DR_ORG_* unset)
│   └── fixtures/testload/        # doc1.txt + doc2.txt (the 2-doc canonical fixture)
└── scripts/install/
    ├── dr_installprep.sh     # OS prep — packages, SELinux off, atd on
    ├── dr_install.sh         # silent installer wrapper with rollback detection
    └── README.md             # install-scripts reference
```

---

## Getting help

- **First**: check [QA_README.md §7 Troubleshooting](QA_README.md#7-troubleshooting) — common errors and their fixes.
- **Then**: skim [BUG_LOG.md](BUG_LOG.md). The Open Items section at the top lists everything currently broken on the server side.
- **For the API**: every endpoint is in [API_DICTIONARY.md](API_DICTIONARY.md) with real request and response shapes.
- **For concepts** (what is a corpus, what is a representation): [DR_Workflow_Guide.md](DR_Workflow_Guide.md).
