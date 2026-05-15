"""dr_tui.scheduler — Job-Scheduler persistence + systemd user-timer helpers.

State layout under `~/.dr-tools/`:

    jobs/<slug>.json        — saved JobDefinition (template; persists)
    runs/<slug>.jsonl       — append-only run log (corpus/data-area handles
                              + task handle + timestamps per execution)
    logs/<slug>-<ts>.log    — captured stdout/stderr of one dr_job_run

Retention deletes are scheduled as systemd user units under
`~/.config/systemd/user/`:

    dr-tools-retention-<slug>-<run_id>.service
    dr-tools-retention-<slug>-<run_id>.timer

The `.timer` fires once via `OnCalendar=` at the absolute time the
retention window elapses; the `.service` invokes `dr_job_delete`. Both
unit names include the run_id so a single saved job can have multiple
in-flight runs with independent retention clocks.

systemd-user requires `loginctl enable-linger <user>` to keep the user
manager running across logout (otherwise the timer dies the moment the
user logs out). README documents this; the helpers below detect it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

__all__ = [
    "JobDefinition",
    "RunRecord",
    "TimerInfo",
    "STATE_DIR",
    "JOBS_DIR",
    "RUNS_DIR",
    "LOGS_DIR",
    "slugify",
    "load_saved_jobs",
    "save_job",
    "delete_saved_job",
    "get_job",
    "append_run",
    "list_runs",
    "schedule_retention_delete",
    "cancel_retention_delete",
    "list_dr_timers",
    "lingering_enabled",
    "systemctl_user_available",
]


# ---- state-dir resolution --------------------------------------------------

def _state_root() -> Path:
    """Resolve the persistent state root, honouring `$DR_TOOLS_STATE_DIR`.

    Defaulting to `~/.dr-tools` keeps the install user-local; the env-var
    override is used by tests so they don't smear over real saved jobs.
    """
    override = os.environ.get("DR_TOOLS_STATE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path("~/.dr-tools").expanduser().resolve()


STATE_DIR = _state_root()
JOBS_DIR = STATE_DIR / "jobs"
RUNS_DIR = STATE_DIR / "runs"
LOGS_DIR = STATE_DIR / "logs"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, JOBS_DIR, RUNS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---- dataclasses -----------------------------------------------------------

@dataclass
class JobDefinition:
    """One saved Job Scheduler template (persists across restarts)."""
    name: str                       # human-friendly; may contain spaces
    org: str                        # organizationName
    project_handle: str             # project this dataset gets indexed into
    connector_name: str
    connector_handle: str
    connector_type: str             # "NFS" / "EXCHANGE" / …
    remote_host: str
    remote_path: str                # connector's root path
    path: str                       # subpath under remote_path to index
    retention_seconds: int = 7 * 24 * 3600   # default: 1 week
    created_at: str = ""            # ISO-8601; set by save_job
    description: str = ""
    # v0.15 — optional recurring schedule. Empty string = one-shot
    # (Run Now only). Otherwise a systemd OnCalendar= expression:
    #   "daily"               — every day at midnight
    #   "*-*-* 03,11,19:00:00" — every day at 03:00, 11:00, 19:00
    #   "Mon..Fri *-*-* 09:00:00" — weekdays at 09:00
    # See systemd.time(7) for the full grammar.
    schedule: str = ""

    def slug(self) -> str:
        return slugify(self.name)


@dataclass
class RunRecord:
    """One execution of a JobDefinition (created by dr_job_run)."""
    run_id: str                    # 14-char UTC stamp, eg "20260513T0300"
    started_at: str                # ISO-8601
    task_handle: str               # from createRepresentation
    corpus_handle: str
    data_area_handle: str
    status: str = "RUNNING"        # RUNNING / SUCCESS / FAILURE / DELETED
    finished_at: str = ""
    notes: str = ""


@dataclass
class TimerInfo:
    """One row parsed out of `systemctl --user list-timers --all`."""
    unit: str
    next_fire: str
    left: str
    activates: str
    state: str = ""                # "active" / "inactive"


# ---- helpers ---------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Convert a job name into a filesystem-safe, systemd-unit-safe slug.

    Lowercase, ASCII-only, dashes between runs of non-alphanum chars.
    Used for both the JSON filename and the systemd unit name so they
    line up 1:1.
    """
    s = (name or "").strip().lower()
    s = _SLUG_RE.sub("-", s)
    s = s.strip("-")
    return s or "unnamed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- JobDefinition CRUD ----------------------------------------------------

