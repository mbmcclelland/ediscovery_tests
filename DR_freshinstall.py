#!/usr/bin/env python3
"""DR_freshinstall.py — end-to-end fresh-install driver for Digital Reef.

Replaces the three-script sequence:

    bash cleandr.sh
    expect -f DR_freshinstall.exp
    python playwright_fresh_init.py        # browser-driven, slow

with a single Python entry point that talks to DR over REST. The
cleandr + installer steps are still done via the existing shell/expect
scripts (kept for "what exactly does this delete?" auditability) but
the post-install provisioning runs entirely through `dr_tui/data.py`
helpers — no Playwright, no Chromium download, no proxy capture. It's
~5x faster than the Playwright path and survives in environments
without a GUI.

Usage:

    sudo .venv/bin/python DR_freshinstall.py             # full sequence
    sudo .venv/bin/python DR_freshinstall.py --dry-run   # print only
    sudo .venv/bin/python DR_freshinstall.py --skip-clean --skip-installer
    sudo .venv/bin/python DR_freshinstall.py --keep-existing

Flags:

    --skip-clean        don't run the cleandr teardown
    --skip-installer    don't run the expect-driven .bin reinstall
                        (use when drd is already up but un-provisioned)
    --skip-api          stop after the installer; useful for debugging
    --keep-existing     idempotent mode — every API step skips if the
                        target object already exists. Safe to re-run
                        after a partial failure.
    --keeprpm           passed through to cleandr.sh
    --dry-run           print every action without doing it
    --hostname HOST     DR host (default: 192.168.58.128)
    --nfs-host HOST     storage / connector NFS server (default: same
                        as --hostname; almost always identical)

The 13 API-level steps are documented in the top-level user request
that produced this script and mirrored in the `STEPS` list below.

This script is destructive when run without `--skip-clean`. Hold on
to /root/license.lic — both this script and DR_freshinstall.exp
expect it there.
"""
from __future__ import annotations

import argparse
import datetime
import logging
import os
import socket
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Optional

# Silence the urllib3 self-signed-cert spam early. data.py imports already
# emit warnings; squash them at module load so the progress log stays
# readable.
warnings.filterwarnings("ignore")

# Repo root + ensure local imports resolve when running as a script.
_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Read the version string from the canonical __version__.py at the repo
# root. Falls back to "?.?.?" so a missing/garbled __version__.py
# doesn't crash the banner.
try:
    _vmod: dict = {}
    exec((_REPO / "__version__.py").read_text(), _vmod)
    _VERSION = _vmod.get("__version__", "?.?.?")
except Exception:
    _VERSION = "?.?.?"

from config import Config                                           # noqa: E402
from helpers.api_client import EDiscoveryClient, APIError           # noqa: E402
from dr_tui import data as drdata                                   # noqa: E402

# Rich is already a runtime dep (textual depends on it). We use it for
# the progress bar + colourised console output. Falling back to plain
# print would be possible but the v0.17.1 spec asks for a progress
# bar, so we hard-require it.
from rich.console import Console                                    # noqa: E402
from rich.progress import (                                         # noqa: E402
    Progress, BarColumn, TextColumn, TimeElapsedColumn,
    SpinnerColumn, MofNCompleteColumn,
)
from rich.panel import Panel                                        # noqa: E402
from rich.text import Text                                          # noqa: E402


# ---------- CLI ----------------------------------------------------------------

_DEFAULT_LOG_DIR = Path("/tmp")
_LOG_TS = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
_DEFAULT_LOG_PATH = _DEFAULT_LOG_DIR / f"dr-freshinstall-{_LOG_TS}.log"


# ---------- Reef-a-TUI logo ----------------------------------------------------

# Path to the bit-generated logo (5 lines of ASCII art). The .txt is the
# uncoloured source; we apply a blue→white vertical gradient at render
# time so we don't have to ship a colored version + plain version.
# Re-generate via `bit "Reef-a-TUI" -save reef-a-tui-logo`.
_LOGO_PATH = _REPO / "reef-a-tui-logo.txt"

# Digital Reef ocean palette — Blue → White → Black, top to bottom,
# like looking down into deepening water.
#   row 0  surface blue          (sky reflected on the water)
#   row 1  shallow / foam-edge   (sunlight scattering)
#   row 2  white foam            (the breaker)
#   row 3  deep blue-grey        (light fading with depth)
#   row 4  abyssal               (dark, with a hint of blue so it's
#                                 still visible on a black terminal)
_LOGO_COLORS = [
    "rgb(50,130,220)",     # row 0 — surface blue
    "rgb(150,200,240)",    # row 1 — shallow / foam edge
    "rgb(255,255,255)",    # row 2 — white foam (the breaker)
    "rgb(70,90,130)",      # row 3 — deep blue-grey (light fading)
    "rgb(10,20,40)",       # row 4 — abyssal (near-black with hint of blue)
]


