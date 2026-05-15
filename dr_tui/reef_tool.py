"""dr_tui.reef_tool — reusable wrapper template for REEF-A-TUI CLI tools.

Embeds the look & feel of `dr_freshinstall.py` (the v0.17.x UX
iteration's reference implementation) into a small reusable harness:

  • Reef-a-TUI logo banner at startup with the blue → light-grey
    ocean-depth gradient
  • Bold-yellow `<Tool Name> version X.Y.Z` subtitle
  • Cyan run-config panel
  • Rich progress bar pinned to the bottom of the live region while
    subprocess / step output scrolls above it
  • Bright-blue / bold-yellow phase banners
  • Per-step `(N.Ns)` elapsed annotations + `phase wall clock:`
    summary lines
  • File log at `/tmp/<tool>-<TS>.log` (configurable via `--log-file`)
  • Help-by-default — no-args invocations print --help, never start
    a destructive default flow
  • Destructive-op confirmation gate (`--force` bypass)
  • Green SUCCESS / red FAILURE end panel

Usage from a new dr_* tool:

    from dr_tui.reef_tool import ReefTool

    def main() -> int:
        tool = ReefTool(
            prog_name="dr_example",
            description="Short one-liner description.",
            phases=[
                ("Validate environment", phase_validate),
                ("Do the work",          phase_work),
                ("Verify outcome",       phase_verify),
            ],
        )
        return tool.run()

Each `phase_*` callable receives the parsed `argparse.Namespace`
and the `ReefTool` instance and may emit progress via
`tool.info("…")`, `tool.ok("…")`, `tool.warn("…")`, `tool.skip("…")`.
Raise any exception to fail the phase (the harness catches + renders
a red FAILURE panel and writes the traceback to the log).

Naming conventions enforced by this harness:

  • Script filename: `dr_<name>.py` (lowercase, underscore-separated)
  • CLI prog name passed to `ReefTool(prog_name="dr_<name>")`
  • Log file: `/tmp/dr_<name>-<YYYYMMDD-HHMMSS>.log`
  • Colour palette: Blue (rgb 36,114,200 → 132,171,214), White
    (255,255,255), Yellow (bright_yellow / bold yellow), Cyan
    accents for the run-config panel. Matches `dr_freshinstall.py`
    and the REEF-A-TUI brand.

The Reef-a-TUI logo file is the same one used by dr_freshinstall —
`reef-a-tui-logo.txt` at the repo root. The harness loads it via
the standard `_LOGO_PATH` resolution so every tool shows the same
banner.
"""
from __future__ import annotations

import argparse
import datetime
import logging
import os
import socket
import sys
import time
import warnings
from pathlib import Path
from typing import Callable, Optional

# Silence urllib3 self-signed-cert spam early so tool output stays clean.
warnings.filterwarnings("ignore")

# Repo root — used to locate the shared logo file.
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Rich is a runtime dep (textual depends on it). Hard-import here so
# tools using this template don't need to remember.
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress, BarColumn, TextColumn, TimeElapsedColumn,
    SpinnerColumn, MofNCompleteColumn,
)
from rich.text import Text


# ---------- shared brand assets -----------------------------------------------

_LOGO_PATH = _REPO_ROOT / "reef-a-tui-logo.txt"

# Digital Reef ocean palette — 7-stop blue → light-grey gradient.
# Same values baked into reef-a-tui-logo.go (the bit reference).
LOGO_COLORS = [
    "rgb(36,114,200)",     # row 0 — deepest blue
    "rgb(68,133,204)",
    "rgb(100,152,209)",
    "rgb(132,171,214)",
    "rgb(164,190,219)",
    "rgb(196,209,224)",
    "rgb(229,229,229)",    # row 6 — light grey (surface)
]

# Brand-style aliases — use these constants in any custom Rich.print
# inside a tool so the look stays consistent.
STYLE_PHASE_BORDER  = "bright_blue"
STYLE_PHASE_TITLE   = "bold yellow"
STYLE_BANNER_BORDER = "cyan"
STYLE_SUCCESS       = "green"
STYLE_FAILURE       = "red"
STYLE_SUBTITLE      = "bold bright_yellow"


# ---------- the ReefTool harness ----------------------------------------------