def save_job(job: JobDefinition) -> JobDefinition:
    """Persist a JobDefinition to `~/.dr-tools/jobs/<slug>.json`.

    Stamps `created_at` if it wasn't already set. Returns the (possibly
    enriched) JobDefinition so the caller can refresh its in-memory copy.
    """
    _ensure_dirs()
    if not job.created_at:
        job.created_at = _now_iso()
    path = JOBS_DIR / f"{job.slug()}.json"
    payload = asdict(job)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return job


def load_saved_jobs() -> list[JobDefinition]:
    """Read every `*.json` under JOBS_DIR. Skips files that fail to parse."""
    _ensure_dirs()
    out: list[JobDefinition] = []
    for f in sorted(JOBS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            out.append(JobDefinition(**data))
        except Exception:
            # Stale / hand-edited / wrong-shape file — skip rather than
            # crash the whole tab. The UI can flag the count mismatch.
            continue
    return out


def get_job(name_or_slug: str) -> Optional[JobDefinition]:
    """Look up a job by either its display name or its slug."""
    s = slugify(name_or_slug)
    path = JOBS_DIR / f"{s}.json"
    if not path.exists():
        return None
    try:
        return JobDefinition(**json.loads(path.read_text()))
    except Exception:
        return None


def delete_saved_job(name_or_slug: str) -> bool:
    """Remove the saved-job JSON. Returns True if a file was deleted."""
    s = slugify(name_or_slug)
    path = JOBS_DIR / f"{s}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


# ---- RunRecord append + read ----------------------------------------------

def append_run(job_slug: str, run: RunRecord) -> None:
    """Append one RunRecord as a JSONL line under RUNS_DIR/<slug>.jsonl."""
    _ensure_dirs()
    path = RUNS_DIR / f"{job_slug}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(asdict(run)) + "\n")


def list_runs(job_slug: str) -> list[RunRecord]:
    """Read every RunRecord for a job (oldest first). Empty on missing file."""
    path = RUNS_DIR / f"{job_slug}.jsonl"
    if not path.exists():
        return []
    out: list[RunRecord] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(RunRecord(**json.loads(line)))
        except Exception:
            continue
    return out


# ---- systemd-user integration ---------------------------------------------

def systemctl_user_available() -> bool:
    """Quick probe for `systemctl --user` working in this environment.

    Returns False when systemd-user isn't a thing here (e.g. running
    inside Docker, on a host with sysvinit, or as a service account
    without an XDG_RUNTIME_DIR). Callers should degrade to "saved-only"
    mode in that case.
    """
    if not shutil.which("systemctl"):
        return False
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-system-running"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return False
    # `is-system-running` returns non-zero in degraded states, but the
    # presence of any output (running / degraded / starting) tells us
    # the user manager is reachable.
    return bool((r.stdout or "").strip())


def lingering_enabled(user: Optional[str] = None) -> bool:
    """True when `loginctl enable-linger` has been run for the user.

    Without lingering, systemd-user units (including our retention
    timers) terminate the moment the user logs out — which is the wrong
    behaviour for a fire-and-forget scheduled task.
    """
    u = user or os.environ.get("USER") or ""
    if not u:
        return False
    if not shutil.which("loginctl"):
        return False
    try:
        r = subprocess.run(
            ["loginctl", "show-user", u, "--property=Linger"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return False
    return "Linger=yes" in (r.stdout or "")


def _user_unit_dir() -> Path:
    """Resolve XDG-correct path for user systemd units."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path("~/.config").expanduser())
    return Path(base) / "systemd" / "user"


def _unit_name(job_slug: str, run_id: str) -> str:
    """Stable unit-name prefix shared by the `.service` and `.timer`."""
    return f"dr-tools-retention-{job_slug}-{run_id}"


def _runtime_bin(name: str) -> str:
    """Find an installed entry-point script on PATH; fall back to a
    sensible default for /opt/dr-tools/venv installs.

    Searched at schedule time so the captured command in the .service
    is absolute and survives PATH changes between cron-style triggers.
    """
    p = shutil.which(name)
    if p:
        return p
    default = f"/opt/dr-tools/venv/bin/{name}"
    return default


def schedule_retention_delete(
    *,
    job_slug: str,
    run_id: str,
    seconds_from_now: int,
    job_name: str = "",
) -> tuple[str, Optional[str]]:
    """Write + start a one-shot user timer that fires `dr_job_delete`.

    Returns `(unit_base, error)` — `unit_base` is the unit name without
    the `.service` / `.timer` suffix, `error` is None on success or a
    short string on failure (caller can surface to the UI without
    raising).

    The timer uses `OnCalendar=` at an absolute UTC time so it survives
    `daemon-reload` restarts; `RemainAfterElapse=false` means the unit
    is GC'd once it fires.
    """
    if seconds_from_now <= 0:
        return ("", "retention seconds must be positive")
    if not systemctl_user_available():
        return ("", "systemctl --user not available on this host")

    fire_ts = int(time.time()) + int(seconds_from_now)
    fire_dt = datetime.fromtimestamp(fire_ts, tz=timezone.utc)
    on_calendar = fire_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    unit_dir = _user_unit_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    base = _unit_name(job_slug, run_id)

    service_body = f"""[Unit]
Description=dr-tools retention cleanup for {job_name or job_slug} run {run_id}

[Service]
Type=oneshot
ExecStart={_runtime_bin('dr_job_delete')} {job_slug} {run_id}
"""
    timer_body = f"""[Unit]
Description=dr-tools retention timer for {job_name or job_slug} run {run_id}

[Timer]
OnCalendar={on_calendar}
Persistent=true
RemainAfterElapse=false
Unit={base}.service

[Install]
WantedBy=timers.target
"""
    (unit_dir / f"{base}.service").write_text(service_body)
    (unit_dir / f"{base}.timer").write_text(timer_body)

    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", f"{base}.timer"],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except subprocess.CalledProcessError as e:
        return (base, (e.stderr or e.stdout or "").strip()[:160])
    except Exception as e:
        return (base, repr(e)[:160])
    return (base, None)


def toggle_retention_timer(unit: str) -> tuple[str, Optional[str]]:
    """v0.14 — flip a timer between enabled+active and disabled+inactive.

    `unit` is the full `.timer` filename (e.g.
    `dr-tools-retention-job-1-20260513T030000.timer`). Returns
    `(new_state, error)` where `new_state` is "active" or "inactive"
    on success and `error` is None; on failure `error` carries a short
    one-line message for the UI.
    """
    if not systemctl_user_available():
        return ("", "systemctl --user not available")
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True, text=True, timeout=5,
        )
    except Exception as e:
        return ("", repr(e)[:160])
    state = (r.stdout or "").strip()
    new_cmd = ["disable", "--now"] if state == "active" else ["enable", "--now"]
    try:
        subprocess.run(
            ["systemctl", "--user"] + new_cmd + [unit],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except subprocess.CalledProcessError as e:
        return ("", (e.stderr or e.stdout or "").strip()[:160])
    return (
        "inactive" if state == "active" else "active",
        None,
    )


def cancel_retention_delete(*, job_slug: str, run_id: str) -> Optional[str]:
    """Stop + disable + remove the unit files for one retention timer.

    Idempotent — missing units are not an error. Returns None on
    success, an error string otherwise.
    """
    base = _unit_name(job_slug, run_id)
    unit_dir = _user_unit_dir()
    err = None
    for cmd in (
        ["systemctl", "--user", "stop",     f"{base}.timer"],
        ["systemctl", "--user", "disable",  f"{base}.timer"],
    ):
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except Exception as e:
            err = repr(e)[:160]
    for suffix in (".service", ".timer"):
        f = unit_dir / f"{base}{suffix}"
        try:
            if f.exists():
                f.unlink()
        except Exception as e:
            err = err or repr(e)[:160]
    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        err = err or repr(e)[:160]
    return err


# --- v0.15: recurring schedules ---------------------------------------------

def _recur_unit_name(job_slug: str) -> str:
    return f"dr-tools-recur-{job_slug}"


# Friendly preset → systemd OnCalendar expression. Anything else is
# treated as a raw OnCalendar string and passed through verbatim
# (advanced users can compose their own).
RECUR_PRESETS = {
    "":         "",                          # one-shot (no schedule)
    "hourly":   "hourly",
    "daily":    "daily",
    "weekly":   "weekly",
    "monthly":  "monthly",
    # 3×/day: 03:00, 11:00, 19:00 (covers shift-change windows for
    # 24/7 labs without piling everything on midnight).
    "3x-day":   "*-*-* 03,11,19:00:00",
    # 4×/day: every 6 hours.
    "4x-day":   "*-*-* 00,06,12,18:00:00",
    "weekdays-9am": "Mon..Fri *-*-* 09:00:00",
}


def schedule_recurring_job(
    *,
    job_slug: str,
    on_calendar: str,
    job_name: str = "",
) -> tuple[str, Optional[str]]:
    """Write + enable a recurring systemd user timer for one saved job.

    `on_calendar` is either a key in `RECUR_PRESETS` or a raw
    OnCalendar= expression (see systemd.time(7)). The timer's
    `.service` invokes `dr_job_run <slug>`. Unlike retention one-shots,
    `Persistent=true` here ensures missed runs (e.g. host was off) fire
    at the next opportunity.

    Returns `(unit_base, error)`. unit_base lives at
    `dr-tools-recur-<slug>.timer`. Idempotent — re-running with a new
    schedule rewrites the unit and restarts the timer.
    """
    if not on_calendar:
        return ("", "no schedule provided")
    if not systemctl_user_available():
        return ("", "systemctl --user not available on this host")
    # Resolve preset → raw expression.
    raw = RECUR_PRESETS.get(on_calendar, on_calendar)

    unit_dir = _user_unit_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    base = _recur_unit_name(job_slug)

    service_body = f"""[Unit]
Description=dr-tools recurring run for {job_name or job_slug}

[Service]
Type=oneshot
ExecStart={_runtime_bin('dr_job_run')} {job_slug}
"""
    timer_body = f"""[Unit]
Description=dr-tools recurring timer for {job_name or job_slug}

[Timer]
OnCalendar={raw}
Persistent=true
Unit={base}.service

[Install]
WantedBy=timers.target
"""
    (unit_dir / f"{base}.service").write_text(service_body)
    (unit_dir / f"{base}.timer").write_text(timer_body)

    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", f"{base}.timer"],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except subprocess.CalledProcessError as e:
        return (base, (e.stderr or e.stdout or "").strip()[:160])
    except Exception as e:
        return (base, repr(e)[:160])
    return (base, None)


def unschedule_recurring_job(*, job_slug: str) -> Optional[str]:
    """Stop + disable + remove the recurring timer for a job. Idempotent."""
    base = _recur_unit_name(job_slug)
    unit_dir = _user_unit_dir()
    err = None
    for cmd in (
        ["systemctl", "--user", "stop",    f"{base}.timer"],
        ["systemctl", "--user", "disable", f"{base}.timer"],
    ):
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except Exception as e:
            err = repr(e)[:160]
    for suffix in (".service", ".timer"):
        f = unit_dir / f"{base}{suffix}"
        try:
            if f.exists():
                f.unlink()
        except Exception as e:
            err = err or repr(e)[:160]
    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        err = err or repr(e)[:160]
    return err


_TIMER_PREFIX = "dr-tools-retention-"
# v0.15 — recurring schedules get their own prefix so they don't get
# confused with retention one-shots in list_dr_timers().
_RECUR_PREFIX = "dr-tools-recur-"

# v0.14 — pull `<slug>` and `<run_id>` back out of a unit base name.
# Slugs are kebab-case (a-z 0-9 -), run_ids are the 14-char UTC stamp
# from cli_jobrun._stamp(): YYYYMMDDTHHMMSS.
_UNIT_PARSE_RE = re.compile(
    rf"^{re.escape(_TIMER_PREFIX)}"
    r"(?P<slug>[a-z0-9-]+?)-"
    r"(?P<run_id>\d{8}T\d{6})$"
)
_LIST_TIMERS_RE = re.compile(
    r"^(?P<next>\S+\s+\S+\s+\S+\s+\S+)\s+(?P<left>\S+\s+\S+)\s+\S+\s+\S+\s+"
    r"(?P<unit>\S+)\s+(?P<activates>\S+)\s*$"
)


def list_dr_timers() -> list[TimerInfo]:
    """Parse `systemctl --user list-timers --all` and return our entries.

    Filters to units beginning with `dr-tools-retention-` (one-shots)
    or `dr-tools-recur-` (v0.15+ recurring schedules). Output format
    isn't strictly machine-readable, so we use a column split on
    headerless lines with `--no-legend`. Whatever doesn't parse cleanly
    is silently dropped; the UI shows a hint when nothing comes back.
    """
    if not systemctl_user_available():
        return []
    try:
        r = subprocess.run(
            ["systemctl", "--user", "list-timers", "--all", "--no-legend"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return []
    out: list[TimerInfo] = []
    for raw_line in (r.stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # v0.15 — accept both retention one-shots and recurring schedules.
        if (_TIMER_PREFIX not in line) and (_RECUR_PREFIX not in line):
            continue
        # Best-effort column split — systemctl pads with two-or-more
        # spaces between columns. The fields we want: NEXT, LEFT, LAST,
        # PASSED, UNIT, ACTIVATES. We don't care about LAST / PASSED.
        cols = [c.strip() for c in re.split(r"\s{2,}", line) if c.strip()]
        if len(cols) < 4:
            continue
        unit = next(
            (c for c in cols
             if (c.startswith(_TIMER_PREFIX) or c.startswith(_RECUR_PREFIX))
             and c.endswith(".timer")),
            "",
        )
        if not unit:
            continue
        # Identify the activates column (last token; ends in .service).
        activates = cols[-1] if cols[-1].endswith(".service") else ""
        # NEXT + LEFT typically occupy the first two columns.
        next_fire = cols[0]
        left = cols[1] if len(cols) > 1 else ""
        out.append(TimerInfo(
            unit=unit, next_fire=next_fire, left=left,
            activates=activates, state="active",
        ))
    return out
