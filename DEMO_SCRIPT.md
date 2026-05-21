# dr-load v0.15 — 30-min Demo Script

**Audience:** Senior developers (you're a sysadmin presenting to engineers).
**Goal:** Walk the architecture, show the data plane in motion, invite critique.
**Length:** 30 min including Q&A.

This script is a run-of-show, not a script to read aloud. Use it as a
checklist with prompts in your own voice.

---

## Before you go on stage

Run these at least 30 minutes before the demo so the recorder has
accumulated real data your `report` can render against.

```bash
# 1. Pre-stage the demo store with ~8 min of real campaign data
./scripts/demo-prep.sh

# 2. Capture the four hero screens as backup .ansi files
./scripts/demo-capture.sh

# 3. Open these tabs in your editor
#    recorder/store.py
#    recorder/health.py
#    recorder/daemon.py
#    tests/test_recorder.py
#    BUG_LOG.md
#    ARCHITECTURE.md

# 4. Confirm terminal is 130×45 or larger so Rich tables render right
stty size                   # expect: 45 130 (or wider)

# 5. Confirm env is set
echo $DR_VERIFY_SSL         # expect: false
```

If something goes wrong on stage, replay any captured hero screen with:

```bash
cat /tmp/demo-captures/dashboard.ansi
cat /tmp/demo-captures/record-status.ansi
cat /tmp/demo-captures/report-mgmt.ansi
cat /tmp/demo-captures/report-capacity.ansi
```

---

## 0:00 — Framing (2 min)

> "I'm a sysadmin who got tired of babysitting Digital Reef soak tests
> in a terminal. I built this with Claude as a pair programmer and as
> an orchestrator for the QA, UX, RPM-packaging, and docs passes. The
> operational needs, the architecture decisions, the tradeoffs are
> mine. The Python is a partnership.
>
> I'll show you what we built, walk the code, and ask where I should
> have made different decisions."

Three honest things to lead with. The third one is what they'll
remember.

---

## 2:00 — The problem (3 min)

Tell the soak-test story in your own words.

| Beat | What to say |
|---|---|
| The pain | "Last quarter I needed to run a 72-hour load test against Digital Reef. The only thing watching it was me, in a terminal, hitting Ctrl-C every few hours to spot-check." |
| The gap | "When my manager asked how it went, I had log files, screenshots, and notes in a Google Doc. No throughput number. No reliability claim. No way to compare week-over-week." |
| The premise | "Phase A of `dr-load monitor` is a persistent recorder, a campaign event log, and a one-page report. Three commands and you have a Monday morning answer." |

---

## 5:00 — Live demo (8 min)

The narrative is: gate → start → annotate → report. Three hero screens.

### Hero #1 — the dashboard (2 min)

```bash
dr-load preflight
dr-load admin dashboard --rich --org training
```

What to point at:
- The four panels (running / scheduled / finished / projects)
- Brand colors (cyan for OK, yellow for warnings, midnight-blue headers)
- "This is what `dr-load admin` looked like before Phase A — it's
  still here, this is what an operator stares at during a manual run."

### Hero #2 — the recorder live state (2 min)

```bash
dr-load record status --rich --store /tmp/demo.db
```

What to point at:
- "Daemon's been running 10 minutes. 16 signals sampled per tick."
- The latest CPU / Mem / Disk / Docs-per-min rows
- The active campaign block
- The recent-events tail

### Mid-demo annotation (30 sec)

Show that an operator can write to the log live:

```bash
dr-load campaign event "audience asked about retention" --store /tmp/demo.db
```

### Hero #3 — the report (3 min, the payoff)

```bash
dr-load report --store /tmp/demo.db --audience mgmt
```

What to point at:
- The verdict line at the top — GREEN / YELLOW / RED + one-sentence reason
- The three framings: throughput, reliability, headroom
- "This is what goes to my manager on Friday. It's a Markdown file. I
  can re-render as CSV for capacity planning, or `--audience self` for
  raw operator metrics."

```bash
dr-load report --store /tmp/demo.db --audience capacity
```

---

## 13:00 — Code walk (12 min)

The audience is here for this. Put `ARCHITECTURE.md` on a side display
or open it in a tab.

### Architecture diagram (30 sec)

Point at the four-layer stack: front-ends → shared core → SQLite TSDB
→ recorder daemon → collectors.

"Three reads, one write. Everything else is a consumer of the store."

### File 1 — `recorder/store.py` (3 min)

Open the file. Scroll to:

1. **The schema** (top of file) — three tables, narrow long format.
   "One row per metric per tick. Easy to query, easy to roll up later."
2. **`Store.__init__` and `default_db_path()`** — graceful fallback
   `/var/lib` → `~/.local/share` → `/tmp`. "Tests can use the same code
   path as the systemd unit."
3. **`write_metrics` / `read_metric`** — the entire read+write API in
   ~20 lines.

**Ask the audience:**
> "Is SQLite the right TSDB choice? I picked it for portability — one
> file, no extra process, you can `cp` it to a laptop. What would you
> have used for months of data?"

### File 2 — `recorder/health.py` (2 min)

Open the file. Show:

1. **The `_classify` band function** — pure, no I/O, testable.
2. **The aggregate rule at the bottom** — moderate philosophy:
   green ≤1 degraded, yellow 2+, red 2+ critical OR indexing stalled.

**Honest weakness to surface:**
> "The indexing baseline is hardcoded at 100 docs/min. Phase E will
> track a rolling 1h baseline in the store. Is that the right approach,
> or would you derive baseline differently?"

### File 3 — `recorder/daemon.py` (3 min)

Open the file. Walk through the `Daemon.run()` method:

1. **Signal handlers** — SIGTERM/SIGINT call `self.stop`.
2. **Per-collector try/except** — a single collector failure doesn't
   take the daemon down.
3. **Lazy client re-login** — `_ensure_client` resets on transient API
   errors and re-logs in next tick.
4. **Interruptible sleep** — the daemon checks `self._running` every
   500ms so SIGTERM is responsive (not stuck in a 10s `time.sleep`).
5. **Health transition events** — only written on state change, not
   every tick.

**Ask the audience:**
> "Should this have been `async`/`await` instead of synchronous threads?
> I went synchronous because the collectors are inherently I/O-bound
> and the code is easier to debug. Tradeoff worth revisiting?"

### File 4 — `tests/test_recorder.py` (2 min)

Open the file. Scroll to:

1. **`TestStoreSchema` / `TestHealthDerivation`** — pure unit tests
   using `tmp_path`.
2. **`TestRecordPidPath`** — the regression test for BUG-1 (PID file
   collision).
3. **`TestReportNoData`** — the regression test for BUG-2 (empty-store
   false-GREEN).
4. The CLI-integration tests using `typer.testing.CliRunner`.

> "112 tests, no live server required. All ran in 47 seconds locally.
> The three bug-fix tests came in the closing pass — QA filed them,
> dev fixed them, regression tests prevent re-occurrence."

### The four-agent pipeline (90 sec)

```bash
git log --oneline -8
```

Walk the commit chain:

```
7703eff  chore: v0.15 RPM build + delete HANDOFF.md
5a6e828  fix(monitor): BUG-1/2/3
75475b5  docs(v0.15): tech-writer pass + API_DICTIONARY rewrite
51f2bd2  build(rpm): packaging spec + systemd unit + offline wheels
3191bf9  feat(monitor): unit tests + DR brand palette + style
25d1c05  docs(monitor): wire record/campaign/report into docs
cbf5a78  feat(monitor): Phase A — recorder + record/campaign/report
```

"Each commit is one agent or one feature. QA → UX → RPM → tech-writer
→ dr-developer for the bug-fix loop. Git is the audit trail."

---

## 25:00 — Discussion (5 min)

These are the questions you actually want answered. Bring a notepad.

1. **SQLite vs Prometheus/InfluxDB.** Right call for months-long
   single-host? Or are you giving up too much?
2. **Indexing baseline derivation.** Hardcoded fallback is wrong;
   what's the right shape?
3. **Retention.** Raw-forever today. Tiered roll-up (24h → 7d → 90d
   → 1y) is designed but unbuilt. Worth the complexity?
4. **Multi-host polling.** Single-SUT for now. When does that bite?
5. **Phase B Textual TUI.** Designed (4-round UX), unbuilt. Would
   you use a TUI, or just keep using `dr-load report` in CSV mode?

Close with:

> "I'm going to write down everything you tell me. Some of it I'll
> push back on; most of it I'll act on. Thanks."

---

## If the demo goes sideways

| What broke | What to do |
|---|---|
| `dr-load preflight` fails | Skip it. Say "trust me, it's green normally — let's keep moving." |
| `dashboard --rich` shows no projects | The org is empty. Run `dr-load admin create-project demo --org training --lifetime 5m` first. |
| `record status` shows STOPPED | Run `./scripts/demo-prep.sh` again, or fall back to `cat /tmp/demo-captures/record-status.ansi`. |
| `report` shows NO DATA | The pre-stage didn't run or `/tmp/demo.db` is empty. Fall back to `cat /tmp/demo-captures/report-mgmt.ansi`. |
| The whole VM is unreachable | Switch to the captures: `cat /tmp/demo-captures/dashboard.ansi`, etc. The narrative still works with images. |
| You forget a command | Open this file on your phone or a side terminal. It's the source of truth. |

---

## What you do NOT do

- ❌ Tour all 12 `admin` subcommands. Reference them by category, run two.
- ❌ Run `pytest tests/` live. 47 seconds of silence kills a demo. State the count and move on.
- ❌ Install the RPM on the demo VM live. Show `rpm -qpl ...x86_64.rpm | head` instead.
- ❌ Apologize for unfinished work. Phase B / D / E are *the roadmap*, not gaps.
- ❌ Read this file aloud. It's a checklist for you, not a script.
