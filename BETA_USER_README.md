# dr-tools — Beta tester guide

**For:** Senior Linux Admin running a Digital Reef lab; using
`dr-tui` as a daily-driver traffic-control station.
**Tool version:** v0.15.0
**You'll need:** a Rocky / RHEL / Fedora 9.x host, sudo, ~10 GB free
under `/data/`, Python 3.9+ already in `/usr/bin/`. No internet
required at install time — the RPM is offline-installable.

---

## What you're getting

`dr-tools` is a self-contained venv at `/opt/dr-tools/venv` plus four
console scripts on `$PATH`:

| Command | What it does |
|---|---|
| `dr-tui` | Textual TUI — your traffic-control station |
| `dr-load` | Headless load-test CLI |
| `dr-job-run` | Run one saved job (used by the TUI's Run / Run-Now and by recurring systemd timers) |
| `dr-job-delete` | Retention cleanup — deletes the corpus + data area created by one run |

State lives under `~/.dr-tools/` (your home dir):

```
~/.dr-tools/jobs/<slug>.json     # saved job templates
~/.dr-tools/runs/<slug>.jsonl    # append-only run history
~/.dr-tools/logs/<slug>-<ts>.log # captured stdout/stderr per run
~/.config/systemd/user/dr-tools-*.{service,timer}  # schedules
```

---

## First-time install (clean state)

You should land here **once** per lab host. Plan ~10 min.

### 1. Wipe any previous DR install (destructive)

```bash
# Drop you back to a known baseline. Preserves /root/license.lic.
# Removes any prior dr-tools RPM and your ~/.dr-tools/ state.
sudo bash cleandr.sh
```

Pass `--keeprpm` if you want to keep an existing dr-tools RPM
installed while you re-init the DR backend. (E.g. testing a DR
upgrade without touching the tooling.)

### 2. Reinstall DR

```bash
# Runs the InstallAnywhere installer; restores license; restarts drd.
# Takes ~5-7 minutes.
expect -f DR_freshinstall.exp
```

When this finishes, `systemctl status drd` should report `active`
and the Web UI should respond on `https://192.168.58.128:8443/ediscovery/`.

### 3. Provision the training org + admin user

```bash
# Idempotent Playwright driver. Creates depots, the training org,
# and admin@training/Password123 → forces a password change to
# 'password' on first login. Takes ~1-2 min.
python playwright_fresh_init.py
```

If the storage-create phase already shows green and the script
errors out (because storage already exists), use the slim variant
that only creates the admin user:

```bash
python qa_create_org_admin.py
```

### 4. *(SKIP unless you're on v0.15.1 or earlier)* Grant role permissions

> **As of v0.15.2 this step is no longer required.** The Job Scheduler
> works out of the box for both DRSysAdmin and the default
> `admin@training` Organization Administrator role. If you're on
> v0.15.2+ (`rpm -q dr-tools` to check), skip to Step 5.
>
> The walkthrough at [`docs/DR_ROLE_SETUP.md`](docs/DR_ROLE_SETUP.md)
> is preserved for reference but isn't part of the default install
> path anymore.

### 5. Install the dr-tools RPM

```bash
sudo dnf install -y \
  ./packaging/rpmbuild/RPMS/x86_64/dr-tools-0.15.0-1.el9.x86_64.rpm
```

After this completes, `dr-tui`, `dr-load`, `dr-job-run`, and
`dr-job-delete` are all on your `$PATH`.

### 6. Configure your `.env`

```bash
cp /opt/dr-tools/share/env.example ~/.env
$EDITOR ~/.env
```

At minimum set:

```ini
DR_BASE_URL=https://192.168.58.128:8443/ediscovery/rest
DR_USERNAME=DRSysAdmin
DR_PASSWORD=password
DR_ORG_USERNAME=admin
DR_ORG_PASSWORD=password
DR_ORG_ORGANIZATION=training
```

### 7. Enable systemd-user lingering (one-time)

So your scheduled jobs survive logout:

```bash
sudo loginctl enable-linger $USER
loginctl show-user $USER --property=Linger     # should print Linger=yes
```

### 8. Launch

```bash
dr-tui
```

Pick **admin@training** at the login screen if you want the full
Job Scheduler functionality (recommended). Pick DRSysAdmin for
realm-wide observability (Landing Dashboard, Realm Settings).

---

## Daily-driver use cases

### Traffic-control station

The **Landing Dashboard** (DRSysAdmin only) is your operations
overview:

- License + node status (refreshed every 30 s)
- Live system metrics: CPU / Memory / Net / Disk IOPS with sparklines
  + peak and average over a rolling 60-sample window (2 s tick)
- Streaming `tail -f /home/auraria/AHS/output/*.log` with
  INFO / WARN / ERROR filter toggles
- Top 5 processes by CPU% (`ps aux` every 3 s)

Press **F3** anywhere to pop the **realm-wide Jobs Monitor**:

- Every running + completed task across every org
- Filter buttons: All / Running / Completed / Deleted
- Operation-type Select (100 enum values — DOCUMENT_ADD_FROM_FILE_LIST,
  PREPARE_FOR_ANALYTICS, etc.)
- Per-task actions: **Pause / Resume / Cancel / Set Priority / Log**
- `L` opens a live tail of the per-task AE log

### Create a job that runs once, right now

1. Job Scheduler tab → **New Job**.
2. Fill in:
   - **Name:** `daily-payroll-import`
   - **Organization:** `training` (auto-picked)
   - **Connector:** the NFS connector (auto-picked)
   - **Folder to index:** type or paste the path
     (e.g. `/data/import/payroll/2026`)
   - **Keep indexed data for:** `5` `days` (default)
   - **Schedule (recurring):** `Run on demand only (no schedule)`
3. Click **Run now**. The TUI saves the template AND immediately
   invokes `dr-job-run`. Watch the **Run History** sub-view for the
   row to flip from RUNNING to SUCCESS.

### Create a job that runs every day, 3 times a day

Same flow as above, but pick:

- **Schedule (recurring):** `3× daily (03/11/19)`
- Click **Schedule** (not Run now — that would fire it once
  immediately too).

The saved template now has a green `3x-day` cell in the Schedule
column. A systemd user timer
`~/.config/systemd/user/dr-tools-recur-daily-payroll-import.timer`
gets created and enabled. It fires `dr-job-run daily-payroll-import`
at 03:00, 11:00, 19:00 every day.

To see all your active timers:

```bash
systemctl --user list-timers --all | grep dr-tools
```

Or look at the **Retention Timers** sub-view in the Job Scheduler tab.

### Cancel a running job

1. F3 (Jobs Monitor) → click the running row.
2. Click **Cancel** → confirm.
3. State flips to `CANCELLED` within ~5 s.

### Promote / demote priority

1. F3 → click the running row.
2. Click **Priority** → modal pops with H / N / L.
3. Press `h` for High, `n` for Normal, `l` for Low.

### Load test with folders of various sizes

To smoke total system throughput, save several templates with
different folder targets:

| Template name | Path | Expected scale |
|---|---|---|
| `loadtest-small`     | `/data/import/testload/SmallFiles`  | a few MB |
| `loadtest-medium`    | `/data/import/testload/MediumFiles` | a few hundred MB |
| `loadtest-large`     | `/data/import/testload/LargeFiles`  | tens of GB |
| `loadtest-longterm`  | `/data/import/testload/LargeFiles`  | same as above but retention=365 days; UI highlights with a `*` marker |

Run them in parallel with `dr-job-run` from a shell, or one at a
time from the TUI's Run button. The F3 Jobs Monitor + the dashboard
metrics together give you the "volumes over time" view: queue depth,
running count, and disk IOPS.

You can also drive the synthetic load test from `dr-load`:

```bash
dr-load indexing --users 5 --duration 300s
```

That runs the full createDataArea → createCorpus →
createRepresentation chain with N parallel users and writes a merged
CSV report to `dr_report.csv`.

---

## Operations cheat sheet

```bash
# Where's my state?
ls ~/.dr-tools/jobs/                 # saved templates
ls ~/.dr-tools/runs/                 # run history
tail -f $(ls -t ~/.dr-tools/logs/*.log | head -1)   # latest run log

# All my active timers
systemctl --user list-timers --all | grep dr-tools

# Manually expire a retention run early
dr-job-delete <slug> <run-id>

# Manually run a saved job
dr-job-run <slug>

# Re-cycle the DR backend (PRESERVES the dr-tools RPM)
sudo bash cleandr.sh --keeprpm
expect -f DR_freshinstall.exp
python qa_create_org_admin.py

# Full reset (DR + dr-tools)
sudo bash cleandr.sh
```

---

## Filing tickets / Feature Requests

If something looks wrong or you want a new feature, open a ticket
by adding a section to:

`QA-v0.14.4-handover-20260514T034704Z.md` (or the current QA log)

with this template:

```
## TICKET — <short description>

**Reporter:** beta-user / <your name>
**Build:** v0.15.0
**Type:** Bug / Feature Request
**Surface:** which tab / modal / CLI
**Repro steps:**
1. …
2. …

**Expected:** …
**Actual:** …
**Artifacts:** any log paths, error strings, screenshots.
```

The QA Engineer (me, today) will pick it up, replicate, and either
fix it inline or escalate.

For RPM-install issues specifically, refer to the **Deployment
Engineer** runbook in [`packaging/README.md`](packaging/README.md)
and the troubleshooting guide in [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

---

## Known issues at v0.15.2 ship

1. **Manual path Input instead of a file browser.** *(v0.15.0
   compromise — partially obsolete.)* The file-tree browser was
   dropped in v0.15 because we believed DR denied
   `exploreConnector` for every role. The v0.15.2 systemScope
   discovery proved that wrong — `exploreConnector` works fine for
   DRSysAdmin and org-admin alike — but the manual-path input is now
   the established UX. **FR-8: bring back the file-tree browser**
   logged for v0.16, since the underlying API permission is no longer
   a blocker.
2. **No "volumes over time" chart.** Filed as FR-3. Workaround: F3
   Jobs Monitor + Landing Dashboard metrics combined.
3. **English-only UI.** Filed as FR-4; i18n landing in v0.17+.
4. **F3 row state cues now glyph+colour.** v0.15.1 fix landed
   `▶ ✓ ✗ ⊘ ‖` glyph prefixes on every status cell. Saved-templates
   `longterm` cue uses bold + asterisk + colour. Broader pass folded
   into FR-5 if anything else surfaces.

---

## Two minutes of credits

- The TUI is built on [Textual](https://textual.textualize.io/) —
  same project as `rich`.
- DR REST API endpoints documented in `docs/endpoints_v0.0{5,6,8}.md`.
- All commits include "Co-Authored-By: Claude Opus 4.7 (1M context)"
  because the v0.06 → v0.15 work was an AI-pair-programming run.

Welcome aboard, and thank you for kicking the tires.
