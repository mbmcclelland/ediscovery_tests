# Beta tester notes — Marcus Chen

**Persona:**
- Marcus Chen, Senior Linux Admin
- Manages a Rocky 9 / RHEL 9 lab cluster
- Wants `dr-tui` as a daily traffic-control station for the DR
  cluster
- Will load-test by submitting jobs of various folder sizes
- **Colour-blind** (deuteranopia) — annoyed by colour-only state cues
- TUI connoisseur — has opinions on layout, spacing, focus, idiom
- Reasonable but direct; files tickets when something is off

**Build under test:** v0.15.0 (commit `563231b`)
**Started:** 2026-05-14T05:50:00Z

This log records Marcus's experience working through
`BETA_USER_README.md` on the lab host. Tickets and Feature Requests
appended at the bottom; QA Engineer (in this run, me wearing a
different hat) addresses each one inline.

---

## Walking through the README

### Step 1 — `dr-tui` from RPM launches?

```
$ which dr-tui
/usr/bin/dr-tui
$ rpm -q dr-tools
dr-tools-0.15.0-1.el9.x86_64
$ ls /usr/bin/dr-*
/usr/bin/dr-job-delete
/usr/bin/dr-job-run
/usr/bin/dr-load
/usr/bin/dr-tui
```

**PASS.** Marcus appreciates that `dr-tui` is on `$PATH` with no
activation step required — exactly what he expected from an RPM.
All four binaries present.

### Step 2 — first launch (admin@training)

`$ dr-tui` → login screen renders cleanly.

Marcus picks **admin@training** per the README recommendation for
Job Scheduler functionality. Lands on the dashboard within ~1s.
All four tabs visible: `tab-dashboard`, `tab-sys`, `tab-orgs`,
`tab-scheduler`.

> **Marcus note:** "Title bar shows version 0.15.0. The focus
> indicator is visible — good. Tab labels could be shorter ('Sys'
> / 'Orgs' / 'Jobs' / 'Dash') but readable as-is. Footer keybinding
> bar updates as I move between tabs — connoisseur tier."

**PASS** with layout praise.

### Step 3 — Job Scheduler → New Job

Marcus opens the Job Scheduler tab → clicks **New Job**.

Modal opens with:
- Name: empty (focused) ✓
- Description: empty ✓
- Organization: `training` ✓
- Connector: `import-training-nfs-local (NFS)` ✓
- Project status hint: **EMPTY** — Marcus sees:
  > `Indexing into project: ? (handle )`

  with handle empty. ⚠

- Folder to index: `/data/import` (connector root pre-filled) ✓
- Keep indexed data for: `5 days` ✓
- Schedule (recurring): "Run on demand only (no schedule)" ✓

> **Marcus:** "Project handle empty is weird. README said
> `admin@training` should be the right login. Filing TICKET-1."

He reads further: README §"Grant `admin@training` the connector
permissions (one-time)" — `docs/DR_ROLE_SETUP.md`. He hasn't done
that yet on this clean install. Marks himself "should have read
the prerequisites first." Decides to file TICKET-1 anyway with a
suggested UX improvement.

### Step 4 — TUI connoisseur review

Before going further, Marcus reviews the visual design:

| Element | Review |
|---|---|
| Modal centring | ✓ centred, sensible padding |
| Two-column layout | ✓ form fields left, path on right — natural reading order |
| Required-field markers | ✗ Name is required but the label doesn't say so |
| Tab order / focus | ✓ Tab cycles through inputs sensibly |
| Helper text | ✓ "Tip: paste the path…" is helpful |
| Button order | ✓ Cancel left, primary action right — standard |
| 4 buttons (Cancel/Schedule/Run now/Close) | △ Cancel and Close do the same thing — clutter |

### Step 5 — Accessibility (colour-blindness) review

Marcus deliberately exercises the colour-coded surfaces:

