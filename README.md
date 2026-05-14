# eDiscovery API Test Suite

**Version 0.14.3**

Automated API tests, load tests, a Textual TUI for live monitoring, and a
reinstall toolchain for the Digital Reef eDiscovery REST API. Includes:

- `dr-load` — headless load-test CLI with preflight, background monitoring, merged CSV reports
- `dr-tui` — lazygit-style Textual TUI with tabbed hierarchical Tree + drill-down detail pane
- `playwright_fresh_install.py` / `playwright_fresh_init.py` — Playwright-driven post-install setup
- `cleandr.sh` + `DR_freshinstall.exp` — destructive uninstall + automated reinstall

Built with **pytest + requests** for functional tests, **Locust** for load testing, **Textual** for the TUI, **Playwright** + **mitmproxy** for UI automation and endpoint capture.

---

## Installation

### Requirements

- Python 3.9+
- Access to the Digital Reef eDiscovery server
- For `dr-load` full monitoring: Postgres peer auth (`sudo -u auraria psql`) and a readable log directory

### Distribution (production / lab hosts) — RPM

For Rocky/RHEL/Fedora hosts, build a self-contained RPM that drops a
venv at `/opt/dr-tools/` and launchers at `/usr/bin/{dr-tui,dr-load}`.
Full build + install instructions in
[`packaging/README.md`](packaging/README.md). TL;DR:

```bash
cd packaging
make rpm                            # builds dr-tools-VERSION-1.el9.x86_64.rpm
sudo dnf install ./rpmbuild/RPMS/x86_64/dr-tools-*.rpm
```

The wheelhouse (~23 MB of pre-built dependency wheels) is bundled
inside the SRPM, so the resulting binary RPM is **offline-installable**
on air-gapped lab hosts. The shipped venv is independent of system
Python — `dr-tools` co-exists with any other Python apps on the box.

### Quick install — shell installer

For dev hosts where you don't want to build an RPM:

```bash
# From a checkout:
bash packaging/install.sh

# Or one-liner (requires internet):
curl -sSL https://github.com/mbmcclelland/ediscovery_tests/raw/v0.06/packaging/install.sh | bash
```

### Editable install for development

```bash
git clone <repo-url> ediscovery_tests
cd ediscovery_tests

python3 -m venv .venv
source .venv/bin/activate

pip install -e .          # runtime deps
pip install -e .[dev]     # + pytest + playwright + mitmproxy
```

Verify:

```bash
dr-tui --help        # launches the Textual login screen
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

## TUI Usage (`dr-tui`)

A lazygit-style Textual TUI for live monitoring. Launch it from any terminal:

```bash
dr-tui            # or: python -m dr_tui
```

**Login screen** — pick `DRSysAdmin` or `admin@training`, type the password
(defaults to `password` for the lab), press Enter.

**Dashboard (v0.06)** — `TabbedContent` with two tabs. Each tab is a
`Horizontal(Tree, ContentSwitcher)`: hierarchical Tree on the left, detail
pane on the right that switches view per selected leaf. System Settings
leaves carry **action bars** with CRUD buttons that drive modal dialogs.

```
 ┌─[ System Settings ]── Organizations ─────────────────────────────┐
 │ ▼ Storage                ┃  Connectors                            │
 │   • Document Storage     ┃ ┌────────────────────────────────────┐ │
 │   • Index Storage        ┃ │ Name   Type   Host   Path   Status │ │
 │   System Storage Depot   ┃ │ nfs1   NFS    …                    │ │
 │   Virus Detection        ┃ └────────────────────────────────────┘ │
 │   System Users           ┃                                        │
 │   System Groups          ┃                                        │
 └────────────────────────────────────────────────────────────────────┘
 DRSysAdmin · org=training · view=org-connectors · connectors=2
 [q] quit  [r] refresh  [l] logout