class ReefTool:
    """Reusable wrapper for dr_* CLI tools — logo, progress bar, logging.

    The minimal contract a tool needs to fulfil is:

      1. Construct `ReefTool(prog_name, description, phases=[...])`
      2. Optionally extend the argparser via `tool.add_argument(...)`
         before calling `tool.run()`. The added args are merged with
         the harness's standard flags (--dry-run, --force, etc.).
      3. Each phase callable has signature
         `def phase(args: argparse.Namespace, tool: ReefTool) -> None`
         — raises on failure, returns None on success.
      4. Call `tool.run()` — it parses args, sets up logging + Rich
         progress, runs each phase inside a `_phase` context manager,
         and returns the exit code (0 = SUCCESS panel, non-zero =
         FAILURE panel + traceback in log).
    """

    def __init__(
        self,
        *,
        prog_name: str,
        description: str,
        version: str = "",
        phases: Optional[list[tuple[str, Callable]]] = None,
        destructive: bool = False,
    ) -> None:
        if not prog_name.startswith("dr_"):
            raise ValueError(
                f"REEF-A-TUI naming convention: prog_name must start with "
                f"'dr_' (got {prog_name!r})"
            )
        self.prog_name = prog_name
        self.description = description
        self.version = version or _read_repo_version()
        self.phases = phases or []
        self.destructive = destructive
        # Parser is built lazily so callers can add their own args via
        # `tool.add_argument()` between __init__ and run().
        self._parser: Optional[argparse.ArgumentParser] = None
        self._extra_args: list[tuple[tuple, dict]] = []
        # Rich state — set up in run().
        self.console = Console(highlight=False)
        self._progress: Optional[Progress] = None
        self._progress_task: Optional[int] = None
        self._log = logging.getLogger(self.prog_name)
        self._step_started_at: Optional[float] = None

    # ---- argument extension ----

    def add_argument(self, *args, **kwargs) -> None:
        """Queue an `argparse.add_argument(*args, **kwargs)` call to be
        applied to the parser. Use before `run()` to add tool-specific
        flags on top of the harness's standard set."""
        self._extra_args.append((args, kwargs))

    # ---- output helpers (mirror dr_freshinstall.py's _ok/_info/etc.) ----

    def info(self, msg: str) -> None:
        self._log.info("INFO  %s", msg)
        self.console.print(f"    [dim]·[/]  {msg}")

    def ok(self, msg: str) -> None:
        elapsed = ""
        if self._step_started_at is not None:
            elapsed = f"  [dim]({time.time() - self._step_started_at:.1f}s)[/]"
        self._log.info("OK    %s", msg)
        self.console.print(f"    [green]✓[/]  {msg}{elapsed}")

    def warn(self, msg: str) -> None:
        self._log.warning("WARN  %s", msg)
        self.console.print(f"    [yellow]⚠[/]  {msg}")

    def fail(self, msg: str) -> None:
        self._log.error("FAIL  %s", msg)
        self.console.print(f"    [bold red]✗[/]  {msg}")

    def skip(self, msg: str) -> None:
        self._log.info("SKIP  %s", msg)
        self.console.print(f"    [dim cyan]⊘[/]  skipped: {msg}")

    def stream_subprocess(
        self, cmd: list[str], *, cwd: Optional[str] = None,
        line_style: str = "dim",
    ) -> int:
        """Run `cmd` and route every stdout/stderr line through the
        Rich console so the live progress bar stays pinned at the
        bottom of the visible region. Same pattern as
        `dr_freshinstall.py::_stream_subprocess`.

        Each subprocess line gets a dim `│` prefix so the user can
        distinguish "shell output" from "driver status". Lines are
        also captured in the file log at DEBUG level via
        `subproc: <line>` entries.

        Returns the subprocess exit code; non-zero is a signal to
        the caller, we don't raise.
        """
        import subprocess
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
                line_text = raw.rstrip("\n")
                if not line_text:
                    continue
                body = Text("    │ ", style=line_style) + Text(line_text)
                self.console.print(body, highlight=False)
                self._log.debug("subproc: %s", line_text)
        finally:
            proc.wait()
        return proc.returncode

    # ---- run loop ----

    def run(self, argv: Optional[list[str]] = None) -> int:
        # No-args → help-by-default. Same safety policy as
        # dr_freshinstall.py: never let a destructive run start
        # without at least one explicit flag.
        if argv is None and len(sys.argv) == 1:
            self._build_parser().print_help(sys.stdout)
            return 0

        args = self._build_parser().parse_args(argv)
        self._setup_logging(Path(args.log_file), args.log_level, args.verbose)
        self._log.debug("args: %s", vars(args))

        self._render_logo()
        self._render_run_config(args)

        if self.destructive and not self._confirm_destruction(args):
            self.fail("aborted by user (or by --force-required policy).")
            return 130

        total = sum(1 for _, _ in self.phases)
        if total == 0:
            self.warn("No phases registered. Nothing to do.")
            return 0

        self._progress = (
            None if args.no_progress or not sys.stdout.isatty()
            else self._build_progress(total)
        )
        if self._progress is not None:
            self._progress_task = self._progress.add_task(
                "starting…", total=total,
            )

        started = time.time()
        rc = 0
        try:
            ctx = self._progress if self._progress is not None else _Null()
            with ctx:
                for i, (name, fn) in enumerate(self.phases, 1):
                    self._phase_enter(i, name)
                    try:
                        fn(args, self)
                        self._phase_exit(i, name, ok=True,
                                         elapsed=time.time() - self._step_started_at)
                    except Exception:
                        self._phase_exit(i, name, ok=False,
                                         elapsed=time.time() - self._step_started_at)
                        raise
        except KeyboardInterrupt:
            self.console.print()
            self.fail("interrupted by user (Ctrl-C)")
            self._log.warning("interrupted by SIGINT")
            rc = 130
        except Exception as e:
            self.console.print()
            self.fail(f"FATAL ({type(e).__name__}): {e}")
            self._log.exception("FATAL exception during run")
            rc = 1

        self._render_summary(rc, time.time() - started, args)
        return rc

    # ---- internals ----

    def _build_parser(self) -> argparse.ArgumentParser:
        if self._parser is not None:
            return self._parser
        ap = argparse.ArgumentParser(
            prog=self.prog_name,
            description=self.description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        # Standard flags every dr_* tool should have, mirroring
        # dr_freshinstall.py.
        behav = ap.add_argument_group("Behaviour")
        behav.add_argument("--dry-run", action="store_true",
                           help="print every action without doing it")
        if self.destructive:
            behav.add_argument("--force", action="store_true",
                               help="bypass the destructive-op y/n prompt")
        behav.add_argument("--no-progress", action="store_true",
                           help="disable the live progress bar (CI / non-TTY)")
        logf = ap.add_argument_group("Logging")
        logf.add_argument(
            "--log-file",
            default=f"/tmp/{self.prog_name}-"
                    f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.log",
            help=f"log file path (default /tmp/{self.prog_name}-<TS>.log)",
        )
        logf.add_argument("--log-level", default="INFO",
                          choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                          help="logger verbosity (default INFO)")
        logf.add_argument("--verbose", "-v", action="store_true",
                          help="equivalent to --log-level=DEBUG")
        # Extra args from the tool author.
        for posargs, kwargs in self._extra_args:
            ap.add_argument(*posargs, **kwargs)
        self._parser = ap
        return ap

    def _setup_logging(self, log_path: Path, level: str, verbose: bool) -> None:
        self._log.handlers.clear()
        self._log.setLevel(logging.DEBUG)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        fh.setLevel(logging.DEBUG if verbose else getattr(logging, level))
        fh.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-7s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        self._log.addHandler(fh)
        self._log.info("%s starting — log file: %s", self.prog_name, log_path)
        self._log_path = log_path

    def _build_progress(self, total: int) -> Progress:
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=None),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            console=self.console,
            transient=False,
            refresh_per_second=8,
        )

    def _render_logo(self) -> None:
        try:
            lines = _LOGO_PATH.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            self.console.print()
            self.console.print("[bold cyan]Reef-a-TUI[/]")
            self.console.print(
                f"[{STYLE_SUBTITLE}]{self.prog_name} version {self.version}[/]"
            )
            self.console.print()
            return
        self.console.print()
        for i, line in enumerate(lines):
            color = LOGO_COLORS[min(i, len(LOGO_COLORS) - 1)]
            self.console.print(
                line, style=color, markup=False, highlight=False,
                no_wrap=True, crop=False, overflow="ignore",
            )
        self.console.print(
            f"    {self.prog_name} version {self.version}",
            style=STYLE_SUBTITLE, highlight=False,
            no_wrap=True, crop=False, overflow="ignore",
        )
        self.console.print()

    def _render_run_config(self, args: argparse.Namespace) -> None:
        body = f"Tool:   {self.prog_name}\nLog:    {self._log_path}"
        if hasattr(args, "dry_run") and args.dry_run:
            body += "\nMode:   dry-run"
        self.console.print(Panel.fit(
            Text(body, style="white"), border_style=STYLE_BANNER_BORDER,
        ))

    def _confirm_destruction(self, args: argparse.Namespace) -> bool:
        if args.dry_run or getattr(args, "force", False):
            return True
        if not sys.stdin.isatty():
            self.fail(f"destructive operation requested without --force "
                      f"on a non-TTY stdin. Re-run with --force.")
            return False
        self.console.print()
        self.console.print(Panel.fit(
            Text(
                f"⚠  Destructive operation requested by {self.prog_name}.\n"
                f"Type 'YES' (uppercase) to proceed.",
                style="bold yellow",
            ),
            border_style=STYLE_FAILURE,
            title=f"[bold {STYLE_FAILURE}]DESTRUCTIVE OPERATION[/]",
        ))
        try:
            answer = input("Proceed? > ").strip()
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            return False
        return answer == "YES"

    def _phase_enter(self, num: int, name: str) -> None:
        self._step_started_at = time.time()
        label = f"Phase {num} — {name}"
        self._log.info("════ %s ════", label)
        if self._progress is not None and self._progress_task is not None:
            self._progress.update(self._progress_task,
                                  description=label, advance=1)
        self.console.print()
        self.console.print(Panel.fit(
            Text(label, style=STYLE_PHASE_TITLE),
            border_style=STYLE_PHASE_BORDER,
        ))

    def _phase_exit(self, num: int, name: str, *, ok: bool,
                    elapsed: float) -> None:
        verdict = "OK" if ok else "FAIL"
        self._log.info("phase wall clock: Phase %d — %s — %s — %.1fs",
                       num, name, verdict, elapsed)
        if ok:
            mm, ss = divmod(int(elapsed + 0.5), 60)
            human = f"{mm}m {ss:02d}s" if mm else f"{ss}s"
            self.console.print(
                f"    [dim]⏱  Phase {num} took {elapsed:.1f}s ({human})[/]",
                highlight=False,
            )

    def _render_summary(self, rc: int, elapsed: float,
                        args: argparse.Namespace) -> None:
        self._log.info("total wall clock: %.1fs (exit=%d)", elapsed, rc)
        self.console.print()
        if rc == 0:
            self.console.print(Panel.fit(
                Text(
                    f"✓  {self.prog_name} complete in {elapsed:.1f}s.\n\n"
                    f"Log file:  {self._log_path}",
                    style=STYLE_SUCCESS,
                ),
                border_style=STYLE_SUCCESS,
                title=f"[bold {STYLE_SUCCESS}]SUCCESS[/]",
            ))
        else:
            self.console.print(Panel.fit(
                Text(
                    f"{self.prog_name} failed after {elapsed:.1f}s.\n"
                    f"Log file: {self._log_path}",
                    style=STYLE_FAILURE,
                ),
                border_style=STYLE_FAILURE,
                title=f"[bold {STYLE_FAILURE}]FAILURE[/]",
            ))


