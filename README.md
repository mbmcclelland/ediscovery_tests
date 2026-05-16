# eDiscovery API Test Suite

**Version 0.03**

Automated API tests and load tests for the Digital Reef eDiscovery REST API,
plus the `dr-load` CLI for running headless load tests with preflight checks,
background monitoring, and merged CSV reports.

Built with **pytest + requests** for functional tests and **Locust** for performance/load testing.

---

## Installation

### Requirements

- Python 3.9+
- Access to the Digital Reef eDiscovery server
- For `dr-load` full monitoring: Postgres peer auth (`sudo -u auraria psql`) and a readable log directory

### Install the `dr-load` CLI (recommended)

This installs `dr-load` as a console script in your virtualenv:

```bash
git clone <repo-url> ediscovery_tests
cd ediscovery_tests

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

Verify:

```bash
dr-load --help
```

### Install for pytest only (no CLI entry point)

```bash
pip install -r requirements.txt
```

### Configure your environment

```bash
cp .env.example .env
# Edit .env — at minimum set DR_PASSWORD and DR_BASE_URL
```

---

## Quick Start

### Run preflight checks

```bash
dr-load preflight
```

### Run a browsing load test

```bash
dr-load browsing --users 5 --duration 60s
```

### Run the full indexing workflow load test

```bash
dr-load indexing --users 1 --duration 120s
```

### Run the pytest functional test suite

```bash
pytest
pytest -m smoke          # Quick health checks only
pytest --html=report.html --self-contained-html
```

---

## CLI Usage (`dr-load`)

`dr-load` wraps the Locust load tests with preflight checks, orphan cleanup,
background monitoring, and a merged report.

### Commands

```bash
# Verify environment before running a test
dr-load preflight

# Run the full indexing workflow load test
dr-load indexing --users 3 --duration 120s --spawn-rate 1

# Run the browsing load test
dr-load browsing --users 10 --duration 60s --spawn-rate 2

# Override the output report path
dr-load indexing --report /tmp/my_report.csv
```

All options fall back to `.env` values (`DR_LOAD_TEST_USERS`, `DR_LOAD_TEST_DURATION`, etc.)
when not specified on the command line.

### What `dr-load indexing` does

1. Runs preflight checks (app reachable, auth, Postgres, NFS, log dir, connector UUID)
2. Sweeps for orphaned `load-test-*` projects and deletes them
3. Starts background `LogWatcher` (tails `*.log` files in `DR_LOG_DIR`) and `JobPoller` (polls `datamining_corpus_representation` every `DR_POLL_INTERVAL` seconds)
4. Runs Locust headless, streaming output to the terminal
5. On exit, prints a summary (Locust stats + error counts + indexing job completion counts)
6. Writes a merged CSV report combining Locust stats with monitor data

### CLI-specific env vars

| Variable            | Default                       | Description                                  |
|---------------------|-------------------------------|----------------------------------------------|
| `DR_LOG_DIR`        | `/home/auraria/AHS/output`    | App log directory to watch                   |
| `DR_POLL_INTERVAL`  | `10`                          | Seconds between job-status DB polls          |
| `DR_REPORT_OUTPUT`  | `dr_report.csv`               | Output path for the merged report CSV        |
| `DR_PG_DB`          | `auraria_mgmt`                | Postgres database name                       |
| `DR_PG_USER`        | `auraria`                     | Postgres user (peer auth via sudo)           |

---

## Configuration (.env)

| Variable                  | Description                                  | Default                                              |
|---------------------------|----------------------------------------------|------------------------------------------------------|
| `DR_BASE_URL`             | Full base URL for REST API                   | `https://192.168.58.128:8443/ediscovery/rest`        |
| `DR_USERNAME`             | Login username                               | `DRSysAdmin`                                         |
| `DR_PASSWORD`             | Login password                               | *(required)*                                         |
| `DR_ORGANIZATION`         | Organization name                            | `super_system_customer`                              |
| `DR_LDAP_DOMAIN`          | LDAP domain (if applicable)                  | *(empty)*                                            |
| `DR_REQUEST_TIMEOUT`      | Default request timeout (seconds)            | `30`                                                 |
| `DR_LONG_REQUEST_TIMEOUT` | Timeout for slow endpoints (seconds)         | `120`                                                |
| `DR_VERIFY_SSL`           | Verify SSL certificates                      | `false`                                              |
| `DR_LOAD_TEST_USERS`      | Locust: concurrent users                     | `10`                                                 |
| `DR_LOAD_TEST_SPAWN_RATE` | Locust: users spawned per second             | `2`                                                  |
| `DR_LOAD_TEST_DURATION`   | Locust: test duration (seconds)              | `60`                                                 |

All variables use a `DR_` prefix to avoid collisions with Windows system environment variables
(Windows sets `USERNAME` automatically).

---

## Project Structure