def _render_logo(version: str) -> None:
    """Print the Reef-a-TUI logo + the bright-yellow product subtitle.

    Falls back to a plain text banner if the logo file is missing
    (e.g. running from an editable install where someone deleted it).
    """
    try:
        lines = _LOGO_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        console.print()
        console.print(f"[bold cyan]Reef-a-TUI[/]", highlight=False)
        console.print(
            f"[bold bright_yellow]Digital Reef Fresh Installer "
            f"version {version}[/]"
        )
        console.print()
        return
    # v0.17.5: regenerated logo (fivebyfive font, scale 0) is wider
    # than the v0.17.4 micro-logo — ~106 cols. If the user's terminal
    # is narrower than the logo, we let it spill rather than wrap
    # (wrapping shatters the ASCII art mid-letter; the terminal will
    # clip the overflow naturally). `no_wrap + crop=False +
    # overflow="ignore"` is the Rich incantation that disables BOTH
    # the wrap AND the soft-clip Rich would otherwise apply.
    console.print()
    for i, line in enumerate(lines):
        color = _LOGO_COLORS[min(i, len(_LOGO_COLORS) - 1)]
        console.print(
            line, style=color,
            markup=False, highlight=False,
            no_wrap=True, crop=False, overflow="ignore",
        )
    console.print(
        f"    Digital Reef Fresh Installer version {version}",
        style="bold bright_yellow", highlight=False,
        no_wrap=True, crop=False, overflow="ignore",
    )
    console.print()


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser separately so `--help` and the
    no-args-shows-help path share one source of truth."""
    ap = argparse.ArgumentParser(
        prog="DR_freshinstall.py",
        description=(
            "End-to-end fresh-install driver for Digital Reef. Runs "
            "teardown (cleandr.sh) → installer (DR_freshinstall.exp) "
            "→ 13 REST provisioning steps in one shot."
        ),
        epilog=(
            "Examples:\n"
            "  # Full destructive teardown + reinstall + provisioning:\n"
            "  sudo .venv/bin/python DR_freshinstall.py --force\n"
            "\n"
            "  # Idempotent recovery (drd already up, /data intact):\n"
            "  sudo .venv/bin/python DR_freshinstall.py "
            "--skip-clean --skip-installer --keep-existing\n"
            "\n"
            "  # See what it would do, no API calls or shelling out:\n"
            "  .venv/bin/python DR_freshinstall.py --dry-run "
            "--skip-clean --skip-installer\n"
            "\n"
            "Logs every run to /tmp/dr-freshinstall-<TIMESTAMP>.log by "
            "default; override with --log-file. The destructive phases "
            "(clean + installer) require --force or an interactive "
            "y/n confirmation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ---- phase toggles ----
    phases = ap.add_argument_group("Phase selection")
    phases.add_argument("--skip-clean", action="store_true",
                        help="skip the cleandr.sh teardown phase")
    phases.add_argument("--skip-installer", action="store_true",
                        help="skip DR_freshinstall.exp (assume drd is "
                             "already up)")
    phases.add_argument("--skip-api", action="store_true",
                        help="skip the 13-step REST provisioning phase")

    # ---- behaviour flags ----
    behav = ap.add_argument_group("Behaviour")
    behav.add_argument("--keep-existing", action="store_true",
                       help="API steps no-op when target already exists "
                            "(idempotent recovery mode)")
    behav.add_argument("--keeprpm", action="store_true",
                       help="passed through to cleandr.sh — keeps the "
                            "dr-tools RPM installed")
    behav.add_argument("--dry-run", action="store_true",
                       help="print every action without doing it; no "
                            "shells out or API calls fire")
    behav.add_argument("--force", action="store_true",
                       help="run destructive phases without the "
                            "interactive y/n confirmation prompt")
    behav.add_argument("--no-progress", action="store_true",
                       help="disable the live progress bar (useful for "
                            "CI logs / non-TTY environments)")

    # ---- target overrides ----
    target = ap.add_argument_group("Target overrides")
    target.add_argument("--hostname", default="192.168.58.128",
                        help="DR REST host (default: 192.168.58.128)")
    target.add_argument("--nfs-host", default="",
                        help="NFS server fqdn for storage + connectors "
                             "(default: same as --hostname)")
    target.add_argument("--inactivity-minutes", type=int, default=99,
                        help="session inactivity timeout in minutes "
                             "(default: 99)")
    target.add_argument("--initial-password", default="DRSysAdmin",
                        help="DRSysAdmin's first-install password "
                             "(default: DRSysAdmin)")
    target.add_argument("--final-password", default="password",
                        help="DRSysAdmin's password after the "
                             "first-login change (default: password)")

    # ---- logging ----
    logf = ap.add_argument_group("Logging")
    logf.add_argument("--log-file", default=str(_DEFAULT_LOG_PATH),
                      help=f"log file path (default: "
                           f"/tmp/dr-freshinstall-<TIMESTAMP>.log)")
    logf.add_argument("--log-level", default="INFO",
                      choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                      help="logger verbosity (default: INFO)")
    logf.add_argument("--verbose", "-v", action="store_true",
                      help="equivalent to --log-level=DEBUG")

    return ap


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    return _build_parser().parse_args(argv)


# ---------- Rich console + logging globals -------------------------------------

# A single Console drives all output. When the progress bar is active
# (every step except the first banner), Rich routes console.print()
# calls above the bar so the running tally stays pinned at the bottom.
# When --no-progress is set or stdout isn't a TTY, the Progress context
# is a no-op and console.print() lines just stream normally.
console = Console(highlight=False)

# Module-level logger — wrapped by every _ok/_info/_warn helper below
# so that file + stdout output stay in lock-step. Configured in
# _setup_logging() at the start of main().
log = logging.getLogger("dr_freshinstall")

# Set by _setup_progress(); the active Progress task ID for the global
# phase tracker. We update its description on every _step() call so the
# user sees the current activity inline with the bar.
_progress: Optional[Progress] = None
_progress_task: Optional[int] = None
# Per-step elapsed-time tracking — written to the log at step finish.
_step_started_at: Optional[float] = None


def _setup_logging(log_path: Path, level: str, verbose: bool) -> None:
    """Configure the module logger to write to a file only.

    The file handler captures everything at DEBUG so post-mortem
    debugging has full detail. We DO NOT add a stderr stream handler:
    user-facing output (including warnings and errors) is already
    routed through the Rich `console` via the `_warn` / `_fail` /
    `_ok` / `_info` helpers — adding a stream handler would print
    every WARN/ERROR twice (QA-v0171-1).

    `--verbose` / `--log-level` now control only the *file* log
    depth. (The Rich console output is always at the same level
    — that's what users see; it doesn't need a separate knob.) If
    you want to inspect DEBUG output, `tail -f` the log file.
    """
    log.handlers.clear()
    log.setLevel(logging.DEBUG)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG if verbose else getattr(logging, level))
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    log.addHandler(fh)

    log.info("dr-freshinstall starting — log file: %s", log_path)


def _setup_progress(total_steps: int, disabled: bool) -> Optional[Progress]:
    """Spin up the global Progress context. Returns the Progress
    object so main() can use it as a context manager."""
    global _progress, _progress_task
    if disabled or not sys.stdout.isatty():
        _progress = None
        _progress_task = None
        log.debug("progress bar disabled (--no-progress or non-TTY stdout)")
        return None
    _progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
        refresh_per_second=8,
    )
    _progress_task = _progress.add_task(
        "starting…", total=total_steps,
    )
    return _progress


def _advance_progress(description: str) -> None:
    """Tick the global progress bar one step forward + update the
    'now doing' label."""
    if _progress is not None and _progress_task is not None:
        _progress.update(_progress_task, advance=1, description=description)


def _pause_progress() -> None:
    """Pause the live progress renderer.

    v0.17.3 fix for "spinner spam during phase 2": Rich's Progress
    refreshes 8 Hz (every 125 ms). When a long subprocess (cleandr's
    `rm -rfv` flood, or the InstallAnywhere installer's
    `[========|========]` progress markers) emits its OWN stdout
    while our Progress is live, every Rich refresh redraws the bar
    on a NEW last line above the subprocess output — so the
    terminal scroll-back (and any captured log) ends up with
    hundreds of duplicate bar-lines.

    Pausing the renderer during phases 1 + 2 lets the subprocess
    output flow cleanly. The bar resumes for phase 3 (the REST
    provisioning) where we own all the output anyway.
    """
    if _progress is not None:
        try:
            _progress.live.stop()
        except Exception:
            pass


def _resume_progress() -> None:
    """Resume the live progress renderer after a `_pause_progress()`."""
    if _progress is not None:
        try:
            _progress.live.start()
        except Exception:
            pass


def _set_progress_description(description: str) -> None:
    """Update the running label without advancing the bar (useful for
    sub-step status inside a long phase)."""
    if _progress is not None and _progress_task is not None:
        _progress.update(_progress_task, description=description)


def _stream_subprocess(
    cmd: list[str], *, cwd: Optional[str] = None,
    line_style: str = "dim",
) -> int:
    """Run *cmd* and stream every output line through Rich's console.

    v0.17.4 — replaces the v0.17.3 pause/resume hack. Instead of
    pausing the Rich progress bar during long subprocess phases, we
    route the subprocess's stdout + stderr line-by-line through
    `console.print()`. Rich's `Live` underpinning the `Progress`
    automatically routes those prints **above** the live region —
    so the progress bar stays pinned at the bottom of the visible
    output while logs scroll cleanly above it.

    Net effect: a stable bottom-of-frame status bar with the spec'd
    "current phase" text, while subprocess output (cleandr's
    `rm -rfv` flood, the InstallAnywhere installer's dialogs, drd's
    systemd debug stream) flows into the scroll-back like a normal
    tail.

    Returns the subprocess exit code. Like `subprocess.run().returncode`,
    a non-zero return is a signal to the caller — we don't raise.
    """
    proc = subprocess.Popen(
        cmd, cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True, bufsize=1,
        errors="replace",
    )
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            # Strip the trailing newline that console.print() re-adds.
            line_text = raw.rstrip("\n")
            if not line_text:
                continue
            # Use Rich's Text builder so the subprocess output is
            # treated as opaque body text — its `[…]` markers (e.g.
            # the InstallAnywhere `[========]` bar, systemd's
            # "Started X [OK]") never get interpreted as Rich markup.
            # The dim "│" prefix matches the bar's visual style.
            body = Text("    │ ", style=line_style) + Text(line_text)
            console.print(body, highlight=False)
            log.debug("subproc: %s", line_text)
    finally:
        proc.wait()
    return proc.returncode


# ---------- user-facing output helpers -----------------------------------------

# These mirror every line into:
#   * the log file (DEBUG → captured)
#   * the Rich console (above the progress bar)
# So the on-screen experience stays tidy AND we have a complete
# audit trail for post-mortem.

# Terminal-width sniff — Rich handles wrapping but the banner rule
# wants a hard width. Same v0.10.2 lesson as before: clamp 80–120.
_TERM_WIDTH = 100
try:
    _TERM_WIDTH = max(80, min(120, os.get_terminal_size().columns))
except Exception:
    pass


def _hr() -> None:
    console.print("─" * _TERM_WIDTH, style="dim")


def _step(num: int, title: str) -> None:
    """Begin a numbered step. Logs the header, advances the progress
    bar, and stamps the wall-clock start so we can report duration on
    success."""
    global _step_started_at
    _step_started_at = time.time()
    label = f"Step {num:2d} — {title}"
    log.info("──── %s ────", label)
    _advance_progress(label)
    # Also emit a visible header above the bar so the user has a
    # rolling history, not just the live label.
    console.print()
    console.print(f"[bold cyan]Step {num:2d}.[/] {title}")


def _ok(msg: str) -> None:
    elapsed = ""
    if _step_started_at is not None:
        elapsed = f"  [dim]({time.time() - _step_started_at:.1f}s)[/]"
    log.info("OK    %s", msg)
    console.print(f"    [green]✓[/]  {msg}{elapsed}")


def _info(msg: str) -> None:
    log.info("INFO  %s", msg)
    console.print(f"    [dim]·[/]  {msg}")


def _warn(msg: str) -> None:
    log.warning("WARN  %s", msg)
    console.print(f"    [yellow]⚠[/]  {msg}")


def _fail(msg: str) -> None:
    log.error("FAIL  %s", msg)
    console.print(f"    [bold red]✗[/]  {msg}")


def _skip(msg: str) -> None:
    log.info("SKIP  %s", msg)
    console.print(f"    [dim cyan]⊘[/]  skipped: {msg}")


def _phase_banner(num: int, name: str) -> None:
    """Sub-header for phases 1/2/3 in main(). Bigger than _step's."""
    log.info("════ Phase %d — %s ════", num, name)
    _advance_progress(f"Phase {num} — {name}")
    console.print()
    console.print(Panel.fit(
        Text(f"Phase {num} — {name}", style="bold magenta"),
        border_style="magenta",
    ))