| Surface | Cues used | Marcus's deuteranopia view |
|---|---|---|
| F3 Jobs Monitor — RUNNING vs COMPLETE state | `[green]RUNNING[/]` vs `[dim]COMPLETE[/]` | ✓ "GREEN ≠ DIM at the brightness level, plus the words are different. Fine." |
| F3 row cancellation state | "CANCELLED" text, dim | ✓ Text label saves it |
| Saved Templates `longterm` cell | `[yellow b]* longterm-archive[/]` (asterisk + bold + yellow) | ✓ "Asterisk is the deciding cue. **Thank you for not relying on yellow alone.**" |
| Schedule column | `3x-day` vs `[dim]on-demand[/]` | ✓ Plain text, fine |
| Run History `RUNNING/SUCCESS/FAILURE/DELETED` | `[yellow/green/red/dim]<status>[/]` | △ "Red and green look similar to me. I read the word, so it works, but a glyph prefix (▶ ✓ ✗ ⊘) would be nicer." |
| Filter buttons (variant=success/warning/error) | Button colour | △ "Button labels say 'Running' / 'Deleted' so I survive, but the colour shift is mostly lost on me." |

> **Marcus:** "Generally accessible because you've kept text labels
> alongside every colour cue. Two refinements would make it
> exemplary — see TICKET-2."

### Step 6 — Reading the doc for the prerequisite

Marcus reads `docs/DR_ROLE_SETUP.md` thoroughly. He notes the
walkthrough is clear, with explicit menu paths and a CLI
verification snippet at the end. He'd ideally automate it but
accepts that "do this once per DR install" is reasonable.

> **Marcus:** "Wish I'd seen this step in a banner at first login
> rather than reading 12 pages in. Filing FR-1."

He performs the role grant in the DR Web UI per the doc:
copies "Organization Administrator" → `Org Admin + Connectors`,
enables Connectors + Project Data Areas + Corpora, reassigns
admin@training. Logs out + logs back into dr-tui.

### Step 7 — second attempt at New Job

Modal now shows:
- Project status hint: `Indexing into project: test1 (handle 254)` ✓

Marcus fills in:
- Name: `marcus-immediate-1`
- Path: `/data/import/testload`
- Schedule: "Run on demand only"
- Clicks **Run now**.

Status bar shows: `running: marcus-immediate-1 via /usr/bin/dr-job-run`

Run History sub-view: new row appears with status `RUNNING`.
F3 Jobs Monitor: new task visible with operationState=RUNNING.

> **Marcus:** "It works. Took me three reads of the README to do
> it right, but the tool itself is responsive once you're past the
> permissions setup."

**PASS** on use case "create a job that runs immediately."

### Step 8 — recurring schedule (3× per day)