```
ediscovery_tests/
├── .env.example              # Environment config template
├── .env                      # Your local config (git-ignored)
├── __version__.py            # Version string
├── CHANGELOG.md              # Release notes
├── config.py                 # Config loader (reads .env)
├── conftest.py               # Shared pytest fixtures (auth, clients, helpers)
├── pytest.ini                # Pytest settings and markers
├── requirements.txt          # Python dependencies
├── setup.cfg                 # Package config + dr-load entry point
├── cli.py                    # dr-load CLI entry point (typer)
├── locustfile.py             # Locust load test: status/reports/browsing
├── locustfile_indexing.py    # Locust load test: full indexing workflow
├── helpers/
│   ├── __init__.py
│   ├── api_client.py         # EDiscoveryClient wrapper
│   ├── preflight.py          # Preflight checks + orphan sweep
│   └── monitor.py            # LogWatcher + JobPoller background threads
└── tests/
    ├── test_auth.py               # Session creation / login
    ├── test_ocr_report.py         # OCR Usage Report
    ├── test_status.py             # Realm, system, node status
    ├── test_projects.py           # Project listing and management
    ├── test_organizations.py      # Organization and resource listing
    ├── test_connectors.py         # Connector listing and retrieval
    ├── test_billing.py            # Billing and report settings
    ├── test_workflows.py          # End-to-end chained workflows
    ├── test_org_user.py           # Org-scoped user tests
    └── test_indexing_workflow.py  # Full indexing lifecycle (create → import → index → delete)
```

---

## Running pytest Tests

### By marker (category)

```bash
pytest -m smoke              # Quick health checks
pytest -m auth               # Authentication tests only
pytest -m ocr                # OCR usage report tests
pytest -m status             # System status tests
pytest -m projects           # Project management
pytest -m orgs               # Organization tests
pytest -m connectors         # Connector tests
pytest -m "smoke and ocr"    # Combine markers
```

### Parallel execution

```bash
pytest -n 4                  # Run on 4 parallel workers
```

### Verbose with logging

```bash
pytest -v --log-cli-level=DEBUG
```

---

## Load Testing with Locust

Three user personas simulate realistic traffic patterns:

| Persona          | Weight | Behavior                                      |
|------------------|--------|-----------------------------------------------|
| `ReadOnlyUser`   | 3      | Status dashboards, realm health, version      |
| `OCRReportUser`  | 1      | OCR report generation with date filters       |
| `ProjectBrowser` | 2      | Browsing projects, orgs, connectors, users    |

### Web UI mode

```bash
locust -f locustfile.py --host https://192.168.58.128:8443
# Open http://localhost:8089 in your browser
```

### Headless mode

```bash
locust -f locustfile.py \
    --host https://192.168.58.128:8443 \
    --headless \
    -u 10 -r 2 \
    --run-time 60s \
    --csv=results/load_test
```

### Filter by tag

```bash
locust -f locustfile.py --tags ocr          # Only OCR tasks
locust -f locustfile.py --tags status       # Only status tasks
locust -f locustfile.py --exclude-tags ocr  # Everything except OCR
```

---

## API Client Usage

The `EDiscoveryClient` can also be used standalone for scripting:

```python
from config import config
from helpers.api_client import EDiscoveryClient

client = EDiscoveryClient(config)
client.login()

# System-scoped: contextHandle stays at the configured org, so
# systemScope is auto-set to True.
data = client.post("realmManager/getRealmStatus")
print(data["realmStatus"])

# Project-scoped: caller overrides contextHandle to a project handle, so
# systemScope is auto-set to False. Older versions of this client always
# sent True, which made the server check super-system roles and return
# HTTP 500. If you ever need to force a value, pass system_scope= explicitly.
client.post("realmManager/initializeOrganization", extra_body={
    "requestHandle": None, "contextHandle": project_handle, "organizationName": "training",
})
client.post("orgManager/createCorpus", extra_body={
    "contextHandle": project_handle, "dataAreaHandles": [da_handle], "name": "my-corpus",
    # ... no need to pass systemScope ...
})

# Discover this org's template-attribute IDs at runtime. Per-org and
# changes on every install — never hardcode these. Caller must have
# listTemplates permission (DRSysAdmin works; admin@training does not).
attrs = client.discover_template_attributes("training")
client.post("ecaManager/createCase", extra_body={"attributes": attrs, ...})

client.logout()
```

---

## How Edge Recordings Map to API Tests

The Edge recorder JSON captures UI clicks. Here's how they translate:

| Edge Step                         | API Equivalent                                |
|-----------------------------------|-----------------------------------------------|
| Navigate to `/ediscovery/`        | —                                             |
| Click username field, Log in      | `POST /realmManager/createSession`            |
| Click Status menu                 | —                                             |
| Click "OCR Usage Report"          | —                                             |
| Set start date (Jan 1 2026)       | `filters[].attribute=FROM_DATE`               |
| Set end date (Jan 31 2026)        | `filters[].attribute=TO_DATE`                 |
| Click "Download Report"           | `POST /realmManager/getOCRUsageStatisticsUrl` |
| Open downloaded file              | GET the returned `url`                        |

---

## Adding New Tests

1. Identify the API endpoint in `swagger.json`
2. Create or extend a test file in `tests/`
3. Use the `api` fixture for a shared session or `api_fresh` for isolated sessions
4. Call `api.post("manager/endpoint", extra_body={...})`
5. Assert `data["status"] == "SUCCESS"` plus any field-level checks
6. Tag with appropriate markers (`@pytest.mark.smoke`, etc.)

---

## CI/CD Integration

```yaml
# Example GitHub Actions step
- name: Run API Tests
  env:
    DR_BASE_URL: ${{ secrets.EDISCOVERY_URL }}
    DR_USERNAME: ${{ secrets.EDISCOVERY_USER }}
    DR_PASSWORD: ${{ secrets.EDISCOVERY_PASS }}
    DR_ORGANIZATION: ${{ secrets.EDISCOVERY_ORG }}
    DR_VERIFY_SSL: "true"
  run: |
    pip install -r requirements.txt
    pytest -m smoke --html=report.html --self-contained-html
```
