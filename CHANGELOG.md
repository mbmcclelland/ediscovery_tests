# Changelog

## Release index

| Version | Date | Headline |
|---|---|---|
| [v0.17.7](#v0177--2026-05-14) | 2026-05-14 | DR_freshinstall.exp — `dr_ctl.sh status` path uses forward slashes (was backslashes; bash stripped them to `homeaurariaAHSbindr_ctl.sh`) |
| [v0.17.6](#v0176--2026-05-14) | 2026-05-14 | Logo swapped to user-supplied 7-line gradient; phase banner re-coloured bright-blue border + bold-yellow text |
| [v0.17.5](#v0175--2026-05-14) | 2026-05-14 | Reef-a-TUI logo regenerated at fivebyfive scale 0 — readable as REEF-A-TUI, single-line render even on narrow terminals |
| [v0.17.4](#v0174--2026-05-14) | 2026-05-14 | DR_freshinstall — Reef-a-TUI logo, ocean-depth gradient, bright-yellow subtitle, subprocess-streaming wrapper (bar stays pinned at the bottom while logs scroll above) |
| [v0.17.3](#v0173--2026-05-14) | 2026-05-14 | DR_freshinstall — pause progress bar during cleandr + installer (no more spinner spam during shell-subprocess phases) |
| [v0.17.2](#v0172--2026-05-14) | 2026-05-14 | DR_freshinstall — 4 QA-driven bug fixes: postgres-drop in cleandr, REST-readiness probe, virus-update timeout, error-log dedup |
| [v0.17.1](#v0171--2026-05-14) | 2026-05-14 | DR_freshinstall — Rich progress bar, file logging, help-by-default + destructive-op confirmation gate |
| [v0.17.0](#v0170--2026-05-14) | 2026-05-14 | **`DR_freshinstall.py`** — one-shot REST-based fresh-install driver (replaces cleandr+expect+playwright sequence) |
| [v0.16.0](#v0160--2026-05-14) | 2026-05-14 | NewJobModal — **connector tree-browser is back** (FR-8), works for both DRSysAdmin and admin@org |
| [v0.15.3](#v0153--2026-05-14) | 2026-05-14 | Documentation overhaul + new **API Programming Guide** for future Claude sessions |
| [v0.15.2](#v0152--2026-05-14) | 2026-05-14 | **api_client no longer auto-injects `systemScope: true`** — fixes the core PERMISSION_DENIED that blocked the whole Job Scheduler chain |
| [v0.15.1](#v0151--2026-05-14) | 2026-05-14 | Beta-tester fixes — glyph prefixes on status cells (accessibility) + actionable empty-project message |
| [v0.15.0](#v0150--2026-05-14) | 2026-05-14 | NewJobModal — manual path Input (drops file-tree) + recurring schedules via systemd user timers |
| [v0.14.10](#v01410--2026-05-14) | 2026-05-14 | NewJobModal — pre-emptive org-admin warning + clearer Browse error translation |
| [v0.14.9](#v0149--2026-05-14) | 2026-05-14 | explore_connector uses project_handle as contextHandle (PROJECT_NOT_ACTIVATED fix) |
| [v0.14.8](#v0148--2026-05-14) | 2026-05-14 | NewJobModal file tree uses org-admin client; explore_connector re-raises APIError so PERMISSION_DENIED is visible |
| [v0.14.7](#v0147--2026-05-14) | 2026-05-14 | set_* fetchers re-read after write (set-endpoint responses don't echo persisted state) |
| [v0.14.6](#v0146--2026-05-14) | 2026-05-14 | dr-job-run / dr-job-delete use org-admin login (DRSysAdmin denied by DR permission model) |
| [v0.14.5](#v0145--2026-05-14) | 2026-05-14 | dr-job-run pre-flight + actionable "binary missing" error; RUNBOOK §4b |
| [v0.14.4](#v0144--2026-05-13) | 2026-05-13 | Documentation overhaul — QA handover (README, Workflow Guide, new QA Test Plan + Runbook, Release index) |
| [v0.14.3](#v0143--2026-05-13) | 2026-05-13 | NewJobModal connector dropdown — `initializeOrganization` per org |
| [v0.14.2](#v0142--2026-05-13) | 2026-05-13 | Connectors view — visible empty state + error messages |
| [v0.14.1](#v0141--2026-05-13) | 2026-05-13 | NewJobModal UX rework — 5-day default, 4 explicit buttons, plain labels |
| [v0.14.0](#v0140--2026-05-13) | 2026-05-13 | Job Scheduler per-view actions + log viewer + timer toggle + lingering banner |
| [v0.13.2](#v0132--2026-05-13) | 2026-05-13 | Dashboard log — escape user-controlled text before `RichLog.write` |
| [v0.13.1](#v0131--2026-05-13) | 2026-05-13 | NewJobModal — fix Org→Connector→folder auto-flow |
| [v0.13.0](#v0130--2026-05-13) | 2026-05-13 | Job Scheduler tab + `dr-job-run` / `dr-job-delete` + systemd retention timers |
| [v0.12.0](#v0120--2026-05-13) | 2026-05-13 | Realm Settings edit modals (mail / splash / pwpolicy / inactivity) |
| [v0.11.0](#v0110--2026-05-12) | 2026-05-12 | Jobs Monitor v2 — single-call `listRealmTasks` + type filter + live AE log |
| [v0.10.2](#v0102--2026-05-12) | 2026-05-12 | dr-tui terminal compatibility — PuTTY + legacy SSH clients |
| [v0.10.1](#v0101--2026-05-12) | 2026-05-12 | Jobs Monitor — Pause / Resume / Cancel / Set Priority wired live |
| v0.10.0 | (rolled into v0.10.1) | F3 Jobs Monitor modal — realm-wide jobs + history |
| v0.09 | — | F2 documentation side-pane — DR PDFs as built-in TUI help |
| v0.08.1 | — | Realm Settings sub-tree (read-only) |
| v0.08 | — | System Settings (advanced) endpoint capture + reference doc |
| v0.07.1 | — | Connector capture + Deactivate button |
| v0.07 | — | RPM packaging + `install.sh` for self-contained distribution |
| v0.06 | — | TUI tabbed layout + CRUD modals (depots, users, groups, virus) |
| v0.05 | — | Initial TUI hierarchical tree views |
| v0.04 and earlier | — | dr-load CLI + Locust load tests + pytest functional suite |

Click a version to jump to its entry. Each entry names the endpoints
touched, files changed, and pilot test added (if any). For
feature-by-feature **expected behaviour** see
[`docs/QA_TEST_PLAN.md`](docs/QA_TEST_PLAN.md). For **symptom →
fix** lookups see [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

---

## v0.17.7 — 2026-05-14

### Fixed: `dr_ctl.sh status` path uses forward slashes

User screenshot at the tail of phase 2:

```
[root@digitalreef tmp]# \home\auraria\AHS\bin\dr_ctl.sh status
    │  bash: homeaurariaAHSbindr_ctl.sh: command not found
```

**Root cause:** `DR_freshinstall.exp` line 53 had the path written
with backslashes — `\\home\\auraria\\AHS\\bin\\dr_ctl.sh`. Tcl's
`send --` rendered each `\\` as `\`, then bash received
`\home\auraria\AHS\bin\dr_ctl.sh`. Bash strips `\` as an escape
character before non-special chars (so `\h` → `h`, `\a` → `a`),
producing the meaningless `homeaurariaAHSbindr_ctl.sh`.

(The companion `\\cp -v ...` on line 51 is *correct* — `\cp` is bash's
"bypass alias" syntax and we genuinely want a single `\` in front
of `cp` to ensure we hit the real binary, not whichever `cp -i`
alias is set in the user's profile.)

**Fix:** Replaced backslashes with forward slashes:
`/home/auraria/AHS/bin/dr_ctl.sh`. The install itself was never
affected — `dr_ctl.sh status` runs AFTER the installer finishes and
drd has been restarted, so the only consequence pre-fix was a
cosmetic "command not found" line at the very tail of phase 2's
streamed output. Post-fix the user sees the actual drd status
breakdown.

**Files:**

- `DR_freshinstall.exp` — line 53 path corrected
- `__version__.py` → 0.17.7
- CHANGELOG.md (this entry).

---

## v0.17.6 — 2026-05-14

### Changed: user-supplied logo (`newreef-a-tui.go`) + Digital-Reef colour tweaks

User dropped a hand-crafted 7-line REEF-A-TUI logo at
`/root/newreef-a-tui.go` with a smooth blue→light-grey gradient.
Imported it verbatim:

- **Logo files** — `reef-a-tui-logo.go` is the user's file
  byte-for-byte; `reef-a-tui-logo.txt` is the ANSI-stripped plain-text
  extraction (7 lines × 110 cols max). The Python `_LOGO_COLORS`
  palette mirrors the seven `rgb(R,G,B)` stops baked into the Go
  source.
- **Phase banner colours** — border swapped from magenta → bright
  blue; title text from bold magenta → bold yellow. The bright-blue
  border now contrasts with the cyan run-config panel above it, so
  the eye picks out the phase header immediately.

The ocean-depth metaphor from v0.17.5 (blue → white → black) is
retired in favour of the user-supplied palette, which is a smooth
single-direction blue→light-grey gradient — like looking *up* through
clear water toward the surface.

Visual preview (130-col terminal, ANSI stripped):

```
██████████                            ████              ██████████              ██████████  ██      ██  ██████
██      ██                            ██                ██      ██                  ██      ██      ██    ██
██      ██  ██████████  ██████████  ██████              ██      ██                  ██      ██      ██    ██
██████████  ██      ██  ██      ██    ██    ██████████  ██████████  ██████████      ██      ██      ██    ██
██    ██    ██████████  ██████████    ██                ██      ██                  ██      ██      ██    ██
██      ██  ██          ██            ██                ██      ██                  ██      ██      ██    ██
██      ██  ██████████  ██████████    ██                ██      ██                  ██      ██████████  ██████
    Digital Reef Fresh Installer version 0.17.6

╭──────────────────────────────────────────────╮    ← bright-blue border
│ Phase 2 — DR installer (DR_freshinstall.exp) │    ← bold yellow text
╰──────────────────────────────────────────────╯
```

**Files:**

- `reef-a-tui-logo.go` — replaced by user's `newreef-a-tui.go`
- `reef-a-tui-logo.txt` — regenerated from the new .go
- `DR_freshinstall.py::_LOGO_COLORS` — 5-stop → 7-stop palette
- `DR_freshinstall.py::_phase_banner` — `border_style="bright_blue"`,
  text `style="bold yellow"`
- `__version__.py` → 0.17.6
- CHANGELOG.md (this entry).

Not yet validated against a live destructive run — user has an
in-progress install at v0.17.5, the v0.17.6 colour changes will
be visible on the next destructive cycle.

---

## v0.17.5 — 2026-05-14

### Changed: regenerated Reef-a-TUI logo so the letters are actually legible

**Symptom (user):** the v0.17.4 logo (built with `bit "Reef-a-TUI"`
defaults — `-scale -1` 0.5×) packed every letter into a 3-column
glyph; the text was unreadable.

**Fix:** Regenerated with `bit -font fivebyfive -scale 0 "Reef-A-TUI"`.
Same five-line vertical footprint as before (no extra screen real
estate), but each letter is now ~10 columns wide and clearly
distinguishable. Sample on a 110+ col terminal:

```
████████    ██████████  ██████████  ██████████            ██████            ██████████  ██      ██  ██████
██      ██  ██          ██          ██                  ██      ██              ██      ██      ██    ██
████████    ████████    ████████    ████████    ██████  ██████████  ██████      ██      ██      ██    ██
██    ██    ██          ██          ██                  ██      ██              ██      ██      ██    ██
██      ██  ██████████  ██████████  ██                  ██      ██              ██        ██████    ██████
```

→ R · E · E · F · - · A · - · T · U · I

The ocean-depth blue→white→black gradient and bold-yellow product
subtitle from v0.17.4 are unchanged. Logo file
(`reef-a-tui-logo.txt`) plus its bit-Go reference (`reef-a-tui-logo.go`)
both refreshed.

**Side fix:** logo lines now use `no_wrap=True` + `crop=False` +
`overflow="ignore"` so a terminal narrower than the logo lets the
overflow clip naturally rather than wrapping each line into two
visual rows (which had shattered the letters mid-glyph in narrow
SSH sessions). On 80-col terminals the right edge clips
cleanly; on 110+ cols the full logo shows.

**Files:**

- `reef-a-tui-logo.txt` — regenerated
- `reef-a-tui-logo.go` — regenerated (bit reference)
- `DR_freshinstall.py::_render_logo` — Rich print kwargs
- `__version__.py` → 0.17.5
- CHANGELOG.md (this entry).

---

## v0.17.4 — 2026-05-14

### Added: Reef-a-TUI logo with ocean-depth gradient + subprocess-streaming wrapper

Two visual upgrades that work together: the start-banner now opens
with a five-line ASCII-art **Reef-a-TUI** logo (generated by
`bit "Reef-a-TUI"` and saved to `reef-a-tui-logo.txt`) coloured top
to bottom in a Digital-Reef ocean palette, followed by the spec'd
bold-bright-yellow product subtitle **`Digital Reef Fresh Installer
version <X.Y.Z>`**. The version is read live from `__version__.py`
so the subtitle never falls out of sync.

**Ocean-depth palette (top→bottom, "Blue White Black"):**

| Row | Colour | Meaning |
|---|---|---|
| 0 | `rgb(50,130,220)` | surface blue (sky reflected on water) |
| 1 | `rgb(150,200,240)` | shallow / foam edge |
| 2 | `rgb(255,255,255)` | white foam (the breaker) |
| 3 | `rgb(70,90,130)` | deep blue-grey (light fading) |
| 4 | `rgb(10,20,40)` | abyssal (near-black with a hint of blue so it stays visible on a black terminal) |

**Subprocess-streaming wrapper (`_stream_subprocess`):**

Replaces the v0.17.3 pause/resume hack. Instead of pausing Rich's
progress bar during the long subprocess phases (cleandr's
`rm -rfv` flood, the InstallAnywhere installer's dialogs, drd's
systemd debug stream), v0.17.4 streams every subprocess line
through `console.print()`. Rich's `Live` underpinning the
`Progress` automatically routes those prints **above** the live
region — so the progress bar stays **pinned at the bottom** of
the visible output while logs scroll cleanly above it.

Each subprocess line is prefixed with a dim `│` so the user can
visually distinguish "subprocess output" from "driver status"
without losing any text:

```
    │ /home/auraria/AHS/utils/importvalidator/normalization.sh
    │ removed directory '/home/auraria/AHS/utils/importvalidator'
    │ [cleandr] dropping postgres DB: auraria_mgmt
    ✓  teardown complete  (32.4s)
    ┃━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┃
    ⠋ Phase 2 — DR installer (DR_freshinstall.exp)  2/15 • 0:00:33
```

Plus the bonus: subprocess output is now also captured in the
`/tmp/dr-freshinstall-<TS>.log` file at DEBUG level (one
`subproc:` entry per line), so post-mortem debugging has every
shell line in the audit trail.

**Files:**

- `reef-a-tui-logo.txt` (NEW) — the plain-text ASCII art from
  `bit "Reef-a-TUI"`. Source of truth; we apply the gradient at
  render time.
- `reef-a-tui-logo.go` (NEW) — the bit-generated reference
  (24-bit-coloured `fmt.Println` lines) — kept for the curious /
  for regen.
- `DR_freshinstall.py` — `_render_logo()`, `_LOGO_COLORS`,
  `_LOGO_PATH`, `_VERSION` constant (read from `__version__.py`),
  `_stream_subprocess()`. `phase_clean` + `phase_installer` switch
  from `subprocess.run` to `_stream_subprocess`. The
  v0.17.3 `_pause_progress` / `_resume_progress` helpers stay in
  the file as a fallback but are no longer called.
- `__version__.py` → 0.17.4
- CHANGELOG.md (this entry).

### Test plan

- `--dry-run --skip-clean --skip-installer` — logo + yellow
  subtitle render; phase 3 walks 13 steps; green SUCCESS panel.
- `--skip-clean --skip-installer --keep-existing` against live DR
  — same as above, but real API calls; bar refreshes smoothly.
- Full destructive `--force` run — terminal output shows
  subprocess lines prefixed with `│`, progress bar **stays at
  the bottom of the frame** with "Phase 1 — Teardown" /
  "Phase 2 — DR installer" / "Phase 3 — API provisioning" rolling
  through as the description.

---

## v0.17.3 — 2026-05-14

### Fixed: Rich progress bar redraws spammed the terminal during phases 1 + 2

**Symptom** (reported by the beta user during their own destructive run):
phases 1 (cleandr) and 2 (installer) produce hundreds of duplicate
bar-lines in the terminal scroll-back / captured log. Each line is the
same Rich progress bar, only the spinner glyph (`⠏ ⠦ ⠴ ⠼ ⠹ …`) and the
elapsed time tick forward:

```
[===============================================================================
Installing...
-------------
 [==================|==================|==================|==================]
⠏ Phase 2 — DR installer (DR_freshinstall.exp) ━━━━━╺━━━━━...  2/15 • 0:02:51
⠦ Phase 2 — DR installer (DR_freshinstall.exp) ━━━━━╺━━━━━...  2/15 • 0:02:51
⠴ Phase 2 — DR installer (DR_freshinstall.exp) ━━━━━╺━━━━━...  2/15 • 0:02:52
[…hundreds more…]
```

**Root cause:** Rich's `Progress` refreshes 8 times per second
(`refresh_per_second=8`). The renderer normally overwrites the previous
bar in-place via `\r`. But when a long subprocess (cleandr's `rm -rfv`
flood, or the InstallAnywhere installer's `[========]` progress + drd's
systemd debug-level output) is streaming its OWN stdout in parallel,
every Rich refresh lands on a NEW last line — the subprocess output
keeps pushing it down. 8 Hz × ~9-minute installer = ~4 000 duplicate
bar-lines.

**Fix:** Pause Rich's live renderer (`_progress.live.stop()`) before
each subprocess call (`bash cleandr.sh`, `expect -f
DR_freshinstall.exp`), resume it (`.live.start()`) after. The
subprocess output now flows cleanly without competing for the last
row, and the progress bar reappears for phase 3 (REST provisioning)
where we own all the output. Wrapped in helpers
`_pause_progress()` / `_resume_progress()` for clarity.

**Files:**

- `DR_freshinstall.py` — new `_pause_progress` / `_resume_progress`
  helpers; `phase_clean()` and `phase_installer()` wrap their
  `subprocess.run` calls in try/finally pause/resume blocks.
- `__version__.py` → 0.17.3
- CHANGELOG.md (this entry).

### Test plan

To verify when convenient (NOT during an active destructive run):
- Phase 3 alone (`--skip-clean --skip-installer`) — bar should still
  refresh smoothly at 8 Hz; one bar line per terminal row, no
  duplication.
- Full destructive run (`--force`) — terminal output during phase 2
  should show ONLY the InstallAnywhere progress markers, no Rich
  redraws. The bar reappears at "Phase 3 — API provisioning".

---

## v0.17.2 — 2026-05-14

### Fixed: 4 QA-driven bug fixes after end-to-end test pass

QA Engineer (Jordan Park persona) ran the full TC1-TC13 test plan
against v0.17.1 with a Dev/QA ping-pong: QA opened tickets, Dev
fixed, QA re-tested in the same session. All 4 tickets closed,
sign-off recommended SHIP. See `QA-DR_freshinstall-v0171.md` for
the full test log with per-TC evidence.

**Issues found and fixed (severity → headline → fix):**

| # | Severity | Issue | Fix |
|---|---|---|---|
| QA-v0171-1 | Medium | Errors printed twice (stderr stream + Rich console) | Dropped the stderr stream handler in `_setup_logging`; file log unaffected |
| QA-v0171-2 | **Critical** | `changeUserPassword` returned HTTP 500 because phase 3 raced wildfly's webapp deploy; uncaught `requests.HTTPError` printed a Python traceback | (a) `wait_for_drd()` adds a REST-readiness probe — POSTs to `createSession`, accepts any non-5xx OR a 5xx whose body mentions `digitalreef` (= structured DR error → handler is alive). (b) `main()` broadened to `except Exception` so HTTP errors produce a clean FAILURE panel |
| QA-v0171-4 | **Critical** | `cleandr.sh` left the 4 DR postgres DBs in place; second install's `mgmtcustomeruser` table was empty, so `changeUserPassword` failed with "User does not exist" even when `getCurrentUser` returned the user | Extended `cleandr.sh` to drop `auraria_mgmt`, `auraria_admin`, `auraria_activemq`, `dr_history` after the filesystem teardown so the installer fully reinitialises them |
| QA-v0171-5 | Medium | `trigger_virus_update()` timed out at 30s — the FIRST call on a fresh install does the inaugural virus-DB sync synchronously (~45-60s) | Bumped that call's timeout to 120 s, matching the storage-depot pattern |

**End state verification (TC12):**

```
DRSysAdmin / password         ← login OK
admin@training / password     ← login OK, sees 3 connectors
training org                  ← exists
localDocStorage @ /data/docstorage   localIndexStorage @ /data/indexstorage
system depot assigned         inactivity = 99 min
import-training-nfs-local    READ        /data/import
export-training-nfs-local    READWRITE   /data/export
archive-training-nfs-local   READWRITE   /data/archive
pda-training-archive (PROJECT)  xda-training-export (EXPORT)
```

**Files:**

- `dr_tui/data.py` — `trigger_virus_update` gets `timeout=120`
- `cleandr.sh` — new postgres-drop block after the filesystem teardown
- `DR_freshinstall.py` — REST-readiness probe in `wait_for_drd`,
  broadened exception catch in `main()`, dropped stderr stream
  handler in `_setup_logging`
- `__version__.py` → 0.17.2
- `QA-DR_freshinstall-v0171.md` — NEW QA report (4 tickets opened+
  closed in-session, sign-off SHIP)
- CHANGELOG.md (this entry).

### Test coverage

- 15/15 pilot tests still pass against the freshly-provisioned DR
- Full TC4 end-to-end destructive run completed cleanly (~10 min wall
  clock: cleandr 30 s, installer ~9 min, API phase 30 s)
- TC5 idempotent recovery completes in 3.9 s with every step
  correctly skip-or-fast-pass

---

## v0.17.1 — 2026-05-14

### Added: progress bar, file logging, and a help-by-default safety gate on `DR_freshinstall.py`

Quality-of-life pass on the v0.17.0 driver. No new functionality —
same 13 API steps, same shell phases — but the UX is now legible
instead of being a wall of plain text.

**Highlights:**

- **Rich progress bar** — single global `rich.progress.Progress`
  spans all phases. The bar shows `Phase X — <name>` or `Step N
  — <title>` as it advances, plus elapsed time and an M/N
  completion counter. Refresh rate 8 Hz so it's smooth without
  burning CPU. `--no-progress` (or non-TTY stdout) disables it
  cleanly — useful for CI logs where the carriage-return tricks
  garble the output.
- **File logging** — every action is mirrored into
  `/tmp/dr-freshinstall-<TIMESTAMP>.log` at DEBUG level, with
  ISO-8601 timestamps. Override with `--log-file`. Stderr stream
  handler honours `--log-level` (default INFO) or `--verbose`
  for full DEBUG flow. Post-mortem debugging now has a full
  audit trail instead of "what did the screen say again?"
- **Per-step timing** — `_ok()` now appends `(0.2s)` to the
  success line so slow phases (e.g. NFS storage provisioning,
  which can run 30-60s) are visible to the eye, not just the
  log. Total wall clock also reported in the final summary.
- **Help by default** — running with no args used to silently
  start the destructive default flow. Now prints help and exits
  0. Matches the convention of `kubectl`, `helm`, etc. — modal
  tools shouldn't default to destruction.
- **Destructive-op confirmation gate** — running with phase 1
  (cleandr) or phase 2 (expect installer) requested now needs
  EITHER `--force` OR an interactive `YES` (uppercase) at a
  Rich-styled red-bordered warning panel. Non-TTY stdin without
  `--force` aborts cleanly. Catches the "rogue CI pipeline
  nukes the lab" failure mode.
- **Rich panel banners** — start banner shows target, phases,
  mode, and log file location in one boxed view. End banner is
  a green SUCCESS or red FAILURE panel with credentials, log
  path, and next-step command. The visual delta between SUCCESS
  and FAILURE is obvious at a glance.

**Flags added (10 → 16):**

| Flag | Purpose |
|---|---|
| `--force` | bypass the destructive-op y/n prompt |
| `--no-progress` | disable the live progress bar |
| `--log-file PATH` | override default `/tmp/dr-freshinstall-*.log` |
| `--log-level LEVEL` | DEBUG / INFO / WARNING / ERROR (default INFO) |
| `--verbose`, `-v` | shortcut for `--log-level=DEBUG` |

**No-args invocation now safe:**

```bash
$ python DR_freshinstall.py
# Prints help + exits 0. Old behaviour: started ripping things up.
```

**Verified:**

- `--dry-run --skip-clean --skip-installer` runs all 13 API steps
  in dry-run, progress bar increments visibly, summary panel green.
- `--skip-clean --skip-installer --keep-existing --no-progress`
  against live install: 15/15 step ticks, per-step timing
  visible, full log written.
- `--skip-installer --skip-api < /dev/null` (non-TTY without
  `--force`) aborts cleanly with a specific error message.
- All 15 pilot tests still pass.

**Files:**

- `DR_freshinstall.py` — refactored argparse (4 argument groups
  for readability), new `_setup_logging`, `_setup_progress`,
  `_advance_progress`, `_phase_banner`, `_confirm_destruction`,
  `_show_help_and_exit`, `_NullContext`. All user-facing helpers
  (`_ok` / `_info` / `_warn` / `_fail` / `_skip` / `_step`) now
  emit to both the logger and the Rich console.
- `__version__.py` → 0.17.1
- CHANGELOG.md (this entry).

---

## v0.17.0 — 2026-05-14

### Added: `DR_freshinstall.py` — end-to-end REST-based fresh-install driver

Replaces the three-script sequence

    bash cleandr.sh
    expect -f DR_freshinstall.exp
    python playwright_fresh_init.py     # browser-driven, slow, needs Chromium

with a single Python entry point that talks to DR over REST. The
cleandr + installer steps are still done via the existing shell/expect
scripts (kept for "what exactly does this delete?" auditability) but
the post-install provisioning runs entirely through `dr_tui/data.py`
helpers — no Playwright, no Chromium download, no mitmproxy capture.

**What it does (13 steps, mirroring the user's spec verbatim):**

1. Login as DRSysAdmin with default `DRSysAdmin`, change to `password`
2. Create document storage at `/data/docstorage`
3. Create index storage at `/data/indexstorage`
4. Create the system storage depot pointing at the index storage
5. Trigger virus-definitions update
6. Set the logon inactivity timeout (default 99 minutes)
7. Create the `training` organization
8. Create `admin@training` as Organization Administrator (auto-clears
   the forced-change flow by logging in once + changing pw to `password`)
9. Add DRSysAdmin to `training` as Organization Administrator
10. Create the read-only IMPORT NFS connector @ `/data/import`
11. Create the read-write NFS connector @ `/data/export`
12. Create the read-write NFS connector @ `/data/archive`
13. Create PROJECT data area on the archive connector + EXPORT data
    area on the export connector

**Flags:**

| Flag | Purpose |
|---|---|
| `--skip-clean` | don't run cleandr.sh |
| `--skip-installer` | don't run the expect-driven `.bin` reinstall |
| `--skip-api` | clean + install only |
| `--keep-existing` | idempotent mode — every API step skips if target already exists |
| `--keeprpm` | passed through to cleandr.sh |
| `--dry-run` | print every action without doing it |
| `--hostname HOST` | DR host (default 192.168.58.128) |
| `--nfs-host HOST` | NFS server fqdn (default = `--hostname`) |
| `--inactivity-minutes N` | session timeout (default 99) |
| `--initial-password PW` | DRSysAdmin's first-install pw (default `DRSysAdmin`) |
| `--final-password PW` | final pw after change (default `password`) |

**Endpoint discovery technique:** the body shapes for the previously-
unwrapped endpoints (`createSystemStorageDepot`, `createOrganization`,
`addSystemUserToOrg`, etc.) came from grepping the deployed
`ediscovery.war`'s `main.js` JS bundle for
`[a-zA-Z]+Manager/[a-zA-Z]+` references, then inspecting the
surrounding call site for the body shape. Documented in
`docs/API_PROGRAMMING_GUIDE.md` §13.

**New helpers in `dr_tui/data.py`:**

| Function | Endpoint |
|---|---|
| `change_user_password()` | `userManager/changeUserPassword` |
| `create_system_storage_depot()` | `realmManager/createSystemStorageDepot` |
| `create_organization()` | `realmManager/createOrganization` |
| `list_org_roles()` | `orgManager/listRoles` |
| `create_org_user()` | `orgManager/createUser` |
| `add_system_user_to_org()` | `adminOrgManager/addSystemUserToOrg` |
| `create_nfs_connector()` | `orgManager/createNFSConnector` |
| `create_data_area()` | `orgManager/createDataArea` |

### Verified

- `--dry-run` passes cleanly through all 13 steps.
- `--keep-existing` against the live install correctly identifies
  every pre-existing object by name OR by export path (so a
  renamed storage depot is still recognised), and actually creates
  the missing pieces (connectors + data areas) on the existing
  `training` org.
- Full fresh-install end-to-end run completed: cleandr → installer
  → all 13 API steps succeed.

### Files

- **NEW** `DR_freshinstall.py` (~580 lines, self-contained driver)
- `dr_tui/data.py` — 8 new fresh-install helpers (~250 lines)
- `__version__.py` → 0.17.0
- CHANGELOG.md (this entry + release-index row)

---

## v0.16.0 — 2026-05-14

### Added: connector tree-browser in the New Indexing Job dialog (FR-8)

The v0.15.0 build dropped the file-tree browser from `NewJobModal` and
replaced it with a manual path Input — at the time, under the (wrong)
theory that `connectorManager/exploreConnector` was permanently broken
for default DR installs. v0.15.2's `systemScope` fix proved that wrong:
the endpoint works fine for any logged-in user who has been granted
org-context (DRSysAdmin via `realmManager/initializeOrganization`;
admin@&lt;org&gt; via login). v0.16.0 wires the tree back into the modal
and verifies it for both account types live.

**Highlights:**

- **Tree widget** is back in `#newjob-tree-wrap`. Lazy expansion via
  `on_tree_node_expanded` calls `explore_connector` in a worker
  thread, so the UI stays responsive even on slow NFS mounts. A
  `loading…` placeholder appears the moment a node is expanded and
  is replaced when the API returns.
- **Path Input is preserved** as an editable mirror beneath the tree
  (per the user's "keep it" answer to the design question). Tree
  clicks auto-fill the Input; the user can still paste a deep path
  from the Web UI's breadcrumb. The new `on_input_changed` handler
  keeps `self._cur_path` synced both ways — a typed value always
  wins over the last tree-click.
- **Status glyphs** (`▸ 🗀` for collapsed folders, `▾ 🗀` for
  expanded, `🗎` for files, `⚠` for errors) work on monochrome
  terminals and pass deuteranopia accessibility (Marcus Chen's
  beta-tester request). Selection is shown on a dedicated
  `#newjob-selected` line — no colour dependency.
- **Error surface** is precise: `on_tree_node_expanded` traps both
  `APIError` (code + extended_status) and bare exceptions; failures
  appear as a red `⚠ <code>: <detail>` chip *on the failing node*
  AND as a full message in `#newjob-error` with actionable hints
  ("If you see PROJECT_NOT_ACTIVATED, the project handle is being
  passed where the org name should go — see API_PROGRAMMING_GUIDE
  §5 + §13").
- **DRSysAdmin support** — `NewJobModal._is_sys_session()` detects a
  super-system client and calls `ensure_org_context(client, org)`
  before each `exploreConnector`, so DRSysAdmin no longer falls
  back to the empty-results / PERMISSION_DENIED path. Verified live
  against DR 5.5.3.2 on 2026-05-14: both DRSysAdmin and
  admin@training return 12 entries under `/data/import` and can
  descend further.

**Fixed:**

- `explore_connector()` — the v0.14.9 `contextHandle = project_handle`
  rule was empirically wrong for sessions that haven't pre-activated a
  project in the Web UI. Live test showed DRSysAdmin gets
  `PROJECT_NOT_ACTIVATED Project 0 not activated` when we pass the
  project handle, but the org name works for both account types.
  Switched to `ctx = org_name or project_handle`. The `project_handle`
  parameter is kept for backward compatibility (and audit trail) but
  no longer drives the request. Long docstring update with the live
  evidence and the no-good `ecaManager/selectProject` workaround
  (it 500s).
- Removed `_warn_if_not_org_admin()` — the yellow banner was always
  shown for DRSysAdmin sessions even though v0.15.2 made DRSysAdmin
  work for the Job Scheduler. Replaced with the helper `_is_sys_session`
  that's used internally (no banner, no clutter).
- `_sch_collect_then_open` comment block in `app.py` updated — the
  v0.14.8 "DRSysAdmin gets PERMISSION_DENIED" rationale was historical.
- Stale v0.14.8 docstring on `explore_connector` rewritten with the
  v0.15.2 + v0.16.0 reality.

### Changed

- CSS — `#newjob-selected` gets `height: auto` + `margin-bottom: 1`
  for a tidy line between the Tree and the path Input.

### Files

- `dr_tui/app.py` — `NewJobModal.compose`, `on_mount`, `on_select_changed`,
  `on_input_changed` (new), `_reload_tree` (new), `on_tree_node_expanded`
  (new), `_fetch_and_fill` (new), `_tree_fill` (new), `_tree_show_error`
  (new), `on_tree_node_selected` (new), `_set_selected_label` (new),
  `_is_sys_session` (new), `_warn_if_not_org_admin` (removed).
  Also: `_sch_collect_then_open` rationale comment refreshed.
- `dr_tui/data.py` — `explore_connector` docstring rewritten;
  `ctx = org_name or project_handle`.
- `dr_tui/app.tcss` — `#newjob-selected` rule added; `#newjob-tree`
  comment updated.
- `tests/test_dr_tui_scheduler.py` — new
  `test_newjob_modal_v016_tree_browser` exercising mount, connector
  switch, manual-edit override.
- `__version__.py` — `0.16.0`.

### Test coverage

- 33/33 pilot tests pass.
- Live verification on DR 5.5.3.2 (192.168.58.128):
  - DRSysAdmin: `ensure_org_context` → `list_connectors` (1 connector)
    → `explore_connector` root (12 entries) → nested browse (12).
  - admin@training: `list_connectors` (1) → `explore_connector` root
    (12) → nested browse (12).
- Both account types get identical results — confirming the v0.15.2
  systemScope fix + the v0.16.0 contextHandle correction generalise.

### Docs

- `CHANGELOG.md` — this entry + release index row.
- `docs/API_PROGRAMMING_GUIDE.md` — §7 connector subsection updated
  with the contextHandle correction; §12 TUI patterns gets a new
  "lazy-loading Tree pattern" subsection.

---

## v0.15.3 — 2026-05-14

### Changed: documentation overhaul after the v0.15.2 systemScope discovery

No code changes. All documentation reflowed to account for v0.15.2's
finding that the role-grant prerequisite was never actually needed.

**New:**

- **`docs/API_PROGRAMMING_GUIDE.md`** — comprehensive API doc
  targeted at a future Claude session implementing a new feature.
  Covers architecture, the EDiscoveryClient wrapper, authentication
  lifecycle, `contextHandle` semantics, the systemScope pitfall (in
  depth with the diagnostic procedure), DR's permission model, every
  endpoint family with body shapes + examples, recipes for composing
  features, async-task / SRI handling, quirks + anti-patterns, the
  five-step recipe for adding a new endpoint, threading rules for
  the TUI, debugging recipes, and a code map. ~14 sections, ~580
  lines. Cross-linked from the README Documentation Map as the
  "★ Read first when adding a new feature" entry.

**Updated:**

- `DR_Workflow_Guide.md` — added §10 "The systemScope pitfall
  (v0.15.2) — and a reusable diagnostic recipe" with the mitmproxy
  reverse-proxy / byte-diff technique. §9.6 "follow-ups worth
  remembering" expanded from three to four entries (the fourth is
  the systemScope auto-inject).
- `docs/RUNBOOK.md` — new §4f covering the v0.15.2 systemScope root
  cause + how to diagnose if it recurs after a regression. §4c
  (`dr-job-run` PERMISSION_DENIED) and §4e (Connectors role grant)
  flagged as **HISTORICAL** since they're no longer the right
  diagnosis after v0.15.2.
- `docs/DR_ROLE_SETUP.md` — deprecation banner at the top: not
  required for default installs anymore. Kept for the rare case of
  custom security-hardening roles.
- `BETA_USER_README.md` — Step 4 ("Grant admin@training the
  connector permissions") replaced with a "skip unless on v0.15.1
  or earlier" note. Known-issues list updated to reflect v0.15.1/2
  fixes.
- `docs/QA_TEST_PLAN.md` — environment-setup section notes the
  role-grant prereq is gone.
- `README.md` — Documentation Map gets the API Programming Guide as
  a ★ entry. Quick-links-by-role adds a "future Claude session"
  entry pointing at the API guide. DR_ROLE_SETUP entry annotated
  *(Historical)*.

All eight markdown files cross-link cleanly (verified
programmatically — no broken `.md` links). 19/19 pilot tests still
pass.

## v0.15.2 — 2026-05-14

### Fixed: api_client no longer auto-injects `systemScope: true`

This is the **root cause** of every `PERMISSION_DENIED` we've fought
since QA-14 (NewJobModal file tree empty), QA-16 (admin@training also
denied), QA-17 (Web UI worked but our REST didn't), and every dead-end
in between.

**Discovery:** mitmproxy capture of a working Web UI browse session
(reverse-proxy mode on port 8091, so no cert install needed) revealed
that Firefox's `exploreConnector` request and ours had **byte-for-byte
identical bodies** — except ours had an extra `"systemScope": true`
field that the Web UI never sends.

```diff
  POST /ediscovery/rest/connectorManager/exploreConnector
  {
    "requestHandle": null,
    "contextHandle": "training",
-   "systemScope": true,        ← we injected this
    "connectorType": "NFS",
    "connectorName": "import-training-nfs-local",
    ...
  }
```

DR's `SecureObjectInterceptor` treats `systemScope: true` as a
declaration that the caller is acting in super-system mode, which
requires the IT Administrator role's super-system permissions —
permissions that **don't include `exploreConnector`** in DR 5.5.3.2.
Without `systemScope` (or with `systemScope: false`), DR uses the
caller's org-context role, which DOES allow exploreConnector for
DRSysAdmin after `initializeOrganization(training)`.

**Code change:** `helpers/api_client.py` line 147–149. Removed the
unconditional `"systemScope": True` from the auto-built base body.
Endpoints that genuinely need `systemScope: true` (Realm Settings —
get/setMailServerConfig, getPasswordPolicy, etc.; F3 actions —
cancelTask; realm-wide reads — listJobs, listRealmTasks; etc.)
already pass it explicitly in their `extra_body` — 34 call sites
verified.

**Live verification after fix (DRSysAdmin):**

```
$ explore_connector(training, "import-training-nfs-local", "/data/import")
12 entries
  🗀 Dave White Collected Hard Drive 2023-07-24
  🗀 deletedcustomerstorage
  🗀 Digital Reef PDFs
  🗀 drmanual
  🗀 prod
  🗀 testload
  ...

$ orgManager/createDataArea(project=254, connector=…, path=/data/import/testload)
OK — handle 00003994fc7a11c0b4954993a3137fa5c7df2d40
```

**Both** the browse path AND the indexing-chain submit (createDataArea)
now succeed for DRSysAdmin — meaning Run-Now and scheduled jobs both
unblock too, with no DR-side role configuration needed.

This also makes the elaborate role-config workaround documented in
`docs/DR_ROLE_SETUP.md` **no longer required**. Kept the doc as a
reference but the prereq is gone.

19/19 pilot tests still pass.

Credit: the user's "DRSysAdmin can browse in the Web UI but the tool
can't — let me show you" insistence + mitmproxy reverse-proxy
capture is what cracked this open. RTFM the wire.

## v0.15.1 — 2026-05-14

### Fixed: two beta-tester findings — accessibility + empty-project wording

From the v0.15 beta walkthrough (see `BETA-Marcus-Chen-20260514.md`):

**TICKET-2 (accessibility):** every status cell — F3 Jobs Monitor
state column, Job Scheduler Running-Jobs sub-view, Run History
status — now renders with a leading glyph prefix in addition to the
colour. The colour-blind beta tester (deuteranopia) confirmed the
text labels saved the cue, but adding a glyph makes the table
scannable without reading every word.

```
▶ RUNNING        (was "[green]RUNNING[/]")
✓ SUCCESS        (was "[green]SUCCESS[/]")
✗ FAILURE        (was "[red]FAILURE[/]")
⊘ DELETED        (was "[dim]DELETED[/]")
⊘ CANCELLED      (was "[dim]CANCELLED[/]")
‖ PAUSED         (was "[dim]PAUSED[/]")
```

Implemented as a single `_status_glyph(status)` helper at module
top, used everywhere a status enum is rendered. UTF-8 required (all
recommended terminals — Tabby, Windows Terminal, iTerm2, GNOME
Terminal — support these glyphs).

**TICKET-1 (UX):** `NewJobModal._refresh_project_status` no longer
renders `Indexing into project: ? (handle )` when the org admin
can't see any projects. New wording:

```
No projects visible to your account in organisation 'training'.
Most likely cause: your role lacks the 'Project Data Areas - View'
permission. See `docs/DR_ROLE_SETUP.md` for the one-time Web UI grant.
```

Yellow header line + dim explanation; surfaces the exact role-grant
prereq the beta user spent three README reads to discover.

**TICKET-3 (Cancel + Close redundancy):** WONT FIX — both labels
preserved for habit-compatibility (original spec listed all four
button labels explicitly).

19/19 pilot tests still pass.

## v0.15.0 — 2026-05-14

### Changed: NewJobModal — manual path Input + recurring schedules

Two changes that together turn the Job Scheduler from "works if your
DR install grants exploreConnector permission" into "works regardless,
matches the proven `locustfile_indexing.py` pattern, and supports
cron-style recurrence".

**1. Drop the file-tree browser.** v0.13 / v0.14 wrapped the modal
around `connectorManager/exploreConnector` with a lazy-loading Tree
widget. In DR 5.5.3.2 that endpoint is denied to both
"IT Administrator" and the default "Organization Administrator" role
(QA-14 + QA-16 findings). Replaced with a plain Path Input pre-filled
with the connector's root path. User types or pastes the subpath
they want indexed. Mirrors what `locustfile_indexing.py` does — same
endpoint chain (`listConnectors → createDataArea →
createCorpus → createRepresentation`), no browse step. Removed:
`Tree`, `_action_browse`, `_action_count`, `_load_children_blocking`,
`_apply_children`, `_count_blocking`, and the `Re-browse` / `Count
files` buttons. Net code reduction: ~150 lines.

**2. Recurring schedules via systemd user timers.** New
`JobDefinition.schedule: str` field. NewJobModal gained a "Schedule
(recurring)" Select with the presets:

| Preset | OnCalendar expression |
|---|---|
| Run on demand only (default) | `""` (no timer) |
| Hourly | `hourly` |
| Daily (midnight) | `daily` |
| 3× daily (03/11/19) | `*-*-* 03,11,19:00:00` |
| 4× daily (00/06/12/18) | `*-*-* 00,06,12,18:00:00` |
| Weekdays 09:00 | `Mon..Fri *-*-* 09:00:00` |
| Weekly | `weekly` |
| Monthly | `monthly` |

Scheduler tab dispatch: on Schedule / Run Now, if `job.schedule != ""`
the parent screen calls `drsch.schedule_recurring_job()` which writes
`~/.config/systemd/user/dr-tools-recur-<slug>.{service,timer}` and
`systemctl --user enable --now`s it. Unlike retention one-shots,
these timers carry `Persistent=true` so missed fires (host was off)
catch up at the next opportunity. Editing the saved template's
schedule to "Run on demand only" calls
`drsch.unschedule_recurring_job()` to remove the timer.

`list_dr_timers()` now picks up both `dr-tools-retention-*` and
`dr-tools-recur-*` timers so they all show in the Retention Timers
sub-view. (FR candidate for v0.16: split that sub-view into
"Recurring schedules" and "Retention timers" — they're conceptually
different.)

**Saved-templates table accessibility tweak.** `longterm`-substring
match now renders with both `[yellow b]` bold AND a leading `* `
asterisk marker (e.g. `* nightly-longterm-archive`) so the cue isn't
colour-only — needed for colour-blind users. Beta-user persona for
v0.15 release certification is colour-blind by design.

**Tests:** updated `test_newjob_modal_v0141_defaults_and_buttons` and
`test_longterm_substring_match` for the new widget id + asterisk
marker. 19/19 pilot tests pass.

## v0.14.10 — 2026-05-14

### Changed: NewJobModal — pre-emptive org-admin warning + clearer Browse error

User-reported after v0.14.9: "you can't browse the directory, and the
connection to the host seems to fail." Diagnosis:

- The TUI session was DRSysAdmin only — `org_client` was None because
  the `admin@training` user is missing in this DR install (the
  ongoing environmental finding from QA-3).
- The modal silently fell back to the sys client.
- DRSysAdmin doesn't have permission for `connectorManager/exploreConnector`
  (DR's permission rules tightened between v0.07 and v0.14 — the
  current realm rejects DRSysAdmin's IT-Administrator role here,
  even though the v0.07 capture worked with the same role).
- DR's async SRI worker reports the failure as
  `PROJECT_NOT_ACTIVATED Project 0 not activated` instead of
  `PERMISSION_DENIED` (server-side quirk — depends on whether the
  sync permission check or the async worker rejects first). The
  user-visible error sounded like a connection / project-config
  problem, not a permission one.

Two UX improvements (no permission-model code change — that's a real
DR server-side constraint we can't bypass):

1. **`on_mount` pre-emptive warning.** New
   `_warn_if_not_org_admin()` runs at modal open. If
   `_client.cfg.organization == "super_system_customer"` (i.e. the
   modal is using the DRSysAdmin session), it writes a yellow banner
   into `#newjob-error` immediately:

   > ⚠ This modal is using a DRSysAdmin session. Browse / Count /
   > Save all require an org-admin login (e.g. admin@training). Log
   > out and log back in as the org admin before scheduling a job.

2. **Translated Browse error.** The PERMISSION_DENIED /
   PROJECT_NOT_ACTIVATED branch in `_load_children_blocking` now
   renders an actionable explanation pointing to org-admin login
   and (if needed) `python playwright_fresh_init.py`, with the
   original error code in dim parentheses for debugging:

   ```
   Browse failed: not enough permission to browse this connector.
   (PROJECT_NOT_ACTIVATED:  Project 0 not activated)
   This DR install requires an org-admin login (e.g. admin@training)
   for browsing. Log out and log back in as the org admin, or ask
   an operator to run python playwright_fresh_init.py if the admin
   user doesn't exist yet.
   ```

19/19 pilot tests still pass.

## v0.14.9 — 2026-05-14

### Fixed: NewJobModal "Browse failed: PROJECT_NOT_ACTIVATED Project 0 not activated"

User-reported during post-v0.14.8 testing: clicking a folder in the
New Job file tree now surfaces (instead of silently failing — good
news) but with `PROJECT_NOT_ACTIVATED Project 0 not activated`.

**Root cause** found by walking the captured proxy sessions:
`connectorManager/exploreConnector` accepts two `contextHandle`
patterns:

| contextHandle value | When it works |
|---|---|
| Org name (`"training"`) | Only immediately after `realmManager/initializeOrganization` — and even then, only for sessions that the server tags with a "current project" via earlier UI clicks |
| **Project handle** (`"254"`) | **Always works for org-admin sessions** — this is what the v0.10+ captures consistently send |

The org-name path is fragile: when the org-admin session has no
active project, the server defaults to project 0 and raises
`PROJECT_NOT_ACTIVATED`. The Web UI gets around this by activating a
project before the user can reach the connector browser; our TUI
doesn't go through that flow.

**Fix.** `dr_tui/data.py`:

- `explore_connector()` gains a new `project_handle: str = ""` kwarg.
  When supplied, it's used as `contextHandle` instead of the org name.
  Falls back to org name for callers that don't have a project context
  yet (preserves the early-init use case).
- `count_files_recursively()` accepts the same kwarg and threads it
  through every recursive `explore_connector` call.

`dr_tui/app.py`: `NewJobModal._load_children_blocking` and
`_count_blocking` now pass `self._cur_project_handle` (the auto-picked
first project of the chosen org) through to both fetchers.

19/19 pilot tests still pass.

## v0.14.8 — 2026-05-14

### Fixed: NewJobModal file tree silently empty for DRSysAdmin

**Found during QA-14** (third bug found in the v0.14.4 handover pass).
The NewJobModal connector dropdown populated correctly (v0.14.3 fix)
but clicking on the file tree to expand a folder did nothing — no
entries, no error.

**Root cause confirmed live.** `connectorManager/exploreConnector` is
**org-admin scoped**, just like the indexing chain (QA-8 / v0.14.6).
DRSysAdmin raises `PERMISSION_DENIED`. Our `explore_connector()`
fetcher caught all `APIError` and returned `[]`, so the permission
failure looked identical to "this directory is empty".

**Code changes:**

- `dr_tui/app.py` — `_sch_collect_then_open()` now prefers
  `self.app.org_client` when present (set during DRSysAdmin login by
  the existing dual-login path) and passes that to `NewJobModal` as
  `api_client`. Org data gathering (list_orgs, list_connectors,
  list_projects) still uses the broader sys client since those
  endpoints accept DRSysAdmin after `initializeOrganization`.
- `dr_tui/data.py` — `explore_connector()` no longer swallows
  `APIError`; it re-raises. Caller (the modal) catches and surfaces
  the specific error.
- `NewJobModal._load_children_blocking()` — on `APIError`, writes the
  error code + extended status into the `#newjob-error` line, and on
  `PERMISSION_DENIED` specifically appends "log in as an org admin
  (admin@<org>) to browse connector folders."

**Why this matters even when org_client is present.** DR's permission
model is: list operations (listConnectors, listProjects) are open to
DRSysAdmin after `initializeOrganization`; *content* operations
(exploreConnector, createDataArea, createCorpus, createRepresentation,
deleteCorpus, deleteDataArea) are org-admin-only. The Job Scheduler
tab's New Job + Run + Retention Delete flows ALL hit content
endpoints — so a working Job Scheduler session requires either:

- Logging in as `admin@<org>` directly (org_client only); OR
- Logging in as DRSysAdmin AND the implicit org-admin co-login at
  startup succeeded (`app.org_client is not None`).

If neither works, the modal now tells the user exactly why and what
to do.

19/19 pilot tests still pass.

## v0.14.7 — 2026-05-14

### Fixed: set_* fetchers re-read after write — set responses don't echo persisted state

**Found during QA-11** of the v0.14.4 handover pass. Calling
`set_password_policy(client, policy=PasswordPolicy(enforce_strong=True,
min_length=12, ...))` and inspecting the return value showed
`enforce_strong=False, min_length=0` — but a subsequent
`get_password_policy()` confirmed the write actually persisted
correctly.

**Root cause confirmed against the live API.** The DR endpoint
`setPasswordPolicy` returns the field keys in its response, but the
values are all zeros / false regardless of what was actually
persisted:

```
setPasswordPolicy response keys: ['enforceStrongPasswords',
    'minimumLowercaseLetters', 'minimumNumbers',
    'minimumPasswordLength', ...]
  enforceStrongPasswords: false      ← lies
  minimumPasswordLength:  0          ← lies
  ...

getPasswordPolicy response:
  enforceStrongPasswords: true       ← actual persisted state
  minimumPasswordLength:  12         ← actual persisted state
```

Same pattern observed in `setSplashMessage` (returned `enabled: false`
while the persisted state was `enabled: true`). `setMailServerConfig`
was masked by a fallback-to-input value in our code, but the same
unreliability applies.

**Fix:** all three `set_*` fetchers in `dr_tui/data.py` now do a
follow-up `get_*` call and return THAT as the canonical persisted
state. `set_inactivity_timeout` already returned the input value
verbatim (the endpoint is 204 No Content) so it was already correct.

**Affected callers**

The TUI side `_settings_write_blocking` triggers `_load_view(...)`
after a successful save, which already re-fetches the leaf — so users
saw the correct state in the TUI even on the buggy build. The bug
mainly affected programmatic users of `dr_tui.data.set_*` and any
future caller that trusted the return value directly.

**Pilot tests:** unchanged. The offline pilot fixtures don't drive
the live `set_*` round-trip; this was a live-API bug visible only
during the handover smoke test.

## v0.14.6 — 2026-05-14

### Fixed: dr-job-run / dr-job-delete now use the org-admin login

**Found during QA-8** (second stopper in the v0.14.4 handover pass).
After v0.14.5 unblocked the binary-not-found issue, the indexing
chain failed with HTTP 500 on `orgManager/createDataArea`. AHS server
log: `User drsysadmin does not have permission to perform
createDataArea operation`.

**Root cause confirmed via DR documentation.** The official 5.5.3.1
PDF "Add or Edit a Project Data Area" states:

> **Requires Organization - Project Data Areas - Add/Edit Permissions.**
> Users in a role with the appropriate permissions can add a new
> Project Data Area…

The indexing chain (`createDataArea` / `createCorpus` /
`createRepresentation`) is gated by an **Organization-scoped** role,
not a System-scoped one. DRSysAdmin doesn't have it. The
`locustfile_indexing.py` reference implementation already uses an org
token for these calls — `dr-job-run` and `dr-job-delete` did not.

**Code change:**

- `dr_tui/cli_jobrun.py` — replaced `_login_drsysadmin()` with
  `_login_for_job(job_org)`, which builds an `EDiscoveryClient` from
  `OrgUserConfig()` (reads `DR_ORG_USERNAME` / `DR_ORG_PASSWORD` /
  `DR_ORG_ORGANIZATION` from `~/.env`). Warns if the job's `org` doesn't
  match the configured org admin's organization.
- `dr_tui/cli_jobdel.py` — same swap; `deleteCorpus` / `deleteDataArea`
  are the inverse of the create chain and share its permission
  requirement.

Both CLIs now surface a specific actionable error if the org-admin
user doesn't exist:

```
FAIL org-admin login: 500 — does the org-admin user (training)
exist? Run `python playwright_fresh_init.py` to (re)create it.
```

19/19 pilot tests still pass — the change only touches the CLI login
path; the data layer + TUI are unchanged.

## v0.14.5 — 2026-05-14

### Fixed: dr-job-run pre-flight + actionable error when binary missing

**Found during QA-8** of the v0.14.4 handover pass: invoking
`dr-job-run` on a host whose venv pre-dates the v0.13.0 setup.cfg
changes raises a `FileNotFoundError`, which the TUI's `_sch_run_now`
worker silently buried in a generic `run error: …` status line. The
underlying cause is that `pip install -e .` only regenerates console
scripts at install time, so a stale editable install never gets the
`dr-job-run` / `dr-job-delete` entry points even when the code is
present.

**Code change:** `_sch_run_now` now pre-flights `os.path.exists(bin_path)`
before spawning the subprocess worker and posts a specific actionable
message:

```
dr-job-run binary missing — re-run `pip install -e .`
(or `make rpm` + reinstall). Looked at <path>.
```

Same hardening on the `FileNotFoundError` branch (kept as a belt for
the case where `shutil.which` succeeds but the binary is removed
mid-session) — it now also tells the user to re-run the install.

**New runbook entry:** RUNBOOK §4b ("dr-job-run or dr-job-delete 'not
found'") documents the root cause, the fix, and the v0.14.5 detection
behaviour.

No new pilot test — the failure is environmental and the new pre-flight
branch only fires when the binary genuinely doesn't exist.

## v0.14.4 — 2026-05-13

### Changed: documentation overhaul for QA Engineer handover

No code changes; documentation only. Targeted at a QA engineer taking
ownership of the test plan, but the same docs are useful for any
developer onboarding to the codebase.

**README.md**

- Refreshed the TUI overview section: now describes all four tabs
  (Landing, System Settings, Organizations, Job Scheduler) with the
  current state of each, instead of stopping at v0.06.
- Documented the F3 Jobs Monitor modal's v0.11 behaviours (single-call
  `listRealmTasks`, operation-type filter, per-task `L` log viewer).
- Rewrote the **Job Scheduler tab** section to reflect v0.14.1 UX
  (5-day default, four buttons, plain-English labels) and the v0.14.3
  connector-dropdown fix.
- Refreshed **Project Structure** to include `scheduler.py`,
  `cli_jobrun.py`, `cli_jobdel.py`, `help_content/`, the new
  `endpoints_v0.08.md`, and the three TUI pilot test files.
- Added a **Documentation Map** section at the bottom listing every
  markdown file in the repo with role-based "quick links" (QA → here,
  on-call → there).
- Added a **TUI pilot tests** subsection under the pytest section —
  these run in ~12 seconds and catch most regressions, so they should
  be in every release-candidate workflow.

**CHANGELOG.md**

- Added a **Release index** table at the top listing every version
  with a one-line headline and a clickable anchor. Lets QA scan the
  release history without reading every entry.

**DR_Workflow_Guide.md**

- Added §9 "Feature additions v0.08 → v0.14 (concise reference)"
  covering Realm Settings (read v0.08 / edit v0.12), the F2 doc
  pane, F3 Jobs Monitor v2, Connector capture + Deactivate, and the
  Job Scheduler tab + companion CLIs.
- §9.6 captures three "mistakes worth remembering" (v0.13.1
  Select-auto-pick, v0.13.2 markup escape, v0.14.3
  initializeOrganization) — the patterns most likely to be repeated
  by a regression.
- §9.7 documents the **markup safety rule** for `RichLog` /
  markup-enabled `Static` widgets.

**docs/QA_TEST_PLAN.md (new)**

Structured handover for QA. Covers:

1. Environment — base URL, test users, persistent state, log
   locations.
2. **10-minute smoke test** with 10 explicit pass/fail steps.
3. **Feature matrix** — every shipped feature mapped to surface,
   pilot test, and changelog entry.
4. Detailed test scenarios for: storage depots, realm settings edit
   modals, F3 Jobs Monitor actions, **NewJobModal end-to-end**,
   retention timers, connectors view, dr-load functional + indexing.
5. Known limitations (API-side gaps and workarounds).
6. Regression areas — ordered by how often each is touched.
7. Filesystem map.
8. Bug report template.

**docs/RUNBOOK.md (new)**

Symptom-driven troubleshooting cookbook. Eight sections:

- §1 `dr-load preflight` failures
- §2 `dr-tui` won't launch / crashes
- §3 Connectors view empty — the v0.14.3 root cause with a live
  reproduction script
- §4 Retention timer didn't fire — full diagnostic chain
- §5 Pilot tests failing
- §6 Where to look when something is "off"
- §7 Quick-reference commands
- §8 Escalation procedure

All five updated markdown files cross-link cleanly (verified
programmatically — no broken `.md` links).

## v0.14.3 — 2026-05-13

### Fixed: NewJobModal connector dropdown — initializeOrganization per org

User report: 'Try to use the UI to create a job. Name the job
testjob-001, and use the training organization. Then click connectors
and see that no connectors appear. Click re-browse and it says no
connector chosen.'

Root cause confirmed against the live API: DRSysAdmin's session starts
in `super_system_customer` context, where
`adminOrgManager/listConnectors` returns an **empty list silently**
(no error, just `connectors: []`). The org context has to be switched
via `realmManager/initializeOrganization` before each per-org list
call, mirroring the pattern in `_client_for_org()`.

`_sch_collect_then_open()` — which gathers the org→connector map the
NewJobModal renders — wasn't doing the context switch. So:

  Org dropdown: training       ✓ (populated from listOrganizations)
  Connector dropdown: (empty)  ✗ (listConnectors returned [])
  Re-browse: "Pick an org + connector first" ✗
  Count files: same ✗
  Save: "Connector not selected" ✗

Fix: in `_sch_collect_then_open`, when `role == ROLE_SYS`, call
`drdata.ensure_org_context(client, org)` before each
`list_connectors(client, org)`. Org-scoped users (admin@<org>) skip
the switch since their session is already pinned.

Verified end-to-end against the live `training` org:

  orgs visible to DRSysAdmin: ['training']
    training: 1 connector(s)
      - name='import-training-nfs-local' type=NFS
        handle=0000ecde48788120...
  Modal Select option count: 1
  _cur_conn_handle post-mount: 0000ecde4878812053604308ac25ef767566612e

19/19 pilot tests pass.

If you're still seeing the **Organizations tab → Connectors leaf** show
zero rows after this update (a separate code path that already calls
ensure_org_context via `_client_for_org`), the v0.14.2 inline status
line should now tell you specifically why — either "Loading…" stuck,
a row count, an empty-state hint, or the actual error.

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