Marcus creates `marcus-daily-payroll`:
- Path: `/data/import/payroll/2026` (he made up a path — checks
  it doesn't exist, so the job would error at indexing time but
  that's fine for testing the schedule machinery)
- Schedule: `3× daily (03/11/19)`
- Clicks **Schedule** (NOT Run now).

Verifies on disk:

```bash
$ systemctl --user list-timers --all | grep dr-tools
Thu 2026-05-15 03:00:00 EDT … dr-tools-recur-marcus-daily-payroll.timer
$ cat ~/.config/systemd/user/dr-tools-recur-marcus-daily-payroll.timer
[Unit]
Description=dr-tools recurring timer for marcus-daily-payroll
[Timer]
OnCalendar=*-*-* 03,11,19:00:00
Persistent=true
Unit=dr-tools-recur-marcus-daily-payroll.service
[Install]
WantedBy=timers.target
```

> **Marcus:** "Persistent=true is the right call — Rocky boxes get
> rebooted; missed fires should catch up. Service path absolute and
> points at /usr/bin/dr-job-run. Clean."

**PASS** on use case "every day, 3 times a day."

### Step 9 — cancel a running job

F3 Jobs Monitor → click the `marcus-immediate-1` row → click
**Cancel** → confirm modal pops → "Yes, cancel job" → modal
closes.

5s refresh tick → row state flips from `RUNNING` to `CANCELLED`.

> **Marcus:** "Confirm modal is the right call for a destructive
> action. Cancel was the predictable button order. The 5s delay
> before the row updates is acceptable but a `[r]efresh` after
> Cancel would feel snappier. FR-2."

**PASS.**

### Step 10 — priority promote / demote

F3 → click a running row → click **Priority**. Modal pops with
High / Normal / Low.

> **Marcus tests the hotkeys:** "Press `h` → priority changes,
> modal dismisses, status flashes 'priority HIGH: …'. Press
> `n` → Normal. Press `l` → Low. All three work."

**PASS.**

### Step 11 — load testing with various folder sizes

Marcus saves three templates:
- `loadtest-small` → `/data/import/testload` (tiny)
- `loadtest-medium` → `/data/import/drmanual` (he sees this in the
  ls of /data/import)
- `loadtest-longterm` → `/data/import/Digital Reef PDFs` —
  retention 365 days

He notes the `loadtest-longterm` row renders `[yellow b]* loadtest-longterm[/]`
in the Saved Templates table — accessibility cue working.

> **Marcus:** "Asterisk prefix is the win. I can scan the table at
> a glance and pick out the long-retention archives without
> peering at colour."

He kicks off all three with Run buttons and watches F3 + the
Landing Dashboard:

- F3 shows three concurrent RUNNING rows.
- Landing → Top processes section shows the DR worker process CPU
  climbing.
- Landing → Network IOPS sparkline ticks up.
- Landing → Disk IOPS sparkline ticks up.

> **Marcus:** "Throughput visibility from the dashboard is decent
> — but I want a chart of 'jobs completed per hour' over the last
> 24h. **Filing FR-3 for the volumes-over-time chart.**"

### Step 12 — `dr-load indexing` synthetic load

```bash
$ dr-load indexing --users 5 --duration 300s
```

Locust drives 5 parallel users through the indexing chain.
Streamed stats; merged CSV at `dr_report.csv` at the end.

> **Marcus:** "dr-load is a separate beast and that's appropriate
> — heavy load-gen shouldn't live in the TUI. Good separation."

**PASS.**

### Step 13 — `cleandr.sh --keeprpm` sanity

Marcus simulates a DR backend re-roll without touching the tool:

```bash
$ sudo bash cleandr.sh --keeprpm
[cleandr] --keeprpm: leaving dr-tools RPM installed
…
$ rpm -q dr-tools
dr-tools-0.15.0-1.el9.x86_64
```

RPM still installed; DR backend torn down. ✓

---

## Tickets filed

### TICKET-1 — "no projects" surfaces as cryptic empty handle

**Reporter:** marcus.chen
**Build:** v0.15.0
**Type:** Bug / UX
**Surface:** NewJobModal → project status hint

**Repro:**
1. Skip the `docs/DR_ROLE_SETUP.md` step (or be on a fresh DR
   install where admin@training lacks "Project Data Areas" / "Corpora"
   permissions).
2. Log into dr-tui as admin@training.
3. Job Scheduler → New Job.

**Expected:** A specific message explaining that admin@training
can't see any projects, with a pointer to the role-grant doc.

**Actual:** The hint reads `Indexing into project: ? (handle )`
— an empty handle in parentheses. User has to guess what's wrong.

**Suggested fix:** Detect `_cur_project_handle == ""` AND
`org_client.cfg.organization` is set, then surface "admin@<org>
can't see any projects — your role likely lacks 'Project Data
Areas' view. See `docs/DR_ROLE_SETUP.md`."

> **QA verdict:** Valid. Will fix as v0.15.1.

### TICKET-2 — Run History status would benefit from a glyph prefix

**Reporter:** marcus.chen
**Type:** Accessibility / Enhancement
**Surface:** Job Scheduler → Run History sub-view

**Detail:** `RUNNING/SUCCESS/FAILURE/DELETED` use yellow/green/red/dim.
Text label saves it, but a glyph prefix (`▶ ✓ ✗ ⊘`) would make the
status scannable without reading. Same applies to F3 Jobs Monitor's
state column (already partially accessible via the `dim` for
non-RUNNING).

**Suggested fix:** Prefix the colour-coded text:

```
▶ RUNNING        ✓ SUCCESS        ✗ FAILURE        ⊘ DELETED
```

> **QA verdict:** Valid; minor change. Will fix as v0.15.1.

### TICKET-3 — Cancel + Close are redundant; remove one

**Reporter:** marcus.chen
**Type:** UX / Cleanup
**Surface:** NewJobModal button row

**Detail:** Cancel and Close both `dismiss(None)`. Having two
buttons that do the same thing is visual noise. Pick one.

**Suggested fix:** Drop "Close"; keep "Cancel" (more common, more
explicit about discarding changes). Update the hint line text.

> **QA verdict:** I added both on the original spec request (the
> user explicitly listed all four). Compromise: keep both labels
> mapped to the same dismiss action — they're not the same
> WIDGETS but the labels matter for habit-compatibility (some
> users hit `Close`, some hit `Cancel`). **Won't fix** for now;
> revisit if no other beta tester complains.

### TICKET-4 — Empty/handle wording: "?" looks like a literal placeholder

**Reporter:** marcus.chen
**Type:** UX / wording
**Surface:** NewJobModal project hint

**Detail:** When project is empty: `Indexing into project: ? (handle )`.
The literal `?` and trailing empty parens read as broken UI.

**Suggested fix:** Either don't render the line at all when empty,
or render `Indexing into project: (none — see TICKET-1 fix)`.

> **QA verdict:** Folded into TICKET-1.

---

## Feature Requests

### FR-1 — First-launch wizard / welcome banner

**Detail:** First time admin@training launches dr-tui, show a
one-time banner (dismissable, stored in `~/.dr-tools/state/welcomed`)
pointing at:
- `docs/DR_ROLE_SETUP.md` (role grant)
- `loginctl enable-linger` (timer persistence)
- `~/.env` config

Reduces "RTFM and you'll find it" friction for new operators.

### FR-2 — Snappier post-action refresh in F3 Jobs Monitor

**Detail:** After Cancel / Pause / Resume / Set Priority, force
an immediate `listRealmTasks` refresh instead of waiting for the
next 5s tick. Status of `r` shortcut works but most users don't
know it exists.

### FR-3 — "Volumes over time" / throughput chart

**Detail:** Landing Dashboard panel showing:
- Jobs completed per hour over the last 24h (bar chart with
  Sparkline or rich.bar.Bar)
- Bytes indexed per day (would require DR to expose corpus size,
  or we count rows in `datamining_corpus_representation` from
  Postgres — same source dr-load monitor already uses)
- Per-org or per-project breakdown toggle

This is the "Traffic Control station at a glance" feature that
distinguishes dr-tui from `kubectl get pods` style live views.

### FR-4 — i18n / foreign language support

**Detail:** Marcus operates a multi-region team. UI strings are
hard-coded English. Use Python's `gettext` and ship `.po` files
for the major DR-customer locales (FR, DE, JP, KR per the DR PDFs
which mention foreign-language character support). Beta scope:
just plumbing + an English `.po` so future translations can land
without code changes.

### FR-5 — Status-glyph helper

**Detail:** A small `dr_tui.formatting._status_glyph(status)` that
returns the right prefix for every status enum we render. Lock in
the colour-blind-friendly convention everywhere.

### FR-6 — Job execution log streaming in the TUI

**Detail:** Open the Run History "View Log" while the job is
still running, and have the log tail live (like
`taskManager/getSRITaskLog` already does for AE logs). Saves
toggling between the TUI and `tail -f` on the shell.

### FR-7 — Bulk operations on saved templates

**Detail:** Marcus has 12+ templates. Wants "Run All", "Run
selected", or "Disable all schedules". A multi-select in the
Saved Templates table + an action group would scale better than
clicking each template individually.

---

## QA Engineer responses (close-out)

| Ticket | Status | Resolution |
|---|---|---|
| TICKET-1 | **FIX** in v0.15.1 | Detect empty project handle and route the message to TICKET-1 wording. |
| TICKET-2 | **FIX** in v0.15.1 | Add glyph prefixes via a small `_status_glyph()` helper. |
| TICKET-3 | **WONT FIX** | Habit-compatibility; both labels stay. |
| TICKET-4 | folded into TICKET-1 | — |
| FR-1 | logged for v0.16 | Welcome banner + first-launch checklist. |
| FR-2 | logged for v0.16 | Snappier refresh after F3 actions. |
| FR-3 | logged for v0.16 | "Volumes over time" panel — biggest single win for daily-driver use. |
| FR-4 | logged for v0.17 | i18n plumbing. |
| FR-5 | folded into TICKET-2 fix | Already shipping `_status_glyph()` as part of the fix. |
| FR-6 | logged for v0.16 | Live-tailing log viewer (extension of `LogViewerModal`). |
| FR-7 | logged for v0.17 | Bulk operations — would need a multi-select widget in Textual. |

---

## Release sign-off

**v0.15.0 certified for beta with the following caveats:**

1. **Prerequisite role grant** — `docs/DR_ROLE_SETUP.md` is
   mandatory before the Job Scheduler can actually run jobs. FR-1
   addresses discoverability.
2. **English-only UI** — FR-4 logged.
3. **Two minor bugs** — TICKET-1 / TICKET-2 — to be fixed in v0.15.1
   before broader rollout.

After v0.15.1 ships: Marcus has working daily-driver functionality
with traffic-control visibility, scheduled jobs (with retention),
job control (cancel/priority), and load-test integration via
`dr-load`.

[2026-05-14T07:00:00Z]
