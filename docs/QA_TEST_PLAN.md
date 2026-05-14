# dr-tools — QA Test Plan & Handover

**Audience:** QA Engineer taking ownership of the dr-tools test
plan from the development team.

**Scope:** `dr-tui` (Textual TUI), `dr-load` (load-test CLI), and the
two scheduler companion CLIs (`dr-job-run`, `dr-job-delete`). Pytest
functional suite (`tests/*`) is the regression net beneath all of it.

**Version covered:** v0.14.3 (last shipped 2026-05-13).

---

## 1. Environment

| What | Where | Notes |
|---|---|---|
| DR REST API | `https://192.168.58.128:8443/ediscovery/rest` | Default; override via `DR_BASE_URL` in `~/.env` |
| Test user (sys) | `DRSysAdmin` / `password` | After fresh install |
| Test user (org) | `admin` in `training` / `password` | After fresh install |
| Persistent state | `~/.dr-tools/{jobs,runs,logs}/` | Override with `DR_TOOLS_STATE_DIR=<path>` (tests use this) |
| systemd timers | `~/.config/systemd/user/dr-tools-retention-*.{service,timer}` | Need `loginctl enable-linger $USER` for cross-logout survival |
| AHS log dir | `/home/auraria/AHS/output/*.log` | Tailed by the Landing Dashboard |
| Postgres (for dr-load) | `auraria_mgmt` db, peer auth via `sudo -u auraria psql` | Optional — only used by Locust monitor |

**Before testing anything**, make sure the lab is in a known-good
state. The fastest path is:

```bash
# Full destructive reset — takes ~7 minutes.
bash cleandr.sh
expect -f DR_freshinstall.exp
python playwright_fresh_init.py
dr-load preflight              # All-green = ready
```

You can skip the fresh install if you trust the current state and just
want to spot-check a feature.

**Note for v0.15.2+:** the prerequisite "grant Connectors permission
via DR_ROLE_SETUP.md" that earlier versions of this plan listed is
**no longer required**. The v0.15.2 systemScope fix removed the need
for any DR-side role customization. Both DRSysAdmin and the default
admin@training Organization Administrator role work out of the box.

---

## 2. Smoke test (10 minutes)

Run these in order. Each step has a clear pass/fail. Failing any of
them means **don't certify the release**; chase the root cause.

| # | Step | Pass | Fail |
|---|---|---|---|
| 1 | `dr-load preflight` | All checks green | Anything red → see RUNBOOK §1 |
| 2 | `pytest -m smoke` | All pass | Failure → flag the failing test for the dev team |
| 3 | `pytest tests/test_dr_tui_dashboard_layout.py tests/test_dr_tui_depot_modal.py tests/test_dr_tui_scheduler.py` | 19/19 green | Pilot regression — TUI is broken at the structural level |
| 4 | `dr-tui` → DRSysAdmin → password | Landing Dashboard appears with metrics scrolling | Login error / blank screen → RUNBOOK §2 |
| 5 | F3 → wait 2s | Jobs Monitor modal lists tasks (or shows "no jobs"). Filter buttons clickable. | Crash → check `~/.dr-tools/logs/` for last run / report |
| 6 | System Settings tab → Realm Settings → Password Policy → Edit | Modal pops; numeric fields visible; Cancel returns to read view | Modal won't open → F4 binding broken |
| 7 | Organizations → training → Connectors | **Green** "N connector(s) for training" status line + 1 row | Yellow "no connectors" or red error → RUNBOOK §3 |
| 8 | Job Scheduler → New Job → name = "qa-smoke-001" → click Schedule (no folder picked yet) | Specific error: "Folder to index not selected. Click a folder in the tree on the right, then try again." | Generic / no error → validation regressed |
| 9 | Same modal: pick a folder → Schedule | Modal closes; row appears in Saved Templates | No row → save path broken |
| 10 | Saved Templates → select row → Run | Status bar shows "running: qa-smoke-001 via /opt/dr-tools/venv/bin/dr-job-run"; new row appears in Run History within a few seconds | No new run row → dr-job-run not invoked or failing |

If all 10 pass: smoke test PASSED for v0.14.3.

---

## 3. Feature matrix

Maps each shipped feature to the version it landed in, the screen /
modal / CLI surface, and the test files that cover it.