# ---------- helpers -----------------------------------------------------------

def _read_repo_version() -> str:
    """Read __version__.py at the repo root. Fallback `?.?.?`."""
    try:
        scope: dict = {}
        exec((_REPO_ROOT / "__version__.py").read_text(), scope)
        return scope.get("__version__", "?.?.?")
    except Exception:
        return "?.?.?"


class _Null:
    """No-op context manager used when the progress bar is disabled."""
    def __enter__(self): return self
    def __exit__(self, *a): return False


# ---------- example tool that doubles as a smoke test --------------------------

def _example_main() -> int:
    """Minimal example tool — run as
       `.venv/bin/python -m dr_tui.reef_tool`
    to see the harness's logo + banner + 2-phase progress in action.
    """
    def phase_one(args, tool: ReefTool) -> None:
        tool.info("doing work in phase one…")
        time.sleep(0.5)
        tool.ok("phase one work done")

    def phase_two(args, tool: ReefTool) -> None:
        tool.info("doing work in phase two…")
        time.sleep(0.3)
        tool.ok("phase two work done")

    tool = ReefTool(
        prog_name="dr_example",
        description="Reef-a-TUI harness demo — 2 phases of fake work.",
        phases=[
            ("Set up",   phase_one),
            ("Tear down", phase_two),
        ],
    )
    return tool.run()


if __name__ == "__main__":
    sys.exit(_example_main())
