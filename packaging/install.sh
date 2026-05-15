#!/usr/bin/env bash
#
# install.sh — single-command installer for dr-tools (dr_tui + dr_load).
#
# Usage:
#   curl -sSL https://github.com/mbmcclelland/ediscovery_tests/raw/v0.06/packaging/install.sh | bash
# or in a checkout:
#   bash packaging/install.sh           # install
#   bash packaging/install.sh uninstall # remove
#
# Creates /opt/dr-tools/venv with all runtime deps and drops launcher
# scripts at /usr/local/bin/{dr_tui,dr_load}. Requires Python 3.9+ and
# sudo. For an air-gapped install build the RPM instead — see
# packaging/Makefile.
set -euo pipefail

INSTALL_ROOT="/opt/dr-tools"
VENV="${INSTALL_ROOT}/venv"
BIN_DIR="/usr/local/bin"
REPO_RAW="https://github.com/mbmcclelland/ediscovery_tests/archive/refs/heads/v0.06.tar.gz"
PYTHON="${PYTHON:-python3}"
REQUIRED_PY_MAJOR=3
REQUIRED_PY_MINOR=9

log()  { printf '[install] %s\n' "$*"; }
warn() { printf '[install] [33mwarning:[0m %s\n' "$*" >&2; }
die()  { printf '[install] [31merror:[0m %s\n' "$*" >&2; exit 1; }

require_python() {
    command -v "$PYTHON" >/dev/null 2>&1 || die "$PYTHON not found on PATH"
    local pyver
    pyver=$("$PYTHON" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
    log "found $PYTHON ($pyver)"
    "$PYTHON" -c "
import sys
sys.exit(0 if sys.version_info >= (${REQUIRED_PY_MAJOR}, ${REQUIRED_PY_MINOR}) else 1)
" || die "Python ${REQUIRED_PY_MAJOR}.${REQUIRED_PY_MINOR}+ required (have $pyver)"
}

need_sudo() {
    if [ "$(id -u)" -ne 0 ]; then
        if ! command -v sudo >/dev/null 2>&1; then
            die "must run as root or have sudo available"
        fi
        SUDO=sudo
    else
        SUDO=""
    fi
}

install_dr_tools() {
    require_python
    need_sudo

    log "creating venv at $VENV"
    $SUDO mkdir -p "$INSTALL_ROOT"
    $SUDO "$PYTHON" -m venv "$VENV"
    $SUDO "$VENV/bin/pip" install --upgrade pip wheel

    if [ -d "$(dirname "$(realpath "$0")")/.." ] && [ -f "$(dirname "$(realpath "$0")")/../setup.cfg" ]; then
        local repo_dir
        repo_dir="$(cd "$(dirname "$(realpath "$0")")/.." && pwd)"
        log "installing from local checkout: $repo_dir"
        $SUDO "$VENV/bin/pip" install "$repo_dir"
    else
        log "no local checkout found — fetching $REPO_RAW"
        local tmp
        tmp=$(mktemp -d)
        trap 'rm -rf "$tmp"' EXIT
        curl -sSL "$REPO_RAW" -o "$tmp/src.tar.gz"
        tar -xzf "$tmp/src.tar.gz" -C "$tmp"
        local extracted
        extracted=$(find "$tmp" -maxdepth 1 -type d -name 'ediscovery_tests-*' | head -1)
        $SUDO "$VENV/bin/pip" install "$extracted"
    fi

    log "creating launcher scripts in $BIN_DIR"
    # v0.19.2 — canonical wrapper name is `dr_tui` (underscore). The
    # hyphen alias `dr-tui` is a symlink to it. Mirrors the RPM
    # spec's layout.
    cat <<'EOF' | $SUDO tee "$BIN_DIR/dr_tui" >/dev/null
#!/bin/sh
# Force a sane TERM + skip kitty-keyboard probe for legacy SSH clients
# (PuTTY in particular). See README "Terminal compatibility" for why.
if [ "$TERM" = "xterm" ] && [ -f /usr/share/terminfo/x/xterm-256color ]; then
    TERM=xterm-256color
fi
: "${TEXTUAL_FEATURES=}"
export TERM TEXTUAL_FEATURES
# Venv binary at /opt/dr-tools/venv/bin/dr-tui is the Python
# console_script entry — name fixed there in setup.cfg. The user-
# facing wrapper above is the canonical name.
exec /opt/dr-tools/venv/bin/dr-tui "$@"
EOF
    cat <<'EOF' | $SUDO tee "$BIN_DIR/dr_load" >/dev/null
#!/bin/sh
exec /opt/dr-tools/venv/bin/dr-load "$@"
EOF
    $SUDO chmod 0755 "$BIN_DIR/dr_tui" "$BIN_DIR/dr_load"
    # v0.19.3 — legacy hyphen aliases as symlinks to the canonical
    # underscored wrappers. Muscle-memory + scripts that already
    # call `dr-tui` / `dr-load` keep working.
    $SUDO ln -sf dr_tui  "$BIN_DIR/dr-tui"
    $SUDO ln -sf dr_load "$BIN_DIR/dr-load"

    log "done."
    log "  Launchers:    $BIN_DIR/dr_tui  $BIN_DIR/dr_load"
    log "                ($BIN_DIR/dr-tui → dr_tui legacy symlink)"
    log "                ($BIN_DIR/dr-load → dr_load legacy symlink)"
    log "  Venv:         $VENV"
    log "  Next step:    cp /path/to/checkout/.env.example ~/.env  (and edit it)"
    log "                then run \`dr_tui\` to launch the TUI."
}

uninstall_dr_tools() {
    need_sudo
    log "removing $INSTALL_ROOT and launcher scripts"
    $SUDO rm -rf "$INSTALL_ROOT"
    $SUDO rm -f "$BIN_DIR/dr_tui" "$BIN_DIR/dr-tui" \
                "$BIN_DIR/dr_load" "$BIN_DIR/dr-load"
    log "done."
}

case "${1:-install}" in
    install)   install_dr_tools ;;
    uninstall) uninstall_dr_tools ;;
    *)         die "usage: $0 [install|uninstall]" ;;
esac