| Feature | Version | Surface | Pilot test | Read this changelog |
|---|---|---|---|---|
| Landing dashboard (license, nodes, metrics, logs, procs) | v0.06 | Landing tab | `test_dashboard_layout` | v0.06 |
| Storage Depot CRUD | v0.06 | System Settings → Document/Index Storage | `test_depot_modal_paths` | v0.06 |
| System User CRUD + reset password | v0.06 | System Settings → System Users | `test_user_modal_paths` | v0.06 |
| System Group CRUD | v0.06 | System Settings → System Groups | `test_group_modal_paths` | v0.06 |
| Virus defs "Update Now" | v0.06 | System Settings → Virus Detection | (manual) | v0.06 |
| Connector "Deactivate" | v0.07.1 | Organizations → org → Connectors | (manual) | v0.07.1 |
| Realm Settings read views (mail/splash/pw/inactivity) | v0.08.1 | System Settings → Realm Settings | `test_dashboard_layout` | v0.08.1 |
| F2 docs side-pane | v0.09 | F2 toggle on each tab | `test_help_pane_toggle` | v0.09 |
| F3 Jobs Monitor modal | v0.10 | F3 anywhere | `test_jobs_monitor_modal` | v0.10 |
| Pause / Resume / Cancel / Priority | v0.10.1 | F3 action buttons | `test_priority_modal_paths` | v0.10.1 |
| PuTTY terminal compat (now obsolete — use Tabby) | v0.10.2 | `/usr/bin/dr-tui` launcher | (manual) | v0.10.2 |
| Jobs Monitor v2: listRealmTasks + type filter + per-task log | v0.11 | F3 — type Select, `L` shortcut | `test_jobs_monitor_modal` | v0.11.0 |
| Realm Settings edit modals | v0.12 | System Settings → Realm Settings → Edit button or F4 | `test_settings_modal_paths` | v0.12.0 |
| Job Scheduler tab (templates + systemd timers + CLIs) | v0.13 | Job Scheduler tab; `dr-job-run`, `dr-job-delete` | `test_dr_tui_scheduler.py` | v0.13.0 |
| NewJobModal auto-flow fix | v0.13.1 | New Job dialog | `test_newjob_modal_auto_picks_org_connector_project` | v0.13.1 |
| Dashboard log markup escape | v0.13.2 | Landing log pane | (manual reproduction) | v0.13.2 |
| Job Scheduler per-view actions + log viewer + timer toggle + lingering banner | v0.14.0 | All four scheduler sub-views | `test_unit_parse_regex`, `test_log_viewer_modal_mount` | v0.14.0 |
| NewJobModal UX rework (5-day default, 4 buttons, plain labels) | v0.14.1 | New Job dialog | `test_newjob_modal_v0141_defaults_and_buttons` | v0.14.1 |
| Connectors view inline status | v0.14.2 | Organizations → Connectors | (manual) | v0.14.2 |
| NewJobModal connector dropdown fix | v0.14.3 | New Job dialog | (manual — see RUNBOOK §3) | v0.14.3 |

---

## 4. Detailed test scenarios

Each scenario has: **Setup**, **Steps**, **Expected**, **Negative cases**.
Where the dev suite already covers it, the pilot test name is in the
title. Manual-only scenarios are flagged.

### 4.1 Storage Depots — CRUD

Pilot: `test_depot_modal_paths` (offline) + manual lab run.

**Setup:** Fresh install. Have one NFS export ready
(`/data/docstorage`, `/data/indexstorage`).

**Steps:**
1. dr-tui → System Settings → Document Storage Depots → F7 (New).
2. Fill: Name = `qa-doc-depot-1`, FQDN/IP = `192.168.58.128`,
   Export = `/data/docstorage`, Allocation = `0`.
3. Save.
4. New row appears in the table. Select it → F4 (Edit) → change FQDN
   to `127.0.0.1` → Save.
5. Select again → F8 (Delete) → confirm.

**Expected:** Each operation flashes green in the status bar; the
table auto-refreshes; no orphan rows.

**Negative cases:**
- Empty Name → Save shows "Name is required." inline; no API call.
- Allocation = `-1` → Save shows "Allocation must be a non-negative integer."
- FQDN with spaces / bogus chars → server rejects with `INVALID_INPUT`;
  status bar shows the error code.

---

### 4.2 Realm Settings — Edit modals (v0.12)

