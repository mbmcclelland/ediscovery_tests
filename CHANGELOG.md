# Changelog

## v0.14.2 — 2026-05-13

### Fixed: Connectors view — silent empty state replaced with clear inline status

User report: "Clicking on 'connectors' doesn't show anything." The
panel switches in correctly, but if the org has no connectors (common
on a fresh install) the table just renders column headers with no
explanation, so it looks broken.

Three improvements:

1. **In-panel status line.** New `#connectors-status` Static sits
   above the DataTable. Updates fire at every interesting moment:
   - On tree-leaf click: `[yellow]Loading connectors for X…[/]`
   - On empty success: `[yellow]No connectors found for X. Create
     one in the DR Web UI under Org Admin → Connectors, then click
     the leaf again to refresh.[/]`
   - On non-empty success: `[green]N connector(s) for X.[/]`
   - On no-session: `[red]No API session for X. Log in again or
     pick a different org.[/]`
   - On API error: the actual error code + extended status, inline.
2. **Errors propagate inline.** `_fetch_view`'s outer except blocks
   now also call `_post_connectors_status()` when the failing kind
   is `org-connectors`, so the user doesn't have to glance down at
   the status bar to see what went wrong.
3. **No-session path no longer silently returns.** Previously if
   `_client_for_org(org)` returned None (no client available), the
   function just `return`ed with no UI feedback. Now it posts a
   clear inline message naming the org.

No new pilot test — the change is a UI-feedback path and the existing
suite already verifies the panel structure mounts cleanly. 19 / 19
pilot tests pass unchanged.

## v0.14.1 — 2026-05-13

### Changed: New Job dialog — readable layout + four explicit buttons + 5-day default

User feedback: "the screen makes no sense". The fix:

- **Two-column layout**: form fields (Name, Description, Organization,
  Connector, Keep indexed data for) stack vertically on the left;
  the file tree owns the right column. Labels are plain English,
  no jargon, no numbered "Step N" prefixes.
- **Default retention is 5 days** (was 1 week / 604800s with weeks
  as the unit). Wired through `_initial_retention_value()` and
  `_initial_retention_mult()` so the input box reads "5" with "days"
  selected on a fresh open.
- **Four explicit buttons** matching the user's spec:
  - **Cancel** — discard the dialog, return None
  - **Schedule** — save the JobDefinition as a reusable template
  - **Run now** — save *and* immediately invoke `dr-job-run`
  - **Close** — same as Cancel; both labels exist so the user
    has the familiar wording regardless of habit
- **Field-specific error messages.** Validation now names the field
  that's wrong and tells the user how to fix it:
  - "Name is empty — please enter a name for this job (e.g.
    'payroll-archive')."
  - "Organization 'X' has no projects. Pick a different organization,
    or create a project in DR before scheduling a job here."
  - "Connector not selected. Pick one from the Connector dropdown
    for organization 'X'."
  - "Folder to index not selected. Click a folder in the tree on the
    right, then try again."
  - "Retention period must be a whole number (got 'foo'). Enter 0 to
    keep forever."
  - "Retention period can't be negative. Enter 0 to keep forever,
    or a positive number."

**Dispatch:** the modal returns a payload with an extra `_action` key
("schedule" or "run"). `_sch_after_modal` strips that key, saves the
JobDefinition, and on `"run"` shells out to `dr-job-run` immediately —
same code path the **Run** button on the Saved Templates view uses.

**Pilot test:** new `test_newjob_modal_v0141_defaults_and_buttons`
covers defaults (5 days, "days" unit, 86400 multiplier), the presence
of all four buttons, Close-equals-Cancel, empty-name error doesn't
dismiss, and that a complete form returns the right `_action` for
both Schedule and Run now. 19 / 19 pilot tests pass.

## v0.14.0 — 2026-05-13

### Added: Job Scheduler — per-view actions, log viewer, timer toggle, linger banner

Closes the four "known v0.13 gaps" the v0.13.0 changelog flagged.
Each sub-view now has its own contextual action row inside it; the
top-of-tab strip that previously conflated unrelated actions is gone.

**Running Jobs** — Pause / Resume / Cancel / Priority / Refresh

Wires the existing `pause_task` / `resume_task` / `cancel_task` /
`set_job_priority` fetchers and reuses `ConfirmModal` / `PriorityModal`
so the action paths match F3 Jobs Monitor exactly (including the
mandatory `systemScope: true` for cancel that v0.10.1 captured).

**Saved Templates** — New Job / Run / Edit / **View Log** / Delete / Refresh

View Log finds the most recent `~/.dr-tools/logs/<slug>-*.log` for the
selected template and pops `LogViewerModal`.

**Retention Timers** — **Toggle** / **Cancel timer** / Refresh

- Toggle flips a timer between `active` / `inactive` via
  `systemctl --user enable/disable --now`. New helper
  `scheduler.toggle_retention_timer(unit)` returns
  `(new_state, error)`.
- Cancel timer parses the unit name (`dr-tools-retention-<slug>-<run_id>.timer`)
  via a new `_UNIT_PARSE_RE` and calls the existing
  `cancel_retention_delete()` helper. Confirms via `ConfirmModal`
  because the action is destructive (retention delete will no
  longer fire automatically).

**Run History** — **View Log** / Refresh