```

- **Dashboard tab** (DRSysAdmin only — hidden for `admin@training`):
  the landing page. Shows License details, Realm Node status (matching
  Monitoring → Node Status), live system metrics (CPU / Memory / Net /
  Disk IOPS with sparklines + peak / avg over a rolling 60-sample
  window), a streaming `tail -f /home/auraria/AHS/output/*.log` view
  with INFO / WARN / ERROR filter toggles, and the top 5 CPU processes
  from `ps aux`. Refresh cadence: metrics 2 s, logs 1 s, processes 3 s,
  license + node 30 s.
- **System Settings tab** (DRSysAdmin only — hidden for `admin@training`):
  Storage > Document/Index Storage Depots (full CRUD), System Storage
  Depot (read), Virus Detection (read + "Update Now"), System Users
  (full CRUD + reset-password), System Groups (full CRUD).
- **Organizations tab** (both roles): one branch per org with 8 leaves —
  Users, Admins, Groups, Projects, Running Jobs, Completed Jobs,
  Connectors, Storage. Read-only for v0.06.

**v0.06 CRUD modals**: depot create / edit / delete; user create / edit /
delete / reset-password; group create / edit / delete; virus-defs
"Update Now". All operations run on worker threads, the status bar
flashes green on success, and the visible leaf auto-refreshes once the
write returns. Modal validation guards empty fields, password mismatch,
etc.

Auto-refresh ticks every 5 s but only re-fetches the currently-visible
leaf (no API hammering). DRSysAdmin drill-down into a non-default org
transparently calls `realmManager/initializeOrganization` first.

### Keyboard navigation (Midnight Commander-style)

The footer renders a live keybinding bar. Press **F1** any time for the
in-app reference card.

| Key | Action |
|---|---|
| **F1** | Help / keyboard reference |
| **F2** | Toggle DR documentation side-pane (extracted from Digital Reef PDFs) |
| **F3** | Realm-wide Jobs Monitor modal — single-call `listRealmTasks`, type filter, [L] for live AE log |
| **F4** | Edit the selected row — also opens Mail / Splash / Password Policy / Inactivity Timeout editors when the corresponding tree leaf is selected (v0.12) |
| **F5** | Refresh current view |
| **F6** | Reset Password (on Users) / Update Now (on Virus) |
| **F7** | New entity (depot / user / group, depending on view) |
| **F8** | Delete the selected row |
| **F10** | Quit |
| **Tab** | Cycle focus (tree ↔ table) |
| **1 / 2** | Jump to System Settings / Organizations tab |
| **↑ ↓ Enter** | Native tree + table navigation |
| **Esc** | Cancel modal |
| **Enter** (in form field) | Save form |
| **q / r / l** | Hidden aliases — quit / refresh / logout |

### Terminal compatibility

`dr-tui` is built on **Textual**, which uses modern terminal capabilities
(true colour, kitty-keyboard protocol, UTF-8 box-drawing). Most modern
terminals Just Work; a few legacy ones need a nudge.

**Recommended terminals** (tested):

- Linux: GNOME Terminal, Konsole, Alacritty, kitty, foot, xterm
- macOS: iTerm2, Terminal.app, WezTerm, Alacritty
- Windows: **Windows Terminal** (Microsoft Store, free), Tabby, WezTerm
- WSL terminals
- VS Code integrated terminal

**PuTTY** works *but needs two non-default settings*:

1. **PuTTY → Window → Translation → Remote character set → `UTF-8`**
   (default is Win-1252 — produces "chunky" box-drawing characters)
2. **`TERM=xterm-256color`** in your session — PuTTY advertises bare
   `xterm` by default, which lacks 256-color terminfo on RHEL/Rocky.

The `/usr/bin/dr-tui` launcher (RPM v0.10.2+) sets these defensively, so
on a clean install you just need to flip PuTTY's UTF-8 setting once.

If the screen renders but **keystrokes don't reach the app**, run with
the kitty-keyboard probe disabled:

```bash
TERM=xterm-256color TEXTUAL_FEATURES= dr-tui
```

(PuTTY swallows the keyboard-enhancement query that Textual sends on
startup. Setting `TEXTUAL_FEATURES=` to empty skips the probe.)

If all else fails, switch to **Windows Terminal** — it handles Textual
apps natively with zero config.

### Endpoints (sample — full list in `docs/endpoints_v0.05.md`)

| Leaf | DRSysAdmin | admin@training |
|---|---|---|
| Doc / Idx depots | `realmManager/listRemoteNFSStorageAreas` (filter `storageUseType`) | (hidden tab) |
| Virus Detection | `realmManager/getVirusDefinitions` | (hidden tab) |
| Connectors | `initializeOrganization` → `adminOrgManager/listConnectors` | direct |
| Projects | `realmManager/listSystemUserProjectsByUserName` | `orgManager/listUserProjectsForAllOrgs` |
| Tasks | `projectManager/listTasks` (split by `dateCompleted`) | same |

---

### Job Scheduler tab (v0.13+)

The Job Scheduler tab lets you define **indexing job templates** and
run them on demand or via a saved CLI. Each template captures the
org, project, connector, target path, retention window, and a
description; the same template can be re-run any number of times.

- **New Job** opens a wizard that lets you pick org → project →
  connector, then browse the connector's filesystem in a lazy-loading
  tree (folders are `🗀`, files `🗎`). Select a directory and click
  **Count files** for a recursive count (DR's REST API exposes no
  folder size endpoint, so v0.13 reports file/dir counts only).
- **Retention period** is set in seconds / minutes / hours / days /
  weeks. Default is **1 week**; `0` means keep forever. When a job
  runs and retention is non-zero, dr-tui writes a one-shot **systemd
  user timer** at `~/.config/systemd/user/dr-tools-retention-<slug>-<run_id>.timer`
  that fires `dr-job-delete <slug> <run_id>` at the retention horizon.
- **Run Now** shells out to `dr-job-run <slug>` — the same code path
  cron / systemd would use, so behaviour is identical in interactive
  and unattended runs.
- Jobs whose name contains the substring **`longterm`** render
  yellow-bold in the Saved Templates table, as a visual cue for
  long-retention archives.

State layout under `~/.dr-tools/`:

```
jobs/<slug>.json       saved JobDefinition (template)
runs/<slug>.jsonl      append-only run history (one JSON per line)
logs/<slug>-<ts>.log   tee'd stdout/stderr of one dr-job-run
```

Override the state root via `DR_TOOLS_STATE_DIR=<path>` (tests use
this; you can use it to relocate state to e.g. `/var/lib/dr-tools`).

**systemd user timers + linger.** A user-scope systemd timer dies the
moment that user logs out unless lingering is enabled. To keep
retention deletes running across logouts:

```bash
sudo loginctl enable-linger $USER
```

Check the current state with `loginctl show-user $USER --property=Linger`.
The TUI surfaces a hint when lingering is off but the user has scheduled
retention timers.

The two CLIs ship as console-script entry points:

- `dr-job-run <name-or-slug>` — run one job manually (also wired to
  the **Run Now** button).
- `dr-job-delete <slug> <run-id>` — retention cleanup; invoked by the
  systemd `.service` automatically, but can be run manually to expire
  a single run early.

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
3. Starts background `LogWatcher` (tails `*.log` files in `DR_LOG_DIR`) and SQL `JobPoller` (polls `datamining_corpus_representation` every `DR_POLL_INTERVAL` seconds for a global "how many indexings finished" signal)
4. Runs Locust headless, streaming output to the terminal. Each Locust user, per workflow, also drives its own per-task REST poll (`taskManager/getTasks` every `DR_INDEX_POLL_INTERVAL` seconds) so it can wait for its specific indexing to complete before deleting the project.
5. On exit, prints a summary (Locust stats + error counts + indexing job completion counts)
6. Writes a merged CSV report combining Locust stats with monitor data

### Indexing handle resolution (v0.03+)

`locustfile_indexing.py` looks up environment-specific handles on each user's `on_start` instead of reading them from `.env`:

- **NFS connector** — via `adminOrgManager/listConnectors`, filtered by `type=NFS, mode=READ`
- **Admin role** — via `orgManager/listRoles`, matched by `name="Organization Administrator"`
- **Template attributes** — via `orgManager/listTemplates`, every `defaultTemplate=true` entry

This makes the load test drift-proof across `playwright_fresh_install.py` reruns, which rebuild the org and regenerate all handles.

> `DR_NFS_CONNECTOR_HANDLE` / `DR_ADMIN_ROLE_HANDLE` / `DR_TEMPLATE_*` are still read by **`tests/test_indexing_workflow.py`** (pytest), so leave them populated in `.env`.

### CLI-specific env vars

| Variable                  | Default                       | Description                                                                  |
|---------------------------|-------------------------------|------------------------------------------------------------------------------|
| `DR_LOG_DIR`              | `/home/auraria/AHS/output`    | App log directory to watch                                                   |
| `DR_POLL_INTERVAL`        | `10`                          | Seconds between SQL job-status polls (`helpers/monitor.py` global poller)    |
| `DR_INDEX_POLL_INTERVAL`  | `5`                           | Seconds between per-workflow `taskManager/getTasks` REST polls               |
| `DR_INDEX_POLL_TIMEOUT`   | `600`                         | Max seconds to wait for a single indexing task to reach `dateCompleted`      |
| `DR_REPORT_OUTPUT`        | `dr_report.csv`               | Output path for the merged report CSV                                        |
| `DR_PG_DB`                | `auraria_mgmt`                | Postgres database name                                                       |
| `DR_PG_USER`              | `auraria`                     | Postgres user (peer auth via sudo)                                           |

---

## Configuration (.env)

### Core

| Variable                  | Description                                  | Default                                              |
|---------------------------|----------------------------------------------|------------------------------------------------------|
| `DR_BASE_URL`             | Full base URL for REST API                   | `https://192.168.58.128:8443/ediscovery/rest`        |
| `DR_USERNAME`             | DRSysAdmin login                             | `DRSysAdmin`                                         |
| `DR_PASSWORD`             | DRSysAdmin password                          | *(required)*                                         |
| `DR_ORGANIZATION`         | System org name                              | `super_system_customer`                              |
| `DR_ORG_USERNAME`         | Org user login                               | `admin`                                              |
| `DR_ORG_PASSWORD`         | Org user password                            | *(required for indexing load test)*                  |
| `DR_ORG_ORGANIZATION`     | Org name                                     | `training`                                           |
| `DR_LDAP_DOMAIN`          | LDAP domain (if applicable)                  | *(empty)*                                            |
| `DR_REQUEST_TIMEOUT`      | Default request timeout (seconds)            | `30`                                                 |
| `DR_LONG_REQUEST_TIMEOUT` | Timeout for slow endpoints (seconds)         | `120`                                                |
| `DR_VERIFY_SSL`           | Verify SSL certificates                      | `false`                                              |
| `DR_LOAD_TEST_USERS`      | Locust: concurrent users                     | `10`                                                 |
| `DR_LOAD_TEST_SPAWN_RATE` | Locust: users spawned per second             | `2`                                                  |
| `DR_LOAD_TEST_DURATION`   | Locust: test duration (seconds)              | `60`                                                 |

### Indexing workflow

| Variable                  | Description                                                          | Default     |
|---------------------------|----------------------------------------------------------------------|-------------|
| `DR_NFS_IMPORT_PATH`      | Path on the NFS connector containing load-test data                  | `/testload` |
| `DR_NFS_DATASET_NAME`     | Label used to name datasets/corpora per workflow                     | `testload`  |
| `DR_INDEX_POLL_INTERVAL`  | Seconds between per-workflow `taskManager/getTasks` polls            | `5`         |
| `DR_INDEX_POLL_TIMEOUT`   | Max seconds to wait for `dateCompleted` on an indexing task          | `600`       |
| `DR_NFS_CONNECTOR_HANDLE` | NFS connector handle — pytest only (locustfile resolves dynamically) | *(varies)*  |
| `DR_ADMIN_ROLE_HANDLE`    | Organization Administrator role handle — pytest only                 | *(varies)*  |
| `DR_TEMPLATE_*` (×17)     | Default-template handles by templateType — pytest only               | *(varies)*  |

All variables use a `DR_` prefix to avoid collisions with Windows system environment variables
(Windows sets `USERNAME` automatically).

### After running `playwright_fresh_install.py`

`playwright_fresh_install.py` ends by deleting the `training` org. Before running the
indexing load test against the same host you must:

1. Re-provision the `training` org with the org user (`admin` / `password` by default).
2. Re-sync `DR_NFS_CONNECTOR_HANDLE`, `DR_ADMIN_ROLE_HANDLE`, and `DR_TEMPLATE_*` in
   `.env` to the freshly-generated values (only needed for pytest — `locustfile_indexing.py`
   resolves them at runtime).

Symptom if you skip step 1: `dr-load preflight` reports `connector_uuid: Expecting value:
line 1 column 1 (char 0)` — the org user login returns HTTP 500 with an HTML error body
that preflight tries to parse as JSON.

---

## Fresh-Install / Reinstall Toolchain (v0.06)

A three-step chain for tearing DR down and bringing it back to a tested
baseline (DRSysAdmin/`password`, `admin@training`/`password`, depots
created, system depot assigned, `training` org provisioned).

> ⚠️ **Destructive and unrecoverable.** Step 1 wipes `/home/auraria/AHS*`,
> `/data/docstorage/*`, `/data/indexstorage/*`, and the InstallAnywhere
> registry. Run it only when you intend to start over.

### Step 1 — `cleandr.sh`

Stops `drd`, preserves `license.lic` to `/root/`, then removes the install
tree and storage scratch dirs.

```bash
bash cleandr.sh
```

Reads either the live `/home/auraria/AHS/conf/license.lic` (preferred) or
a copy in CWD; falls back to any pre-existing `/root/license.lic` if both
sources are missing.

### Step 2 — `DR_freshinstall.exp`

Expect script that drives the InstallAnywhere console installer
(`/tmp/5.5.3.2.bin -i console`), accepts the license, picks Full node /
eDiscovery / IP 192.168.58.128, and restores the license + restarts `drd`
at the end.

```bash
cd /tmp
expect -f /home/auraria/scripts/ediscovery_tests/DR_freshinstall.exp
```

Typical wall-clock time: ~5–7 minutes (most of it is the bundled JRE
extraction). The installer auto-starts `drd`; the script also runs
`systemctl restart drd` after replacing the license file so DRD picks up
the licensed features.

### Step 3 — `playwright_fresh_init.py`

Idempotent Playwright driver: first login (DRSysAdmin/`DRSysAdmin`) →
forced password change to `password` → create `localDocStorage` + 
`localIndexStorage` → assign System Storage Depot → create `training` org
→ create `admin/training` user → forced password change on first
admin@training login → logout.

```bash
source .venv/bin/activate
python playwright_fresh_init.py            # headless
python playwright_fresh_init.py --no-headless --slow-mo 200   # watch it run
```

All phases skip-if-exists, so re-running is safe. Captures API traffic to
`/tmp/dr_api_capture.json` and (via mitmproxy on `:8090`)
`/tmp/dr_proxy_capture.json`.

After step 3 completes: `dr-load preflight` should return all-green; the
pytest suite and `dr-tui` work without further configuration.

### What if step 2's expect script hangs?

Autoexpect scripts are fragile about bash prompts. The current
`DR_freshinstall.exp` was hand-cleaned to match installer text (which is
deterministic) and avoid bash-prompt expectations entirely. If you
regenerate it via autoexpect on a different host, watch for prompt
mismatches in the bash bracketed-paste sequences and switch
`expect -exact` to `expect -re` for any `tmp]# ` matches.

---

## Project Structure

```
ediscovery_tests/
├── .env.example              # Environment config template
├── .env                      # Your local config (git-ignored)
├── __version__.py            # Version string
├── CHANGELOG.md              # Release notes
├── README.md                 # This file
├── PLAN.md                   # Active task plan
├── DR_Workflow_Guide.md      # API + database walkthrough
├── config.py                 # Config loader (reads .env)
├── conftest.py               # Shared pytest fixtures (auth, clients, helpers)
├── pytest.ini                # Pytest settings and markers
├── requirements.txt          # Python dependencies
├── setup.cfg                 # Package config + dr-load + dr-tui entry points
├── setup.py                  # setuptools shim for editable install
│
├── cli.py                    # dr-load CLI entry point (typer)
├── locustfile.py             # Locust load test: status/reports/browsing
├── locustfile_indexing.py    # Locust load test: full indexing workflow
│
├── cleandr.sh                # Destructive uninstall (preserves license)
├── DR_freshinstall.exp       # Expect: drives InstallAnywhere console installer
├── playwright_fresh_install.py # Full Playwright fresh-install + lifecycle workflow
├── playwright_fresh_init.py    # Focused post-install setup (just enough for tests)
├── proxy_logger.py           # mitmproxy addon — records DR REST traffic to /tmp
│
├── dr_tui/                   # Textual TUI (v0.05+ tabbed hierarchical views)
│   ├── __init__.py / __main__.py
│   ├── app.py                # DRTUIApp / LoginScreen / DashboardScreen
│   ├── data.py               # Sync API fetchers per leaf
│   └── app.tcss              # Textual stylesheet
│
├── helpers/
│   ├── __init__.py
│   ├── api_client.py         # EDiscoveryClient wrapper (v0.06: handles 204)
│   ├── preflight.py          # Preflight checks + orphan sweep
│   └── monitor.py            # LogWatcher + JobPoller background threads
│
├── docs/
│   ├── endpoints_v0.05.md    # Read-path endpoint reference (dr-tui views)
│   └── endpoints_v0.06.md    # Write-path endpoint reference (CRUD work)
│
├── tests/                    # pytest functional suite (10 modules, 87 tests)
│   ├── test_auth.py
│   ├── test_ocr_report.py
│   ├── test_status.py
│   ├── test_projects.py
│   ├── test_organizations.py
│   ├── test_connectors.py
│   ├── test_billing.py
│   ├── test_workflows.py
│   ├── test_org_user.py
│   └── test_indexing_workflow.py
│
└── misc/                     # Historical recordings, old debug scripts,
                              # stale Locust CSVs, foreign-language files
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

# Every request auto-injects drWsClientContext with session token
data = client.post("realmManager/getRealmStatus")
print(data["realmStatus"])

# Pass extra fields into the request body
stats = client.post(
    "realmManager/getOCRUsageStatistics",
    extra_body={
        "filters": [
            {"attribute": "FROM_DATE", "operator": "AFTER", "value": "1704067200000"},
            {"attribute": "TO_DATE", "operator": "BEFORE", "value": "1706745600000"},
        ]
    },
)

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