Pilot: `test_settings_modal_paths` (offline) + manual lab run.

**Setup:** Fresh install or known-good DR.

**Mail Server:**
1. System Settings → Realm Settings → Mail Server → Edit.
2. Set SMTP host = `smtp.example.com`, port = `587` → Save.
3. Panel re-renders with the new values.

**Negative:** Port = `99999` → "Port must be an integer in 1–65535."

**Splash Message:**
1. Edit → check Enabled → leave message empty → Save.

**Expected error:** "Message text required when enabled."

2. Fill text, Save → panel shows new message.

**Password Policy:**
1. Edit → min length = `4`, min uppercase = `3`, min numbers = `3` → Save.

**Expected error:** "Composition requirements (6) exceed min length (4)."

2. Sensible values (e.g. min length = 8, min upper = 1, expiration = 90)
   → Save. Panel re-renders.

**Inactivity Timeout:**
1. Edit → enter `300` (5 minutes) → Save. Panel shows "300 seconds
   (0h:5m:0s)".

**Negative:** `-1` → "Seconds must be a non-negative integer."

---

### 4.3 Jobs Monitor (F3) — Pause / Resume / Cancel / Priority / Log

Pilot: `test_jobs_monitor_modal` (offline) + manual lab run.

**Setup:** Have at least one indexing job running. Easiest path: run
the indexing load test for 30 s:

```bash
dr-load indexing --users 1 --duration 30s
```

**Steps:**
1. F3 → modal opens; running job appears in the table.
2. Select the row → click **Pause**. State should flip to `PAUSED`
   on next 5 s refresh.
3. Click **Resume** → state returns to `RUNNING`.
4. Click **Priority** → modal pops; press `h` (or click High) →
   priority chip on the row updates.
5. Click **Cancel** → confirm modal → confirm → state flips to
   `CANCELLED`.
6. Press `L` on a running row → live AE log opens, scrolls.

**Expected:** Each action flashes green or yellow status in the
modal's detail pane and the table auto-refreshes. Cancel requires
explicit confirm (destructive action).

**Negative cases:**
- Pause on a `COMPLETE` task → "could not pause (state=COMPLETE)" yellow.
- `L` on a finished task → "Live log only available for RUNNING tasks".

---

### 4.4 Job Scheduler — New Job wizard end-to-end

**Pilot tests** are extensive here (see `test_dr_tui_scheduler.py`),
but a manual lab run is **mandatory** because the wizard talks to
the live connector-browse endpoint.

**Setup:**
- Fresh install with the default `training` org and the
  `import-training-nfs-local` NFS connector.
- `/data/import` on the lab host has at least one subfolder with
  some files in it.

**Happy path:**
1. dr-tui → Job Scheduler → New Job.
2. **Verify defaults:**
   - Name: empty
   - Organization: `training` (auto-picked)
   - Connector dropdown shows `import-training-nfs-local (NFS)`
     **(if this is empty, see RUNBOOK §3 immediately — known bug pattern)**
   - File tree shows `/data/import` and starts auto-loading children
   - Retention: `5` `days`
3. Click `🗀 data/import` → expand. Click a subfolder → it becomes the
   selection. The "Selected:" line under the tree updates.
4. Click **Count files (recursive)** → status flips to "counting…",
   then to "`N files, M dirs under <path>`".
5. Type Name = `qa-newjob-001` → click **Schedule**.
6. Modal closes. Saved Templates view shows the new row with retention
   "5d", org training, path correct.
7. Select the row → click **Run**. Status bar: "running: qa-newjob-001
   via /opt/dr-tools/venv/bin/dr-job-run". Within ~5 s, a row appears
   in **Run History** with status `RUNNING`.
8. Wait for the run to complete (Realm-wide F3 jobs view confirms).
   Run History row flips to `SUCCESS`.
9. Retention Timers view: one timer present, next-fire ≈ 5 days from
   now.

**Negative cases — validation:**
- Empty name + Schedule → "Name is empty — please enter a name for
  this job (e.g. 'payroll-archive')."
- Org with no projects → "Organization 'X' has no projects. Pick a
  different organization, or create a project in DR before scheduling
  a job here."
- No folder picked → "Folder to index not selected. Click a folder
  in the tree on the right, then try again."