View Log opens the log for the specific `run_id` (falls back to the
newest log for that template if the exact stamp's file is missing —
shouldn't happen, but defensive).

**New modal: `LogViewerModal`**

Read-only file tail. Renders into a `RichLog(markup=False)` so log
lines containing literal `[...]` brackets (Java argv dumps,
"Connection refused: 192.168.58.128:8443[NOT_LOCAL]", etc.) don't
trip the markup parser. Same trap that bit v0.13.2 on the landing
dashboard — `markup=False` is the simpler fix for this widget since
nothing here needs colour-coding.

**Lingering banner** — visible only when retention timers exist AND
`loginctl enable-linger` is off AND `systemctl --user` is reachable.
Renders one yellow-on-dark line at the top of the Job Scheduler tab
telling the user to run `sudo loginctl enable-linger $USER`. Three
layers of "off" mean no banner — the calmer default.

**Pilot tests added:**

- `test_unit_parse_regex` — verifies the systemd unit-name parser
  recovers slug + run_id for both single- and multi-word slugs;
  rejects malformed names.
- `test_log_viewer_modal_mount` — writes a real temp log, mounts the
  modal, asserts it appears and dismisses cleanly on Esc.

18 / 18 pilot tests pass (was 16; +2 for v0.14).

## v0.13.2 — 2026-05-13

### Fixed: dash-log RichLog crashed on log lines containing `[/...]` brackets

The landing dashboard's log-stream pane crashed with
`rich.errors.MarkupError: closing tag '[/bin/bash, ...]' at position
N doesn't match any open tag` whenever the AHS log emitted a line
with bracketed argv content — `updatevirusdefinitions.sh` was the
specific trigger reported by the user.

Cause: `_dash_tick_logs` was feeding raw log text into
`RichLog.write()` without escaping, and the underlying
`Text.from_markup()` interprets every `[…]` token as either an
opening or closing markup tag. Java logger categories
(`[com.foo.Bar]`) had been benign by luck (no `/` prefix), but argv
dumps like `[/bin/bash, …, /path/with-dashes]` looked like an
unbalanced closing tag and raised.

Fix: escape the user-controlled portions of each log line with
`rich.markup.escape()` before assembling the `[cyan]…[/] [green]…[/]
text` payload. Our own colour markers are still parsed normally; only
the file name + raw text are escaped.

TaskLogModal's RichLog wasn't affected — it ships with `markup=False`
because per-task AE log lines can contain arbitrary content. We could
have made the dashboard log do the same, but we use the `[colour]`
markers there intentionally to colour-code INFO/WARN/ERROR, so the
escape-only approach keeps both behaviours.

## v0.13.1 — 2026-05-13

### Fixed: New Job wizard — Org → Connector → folder now actually flows

The v0.13.0 New Job modal had two flow bugs and one missed
assumption from the spec:

1. **Browse failed silently after auto-pick.** `_cur_conn_handle` /
   `_cur_org` were initialized from the (often empty) `existing`
   argument and never updated when Textual's `Select(allow_blank=False)`
   auto-selected its first option on mount. `on_select_changed` only
   fires on a *change*, so the initial pick went unrecorded — clicking
   **Browse** then hit "Pick a connector first" against a dropdown that
   visually showed one selected.
2. **Org changes didn't propagate.** Switching the Org Select
   re-populated the Connector Select via `set_options()` but didn't
   update `_cur_conn_handle` to track the new first option.
3. **Project picker wasn't in the spec.** The user asked for
   Organization / Connector / folder. v0.13.0 added a Project picker
   on top of that — every saved job still needs a project context
   server-side, but the user shouldn't have to think about it.

**Changes:**

- **Drop the Project Select.** First project of the chosen org is
  auto-picked behind the scenes; a small hint line under the Connector
  picker tells the user which project (and warns when the org has
  none).
- **Sync `_cur_org` / `_cur_conn_handle` from the Select's auto-pick**
  in `__init__` so the first Browse works without a click.
- **Auto-load the file tree on mount and on connector change.** The
  Browse button is still there (relabelled "Re-browse") as a manual
  refresh.
- New regression test
  `test_newjob_modal_auto_picks_org_connector_project` confirms the
  modal opens with org, connector, and project handle all populated
  from realistic mock data, and that switching orgs propagates
  correctly to both connector and project.

16 / 16 pilot tests pass.

## v0.13.0 — 2026-05-13

### Added: dr-tui — Job Scheduler tab

A new top-level tab for defining + running indexing jobs as reusable
templates, with optional retention-driven cleanup scheduled via
systemd user timers.

**The tab is divided into four leaf views** (left-tree, content-switcher
on the right, same idiom as the System Settings / Organizations tabs):

| Leaf | Source | Notes |
|---|---|---|
| Running Jobs | `realmManager/listRealmTasks` filtered to `operationState=RUNNING` | Action bar mirrors the F3 modal (Pause/Resume/Cancel/Priority paths land in v0.14). |
| Saved Templates | `~/.dr-tools/jobs/*.json` | One row per JobDefinition; **"longterm" anywhere in the name renders yellow-bold**, per spec. |
| Retention Timers | `systemctl --user list-timers --all` filtered to `dr-tools-retention-*` | Live view of pending retention deletions. |
| Run History | append-only `~/.dr-tools/runs/<slug>.jsonl` | Status colour-coded (RUNNING=yellow, SUCCESS=green, FAILURE=red, DELETED=dim). |

**New Job wizard (`NewJobModal`):**

- Org picker, project picker (filtered by org), connector picker
  (filtered by org).
- File tree backed by `connectorManager/exploreConnector` — lazy-loads
  children on node-select via a worker thread; folders are `🗀`, files
  `🗎`. The currently-selected path is echoed below the tree.
- **Count files** button does a client-side recursive walk using
  `count_files_recursively()`. DR's REST API exposes **no folder-size
  endpoint** and exploreConnector returns no size data, so v0.13 ships
  with file/directory counts only (no byte totals).
- Retention period: integer input + units Select (seconds / minutes /
  hours / days / weeks). Default **1 week**. `0 = keep forever`.

**New endpoints + helpers (`dr_tui/data.py`):**

- `explore_connector(client, *, org_name, connector_*, parent_path)` →
  `list[PathEntry]`
- `count_files_recursively(client, …, root_path, progress_cb, max_depth=12)`
  → `(files, dirs)`. Iterative BFS so deep trees don't blow the stack;
  `progress_cb(files, dirs, current)` fires every 100 entries.
- `submit_indexing_job(client, *, project_handle, connector_handle,
  path, dataset_name)` — wraps the full
  `createDataArea → getCorpusSetByName → createCorpus → addCorpus →
  createRepresentation` chain (body shapes pinned from
  `locustfile_indexing.py`).
- `delete_corpus(...)`, `delete_data_area(...)` — used by the retention
  cleanup CLI.

**New module: `dr_tui/scheduler.py`**

- `JobDefinition` dataclass (template) + `RunRecord` (one execution) +
  `TimerInfo` (parsed `list-timers` row).
- State layout under `~/.dr-tools/`:
  - `jobs/<slug>.json` — saved JobDefinition
  - `runs/<slug>.jsonl` — append-only run log
  - `logs/<slug>-<ts>.log` — captured stdout/stderr of one run
- `save_job` / `load_saved_jobs` / `get_job` / `delete_saved_job`.
- `append_run` / `list_runs`.
- `schedule_retention_delete(...)` writes
  `~/.config/systemd/user/dr-tools-retention-<slug>-<run_id>.{service,timer}`,
  `systemctl --user daemon-reload`, `enable --now`. One-shot
  `OnCalendar=` timer with `RemainAfterElapse=false` so the unit GCs
  itself after firing.
- `cancel_retention_delete(...)` (idempotent stop+disable+rm).
- `list_dr_timers()` parses `systemctl --user list-timers --all
  --no-legend` and filters to our prefix.
- `lingering_enabled()` + `systemctl_user_available()` probes — the UI
  hints at the user to run `loginctl enable-linger $USER` if the timer
  unit will die at logout.
- `DR_TOOLS_STATE_DIR` env-var lets tests redirect state to a tmp dir
  without smearing real saved jobs.

**Two new CLIs** (entry points added in `setup.cfg`):

- `dr-job-run <name-or-slug>` — same code path the TUI "Run Now"
  button shells out to; loads JobDefinition, logs in via
  `Config`/`OrgUserConfig`, runs the submit chain, appends a
  RunRecord, schedules retention timer if applicable, tees stdout to
  `~/.dr-tools/logs/<slug>-<ts>.log`.
- `dr-job-delete <slug> <run-id>` — invoked by the systemd
  `.service` at retention horizon; calls `deleteCorpus +
  deleteDataArea` against the handles stored in the matching
  RunRecord, then rewrites the JSONL with `status=DELETED`.

**Why a separate CLI rather than inline:** single code path for "Run
Now" + future cron/timer launches, runs even when dr-tui isn't open,
debuggable from a shell, and dr-job-delete needs to be invokable by
the systemd unit without an interactive TUI process.

**Tests:** new `tests/test_dr_tui_scheduler.py` covers
JobDefinition save/load round-trip, RunRecord append+read, slugify
edge cases, NewJobModal mount + cancel, and the 'longterm' coloring
rule. 15 / 15 pilot tests pass.

**Operational note:** systemd user timers stop when the user logs
out unless `loginctl enable-linger <user>` has been run. README §
"Job Scheduler" covers this; `lingering_enabled()` will eventually
surface a one-line hint in the TUI.

## v0.12.0 — 2026-05-13

### Added: dr-tui — Realm Settings edit modals (Mail / Splash / Password / Inactivity)

The four Realm Settings sub-tree views shipped as read-only in v0.08.1.
v0.12 closes the loop with edit modals for every one of them, plus an
inline **Edit** button in each panel and full F4 dispatch on the
matching tree leaf.

**Endpoints wired** (captured in v0.08, see
`docs/endpoints_v0.08.md`):

| View | Write endpoint | Body |
|---|---|---|
| Mail Server | `realmManager/createMailServerConfig` | `smtpHostId`, `smtpHostPort`, `contextHandle`, `systemScope: true` |
| Splash Message | `realmManager/setSplashMessage` | `enabled`, `splashMessage`, `contextHandle`, `systemScope: true` |
| Password Policy | `realmManager/setPasswordPolicy` | `enforceStrongPasswords` + six numeric fields (length / upper / lower / numbers / symbols / expiration days) |
| Inactivity Timeout | `realmManager/setInactivityTimeout` | `inactivityTimeoutInSeconds` — returns 204 |

Despite the "create" name, `createMailServerConfig` is the upsert path:
there's no separate update endpoint. `setPasswordPolicy` demands all
eight fields every call (server's "missing field" handling is
inconsistent); the modal computes a composition guard so users can't
accidentally configure `minLength=4` with `minUppercase+minNumbers=6`.

**New modals (`dr_tui/app.py`):**

- `MailServerFormModal` — SMTP host + port, port validated to 1–65535.
- `SplashMessageFormModal` — `Checkbox` for enabled + multi-line
  `TextArea` for the banner text. Refuses save when enabled with
  empty text (would be a silent footgun).
- `PasswordPolicyFormModal` — `Checkbox` + six numeric inputs.
  Validation: every field non-negative, `min_length ≥ 1`,
  `min_upper + min_lower + min_numbers + min_symbols ≤ min_length`.
- `InactivityTimeoutFormModal` — single seconds field with hint text
  listing the common conversions (1800 = 30 min, 3600 = 1 h,
  5940 = 99 min DR default, 0 = disable).

**UI dispatch (`DashboardScreen`):**

- Each `sys-*-view` now has an inline **Edit** button (top of the
  panel) calling `_settings_*_open_edit()`.
- `action_ctx_edit` (F4) routes `sys-mail` / `sys-splash` /
  `sys-pwpolicy` / `sys-inactivity` leaves to the same handlers.
- Last-read state is cached in `_mail_last`, `_splash_last`,
  `_pwpolicy_last`, `_inactivity_last` (set on each `_apply_*`) so
  modals open pre-populated with the current values.
- After save, the matching leaf is re-loaded via `_load_view(kind, "")`
  so the panel reflects the new state without a manual refresh.

**Data layer (`dr_tui/data.py`):**

- `set_mail_server_config(client, *, smtp_host, smtp_port)` →
  `MailServerConfig`
- `set_splash_message(client, *, enabled, message)` → `SplashMessage`
- `set_password_policy(client, *, policy)` → `PasswordPolicy`
- `set_inactivity_timeout(client, *, seconds)` → `InactivityTimeout`

Each write returns the canonical state echoed by the server (or, for
the 204 `setInactivityTimeout`, the value just submitted) so callers
can refresh local caches without an extra read.

**Tests:** new `test_settings_modal_paths` exercises happy-path save,
bad-input validation, and Cancel on every modal. 10 / 10 pilot tests
pass; existing v0.11 jobs-monitor / depot / user / group / priority
suites unchanged.

## v0.11.0 — 2026-05-12

### Added: dr-tui — Jobs Monitor v2 (realm-wide tasks, type filter, live log)

Three changes that together turn the F3 Jobs Monitor from "a useful
inventory" into "the thing you reach for when something is wrong."

**1. Single-call realm-wide task list.** v0.10 fanned out
`projectManager/listTasks` once per project — `N` round trips, no
operationState, no orgName/owner pre-filled. v0.11 replaces that with
one call to `realmManager/listRealmTasks`:

```json
{
  "contextHandle": "super_system_customer",
  "startIndex": 0, "count": 500,
  "filters": [{"attribute": "SYNTAXERROR", "operator": "EQUALS", "value": "false"}]
}
```

The `SYNTAXERROR EQUALS false` filter is a sentinel — it's what the
DR Web UI sends to mean "give me everything". The response items are
already flat (`orgName`, `owner`, `projectName`, `dateStarted`,
`dateCompleted`, `secondsElapsed`, `operationState`, `operationType`)
so the modal builds `JobRow` instances directly without descending
into `currentStatus[]`. State buckets are now based on the proper
`operationState` enum (`RUNNING` / `PAUSED` / `SUCCESS` / `FAILURE` /
`CANCELLED` / …) instead of the old "dateCompleted present ⇒ done"
heuristic.

**2. Operation-type filter dropdown.** A new `Select` widget on the
filter row, populated lazily on first fetch from
`realmManager/listOperationTypes` (100 entries: `DOCUMENT_ADD_FROM_FILE_LIST`,
`PREPARE_FOR_ANALYTICS`, `COLLECTION_WEIGHT`, …). Selection adds an
`OPERATION_TYPE EQUALS <value>` filter to `listRealmTasks` server-side
— no client-side filtering, no fetch-everything-then-discard.

**3. Per-task live log viewer.** New `TaskLogModal` (bound to `L`)
tails the AE log for the selected running task via
`taskManager/getSRITaskLog`. Two-step lookup:

  1. `taskManager/getTasks` with `includeDrDebug: true` to find the
     `"Instance ID"` under the `"Service Node Debug State"` status
     section — that's the `taskSri` (the SRI is the AE worker's
     instance number, e.g. `593`; it is **not** exposed in
     `listRealmTasks` or `listJobs`).
  2. `taskManager/getSRITaskLog` with `{ taskSri, numLines }` returns
     `logLines[]` straight from the AE.

