"""
helpers/style.py — Central style and color vocabulary for dr-load CLI output.

Digital Reef brand palette mapped to ANSI 16-color terminals:
  - Midnight Blue   → bright_blue  (headers, chrome, section titles)
  - Teal            → cyan         (success, OK, RUNNING states)
  - Orange          → yellow       (warnings, highlights, DEGRADED states)
  - White           → (default)    (body text — explicit WHITE looks gray)
  - Red             → red          (errors, failures — universally understood)
  - Dim             → (dim)        (secondary info, handles, timestamps)

Prefix conventions (all commands must use these):
  OK    — cyan bold prefix, success confirmation
  WARN  — yellow bold prefix, non-fatal warning
  FAIL  — red bold prefix, error (written to stderr)
  ..    — blue prefix, progress / informational step

Exit-code contract:
  0  — success
  1  — user error (bad args, login failed)
  2  — unexpected state (not running, not found, timeout)
"""

from __future__ import annotations

import typer

# ── Color tokens ──────────────────────────────────────────────────────────────

# Map semantic roles to ANSI color names (16-color safe)
C_SUCCESS = typer.colors.CYAN        # teal family — OK, RUNNING, GREEN health
C_WARN = typer.colors.YELLOW         # orange family — warnings, DEGRADED/YELLOW health
C_ERROR = typer.colors.RED           # errors, failures, RED health
C_HEADER = typer.colors.BRIGHT_BLUE  # midnight-blue family — section titles, chrome
C_DIM = None                         # use bold=False + dim via Rich where needed
C_INFO = typer.colors.BLUE           # progress steps ("..  ")

# ── State color map (used by both admin dashboard and record status) ──────────

# Health traffic-light → ANSI color
HEALTH_COLORS: dict[str, str] = {
    "GREEN": typer.colors.CYAN,
    "YELLOW": typer.colors.YELLOW,
    "RED": typer.colors.RED,
}

# Campaign / event kind → ANSI color
EVENT_KIND_COLORS: dict[str, str | None] = {
    "START": typer.colors.CYAN,
    "END": None,          # dim — rendered via typer.style bold=False
    "ADJUST": typer.colors.YELLOW,
    "ANNOTATE": None,     # default white
    "YELLOW": typer.colors.YELLOW,
    "RED": typer.colors.RED,
    "GREEN": typer.colors.CYAN,
}

# ── Prefix helpers ────────────────────────────────────────────────────────────


def ok(msg: str) -> None:
    """Print a success line: cyan 'OK ' + message."""
    typer.echo(typer.style("OK ", fg=C_SUCCESS, bold=True) + msg)


def warn(msg: str) -> None:
    """Print a warning line: yellow 'WARN ' + message."""
    typer.echo(typer.style("WARN ", fg=C_WARN, bold=True) + msg)


def fail(msg: str) -> None:
    """Print an error line to stderr: red 'FAIL ' + message."""
    typer.echo(typer.style("FAIL ", fg=C_ERROR, bold=True) + msg, err=True)


def info(msg: str) -> None:
    """Print a progress step line: blue '..   ' + message."""
    typer.echo(typer.style("..   ", fg=C_INFO) + msg)


def header(msg: str) -> None:
    """Print a section header styled in bright_blue."""
    typer.echo(typer.style(msg, fg=C_HEADER, bold=True))


# ── Column-header helpers ─────────────────────────────────────────────────────


def col_headers(line: str) -> None:
    """Print a column-header line styled in bright_blue bold."""
    typer.echo(typer.style(line, fg=C_HEADER, bold=True))


def divider(width: int = 80) -> None:
    """Print a dim horizontal divider."""
    typer.echo(typer.style("-" * width, fg=typer.colors.BRIGHT_BLACK if hasattr(typer.colors, "BRIGHT_BLACK") else None))


# ── State renderers ───────────────────────────────────────────────────────────


def styled_state(state: str) -> str:
    """
    Return an ANSI-styled state string.

    RUNNING/ACTIVE/SUCCESS/GREEN → cyan
    QUEUED/PENDING/PROCESSING/YELLOW → yellow
    FAILURE/FAILED/ERROR/RED → red
    DELETE_PENDING/DELETING → magenta
    STOPPED → yellow (not running = needs attention)
    """
    s = (state or "").upper()
    if s in ("RUNNING", "ACTIVE", "SUCCESS", "GREEN"):
        return typer.style(state, fg=C_SUCCESS, bold=True)
    if s in ("QUEUED", "PENDING", "PROCESSING", "YELLOW", "STOPPED", "DEGRADED"):
        return typer.style(state, fg=C_WARN, bold=True)
    if s in ("FAILURE", "FAILED", "ERROR", "RED"):
        return typer.style(state, fg=C_ERROR, bold=True)
    if "DELETE" in s or s == "DELETING":
        return typer.style(state, fg=typer.colors.MAGENTA)
    return state


def styled_health(verdict: str) -> str:
    """Return an ANSI-styled health verdict (GREEN/YELLOW/RED)."""
    color = HEALTH_COLORS.get(verdict.upper(), None)
    return typer.style(verdict, fg=color, bold=True) if color else verdict


def styled_event_kind(kind: str) -> str:
    """Return an ANSI-styled event kind for tail/show output."""
    color = EVENT_KIND_COLORS.get(kind.upper())
    if color:
        return typer.style(f"{kind:<14}", fg=color, bold=True)
    return f"{kind:<14}"


# ── Rich admin dashboard state color map ──────────────────────────────────────
# These are Rich markup color names (not typer/ANSI) — used in admin.py Rich tables.

RICH_STATE_COLORS: dict[str, str] = {
    "running": "cyan",
    "active": "cyan",
    "success": "cyan",
    "green": "cyan",
    "queued": "yellow",
    "pending": "yellow",
    "processing": "yellow",
    "yellow": "yellow",
    "failure": "red",
    "failed": "red",
    "error": "red",
    "red": "red",
    "delete": "magenta",   # prefix match — any state containing "delete"
}


def rich_state_color(state: str) -> str:
    """
    Map a project/task state string to a Rich color name.
    Used by admin.py's Rich dashboard renderer.
    """
    s = (state or "").lower()
    # Exact matches first
    if s in RICH_STATE_COLORS:
        return RICH_STATE_COLORS[s]
    # Prefix/substring matches
    if "delete" in s:
        return "magenta"
    if s in ("running", "active"):
        return "cyan"
    return "white"