- Retention = `foo` → "Retention period must be a whole number (got
  'foo'). Enter 0 to keep forever."
- Retention = `-1` → "Retention period can't be negative. Enter 0 to
  keep forever, or a positive number."

**Negative case — connector dropdown empty:** This was the v0.14.3 bug
— make sure the regression hasn't returned. The dropdown must populate
for `training` (1 row: `import-training-nfs-local`). If empty,
**root cause is missing `initializeOrganization` switch** in
`_sch_collect_then_open` (see RUNBOOK §3).

**Visual rule:** Type Name = `qa-longterm-001` → Schedule. The row in
Saved Templates should render **yellow-bold**. (`longterm` substring
match is the trigger.)

---

### 4.5 Job Scheduler — Retention timers

**Setup:** Run a job with retention = `2 minutes` so the timer fires
during your test session (vs. waiting 5 days).

**Steps:**
1. New Job → name = `qa-retention-001`, retention = `2` `minutes`,
   pick a folder → Run now.
2. Run History shows `RUNNING` → `SUCCESS` once done.
3. Retention Timers view shows the new `dr-tools-retention-qa-retention-001-*.timer`
   row with `time left ≈ 2 min`.
4. Wait 2 minutes.
5. The timer fires. The corpus + data area created during the run get
   deleted. Run History row flips to `DELETED`. Retention Timers row
   disappears.

**Verify on disk:**

```bash
systemctl --user list-timers --all | grep dr-tools-retention
ls ~/.config/systemd/user/dr-tools-retention-*
journalctl --user -u dr-tools-retention-qa-retention-001-*.service
```

**Negative cases:**
- Toggle button on an active timer → state flips to `inactive`; the
  timer won't fire. Toggle again → back to `active`. Verify with
  `systemctl --user is-active <unit>`.
- Cancel timer → confirm modal → unit files removed from
  `~/.config/systemd/user/`. `systemctl --user list-timers --all`
  no longer shows it.
- Lingering banner: `sudo loginctl disable-linger $USER`, refresh
  the tab → yellow banner appears. Re-enable → banner disappears
  on next refresh.

---

### 4.6 Connectors view (Organizations tab)

**Setup:** Fresh install with the default `import-training-nfs-local`
connector for `training`.

**Steps:**
1. dr-tui → Organizations → training → Connectors.
2. Inline status flips: `Loading connectors for training…` (yellow)
   → `1 connector(s) for training.` (green).
3. Table shows the row: name, type=NFS, mode=READ, status=AVAILABLE.
4. Select the row → click Deactivate → confirm → status flips to
   `DEACTIVATED` on next refresh.

**Negative cases:**
- Org with no connectors → status: "No connectors found for X. Create
  one in the DR Web UI under Org Admin → Connectors, then click the
  leaf again to refresh." (yellow)
- API session lost → status: "No API session for X. Log in again
  or pick a different org." (red)

---

### 4.7 dr-load — Functional + indexing

**Setup:** Fresh install + `playwright_fresh_init.py` done. `dr-load
preflight` all-green.

**Functional smoke:**
```bash
pytest -m smoke --html=report.html --self-contained-html
```

**Browsing load test:**
```bash
dr-load browsing --users 5 --duration 60s
```

**Expected:** Locust headless run, then a summary table; merged CSV
written to `dr_report.csv`. No 5xx errors in the response stats.

**Indexing load test:**
```bash
dr-load indexing --users 2 --duration 120s
```

**Expected:** Each Locust user runs the full chain (createDataArea →
createCorpus → createRepresentation → poll → delete project), the
SQL monitor reports completion counts at the end, and the merged
report shows per-step stats.