`r` re-fetches, `n` cycles 1000 → 2000 → 3000 lines (matches the
"View More" button in the DR Web UI). Log is only viable while the
worker is running; for finished/cancelled tasks the modal hints
"Live log only available for RUNNING tasks" instead of doing a
doomed lookup.

**Files touched:**

- `dr_tui/data.py` — added `list_realm_tasks`, `list_operation_types`,
  `get_task_sri`, `get_sri_task_log`. `collect_jobs` / `list_tasks_for_project`
  are kept (still used by the landing dashboard's "Running jobs"
  micro-table, where the operationState detail isn't needed).
- `dr_tui/app.py` — `JobsMonitorModal._fetch_blocking` now does one
  fetch instead of N; new `_type_filter` + `_op_types` state; new
  `TaskLogModal` (`RichLog`-backed log viewer with `r` / `n` / Esc).
- `dr_tui/app.tcss` — `#tasklog-card` + `#jobs-type-select` styles.
- `tests/test_dr_tui_dashboard_layout.py` — extended `_walk_jobs_monitor`
  to verify the new Select + Log button.

All 9 pilot tests pass.

## v0.10.2 — 2026-05-12

### Fixed: dr-tui terminal compatibility (PuTTY + other legacy SSH clients)

PuTTY's default `TERM=xterm` + Win-1252 character set + missing
kitty-keyboard support left dr-tui unusable: garbled box-drawing,
escape codes leaking onto the screen, keystrokes not reaching the app.

Three changes landed:

1. **`/usr/bin/dr-tui` launcher** (in both `packaging/dr-tools.spec`
   and `packaging/install.sh`) now sets two env vars defensively:

   ```sh
   if [ "$TERM" = "xterm" ] && [ -f /usr/share/terminfo/x/xterm-256color ]; then
       TERM=xterm-256color
   fi
   : "${TEXTUAL_FEATURES=}"
   ```

   `TERM=xterm-256color` gives Textual the right terminfo entry for
   true-colour rendering. `TEXTUAL_FEATURES=` (empty) skips the
   kitty-keyboard probe that PuTTY swallows.

2. **README** gained a new "Terminal compatibility" section under
   `TUI Usage` listing recommended terminals (Windows Terminal, Tabby,
   Alacritty, iTerm2, GNOME Terminal, …), the two PuTTY-specific
   knobs (UTF-8 remote charset + the env-var workaround), and a
   diagnostic recipe for capturing a `TEXTUAL_LOG=` trace.

3. The env-var workaround was confirmed live in a PuTTY session —
   `TERM=xterm-256color TEXTUAL_FEATURES= dr-tui` rendered cleanly and
   accepted input.

Existing RPM installs (v0.10 / v0.10.1) can either rebuild + reinstall
the RPM to pick up the launcher fix, or just use the env-var
workaround until the next upgrade.

## v0.10.1 — 2026-05-12

### Added: dr-tui — Jobs Monitor: Pause / Resume / Cancel / Set Priority

The four action buttons on the F3 Jobs Monitor modal are now fully
wired to live endpoints — the v0.10 ship had Pause / Resume working
plus "pending capture" stubs for Cancel / Priority. v0.10.1 closes
both gaps after a manual mitmproxy capture during a real index-build
cycle.

**Endpoints pinned:**

| Action | Endpoint | Body | Returns |
|---|---|---|---|
| Cancel | `taskManager/cancelTask` | `taskHandle`, `systemScope: true` | 200 + empty body |
| Set Priority | `taskManager/updateJobPriority` | `priority: "HIGH"`/`"NORMAL"`/`"LOW"`, `taskHandle` | 204 No Content |

The `systemScope: true` flag is **mandatory** for `cancelTask` — every
earlier probe without it returned HTTP 500 with a NullPointerException.
That's the one subtle quirk; both endpoints are otherwise minimal.

**Set Priority body is unusually small** — just `requestHandle`,
`priority`, and `taskHandle`. No `contextHandle`, no `systemScope`.
The priority value is the uppercase enum string (server is
case-sensitive).

**UI additions:**

- `PriorityModal` — warning-bordered modal with three coloured option
  buttons (High = error/red, Normal = primary/blue, Low = default) +
  Cancel. Single-letter hotkeys `h` / `n` / `l` pick directly; Esc
  cancels. Renders the current priority as a header subtitle when
  available (parsed from the task's `currentStatus[]` block).
- Cancel button now opens a `ConfirmModal` ("Cancel Job?") before
  firing — destructive action, requires explicit confirmation.
- The Jobs Monitor detail pane flashes green on a successful action
  and yellow on failure ("could not pause — task was already
  completed", etc.). Master table auto-refreshes after every action
  so state changes propagate immediately.

**Data layer:**

- `dr_tui.data.cancel_task(client, *, task_handle)` — wraps the
  endpoint with the mandatory `systemScope: true`.
- `dr_tui.data.set_job_priority(client, *, task_handle, priority)` —
  validates `priority ∈ {HIGH, NORMAL, LOW}` and rejects others before
  the round-trip.

**Bonus endpoints captured in the same session** (documented in
`docs/endpoints_v0.06.md`, ready for future wiring):

- `realmManager/listRealmTasks` — realm-wide tasks with
  `operationState` + filters. Cleaner than the current per-project
  `listTasks` fan-out; will replace it in a future v0.11.
- `realmManager/listOperationTypes` — full enum of workbasket task
  types, source for a future "filter by type" dropdown.
- `taskManager/getSRITaskLog` — per-task live log payload, source for
  a future "View Live Log" enhancement.

**Tests:** new `test_priority_modal_paths` verifies all three priority
buttons + cancel return the right value (`HIGH`/`NORMAL`/`LOW`/None).
9 / 9 pilot tests passing.

## v0.10 — 2026-05-12

### Added: dr-tui — F3 Jobs Monitor modal

A new realm-wide jobs monitor — press **F3** from anywhere to pop a
90% × 90% modal showing every job across every project + org, plus
historically-deleted projects, with live detail-pane drill-down.

Layout:

| Section | Content |
|---|---|
| Title bar | "Jobs Monitor" |
| Summary | `running=N · complete=N · deleted=N · showing=N · cores=N` (live counts) |
| Filter row | 4 toggle buttons: All / Running / Complete / Deleted + search input |
| Master table | Org · Project · Job · State · Started · Completed · Duration · User |
| Detail pane | Full per-job breakdown — every `currentStatus` section + every attribute, rendered as a label/value tree |
| Hint footer | `[r] refresh · [a/u/c/d] filter · [/] search · [Esc] close` |

Auto-refreshes every 5 s while open. Detail pane updates on row-cursor
move. Search is incremental (matches against org + project + job +
user, case-insensitive).

**Data sources:**

| Endpoint | Provides |
|---|---|
| `realmManager/listJobs` | Realm-wide active jobs count + total CPU cores |
| `realmManager/listProjects` (DRSysAdmin) | All realm projects — fans out to per-project `projectManager/listTasks` for full task history |
| `orgManager/listUserProjectsForAllOrgs` (org admin) | Org-scoped project list — same fan-out |
| `realmManager/listDeletedProjects` | Historical project deletions (separate "Deleted" filter) |

Each `JobRow` now carries a `raw: dict` snapshot of the full
`listTasks` response, so the detail pane can render the complete
status payload without a second round-trip. `format_job_detail()`
walks every section + attribute and formats it as a Rich-markup block.

The DRSysAdmin project-list path switched from
`listSystemUserProjectsByUserName` to `realmManager/listProjects` for
the Jobs Monitor — the user-scoped endpoint missed projects on a
fresh install (it filters to projects the user is *bound to*, which
can be empty for a freshly-installed realm).

`DeletedProject` is a new dataclass capturing the
`listDeletedProjects` shape (`project_id`, `project_name`,
`description`, `org_name`, `user_name`, `date_created`,
`date_deleted`).

**Tests:** `test_jobs_monitor_modal` verifies F3 opens the modal,
filter buttons click cleanly, the search input accepts text, and Esc
closes back to the DashboardScreen. 8 / 8 pilot tests passing.

## v0.09 — 2026-05-12

### Added: dr-tui — F2 documentation side-pane (DR PDFs as built-in help)

The 217 Digital Reef help PDFs (1.3 GB at
`/data/import/Digital Reef PDFs/5.5.3.1 complete`) are now searchable
from inside the TUI. Press **F2** on any leaf to slide in a 35%-width
markdown pane showing the matching DR topic — title, navigation path,
required permissions, description, and field-by-field options. F2
again to hide. Help content updates automatically when you pick a new
tree leaf.

**Pipeline (preprocessor + runtime):**

1. `tools/extract_help.py` — one-shot script, run locally. For each
   of the 18 TUI views currently rendering data:
   - Picks a matching PDF (44 small "per-topic" PDFs cover some views
     directly; for the rest it locates the topic inside a big-corpus
     PDF using the recurring `"You are here:"` boundary marker).
   - Runs `pdftotext`, strips the web-help nav boilerplate
     (`Skip To Main Content / Account / Settings / Logout / Search /
     Filter / Submit Search / You are here: / Copyright …`).
   - Writes `dr_tui/help_content/<view_id>.md` and a
     `help_index.json` with metadata (label, source PDF, file).
2. `dr_tui/help.py` — runtime loader. `get_help(view_id)` returns a
   `HelpEntry(view_id, label, title, source_pdf, body_markdown)` or
   None. Index is cached after first load; per-view payloads are
   cached on first access.
3. `dr_tui/app.py` — adds a `Markdown` widget to both the System
   Settings and Organizations tabs, `display=False` by default. F2
   toggles visibility on both tabs simultaneously and refreshes
   content. Tree-leaf selection auto-updates content while the pane
   is open.

**Coverage (18/18 views with extracted help):**

| Tab | Views with help |
|---|---|
| System Settings | doc/idx depots, system depot, virus, system users, system groups, mail server, splash message, password policy, inactivity timeout |
| Organizations | users, admins, groups, projects, connectors, storage, running jobs, completed jobs |

The 4 hardest topics (Mail Server, Splash, Password Policy, Inactivity
Timeout) had no dedicated PDF — they live as sub-sections of the big
"View and Manage the Password and User Logout Policy" / "Configure an
Email Server & Notifications" / "Configure a System Message" topics
inside any big-corpus PDF. The extractor finds them by `topic_title`
substring match against the title line that follows each
`"You are here:"` marker.

**Packaging:**

- `setup.cfg` extends `package_data` to ship `help_content/*.md` and
  `help_content/help_index.json` alongside the existing `*.tcss`. The
  RPM build picks these up automatically through `pip wheel`, so no
  spec-file change is needed.

**Tests:** `test_help_pane_toggle` verifies F2 flips both panes from
hidden → visible → hidden without exceptions. 7 / 7 pilot tests passing.

## v0.08.1 — 2026-05-12

### Added: dr-tui — Realm Settings sub-tree (read-only)

System Settings tree gains a new collapsible **Realm Settings**
branch with four leaves:

| Leaf | Source endpoint | Renders |
|---|---|---|
| Mail Server | `realmManager/getMailServerConfig` | SMTP host / port / auth flag, or "no mail server configured" |
| Splash Message | `realmManager/getSplashMessage` | Enabled flag + message body |
| Password Policy | `realmManager/getPasswordPolicy` | All 7 policy knobs (length, casing, digits, symbols, expiry) |
| Inactivity Timeout | `realmManager/getInactivityTimeout` | Seconds + friendly `h:m:s` |

Read-only this pass — the edit modals (POST `createMailServerConfig` /
`setSplashMessage` / `setPasswordPolicy` / `setInactivityTimeout`) are
captured in `endpoints_v0.08.md` and will land in v0.08.2 after
you've eyeballed the read layouts.

Backed by 4 new dataclasses + 4 fetchers in `dr_tui/data.py`:
`MailServerConfig`, `SplashMessage`, `PasswordPolicy`,
`InactivityTimeout` + corresponding `get_*` functions, each verified
live against the running DR.

Tests: `test_dashboard_layout` extended with 8 new widget-presence
assertions for the realm-settings views. 6 / 6 pilot tests still
passing.

## v0.08 — 2026-05-12

### Added: docs/endpoints_v0.08.md — System Settings (advanced) capture

Manual mitmproxy capture during a comprehensive System Settings walk
yielded 170 entries covering 13 previously-undocumented endpoint
families. Saved at `/tmp/dr_proxy_capture_v08_syssettings.json`,
documented in `docs/endpoints_v0.08.md`. The new endpoints fall into
these areas:

| Area | New endpoints |
|---|---|
| Mail Server | `createMailServerConfig`, `setEmailNotificationCfg`, `listEmailIdsToNotify` |
| Splash Message | `getSplashMessage`, `setSplashMessage` |
| Realm Nodes | `createNode` (add worker — `listNodes` already in v0.07) |
| Services | `listServices`, `createService`, `serviceManager/updateService`, `deleteService`, `serviceManager/listProjectsForService`, `connectorManager/getReefReviewConnector` |
| Templates | `createTemplate`, `updateTemplate`, `deleteTemplate`, `listTemplates` |
| Template ops | `copyFromTemplate`, `copyToTemplate`, `exportTemplates`, `importTemplates`, `getMetaTemplateProfileEntries`, `copyMetaTemplateProfileEntriesToOrganizations` |
| Email Signatures | `listEmailSignatures`, `createEmailSignature` |
| Project Analytics | `getAnalyticalSettings` (large nested object — every dedup / threading / inclusion knob) |
| Permissions catalogue | `getSecureObjectGroups` (UI permission tree source) |
| Tasks tracker | `taskManager/getTasks` (poll async ops by handle) |
| Realm-user org cross-link | `realmManager/listSystemUserOrgs` |

**Key findings:**

- **Service create body** (`createService`) takes three node arrays —
  `serviceExpressNodes`, `serviceOcrNodes`, `serviceRealmNodes` —
  empty arrays mean "use system default" for that pipeline class.
- **Service update** reuses the `requestHandle` field to carry the
  service's handle (same pattern as `updateRemoteNFSStorageArea`).
- **Template push to orgs** (`copyMetaTemplateProfileEntriesToOrganizations`)
  is async — returns a `taskHandle`, poll with `taskManager/getTasks`.
- **Template export** returns a `fileUrl` like
  `/getfile?templatesDownload=…&token=…` — fetch with plain GET.
- **`createMailServerConfig`** is also the update path; there's no
  separate update endpoint for mail config.

**Remaining capture gaps (v0.08.1 candidates):** `updateNode` /
`deleteNode`, `setAnalyticalSettings`, `updateEmailSignature` /
`deleteEmailSignature`, `updateNFSConnector`. Documented as such in
the new doc's "Capture gaps remaining" section.

## v0.07.1 — 2026-05-12

### Added: Connector capture (last v0.06/v0.07 gap closed)

Manual mitmproxy capture during a UI Create → Edit → Delete →
Deactivate cycle pinned down every connector-CRUD endpoint:

| Op | Endpoint | Notes |
|---|---|---|
| Create NFS | `orgManager/createNFSConnector` | `mountedConnectorMode: "CLASSIC"` |
| Create Exchange | `orgManager/createExchangeConnector` | Azure-AD or domain-controller auth |
| Update Exchange | `connectorManager/updateExchangeConnector` | uses `handle` |
| Get Exchange detail | `connectorManager/getExchangeConnector` | pre-fill for edit modal |
| Validate NFS | `connectorManager/validateNFSConnector` | pre-save uniqueness + reachability |
| Validate Exchange | `connectorManager/validateExchangeConnector` | pre-save |
| Browse NFS paths | `connectorManager/exploreConnector` | path picker |
| Delete (true removal) | `orgManager/deleteConnector` | returns 204; by `handle` + `taskDescription` |
| Deactivate (soft) | `adminOrgManager/deactivateConnectors` | returns 204; takes connector **name** in a `handles` list |

Big finding: **delete and deactivate are separate operations**.
`deleteConnector` removes the row outright; `deactivateConnectors`
flips `status` to `DEACTIVATED` but keeps the row visible. The capture
also confirmed `deactivateConnectors` takes the connector's *name* (not
handle) in a bulk-capable list.

Capture saved at `/tmp/dr_proxy_capture_v07_connectors.json`. Endpoints
documented in `docs/endpoints_v0.06.md` (Connectors section);
`Still missing` table now empty for v0.07.

### Added: dr-tui — Deactivate button on the Connectors panel

`Organizations → <org> → Connectors` now carries a warning-coloured
**Deactivate** button above the table. Click → confirmation modal →
`adminOrgManager/deactivateConnectors`. Status flips to `DEACTIVATED`
and the panel auto-refreshes. Already-deactivated rows are a no-op
with a friendly status-bar hint.

Backed by two new fetchers in `dr_tui/data.py`:

- `deactivate_connectors(client, *, org, names)` — soft delete.
- `delete_connector(client, *, org, handle, name)` — true removal
  (not yet surfaced in the UI; ready for a future Delete button).

Both verified live: created `d9deact` NFS connector → deactivated
(status: `DEACTIVATED`) → deleted (row gone).

## v0.07 — 2026-05-12

### Added: distribution / RPM packaging

`packaging/` directory carries everything needed to ship a self-contained
`dr-tools` RPM:

| File | Role |
|---|---|
| `packaging/dr-tools.spec` | RPM spec — venv at `/opt/dr-tools/venv`, launchers at `/usr/bin/{dr-tui,dr-load}`, `%post` env-example pointer |
| `packaging/Makefile` | `make wheels` / `make tarball` / `make srpm` / `make rpm` / `make install` / `make clean` |
| `packaging/install.sh` | Bash one-shot installer (alternative to RPM for dev hosts) |
| `packaging/README.md` | Build + distribution guide |

**Build path:** `cd packaging && make rpm` produces
`rpmbuild/RPMS/x86_64/dr-tools-VERSION-1.el9.x86_64.rpm` (~20 MB) plus a
~24 MB SRPM. The SRPM bundles a pre-built **wheelhouse** of every
runtime dependency, so the binary RPM is **offline-installable** on
air-gapped lab hosts. Verified end-to-end:

```
$ sudo dnf install ./dr-tools-0.07-1.el9.x86_64.rpm
$ dr-tui          # launches the login screen from the installed venv
$ dr-load --help  # prints Typer help
```

**Supporting changes:**

- `setup.cfg`: renamed package `ediscovery-tests` → `dr-tools`, moved
  `pytest` / `playwright` / `mitmproxy` to `extras_require[dev]` so the
  install_requires set is the minimal runtime closure. Added
  `package_data = dr_tui/*.tcss` (without this `pip install` skipped
  the Textual stylesheet).
- `pyproject.toml`: new — minimal PEP 517 build-system declaration so
  `python -m build` + `pip wheel` work cleanly.
- `.gitignore`: ignores `build/`, `dist/`, `packaging/rpmbuild/`.

### Added: dr-tui landing dashboard

A new **Dashboard** tab is now the initial active tab after login (for
DRSysAdmin; hidden for org users since it requires realm-scope reads).
Layout, top to bottom:

| Pane | Source | Refresh |
|---|---|---|
| License | `realmManager/getLicenseInfo` — every label/value pair (Application, Mode, Issued to, Valid until, AE / Express AE / OCR core counts, …) | 30 s |
| Realm Node — Status Details | `realmManager/listNodes` + per-node `realmManager/getNodeStatus` (components, connectors, storage mounts). Mirrors the Monitoring → Node Status panel. | 30 s |
| System Metrics | `psutil` — CPU%, Memory%, Network rx/tx bytes-per-sec, Disk read+write IOPS. Peak + average over a rolling 60-sample window. CPU + Memory rendered as `Sparkline`. | 2 s |
| Logs | `LogTailer` — multi-file `tail -f` of `/home/auraria/AHS/output/*.log`. Detects `INFO` / `WARN` / `ERROR` per line; filter toggles in the panel header switch each level on/off. Rotation-safe (re-opens on truncate). | 1 s |
| Top processes | `psutil.process_iter` — top 5 by CPU%, ps-aux style (PID / USER / CPU% / MEM% / CMD). | 3 s |

New module `dr_tui/metrics.py` carries the pure local-OS helpers
(`sample_metrics`, `MetricsHistory`, `LogTailer`, `top_processes`)
separate from the REST data layer in `dr_tui/data.py` (which gains
`get_license_info`, `list_nodes`, `get_node_status` and the
`LicenseField` / `NodeInfo` / `NodeStatusDetail` dataclasses).

The four refresh cycles are independent `set_interval` timers so a slow
REST round-trip doesn't stall metrics or the log stream. Realm calls
run on a worker thread; metrics / logs / processes are local and read
on the UI thread (cheap psutil + file-stat polls).

Tests: `test_dashboard_layout` now also asserts the dashboard widget
inventory (12 widgets) on top of the existing 12 System Settings action
buttons.

## v0.06.1 — 2026-05-12

### Added: dr-tui — Midnight Commander-style keyboard navigation

The footer now renders an F-key action bar that drives every CRUD entry
point:

| Key | Action |
|---|---|
| F1 | `HelpModal` — in-app keyboard reference |
| F4 | Edit selected row (depot / user / group) |
| F5 | Refresh current view |
| F6 | Reset Password (on Users) / Update Now (on Virus) |
| F7 | New entity (depot / user / group) |
| F8 | Delete selected row |
| F10 | Quit |
| Tab | Cycle focus (tree ↔ table) |
| 1 / 2 | Jump to System Settings / Organizations tab |

The F-keys resolve to the right CRUD handler by inspecting
`selected_kind`, so the same key works across depots / users / groups.
Form modals now accept Enter inside any Input field as Save (via
`on_input_submitted`), and a `[Enter] save · [Esc] cancel · [Tab] next`
hint footer renders inside each modal card. Legacy `q` / `r` / `l`
remain as hidden aliases for muscle memory.

Coverage: `tests/test_dr_tui_dashboard_layout.py` adds
`test_keybindings` (F1 opens help; 1 / 2 switch tabs; F7 on a no-leaf
view is graceful) and `test_enter_saves_form_modal` (Enter in a
DepotFormModal Input fires save). 6 / 6 pilot tests passing.

## v0.06 — 2026-05-12

### Summary

System Settings CRUD layer for `dr-tui` (depots, system users, system
groups, virus-defs "Update Now"), backed by a write-path endpoint
reference derived from three mitmproxy captures. Adds a destructive
reinstall toolchain (`cleandr.sh` + Expect + Playwright) that brings DR
back to a tested baseline in ~10 minutes. Closes seven endpoint-capture
gaps left over from v0.05; only Connector edit/delete remains for
v0.06.1.

Test coverage: 4 pilot smoke tests (depot + user + group modals,
dashboard layout) — all passing. Every CRUD modal verified live against
DR with create → update → delete round-trips.

### Added: fresh-install / reinstall toolchain

A three-step chain for tearing down DR and bringing it back to a tested
baseline (DRSysAdmin/`password`, `admin@training`/`password`, depots,
system depot, training org):

| Step | Tool | Purpose |
|---|---|---|
| 1 | `cleandr.sh` | Stops `drd`, preserves `license.lic` to `/root/`, wipes `/home/auraria/AHS*`, `/data/docstorage/*`, `/data/indexstorage/*`, the InstallAnywhere registry, and stale `/tmp` artefacts. |
| 2 | `DR_freshinstall.exp` | Expect script that drives the InstallAnywhere console installer (`/tmp/5.5.3.2.bin -i console`): license accept, Full node, eDiscovery, generate SSL, IP=192.168.58.128, then restores `/root/license.lic` → `/home/auraria/AHS/conf/license.lic` and `systemctl restart drd`. |
| 3 | `playwright_fresh_init.py` | Focused Playwright driver: first login → forced password change → create Doc + Idx depots → assign System Storage Depot → create `training` org → create `admin/training` user → forced password change → logout. Idempotent (skip-if-exists in every phase). |

The full chain takes ~10 minutes end-to-end and leaves the system ready
for `dr-load`, `dr-tui`, and the pytest suite to run unmodified.

### Added: `playwright_fresh_install.py` is now an importable module

Module-level `argparse.parse_args()` was gated behind `_parse_args()` so
phases (`phase_login_initial`, `phase_change_password`, `phase_create_storages`,
…) can be reused by `playwright_fresh_init.py` without polluting `sys.argv`.

### Added: docs/endpoints_v0.06.md

Comprehensive endpoint reference for v0.06 write paths, derived from two
Playwright runs against a freshly-installed DR plus a hybrid manual capture
through mitmproxy. Covers full CRUD on storage depots, organizations, org
users, and groups, plus the realm-settings bonus (`setPasswordPolicy`,
`setInactivityTimeout`, etc.).

### Fixed: `api_client.post()` 204 No Content handling

`helpers/api_client.py` previously crashed on `.json()` when a delete-style
endpoint (`deleteStorageArea`, `deleteOrganization`, `setInactivityTimeout`)
returned 204 with an empty body. Now returns an empty `{}` on 204 or empty
response — unblocks every DELETE in v0.06 CRUD.

### Added: dr-tui — System Groups CRUD (D6)

`System Settings → System Groups` now carries a **New / Edit / Delete**
action bar above the group table:

- **New** → `GroupFormModal` (name, description, role dropdown) →
  `adminOrgManager/createGroup` with
  `organizationName: "super_system_customer"` + `systemScope: true`.
- **Edit** → modal pre-fills from the selected `GroupRow` (extended to
  carry `role_handle` + `role_name` for the dropdown round-trip) →
  `orgManager/updateGroup` with `systemScope: true`. The captured body
  uses a nested `group` object.
- **Delete** → red `ConfirmModal` (warns about member-role loss) →
  `orgManager/deleteGroup` with `systemScope: true`.

**Key finding:** there is no separate `adminOrgManager/updateGroup` /
`adminOrgManager/deleteGroup`. The org-scope endpoints handle both
system and org groups via the `systemScope` flag. The D3 docs are
updated accordingly.

The role dropdown shares the system-roles cache populated by D5
(`realmManager/listSystemRoles`), so opening the group form for the
first time after the user-form is free.

### Added: docs/endpoints_v0.06.md — D6 capture-gap closures

A capture pass (saved at `/tmp/dr_proxy_capture_v06_sysgroups.json`)
filled three of the remaining gaps:

| Endpoint | Status |
|---|---|
| `orgManager/updateGroup` (system) | ✅ confirmed — works for system groups via `systemScope: true` |
| `orgManager/deleteGroup` (system) | ✅ same — no separate admin variant |
| `groupManager/setUsers` | ✅ bonus — bulk-replace group membership |

Only remaining v0.06.1 gap: Connector edit / delete.

### Added: dr-tui — System Users CRUD + reset-password (D5)

`System Settings → System Users` now carries a **New / Edit / Reset PW /
Delete** action bar above the user table:

- **New** → `UserFormModal` (username, email, first/last, initial
  password, role dropdown) → `adminOrgManager/createUser` with
  `orgName: "super_system_customer"` + `systemScope: true`.
- **Edit** → same modal pre-filled (username locked, no password field)
  → `userManager/updateUser` carrying `userHandle`.
- **Reset PW** → `ResetPasswordModal` (new + confirm) →
  `userManager/resetPassword`.
- **Delete** → red `ConfirmModal` → `adminOrgManager/deleteUser` with
  `organizationName: "super_system_customer"`.

Role dropdown is lazily populated via `realmManager/listSystemRoles`
(cached for the screen's lifetime — refresh on next login). The status
bar flashes green on success and the table auto-refreshes once the
write returns.

### Added: docs/endpoints_v0.06.md — capture-gap closures

A manual mitmproxy capture during D5 (saved to
`/tmp/dr_proxy_capture_v06_sysusers.json`) closed three of the gaps
flagged in D3:

| Endpoint | Status |
|---|---|
| `userManager/updateUser` | ✅ now confirmed — works for both system and org users via `userHandle` |
| `adminOrgManager/createUser` | ✅ confirmed (distinct from `orgManager/createUser`) with `orgName: "super_system_customer"` |
| `adminOrgManager/addSystemUserToOrg` | ✅ confirmed — parallel of `addSystemGroupToOrg` |

Remaining gaps for v0.06.1: `orgManager/updateGroup`,
`adminOrgManager/updateGroup`, `adminOrgManager/deleteGroup`,
connector edit/delete.

### Added: dr-tui — Storage Depot CRUD (D4)

Both `System Settings → Document Storage Depots` and `… → Index Storage
Depots` views now carry a **New / Edit / Delete** action bar above the
table:

- **New** opens `DepotFormModal` — Name, FQDN/IP, Export, Allocation —
  posts to `realmManager/createRemoteNFSStorageArea`.
- **Edit** pre-fills the modal from the selected row (Name locked,
  immutable server-side) and posts to
  `storageAreaManager/updateRemoteNFSStorageArea`.
- **Delete** opens a red-bordered `ConfirmModal` and posts to
  `realmManager/deleteStorageArea` (returns 204 → D1 fix).

Writes run on Textual worker threads, the status bar flashes green on
success, and whichever depot leaf is visible auto-refreshes once the
write returns. Create + edit calls use a 120 s timeout — fresh NFS
probes on a clean install can run ~30–60 s and the default 30 s timeout
otherwise misleads the user into thinking the call failed while the
server keeps working.

Coverage:

- Pilot smoke: `tests/test_dr_tui_depot_modal.py` (5 scenarios — empty
  validation, valid create, edit pre-fill, confirm yes, confirm no).
- Live verification: full create → edit → delete cycle confirmed
  against the freshly-reinstalled DR (DOCUMENT_STORE handle 607 round-
  trip; export path mutated and read back; 204 cleanup observed).

### Added: dr-tui — Virus Detection "Update Now" (D7)

`System Settings → Virus Detection` now carries an **Update Now** button
that fires `realmManager/updateVirusDefinitions` with
`updateDefinitionFiles: true`. The handler preserves the most recently
read `enabled` + `frequency` so the schedule config stays untouched.
"Already running" responses (errorCode `INVALID_STATE`) surface as a
friendly status-bar message rather than a stack trace.

### Added: pilot smoke + thread-safe status bar (D8)

- `tests/test_dr_tui_depot_modal.py` — 3 tests covering DepotFormModal,
  UserFormModal + ResetPasswordModal, GroupFormModal (validation +
  cancel + valid-submit per modal).
- `tests/test_dr_tui_dashboard_layout.py` — 1 test that mounts the full
  DashboardScreen with a fake client, asserts every CRUD action-bar
  button is present, and confirms the "no row selected" guard on
  Edit / Delete buttons doesn't crash.
- Made `DashboardScreen._post_status` thread-aware. It previously
  always bounced through `App.call_from_thread`, which Textual 8.x
  rejects when called from the main UI thread. Now it detects which
  thread it's running on and dispatches accordingly.

### Bumped: `__version__` 0.05 → 0.06

README updated to reflect v0.06 features (CRUD modals + reinstall
toolchain). Project Structure section preserved.

### Known capture gaps (v0.06.1 candidates)

- Connector edit / delete — not exercised yet

(D5 closed `updateUser` + `addSystemUserToOrg`; D6 closed group update /
delete by confirming the org-scope endpoints handle both scopes.)

---

## v0.05 — 2026-05-11

### Restructured: `dr-tui` — tabbed hierarchical views, read-only

Replaced the v0.04 three-panel dashboard with a `TabbedContent` layout: a
left-side `Tree` per tab and a `ContentSwitcher` detail pane on the right.
Every leaf maps to a read-only view; create / edit / delete arrive in v0.06.

**Tab 1 — System Settings** (DRSysAdmin only; tab is hidden via
`TabbedContent.hide_tab("tab-sys")` when role is `admin@training`):

| Leaf | Endpoint | View |
|---|---|---|
| Storage › Document Storage Depots | `realmManager/listRemoteNFSStorageAreas` (filter `storageUseType == DOCUMENT_STORE`) | DataTable |
| Storage › Index Storage Depots    | same endpoint, `INDEX_STORE` filter | DataTable |
| System Storage Depot              | `realmManager/getSystemStorageDepot` | Key/value pane |
| Virus Detection                   | `realmManager/getVirusDefinitions`   | Key/value pane |
| System Users                      | `adminOrgManager/listUsersAndGroups` (super_system_customer) → `users[]` | DataTable |
| System Groups                     | same endpoint → `groups[]` | DataTable |

**Tab 2 — Organizations** (both roles). Tree populated by
`realmManager/listOrganizations` (sys) or `OrgUserConfig.organization` (org).
Each org expands to eight leaves:

| Leaf | Endpoint | View |
|---|---|---|
| Users / Admins | `orgManager/listUsersAndGroups` (split by `admin` flag / "Organization Administrator" role) | DataTable |
| Groups | same response → `groups[]` | DataTable |
| Projects | `realmManager/listSystemUserProjectsByUserName` (sys) / `orgManager/listUserProjectsForAllOrgs` (org), filtered by org name | DataTable |
| Running Jobs / Completed Jobs | `projectManager/listTasks` per project, split by `dateCompleted` | DataTable |
| Connectors | `adminOrgManager/listConnectors` | DataTable (relocated from v0.04 dashboard) |
| Storage | cross-ref `listOrganizations.storageUsages` ↔ `listRemoteNFSStorageAreas` (sys only) | DataTable |

**Behaviour**

- Each leaf has its own fetcher in `dr_tui/data.py` and applier in
  `DashboardScreen`; selection fires `_load_view(kind, org)` on a worker
  thread.
- Auto-refresh ticks every 5 s but only re-fetches the currently-visible
  leaf (no more hammering all endpoints).
- DRSysAdmin drill-down into a non-default org transparently calls
  `realmManager/initializeOrganization` first (`_client_for_org`).
- Status bar now shows the active view kind alongside role / org / counts.

**Smoke test (2026-05-11)**

Headless `Pilot` walk through every leaf for both roles (`/tmp/dr_tui_c_pilot.py`):

| Leaf | Sys rows | Org rows |
|---|---|---|
| Document Storage Depots | 1 | (hidden tab) |
| Index Storage Depots    | 1 | (hidden tab) |
| System Storage Depot    | rendered | (hidden tab) |
| Virus Detection         | rendered | (hidden tab) |
| System Users            | 1 | (hidden tab) |
| System Groups           | 0 | (hidden tab) |
| Users                   | 0 | 0 |
| Admins                  | 2 | 2 |
| Groups                  | 0 | 0 |
| Projects                | 1 | 1 |
| Running Jobs            | 0 | 0 |
| Completed Jobs          | 0 | 0 |
| Connectors              | 2 | 2 |
| Storage                 | 3 | 0 (org user lacks `listOrganizations` privilege — by design) |

SVG snapshots at `/tmp/dr_tui_c-*.svg`.

**New files / changed files**

- `dr_tui/app.py` — full DashboardScreen rewrite (TabbedContent + Trees +
  ContentSwitcher + dispatcher); `LoginScreen` and `DRTUIApp` unchanged.
- `dr_tui/data.py` — new dataclasses (`StorageDepot`, `SystemDepot`,
  `VirusDefs`, `UserRow`, `GroupRow`, `ProjectRow`, `OrgStorageRow`,
  `OrgInfo`) + nine new fetchers.
- `dr_tui/app.tcss` — replaced 2×2 grid with full-height tab layout; added
  `.detail-body` for key/value panes.
- `docs/endpoints_v0.05.md` — endpoint reference (also flags v0.06 deferred
  write paths).

**Known limitations (deferred to v0.06)**

- All views are read-only. No create / edit / delete / virus-update yet.
- Org-scoped users cannot see Storage (depends on realmManager privileges).
- `api_client.post()` will still crash on 204 No Content responses — fix
  pending for v0.06 write paths (task #13).

---

## v0.04 — 2026-05-11

### Added: `dr-tui` — Textual TUI

A lazygit-style three-panel TUI for monitoring the live system. Installed as a
new console script alongside `dr-load`.

```bash
dr-tui            # or: python -m dr_tui
```

**Screens**

- **Login** — radio toggle between `DRSysAdmin` and `admin@training`, password
  field (defaults to `password` for the lab). Enter to submit, Esc to quit.
  On DRSysAdmin login the TUI also attempts an org-user login in the background
  so org-scoped panels work when DRSysAdmin is also an Org Admin.
- **Dashboard** — three panels:
  - **Connectors** (left, full height) — name, type, mode, host, path, status.
  - **Running Jobs** (top right) — project, job description, task handle, elapsed.
  - **Completed Jobs** (bottom right) — project, job, task, completion time, duration.
  - Header clock, status bar with role/org/counts, footer with `[q] [r] [l]` bindings.
  - Auto-refresh every 5 seconds via a background worker thread.

**Endpoints used (role-aware)**

| Concern | DRSysAdmin path | admin@training path |
|---|---|---|
| Connectors | `realmManager/initializeOrganization` → `adminOrgManager/listConnectors` | `adminOrgManager/listConnectors` (direct) |
| Projects | `realmManager/listSystemUserProjectsByUserName` (all orgs) | `orgManager/listUserProjectsForAllOrgs` |
| Tasks | `projectManager/listTasks` per project; split by `dateCompleted` | same |

**New files**

- `dr_tui/__init__.py`, `__main__.py`
- `dr_tui/app.py` — `DRTUIApp`, `LoginScreen`, `DashboardScreen`
- `dr_tui/data.py` — sync API fetchers (`list_connectors`, `list_projects_sys`,
  `list_projects_org`, `collect_jobs`) invoked from Textual worker threads
- `dr_tui/app.tcss` — Textual stylesheet (lazygit-style borders, btop-style colors)

**Requirements**

- Adds `textual>=0.40.0` to `requirements.txt` and `setup.cfg`. Reinstall with
  `pip install -e .` to register the `dr-tui` console script.

**Smoke test (2026-05-11)**

End-to-end Textual `Pilot` test against 192.168.58.128: logged in as both
roles, dashboard rendered, Connectors panel populated with the 2 NFS
connectors in `training`, logout returned to the login screen cleanly.
SVG snapshot at `/tmp/dr_tui_dashboard.svg`.

---

## v0.03 — 2026-05-11

### Fixed: `locustfile_indexing.py` realigned to captured UI flow

Rewrote the indexing workflow against ground truth from the May 11 playwright
capture (`/tmp/dr_api_capture.json`, 211 calls). Previous version diverged from
real UI traffic in nine places — see `PLAN.md` Tasks 1, 9, 10.

#### Behavioural changes

- **Dynamic handle resolution (new `on_start`)** — connector handle, admin role
  handle, and template attribute IDs are now resolved via API at user startup
  (`adminOrgManager/listConnectors`, `orgManager/listRoles`,
  `orgManager/listTemplates`). Removes drift after `playwright_fresh_install.py`
  reruns the environment.
- **Job-completion polling rewritten** — replaced the `projectManager/getUpdateStatus`
  fixed-count loop with `taskManager/getTasks([taskHandle])` polling on
  `dateCompleted`. The `taskHandle` comes straight from the
  `corpusManager/createRepresentation` response — no `listTasks` needed. Two
  new env vars: `DR_INDEX_POLL_INTERVAL` (default 5s), `DR_INDEX_POLL_TIMEOUT`
  (default 600s). This resolves PLAN.md **Task 1** (monitoring endpoint) and
  obsoletes PLAN.md **Task 9** (representation_state SQL enum — no longer
  needed for per-workflow tracking; `helpers/monitor.py` still uses it for
  the global signal).
- **Project-scoped context** — dropped the spurious "initOrg→project" call;
  the captured flow passes `contextHandle=<projectHandle>` directly on
  `createDataArea` / `createCorpus` / `createRepresentation`.
- **Corpus-set lookup** — switched from `projectManager/listCorpusSets` to
  `corpusSetManager/getCorpusSetByName(corpusSetName="AllCorpora")`.
- **Indexing runs as org user**, not DRSysAdmin — admin@training has the
  needed permissions once added as Organization Administrator in
  `ecaManager/createCase`.
- **Deletion split across both users:**
  `orgManager/requestProjectDelete` (org token, `ctx=ORG_NAME`) →
  `realmManager/listDeletePendingProjects` (sys token, `ctx=SYS_ORG`) →
  `adminOrgManager/approveProjectDeleteRequest`. Replaces the previous
  `adminOrgManager/requestProjectDelete` + brittle stringified-match.
- **`IS_IMPORTED` attribute removed** from `createCase` body — not present
  in captured payloads.

#### Removed env vars

`DR_NFS_CONNECTOR_HANDLE`, `DR_ADMIN_ROLE_HANDLE`, and `DR_TEMPLATE_*` are no longer
read by `locustfile_indexing.py` — all resolved at runtime via `listConnectors` /
`listRoles` / `listTemplates`. These vars are still read by:

- `helpers/preflight.py` — `connector_uuid` check (`_check_connector` reads
  `DR_NFS_CONNECTOR_HANDLE` and verifies it appears in `listConnectors`).
- `tests/test_indexing_workflow.py` — pytest indexing test reads
  `DR_NFS_CONNECTOR_HANDLE`, `DR_ADMIN_ROLE_HANDLE`, and `DR_TEMPLATE_*`.

Leave them populated in `.env`; resync them after each `playwright_fresh_install.py` run.

#### Smoke test (2026-05-11)

`dr-load indexing -u 1 -d 90s` against 192.168.58.128 — **50 requests, 0 failures**,
3 complete project lifecycles (create → index → poll → delete → approve), 4 indexing
jobs reached `COMPLETE`. All nine v0.03 fixes exercised end-to-end.

#### Known fragility uncovered

- `helpers/preflight.py:_check_connector` calls `resp.json()` without first checking
  `resp.status_code`. If the upstream auth bounce returns HTML (HTTP 500) on the first
  call — which the captured browser flow also hits intermittently — the check fails with
  `Expecting value: line 1 column 1 (char 0)`. Workaround: re-run preflight; permanent
  fix is to add a status-code check before parsing.
- After `playwright_fresh_install.py` Phase R (deleteOrganization), the `training` org
  and `admin` user must be re-provisioned manually before the load test runs. See
  README §"After running `playwright_fresh_install.py`".

---

## v0.02 — 2026-05-08

### Added: `dr-load` CLI

A Typer-based command-line tool that wraps the Locust load tests with preflight checks,
orphan cleanup, background monitoring, and a merged report.

#### Commands

- **`dr-load preflight`** — Runs 6 environment checks (app reachable, auth, Postgres, NFS mount, log directory, connector UUID). Exits non-zero if any check fails.
- **`dr-load browsing`** — Runs the browsing load test (`locustfile.py`) headless with background log/job monitoring.
- **`dr-load indexing`** — Runs the full indexing workflow load test (`locustfile_indexing.py`) with orphan sweep before and after.

All commands read defaults from `.env` and accept `--users`, `--duration`, `--spawn-rate`, and `--report` overrides.

#### New Files

- `cli.py` — Typer CLI entry point (`dr-load = cli:app`)
- `helpers/monitor.py` — Background monitoring during Locust runs:
  - `LogWatcher` — tails `*.log` files in `DR_LOG_DIR`, collects ERROR/WARN/FATAL/Exception lines
  - `JobPoller` — polls `datamining_corpus_representation` in Postgres every `DR_POLL_INTERVAL` seconds, counts state 0→1 transitions (NONE→COMPLETE)
  - `Monitor` — owns both threads, produces a `MonitorResult` at `stop()`
- `helpers/preflight.py` — `run_preflight()` (6 checks) + `run_orphan_sweep()` (deletes stale `load-test-*` projects)
- `setup.cfg` — Installs package as `dr-load` console script; adds `py_modules = cli, config`

#### CLI-Specific Environment Variables

| Variable           | Default                    | Description                                |
|--------------------|----------------------------|--------------------------------------------|
| `DR_LOG_DIR`       | `/home/auraria/AHS/output` | App log directory to watch                 |
| `DR_POLL_INTERVAL` | `10`                       | Seconds between job-status DB polls        |
| `DR_REPORT_OUTPUT` | `dr_report.csv`            | Output path for the merged report CSV      |
| `DR_PG_DB`         | `auraria_mgmt`             | Postgres database name                     |
| `DR_PG_USER`       | `auraria`                  | Postgres user (peer auth via sudo)         |

#### Bug Fixed

- **`threading.Thread._stop()` name collision** — `LogWatcher` and `JobPoller` both subclass `threading.Thread`. Storing the stop signal as `self._stop` overwrote the thread's internal `_stop()` method, causing `TypeError: 'Event' object is not callable` on thread join. Fixed by renaming to `self._stop_event` in both classes.

---

## v0.01 — 2026-03-30

Initial release.

### Features
- **87 tests** across 10 test modules
- **pytest + requests** for functional API testing
- **Locust** load tests with 3 browsing personas + full indexing workflow scenario
- **Two user profiles**: system admin (DRSysAdmin) and org user (admin@training)
- **Rolling token management**: automatic capture and reuse of session tokens
- **Graceful skip handling**: tests skip cleanly on permission denied or server errors

### Test Modules
- `test_auth.py` — Session creation, login, version checks
- `test_ocr_report.py` — OCR Usage Report (mirrors Edge recording workflow)
- `test_status.py` — Realm status, system status, nodes, services, licenses
- `test_projects.py` — Project listing, users, groups
- `test_organizations.py` — Organization listing, org resources
- `test_connectors.py` — Connector listing and retrieval
- `test_billing.py` — Billing reports, storage reports
- `test_workflows.py` — End-to-end chained workflows
- `test_org_user.py` — Org-scoped user tests
- `test_indexing_workflow.py` — Full lifecycle: create project → NFS import → index → delete

### Load Test Scenarios
- `locustfile.py` — ReadOnlyUser, OCRReportUser, ProjectBrowser personas
- `locustfile_indexing.py` — Full indexing workflow under concurrent load

### Auth Protocol (reverse-engineered from browser traffic)
1. Login: `POST /realmManager/createSession` with HTTP Basic Auth + `userDeviceID` (UUID)
2. All calls: raw `sessionToken` as `Authorization` header (not Bearer/Basic)
3. Body: `contextHandle` + `systemScope: true` (not `drWsClientContext`)
4. Rolling tokens: every response returns a fresh token