def _confirm_destruction(args: argparse.Namespace) -> bool:
    """Interactive y/n gate for the destructive phases.

    Returns True to proceed, False to abort. --force bypasses the
    prompt entirely (CI / scripted-run path). --dry-run also bypasses
    because nothing destructive actually runs in that mode.
    """
    if args.dry_run or args.force:
        return True
    if args.skip_clean and args.skip_installer:
        # Non-destructive run — neither shell phase will fire.
        return True
    if not sys.stdin.isatty():
        # No human to ask. Require --force in scripted contexts so a
        # rogue pipeline can't accidentally nuke a working install.
        _fail("destructive phases requested without --force on a non-TTY "
              "stdin. Re-run with --force or --skip-clean --skip-installer.")
        return False

    console.print()
    console.print(Panel.fit(
        Text(
            "⚠  This will DESTROY the current DR install:\n"
            "    • /home/auraria/AHS*    (entire install tree)\n"
            "    • /data/docstorage/*    (document storage)\n"
            "    • /data/indexstorage/*  (index storage)\n"
            "    • dr-tools RPM          (unless --keeprpm)\n"
            "    • per-user systemd timers (retention + recurring jobs)\n"
            "\n"
            "License is preserved to /root/license.lic automatically.\n"
            "This is NOT recoverable. Type 'YES' (uppercase) to proceed.",
            style="bold yellow",
        ),
        border_style="red",
        title="[bold red]DESTRUCTIVE OPERATION[/]",
    ))
    try:
        answer = input("Proceed? > ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
    return answer == "YES"


# ---------- Phase 1: teardown via cleandr.sh -----------------------------------

def phase_clean(args: argparse.Namespace) -> None:
    """Inline cleandr.sh action.

    We call the existing shell script as a subprocess rather than
    re-implementing it in Python — `rm -rfv` with a real shell is
    auditable, and the script has been battle-tested. The user can
    diff cleandr.sh and trust this driver to behave identically.
    """
    cmd = ["bash", str(_REPO / "cleandr.sh")]
    if args.keeprpm:
        cmd.append("--keeprpm")
    if args.dry_run:
        _info(f"DRY-RUN: would run: {' '.join(cmd)}")
        return
    _info(f"running: {' '.join(cmd)}")
    # v0.17.4 — stream each subprocess line via Rich so the progress
    # bar stays pinned at the bottom of the live region while
    # cleandr's `rm -rfv` flood scrolls cleanly above it.
    rc = _stream_subprocess(cmd)
    if rc != 0:
        raise RuntimeError(f"cleandr.sh exited with {rc}")
    _ok("teardown complete")


# ---------- Phase 2: installer via DR_freshinstall.exp -------------------------

def phase_installer(args: argparse.Namespace) -> None:
    """Run the expect script that drives the InstallAnywhere .bin.

    The .bin lives at /tmp/5.5.3.2.bin (the script `cd`s to /tmp
    internally via `spawn ./5.5.3.2.bin`). License restoration is
    appended inside the expect file itself (it copies /root/license.lic
    back to /home/auraria/AHS/conf/ and restarts drd).
    """
    if not (_REPO / "DR_freshinstall.exp").is_file():
        raise FileNotFoundError("DR_freshinstall.exp not found")
    if not Path("/tmp/5.5.3.2.bin").is_file():
        raise FileNotFoundError(
            "/tmp/5.5.3.2.bin not found — copy the DR installer there "
            "before running."
        )
    cmd = ["expect", "-f", str(_REPO / "DR_freshinstall.exp")]
    if args.dry_run:
        _info(f"DRY-RUN: would run: {' '.join(cmd)}")
        return
    _info("driving the installer (this takes a few minutes…)")
    # The expect script spawns `./5.5.3.2.bin -i console` from /tmp,
    # so we cd there first. cwd= isolates the change from the rest
    # of the driver.
    # v0.17.4 — stream each subprocess line via Rich. The
    # InstallAnywhere `[========]` markers and drd-restart systemd
    # debug output scroll above the pinned progress bar instead of
    # competing with it. Replaces the v0.17.3 pause/resume hack.
    rc = _stream_subprocess(cmd, cwd="/tmp")
    if rc != 0:
        raise RuntimeError(f"DR_freshinstall.exp exited with {rc}")
    _ok("installer finished")


# ---------- Phase 2.5: wait for drd --------------------------------------------

def _drd_listening(host: str, port: int = 8443, timeout: float = 5.0) -> bool:
    """Cheap TCP probe — does drd accept a connection on :8443 yet?"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _drd_api_ready(host: str, timeout: float = 5.0) -> bool:
    """App-readiness probe — confirms the eDiscovery webapp's REST
    handlers are wired up.

    v0.17.2 (QA-v0171-2) — first cut accepted "status < 500" as
    ready. Refined after QA found that DR's createSession returns
    a structured 500 ("AuthenticationInfo is null") when probed with
    nonsense credentials EVEN ON A FULLY-DEPLOYED WEBAPP — so we
    were wrongly waiting out the 240s deadline. The ground truth
    we actually want: did our request reach a DR handler at all?
    If yes → webapp is alive (auth might still fail later, but the
    routing exists). If no → still deploying.

    Detection signal: a structured DR response includes a
    `com.digitalreefinc.*` class reference in either the HTML body
    or the JSON. Pre-deploy 502/503/Wildfly-default-error pages don't.
    Also: any 2xx/3xx/4xx counts as ready directly.
    """
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    import requests
    url = f"https://{host}:8443/ediscovery/rest/realmManager/createSession"
    try:
        r = requests.post(
            url,
            json={"requestHandle": None, "userName": "_readiness_probe_",
                  "password": "x", "domain": "local", "customerName": ""},
            verify=False, timeout=timeout,
        )
    except Exception:
        return False
    if r.status_code < 500:
        return True
    # Structured DR 5xx → handler routed correctly, webapp is alive.
    return "digitalreef" in r.text.lower()


def wait_for_drd(host: str, max_wait_s: int = 240) -> None:
    """Poll until drd is REST-ready after an installer run.

    Two-stage: first wait for TCP-listen on :8443 (quick — usually
    a few seconds), then poll the REST API itself until the
    eDiscovery webapp has finished deploying. The second stage is
    the one that matters — pre-v0.17.2 we only checked TCP and
    QA-v0171-2 caught the resulting 500 on a fresh install.

    Bumped to 240s default (from 180s) to cover slower hosts where
    war deploy + DB schema init takes >2 min.
    """
    deadline = time.time() + max_wait_s
    # Stage 1: TCP listen
    tcp_ready_at: Optional[float] = None
    while time.time() < deadline:
        if _drd_listening(host):
            tcp_ready_at = time.time()
            log.debug("drd TCP listener up after %.1fs",
                      tcp_ready_at - (deadline - max_wait_s))
            break
        time.sleep(3)
    if tcp_ready_at is None:
        raise TimeoutError(
            f"drd did not start listening on {host}:8443 within "
            f"{max_wait_s}s — check /home/auraria/AHS/output/server.log"
        )

    # Stage 2: REST API ready (eDiscovery webapp deployed). This is
    # the real readiness signal — pre-v0.17.2 we skipped this and
    # hit QA-v0171-2's HTTP 500 on changeUserPassword.
    _set_progress_description(f"waiting for eDiscovery webapp to deploy…")
    while time.time() < deadline:
        if _drd_api_ready(host):
            elapsed = time.time() - tcp_ready_at
            _ok(f"drd is REST-ready on {host}:8443 "
                f"(webapp deployed in {elapsed:.1f}s after TCP listen)")
            return
        time.sleep(3)
    raise TimeoutError(
        f"drd TCP listener is up but eDiscovery REST API still "
        f"returns 5xx after {max_wait_s}s — webapp deploy may have "
        f"failed. Check /home/auraria/AHS/output/server.log"
    )


# ---------- Phase 3: API provisioning ------------------------------------------

# These are the 13 steps from the user request. Kept as a single list
# so the script's structure mirrors the spec exactly — anyone reading
# this can match step N here to step N in the request.

STEPS = [
    "Login + change DRSysAdmin's default password",
    "Create document storage at /data/docstorage",
    "Create index storage at /data/indexstorage",
    "Create the system storage depot (using the index storage)",
    "Update virus definitions",
    "Set the logon inactivity timeout (minutes)",
    "Create the 'training' organization",
    "Create admin@training as Organization Administrator",
    "Add DRSysAdmin to 'training' as Organization Administrator",
    "Create read-only IMPORT connector @ /data/import",
    "Create read-write connector @ /data/export",
    "Create read-write connector @ /data/archive",
    "Create PROJECT data area on /data/archive + EXPORT data area on /data/export",
]


def _make_cfg(host: str, username: str, password: str,
              organization: str = "super_system_customer") -> Config:
    """Config is a frozen dataclass — build a fresh instance per call
    rather than mutating fields (the env-driven defaults still apply
    for anything we don't override)."""
    base_url = f"https://{host}:8443/ediscovery/rest"
    return Config(
        base_url=base_url,
        username=username,
        password=password,
        organization=organization,
    )


def _try_initial_login(host: str, initial_pw: str, final_pw: str) -> tuple[EDiscoveryClient, bool]:
    """Try the final password first (idempotent re-run), then the
    initial. Returns (client, changed_already) — `changed_already`
    is True when we logged in with the final password (so step 1's
    change-password call is a no-op).
    """
    # Final-password attempt first → idempotent re-run path.
    try:
        c = EDiscoveryClient(_make_cfg(host, "DRSysAdmin", final_pw))
        c.login()
        return c, True
    except (APIError, Exception):
        pass
    # Fall back to the default first-install password.
    c = EDiscoveryClient(_make_cfg(host, "DRSysAdmin", initial_pw))
    c.login()
    return c, False


def step_1_login_and_change_password(args) -> EDiscoveryClient:
    _step(1, STEPS[0])
    if args.dry_run:
        _info(f"DRY-RUN: would login {args.initial_password!r} → "
              f"change to {args.final_password!r}")
        return None  # type: ignore
    client, already_changed = _try_initial_login(
        args.hostname, args.initial_password, args.final_password,
    )
    if already_changed:
        _ok(f"already logged in with {args.final_password!r} "
            f"(password previously changed)")
        return client
    _info(f"logged in with default password {args.initial_password!r}")
    drdata.change_user_password(
        client,
        old_password=args.initial_password,
        new_password=args.final_password,
        org_name="super_system_customer",
    )
    _ok(f"password changed → {args.final_password!r}")
    # Re-login with the new password to refresh the session token in
    # the canonical "post-change" state. Some endpoints reject the
    # old token after a password change even though it's not yet
    # expired. Config is a frozen dataclass — build a fresh client
    # rather than mutating in place.
    client = EDiscoveryClient(
        _make_cfg(args.hostname, "DRSysAdmin", args.final_password)
    )
    client.login()
    _ok("re-logged in with new password")
    return client


def step_2_create_doc_storage(args, client: EDiscoveryClient) -> str:
    """Returns the document-storage handle (for traceability)."""
    _step(2, STEPS[1])
    name = "localDocStorage"
    nfs_host = args.nfs_host or args.hostname
    if args.dry_run:
        _info(f"DRY-RUN: createRemoteNFSStorageArea name={name} "
              f"export=/data/docstorage")
        return ""
    export = "/data/docstorage"
    if args.keep_existing:
        # Match by (export, fqdn) first so renamed depots are still
        # recognised — a partially-failed prior run might have left
        # the same mount under a different label.
        for d in drdata.list_storage_depots(client, "DOCUMENT_STORE"):
            if d.export == export and (not d.fqdn or d.fqdn == nfs_host):
                _skip(f"DOC storage at {export!r} already exists "
                      f"(name={d.name!r} handle={d.handle})")
                return d.handle
    resp = drdata.create_storage_depot(
        client, name=name, fqdn=nfs_host, export=export,
        use_type="DOCUMENT_STORE",
    )
    handle = (resp.get("remoteStorageArea") or {}).get("handle", "")
    _ok(f"created {name} → handle={handle}")
    return handle


def step_3_create_index_storage(args, client: EDiscoveryClient) -> tuple[str, str, str]:
    """Returns (handle, fqdn, export) — needed by step 4."""
    _step(3, STEPS[2])
    name = "localIndexStorage"
    nfs_host = args.nfs_host or args.hostname
    export = "/data/indexstorage"
    if args.dry_run:
        _info(f"DRY-RUN: createRemoteNFSStorageArea name={name} "
              f"export={export}")
        return ("", nfs_host, export)
    if args.keep_existing:
        for d in drdata.list_storage_depots(client, "INDEX_STORE"):
            if d.export == export and (not d.fqdn or d.fqdn == nfs_host):
                _skip(f"INDEX storage at {export!r} already exists "
                      f"(name={d.name!r} handle={d.handle})")
                return (d.handle, d.fqdn or nfs_host, d.export or export)
    resp = drdata.create_storage_depot(
        client, name=name, fqdn=nfs_host, export=export,
        use_type="INDEX_STORE",
    )
    handle = (resp.get("remoteStorageArea") or {}).get("handle", "")
    _ok(f"created {name} → handle={handle}")
    return (handle, nfs_host, export)


def step_4_create_system_storage_depot(
    args, client: EDiscoveryClient,
    idx_handle: str, idx_fqdn: str, idx_export: str,
) -> None:
    _step(4, STEPS[3])
    if args.dry_run:
        _info(f"DRY-RUN: createSystemStorageDepot using "
              f"index storage handle={idx_handle}")
        return
    if args.keep_existing:
        cur = drdata.get_system_storage_depot(client)
        if cur and cur.directory_path:
            _skip(f"system depot already assigned: {cur.name!r}")
            return
    if not idx_handle:
        # Re-discover by name (covers a partial-failure run).
        for d in drdata.list_storage_depots(client, "INDEX_STORE"):
            if d.name == "localIndexStorage":
                idx_handle, idx_fqdn, idx_export = (
                    d.handle, d.fqdn or idx_fqdn, d.export or idx_export,
                )
                break
    drdata.create_system_storage_depot(
        client,
        ip_address=idx_fqdn,
        storage_facility_id=idx_handle,
        mount_point=idx_export,
    )
    _ok(f"system storage depot pointed at {idx_fqdn}:{idx_export}")


def step_5_virus_update(args, client: EDiscoveryClient) -> None:
    _step(5, STEPS[4])
    if args.dry_run:
        _info("DRY-RUN: trigger_virus_update")
        return
    try:
        drdata.trigger_virus_update(client, enabled=True, frequency="DAILY")
        _ok("virus update queued (runs in background)")
    except APIError as e:
        # INVALID_STATE on a re-run just means an update is already in
        # progress — treat as success.
        if e.error_code == "INVALID_STATE":
            _skip("virus update already in progress")
        else:
            raise


def step_6_inactivity_timeout(args, client: EDiscoveryClient) -> None:
    _step(6, STEPS[5])
    minutes = args.inactivity_minutes
    seconds = minutes * 60
    if args.dry_run:
        _info(f"DRY-RUN: setInactivityTimeout {seconds}s ({minutes} min)")
        return
    drdata.set_inactivity_timeout(client, seconds=seconds)
    _ok(f"session timeout set to {minutes} minutes ({seconds}s)")


def step_7_create_training_org(args, client: EDiscoveryClient) -> None:
    _step(7, STEPS[6])
    if args.dry_run:
        _info("DRY-RUN: createOrganization name='training'")
        return
    if args.keep_existing:
        for o in drdata.list_organizations_sys(client):
            if o.name == "training":
                _skip(f"org 'training' already exists (handle={o.handle})")
                return
    drdata.create_organization(client, name="training", description="")
    _ok("created organization 'training'")


def _resolve_org_admin_role(client: EDiscoveryClient) -> str:
    """Look up the Organization Administrator role handle for training.

    Uses the sys-scoped `adminOrgManager/listRoles` so the call works
    even when DRSysAdmin hasn't been added to the org yet (the state
    of a brand-new org created by `realmManager/createOrganization`).
    """
    drdata.ensure_org_context(client, "training")
    roles = drdata.list_org_roles(client, org_name="training", sys_scope=True)
    for name, h in roles:
        if name == "Organization Administrator":
            return h
    raise RuntimeError(
        f"Organization Administrator role not found in training. "
        f"Available roles: {[n for n,_ in roles]!r}"
    )


def step_8_create_org_admin(
    args, client: EDiscoveryClient, org_admin_handle: str,
) -> None:
    """Creates `admin@training`. Requires DRSysAdmin to already be a
    member of the org (step 9 has been moved BEFORE step 8 in
    `phase_api` for this reason)."""
    _step(8, STEPS[7])
    if args.dry_run:
        _info("DRY-RUN: createUser admin@training with Organization "
              "Administrator role")
        return
    if args.keep_existing:
        # listUsersAndGroups → look for 'admin'
        try:
            r = client.post(
                "adminOrgManager/listUsersAndGroups",
                extra_body={
                    "contextHandle": "training",
                    "organizationName": "training",
                    "systemScope": True,
                },
            )
            for u in (r.get("users") or []):
                if (u.get("userName") or "").lower() == "admin":
                    _skip(f"admin@training already exists "
                          f"(handle={u.get('handle')})")
                    return
        except Exception:
            pass
    drdata.create_org_user(
        client,
        org_name="training",
        user_name="admin",
        password="Password123",
        role_handles=[org_admin_handle],
        email="admin@localhost.com",
        first_name="Admin",
        last_name="User",
    )
    _ok("created admin@training (initial pw 'Password123')")


def step_8b_change_org_admin_password(args, client: EDiscoveryClient) -> None:
    """Bonus: admin@training is forced to change pw on first login. The
    dr-tui org-pinned login expects 'password' (env DR_ORG_PASSWORD).
    Log in once as admin@training, change the pw, log back out."""
    if args.dry_run:
        _info(f"DRY-RUN: would login admin@training and change pw → "
              f"{args.final_password!r}")
        return
    # Try the FINAL password first — handles the idempotent re-run
    # path (admin already past the forced-change flow). DR returns
    # 500 (not a structured APIError) for a bad password, so we
    # catch broadly and fall through.
    try:
        EDiscoveryClient(
            _make_cfg(args.hostname, "admin", args.final_password,
                      organization="training")
        ).login()
        _skip("admin@training already on final password")
        return
    except Exception:
        pass
    # Initial password — first run after createUser.
    org_client = EDiscoveryClient(
        _make_cfg(args.hostname, "admin", "Password123",
                  organization="training")
    )
    org_client.login()
    drdata.change_user_password(
        org_client,
        old_password="Password123",
        new_password=args.final_password,
        org_name="training",
    )
    _ok(f"admin@training password → {args.final_password!r}")


def step_9_add_drsysadmin_to_org(
    args, client: EDiscoveryClient, role_handle: str,
) -> None:
    _step(9, STEPS[8])
    if args.dry_run:
        _info(f"DRY-RUN: addSystemUserToOrg DRSysAdmin → training "
              f"(role={role_handle})")
        return
    if args.keep_existing:
        # listUsersAndGroups for training — does DRSysAdmin appear?
        try:
            r = client.post(
                "adminOrgManager/listUsersAndGroups",
                extra_body={
                    "contextHandle": "training",
                    "organizationName": "training",
                    "systemScope": True,
                },
            )
            for u in (r.get("users") or []):
                if (u.get("userName") or "").lower() == "drsysadmin":
                    _skip("DRSysAdmin already a member of training")
                    return
        except Exception:
            pass
    drdata.add_system_user_to_org(
        client,
        system_user_name="DRSysAdmin",
        org_name="training",
        role_handle=role_handle,
    )
    _ok("DRSysAdmin added to training as Organization Administrator")


def step_10_create_import_connector(
    args, client: EDiscoveryClient,
) -> str:
    _step(10, STEPS[9])
    nfs_host = args.nfs_host or args.hostname
    name = "import-training-nfs-local"
    if args.dry_run:
        _info(f"DRY-RUN: createNFSConnector {name} (read-only) → "
              f"/data/import")
        return ""
    if args.keep_existing:
        for c in drdata.list_connectors(client, "training"):
            if c.name == name:
                _skip(f"{name} already exists (handle={c.handle})")
                return c.handle
    resp = drdata.create_nfs_connector(
        client, org_name="training", name=name,
        remote_host=nfs_host, remote_path="/data/import",
        read_only=True,
    )
    handle = (resp.get("connector") or {}).get("handle", "")
    _ok(f"created {name} (READ ONLY) → handle={handle}")
    return handle


def step_11_create_export_connector(
    args, client: EDiscoveryClient,
) -> str:
    _step(11, STEPS[10])
    nfs_host = args.nfs_host or args.hostname
    name = "export-training-nfs-local"
    if args.dry_run:
        _info(f"DRY-RUN: createNFSConnector {name} (read/write) → "
              f"/data/export")
        return ""
    if args.keep_existing:
        for c in drdata.list_connectors(client, "training"):
            if c.name == name:
                _skip(f"{name} already exists (handle={c.handle})")
                return c.handle
    resp = drdata.create_nfs_connector(
        client, org_name="training", name=name,
        remote_host=nfs_host, remote_path="/data/export",
        read_only=False,
    )
    handle = (resp.get("connector") or {}).get("handle", "")
    _ok(f"created {name} (READ/WRITE) → handle={handle}")
    return handle


def step_12_create_archive_connector(
    args, client: EDiscoveryClient,
) -> str:
    _step(12, STEPS[11])
    nfs_host = args.nfs_host or args.hostname
    name = "archive-training-nfs-local"
    if args.dry_run:
        _info(f"DRY-RUN: createNFSConnector {name} (read/write) → "
              f"/data/archive")
        return ""
    if args.keep_existing:
        for c in drdata.list_connectors(client, "training"):
            if c.name == name:
                _skip(f"{name} already exists (handle={c.handle})")
                return c.handle
    resp = drdata.create_nfs_connector(
        client, org_name="training", name=name,
        remote_host=nfs_host, remote_path="/data/archive",
        read_only=False,
    )
    handle = (resp.get("connector") or {}).get("handle", "")
    _ok(f"created {name} (READ/WRITE) → handle={handle}")
    return handle


def step_13_create_data_areas(
    args, client: EDiscoveryClient,
    archive_handle: str, export_handle: str,
) -> None:
    _step(13, STEPS[12])
    if args.dry_run:
        _info("DRY-RUN: createDataArea PROJECT on archive, "
              "EXPORT on export")
        return

    # PROJECT data area on the archive connector.
    project_name = "pda-training-archive"
    try:
        drdata.create_data_area(
            client,
            context_handle="training",
            connector_handle=archive_handle,
            name=project_name,
            mode="PROJECT",
            path=".",
        )
        _ok(f"created PROJECT data area '{project_name}' on archive")
    except APIError as e:
        if args.keep_existing and "ALREADY" in (e.extended_status or "").upper():
            _skip(f"{project_name} already exists")
        else:
            raise

    # EXPORT data area on the export connector.
    export_name = "xda-training-export"
    try:
        drdata.create_data_area(
            client,
            context_handle="training",
            connector_handle=export_handle,
            name=export_name,
            mode="EXPORT",
            path=".",
        )
        _ok(f"created EXPORT data area '{export_name}' on export")
    except APIError as e:
        if args.keep_existing and "ALREADY" in (e.extended_status or "").upper():
            _skip(f"{export_name} already exists")
        else:
            raise


# ---------- Phase 3 orchestrator ------------------------------------------------

def phase_api(args: argparse.Namespace) -> None:
    """Run the 13 provisioning steps end-to-end."""
    if not args.dry_run:
        wait_for_drd(args.hostname)

    client = step_1_login_and_change_password(args)
    step_2_create_doc_storage(args, client)
    idx_handle, idx_fqdn, idx_export = step_3_create_index_storage(args, client)
    step_4_create_system_storage_depot(args, client, idx_handle, idx_fqdn, idx_export)
    step_5_virus_update(args, client)
    step_6_inactivity_timeout(args, client)
    step_7_create_training_org(args, client)
    # Resolve the Organization Administrator role handle BEFORE
    # creating any users. The sys-scoped listRoles works without
    # DRSysAdmin being a member yet (a brand-new org has zero users,
    # not even DRSysAdmin).
    if args.dry_run:
        org_admin_role = ""
    else:
        org_admin_role = _resolve_org_admin_role(client)
    # Step 9 BEFORE step 8 — DRSysAdmin needs to be in the org as
    # Organization Administrator before `orgManager/createUser` will
    # accept it. The user's spec lists steps 8 and 9 in the other
    # order, but the dependency only flows one way, so we run them
    # in dependency order and call out the swap in the step header.
    step_9_add_drsysadmin_to_org(args, client, org_admin_role)
    step_8_create_org_admin(args, client, org_admin_role)
    # Bonus: log in once as admin@training to clear the forced-change.
    # This keeps the dr-tui org login working with `password` afterwards.
    step_8b_change_org_admin_password(args, client)
    import_handle  = step_10_create_import_connector(args, client)
    export_handle  = step_11_create_export_connector(args, client)
    archive_handle = step_12_create_archive_connector(args, client)
    step_13_create_data_areas(args, client, archive_handle, export_handle)


# ---------- main ----------------------------------------------------------------

def _show_help_and_exit() -> int:
    """No-args path — print full help and exit 0.

    The default flow without any flags is destructive (cleandr + expect
    + API). Running the script with no args used to silently start
    that flow, which is a footgun. v0.17.1 switches the no-args path
    to print help instead, matching how most "modal" CLI tools behave
    (kubectl, helm, etc.).
    """
    _build_parser().print_help(sys.stdout)
    print()
    print("[Tip] Run with --dry-run --skip-clean --skip-installer "
          "to see the API phase plan without doing anything.")
    return 0


def main() -> int:
    # ---- 0. No args → print help and exit. ----
    # This is a safety guard: the default flow is destructive, so we
    # require at least ONE explicit flag (even just `--force`) before
    # the script starts ripping things up. See _show_help_and_exit
    # for the rationale.
    if len(sys.argv) == 1:
        return _show_help_and_exit()

    args = _parse_args()

    # ---- 1. Set up logging FIRST so every subsequent action is
    # recorded, even if the confirmation prompt aborts. ----
    log_path = Path(args.log_file)
    _setup_logging(log_path, args.log_level, args.verbose)
    log.debug("args: %s", vars(args))

    # ---- 2. Banner: Reef-a-TUI logo + bright-yellow product subtitle. ----
    # The logo is loaded from the bit-generated reef-a-tui-logo.txt
    # and colour-graded blue→white at render time. The subtitle is
    # the v0.17.4 spec'd "Digital Reef Fresh Installer version X.Y.Z"
    # in bold bright yellow.
    _render_logo(_VERSION)
    # Run-config summary stays underneath as a small panel — same
    # info as before (phases, mode, log path, target).
    console.print(Panel.fit(
        Text(
            f"Target:  {args.hostname}\n"
            f"Phases:  clean={'no' if args.skip_clean else 'YES'}  "
            f"|  installer={'no' if args.skip_installer else 'YES'}  "
            f"|  api={'no' if args.skip_api else 'YES'}\n"
            f"Mode:    dry-run={args.dry_run}  "
            f"keep-existing={args.keep_existing}  "
            f"force={args.force}\n"
            f"Log:     {log_path}",
            style="white",
        ),
        border_style="cyan",
    ))

    # ---- 3. Destructive-operation confirmation. ----
    if not _confirm_destruction(args):
        _fail("aborted by user (or by --force-required policy).")
        return 130

    # ---- 4. Compute total progress steps for the bar. ----
    # Each shell phase counts as 1; phase 3 counts as len(STEPS).
    total_units = (
        (0 if args.skip_clean else 1)
        + (0 if args.skip_installer else 1)
        + (0 if args.skip_api else len(STEPS))
    )
    if total_units == 0:
        _warn("All phases skipped — nothing to do.")
        return 0

    progress = _setup_progress(total_units, disabled=args.no_progress)

    # ---- 5. Run the phases inside the Progress context. ----
    started_at = time.time()
    rc = 0
    try:
        ctx = progress if progress is not None else _NullContext()
        with ctx:
            if not args.skip_clean:
                _phase_banner(1, "Teardown (cleandr.sh)")
                phase_clean(args)
            else:
                _skip("Phase 1 (teardown)")

            if not args.skip_installer:
                _phase_banner(2, "DR installer (DR_freshinstall.exp)")
                phase_installer(args)
            else:
                _skip("Phase 2 (installer)")

            if not args.skip_api:
                _phase_banner(3, f"API provisioning ({len(STEPS)} steps)")
                phase_api(args)
            else:
                _skip("Phase 3 (API provisioning)")
    except (APIError, RuntimeError, TimeoutError, FileNotFoundError) as e:
        console.print()
        _fail(f"FATAL: {e}")
        log.exception("FATAL exception during run")
        if isinstance(e, APIError):
            console.print(f"        [red]error_code={e.error_code}  "
                          f"status={e.status}[/]")
            console.print(f"        [red]extended="
                          f"{e.extended_status[:200]}[/]")
        rc = 1
    except Exception as e:
        # v0.17.2 fix for QA-v0171-2 part 2: catch the requests.*
        # exception hierarchy (HTTPError, ConnectionError, Timeout)
        # plus anything else unexpected. Without this, an HTTP 500
        # from a not-yet-deployed webapp leaks the full Python
        # traceback to the user instead of a clean failure panel.
        # `requests` exceptions all subclass IOError → catching
        # the broad `Exception` here means even unforeseen failures
        # produce a friendly summary. The full traceback still goes
        # to the log file via log.exception().
        console.print()
        _fail(f"FATAL ({type(e).__name__}): {e}")
        log.exception("FATAL exception during run")
        rc = 1
    except KeyboardInterrupt:
        console.print()
        _fail("interrupted by user (Ctrl-C)")
        log.warning("interrupted by SIGINT")
        rc = 130

    # ---- 6. Summary. ----
    elapsed = time.time() - started_at
    log.info("total wall clock: %.1fs (exit=%d)", elapsed, rc)
    console.print()
    if rc == 0:
        console.print(Panel.fit(
            Text(
                f"✓  Fresh install complete in {elapsed:.1f}s.\n\n"
                f"DR Web UI:        https://{args.hostname}:8443/ediscovery/\n"
                f"DRSysAdmin     /  {args.final_password}\n"
                f"admin@training /  {args.final_password}\n\n"
                f"Log file:         {log_path}\n"
                f"Run dr-tui:       .venv/bin/dr-tui",
                style="green",
            ),
            border_style="green",
            title="[bold green]SUCCESS[/]",
        ))
    else:
        console.print(Panel.fit(
            Text(
                f"Run failed after {elapsed:.1f}s.\n"
                f"Log file: {log_path}\n"
                f"For symptom→fix lookup see docs/RUNBOOK.md "
                f"§4g/§4h/§5.",
                style="red",
            ),
            border_style="red",
            title="[bold red]FAILURE[/]",
        ))
    return rc


class _NullContext:
    """Context-manager no-op used when the progress bar is disabled
    (--no-progress or non-TTY). Keeps main()'s `with` block uniform."""
    def __enter__(self): return self
    def __exit__(self, *a): return False


if __name__ == "__main__":
    raise SystemExit(main())