**Negative case:** Stale `.env` handles after fresh install →
preflight surfaces "connector_uuid: Expecting value: line 1 column
1 (char 0)". Fix: rerun `playwright_fresh_init.py` and re-sync
`.env` (locustfile resolves handles dynamically; pytest doesn't).

---

## 5. Known limitations (won't-fix or deferred)

| Symptom | Why | Workaround |
|---|---|---|
| New Job wizard reports counts only, no folder size | DR's REST API has no `getFolderSize` endpoint and `connectorManager/exploreConnector` returns no size data. | Use `du -sb` on the lab host directly if you need bytes. |
| Connectors view empty for an org you know has connectors | DRSysAdmin's session starts in `super_system_customer` context; `adminOrgManager/listConnectors` returns `[]` silently without `initializeOrganization` switch first. The TUI does this in `_client_for_org()` automatically; verify the call actually fired (RUNBOOK §3). | Click the leaf again; status bar tells you the result. |
| Retention timer didn't fire after retention period | systemd-user units die at logout unless lingering is enabled. | `sudo loginctl enable-linger $USER`. The TUI surfaces a yellow banner when this applies. |
| Dashboard log pane crashed with `MarkupError` | (v0.13.1 and earlier) Log lines containing literal `[/…]` brackets were parsed as markup. | Upgrade to v0.13.2+. |
| PuTTY box-drawing chunky, keys don't reach app | PuTTY's defaults don't match Textual. | Use **Tabby**, Windows Terminal, or Alacritty. |
| `dr-load preflight` reports `connector_uuid: Expecting value` | Stale handles in `.env` after a `playwright_fresh_install.py` rebuild. | Re-sync the `DR_*_HANDLE` values; or just use the locust load-test directly (resolves handles at runtime). |

---

## 6. Regression areas (what's worth re-testing on every release)

Order matters — items higher up are touched more often:

1. **NewJobModal** — three releases in two days have rewritten it
   (v0.13 → v0.13.1 → v0.14.1 → v0.14.3). Pilot tests cover most of
   the flow but the live connector-browse + count-files round trip
   needs a manual smoke per release.
2. **Job Scheduler tab routing** — per-view action rows landed in
   v0.14.0. Every button on every sub-view should be exercised
   (Pause/Resume/Cancel/Priority/View Log/Toggle/Cancel timer/Refresh).
3. **F3 Jobs Monitor** — refactored in v0.11 to use `listRealmTasks`.
   Verify the type-filter Select populates and that the operation-type
   filter actually reduces the row set.
4. **Realm Settings editors (F4)** — v0.12 introduced four new modals.
   Check that the existing read views still update after each edit
   (the apply method should re-load the leaf).
5. **Login flow + role gating** — `admin@training` should see only
   the Organizations + Job Scheduler tabs (System Settings + Landing
   are hidden). `DRSysAdmin` sees all four.
6. **PuTTY / Tabby compat** — only if you control terminal choice.
   The team has moved to Tabby; PuTTY is best-effort.

---

## 7. Where things live (filesystem map for QA)

| Where | What's there |
|---|---|
| `~/.env` | Login credentials, base URL, timeouts. |
| `~/.dr-tools/jobs/<slug>.json` | Saved job template. Hand-editable if you need to bulk-rewrite. |
| `~/.dr-tools/runs/<slug>.jsonl` | One JSON per dr-job-run execution. Newest at the end. |
| `~/.dr-tools/logs/<slug>-<ts>.log` | tee'd stdout+stderr from one run. |
| `~/.config/systemd/user/dr-tools-retention-*.{service,timer}` | One pair per pending retention deletion. |
| `/tmp/dr_proxy_capture*.json` | Captured DR REST traffic from mitmproxy sessions. Useful when reproducing endpoint shape bugs. |
| `/home/auraria/AHS/output/*.log` | DR server's own logs (AHS). The dashboard tails these. |
| `/data/docstorage/`, `/data/indexstorage/` | NFS-style storage roots created during fresh install. |

---

## 8. Reporting bugs

Use this template when filing a bug:

```
TITLE:    [v0.14.3] <short symptom>

ENVIRONMENT
  Terminal:    Tabby / Windows Terminal / …
  dr-tui ver:  0.14.3
  Role:        DRSysAdmin / admin@training
  Tab:         Landing / System Settings / Organizations / Job Scheduler
  Sub-view:    e.g. "Job Scheduler → Saved Templates"

REPRO
  1. …
  2. …
  3. …

EXPECTED
  …

ACTUAL
  … (paste any error from the inline status line OR the bottom status bar)

ARTIFACTS
  ~/.dr-tools/logs/…    (if scheduler-related)
  /home/auraria/AHS/output/server-*.log   (server-side)
  /tmp/dr_proxy_capture.json              (only if mitmproxy was running)
```

Cross-reference: every commit message ends in
`Co-Authored-By: …` and names the changelog entry. The pilot suite
provides immediate regression coverage — re-running the relevant
`test_dr_tui_*.py` file is usually the first diagnostic step.
